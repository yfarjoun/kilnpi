"""Kiln statistics API.

/stats/summary and /stats/health aggregate over the firing_stats table (one
row per completed firing, written by the recorder at firing end). Any
completed firing that still lacks a row — a firing from before this service,
or one whose end-of-firing compute failed — is backfilled on the first
request that sees it.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_session
from backend.models.schemas import Firing, FiringStats, Reading
from backend.services.firing_stats import (
    TEMP_BANDS,
    compute_and_store,
    compute_firing_stats_from_readings,
)

router = APIRouter()

logger = logging.getLogger(__name__)


async def _backfill_missing_stats(session: AsyncSession) -> int:
    """Compute firing_stats rows for any completed firing that lacks one and
    has at least one reading. Returns the count actually written.

    The LEFT JOIN + IS NULL probe is index-only (idx_firings_status plus
    the firing_stats PK). Firings with no readings are excluded so they
    don't get re-queried on every request — compute_and_store writes no
    row for them and they would otherwise match the "missing" query forever.
    """
    r = await session.execute(
        select(Firing.id)
        .outerjoin(FiringStats, FiringStats.firing_id == Firing.id)
        .join(Reading, Reading.firing_id == Firing.id)
        .where(Firing.status == "completed", FiringStats.firing_id.is_(None))
        .group_by(Firing.id)
    )
    missing_ids = [row[0] for row in r.all()]
    if not missing_ids:
        return 0

    logger.info(
        "firing_stats lazy backfill: %d firing(s) missing (first few: %s)",
        len(missing_ids),
        missing_ids[:5],
    )
    written = 0
    for fid in missing_ids:
        try:
            result = await compute_and_store(session, fid)
            if result is not None:
                written += 1
        except Exception:
            # Roll back so the next iteration's SELECT doesn't inherit a
            # poisoned session state (PendingRollbackError would cascade
            # through the rest of the loop).
            try:
                await session.rollback()
            except Exception:
                pass
            logger.exception("Failed to backfill firing_stats for #%d", fid)
    return written


@router.get("/stats/summary")
async def stats_summary(session: AsyncSession = Depends(get_session)) -> dict:
    await _backfill_missing_stats(session)

    total_firings_r = await session.execute(
        select(func.count(Firing.id)).where(Firing.status == "completed")
    )
    total_firings: int = total_firings_r.scalar() or 0

    # Prefer active_duration_min (pre-sitter) over duration_min so the total
    # isn't inflated by post-cutoff cooldown time on firings where the sitter
    # tripped.
    total_mins_r = await session.execute(
        select(func.sum(func.coalesce(FiringStats.active_duration_min, FiringStats.duration_min)))
        .join(Firing, Firing.id == FiringStats.firing_id)
        .where(Firing.status == "completed")
    )
    total_mins = total_mins_r.scalar() or 0.0
    total_hours = round(float(total_mins) / 60, 1)

    by_program_r = await session.execute(
        select(
            Firing.program_name,
            func.count(Firing.id).label("count"),
            func.avg(FiringStats.duration_min).label("avg_duration_min"),
            func.avg(FiringStats.max_temp).label("avg_max_temp"),
        )
        .join(FiringStats, FiringStats.firing_id == Firing.id)
        .where(Firing.status == "completed", Firing.program_name.isnot(None))
        .group_by(Firing.program_name)
    )
    by_program = [
        {
            "name": row.program_name,
            "count": row.count,
            "avg_duration_min": round(float(row.avg_duration_min or 0), 1),
            "avg_max_temp": round(float(row.avg_max_temp or 0), 1),
        }
        for row in by_program_r.all()
    ]

    return {
        "total_firings": total_firings,
        "total_hours": total_hours,
        "by_program": by_program,
    }


@router.get("/stats/firing/{firing_id}")
async def firing_stats(firing_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    """Stats for a single firing. Live-computed from readings each call —
    one firing at a time is fast enough that storing the row adds no
    noticeable speedup here."""
    firing = await session.get(Firing, firing_id)
    if not firing:
        raise HTTPException(status_code=404, detail="Firing not found")

    rows = (
        await session.execute(
            select(Reading.timestamp, Reading.pv, Reading.mv)
            .where(Reading.firing_id == firing_id)
            .order_by(Reading.timestamp)
        )
    ).all()

    # Rebuild a minimal object with the three fields the compute needs,
    # matching the shape of _ReadingTuple.
    class _Row:
        __slots__ = ("timestamp", "pv", "mv")

        def __init__(self, ts: str, pv: float, mv: float) -> None:
            self.timestamp = ts
            self.pv = pv
            self.mv = mv

    tuples = [_Row(r[0], r[1], r[2]) for r in rows]
    return compute_firing_stats_from_readings(tuples)  # type: ignore[arg-type]


@router.get("/stats/health")
async def health_trend(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Per-band heating rates + cooling-rate trend over the last 50 firings.
    Reads firing_stats rows directly — no reading scan, just one JSON
    decode per row."""
    await _backfill_missing_stats(session)

    r = await session.execute(
        select(FiringStats, Firing.started_at)
        .join(Firing, Firing.id == FiringStats.firing_id)
        .where(Firing.status == "completed")
        .order_by(Firing.started_at.desc())
        .limit(50)
    )
    rows = r.all()

    band_data: dict[str, list[dict]] = {label: [] for label, _, _ in TEMP_BANDS}
    cooling_data: list[dict] = []

    # Chart wants chronological order; the LIMIT needed DESC so we flip here.
    for stats, started_at in reversed(rows):
        for band, rate in stats.heating_rates.items():
            if band in band_data:
                band_data[band].append(
                    {"firing_id": stats.firing_id, "date": started_at, "rate": rate}
                )
        if stats.cooling_rate > 0:
            cooling_data.append(
                {"firing_id": stats.firing_id, "date": started_at, "rate": stats.cooling_rate}
            )

    bands: list[dict] = [
        {"band": label, "datapoints": band_data[label]} for label in band_data if band_data[label]
    ]
    if cooling_data:
        bands.append({"band": "Cooling", "datapoints": cooling_data})
    return bands

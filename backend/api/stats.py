"""Kiln statistics API — reads from precomputed firing_stats.

Both aggregate endpoints (/stats/summary and /stats/health) used to pull every
reading of every completed firing into Python on each request, which on the Pi
Zero 2W with ~10+ long firings made the Statistics page unusable.  Now they
read from the firing_stats table, which the recorder populates once when a
firing transitions to "completed" and never updates after.  For firings that
predate this service (or were closed via the stale-firing path), the first
request lazily backfills any missing rows; subsequent requests are pure SQL
aggregates.
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
    """Compute firing_stats rows for any completed firing that lacks one.

    Called at the top of /stats/summary and /stats/health.  After the first
    page load following an upgrade, all existing completed firings have stats
    rows, and future calls find nothing missing and return instantly.  Normal
    end-of-firing stats are written by the recorder; this exists purely to
    cover the migration case.
    """
    r = await session.execute(
        select(Firing.id)
        .outerjoin(FiringStats, FiringStats.firing_id == Firing.id)
        .where(Firing.status == "completed", FiringStats.firing_id.is_(None))
    )
    missing_ids = [row[0] for row in r.all()]
    if not missing_ids:
        return 0

    logger.info(
        "firing_stats lazy backfill: %d firing(s) missing (first few: %s)",
        len(missing_ids),
        missing_ids[:5],
    )
    for fid in missing_ids:
        try:
            await compute_and_store(session, fid)
        except Exception:
            logger.exception("Failed to backfill firing_stats for #%d", fid)
    return len(missing_ids)


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
    this path is used by the History firing-detail view for one firing at a
    time, which is fast enough that persisting adds no visible speedup."""
    firing = await session.get(Firing, firing_id)
    if not firing:
        raise HTTPException(status_code=404, detail="Firing not found")

    result = await session.execute(
        select(Reading).where(Reading.firing_id == firing_id).order_by(Reading.timestamp)
    )
    readings = list(result.scalars().all())
    return compute_firing_stats_from_readings(readings)


@router.get("/stats/health")
async def health_trend(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Per-band heating rates + cooling rate trend over the last 50 firings.
    Pulls rows from firing_stats (not readings), parsing the small JSON blob
    once per firing — 50 JSON decodes, no reading scan."""
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

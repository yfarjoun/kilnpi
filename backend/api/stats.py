"""Kiln statistics API — computed on-the-fly from readings."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_session
from backend.models.schemas import Firing, Reading

router = APIRouter()

# Temperature bands for heating rate analysis
TEMP_BANDS = [
    ("0-200", 0, 200),
    ("200-400", 200, 400),
    ("400-600", 400, 600),
    ("600-800", 600, 800),
    ("800-1000", 800, 1000),
    ("1000+", 1000, float("inf")),
]


def _parse_ts(ts: str) -> datetime:
    """Parse ISO timestamp string to datetime."""
    return datetime.fromisoformat(ts)


def _find_sitter_cutoff(
    timestamps: list[datetime], pvs: list[float], mvs: list[float]
) -> int | None:
    """Detect kiln sitter cutoff: temp dropping sharply while MV is still high.

    Returns the index where the sitter tripped, or None for a normal firing.
    """
    if len(pvs) < 4:
        return None

    peak_idx = pvs.index(max(pvs))
    window = 3

    for i in range(peak_idx, len(pvs) - window):
        pv_drop = pvs[i] - pvs[i + window]
        avg_mv = sum(mvs[i : i + window]) / window
        if pv_drop > 10 and avg_mv > 50:
            return i

    return None


def _compute_firing_stats(readings: list[Reading]) -> dict:
    """Compute stats for a single firing from its readings."""
    if not readings:
        return {
            "duration_min": 0,
            "max_temp": 0,
            "avg_mv": 0,
            "heating_rates": {},
            "cooling_rate": 0,
            "active_duration_min": None,
            "cutoff_timestamp": None,
        }

    timestamps = [_parse_ts(r.timestamp) for r in readings]
    pvs = [r.pv for r in readings]
    mvs = [r.mv for r in readings]

    duration_sec = (timestamps[-1] - timestamps[0]).total_seconds()
    duration_min = round(duration_sec / 60, 1)
    max_temp = max(pvs)

    # Detect sitter cutoff
    cutoff_idx = _find_sitter_cutoff(timestamps, pvs, mvs)
    cutoff_timestamp: str | None = None
    active_duration_min: float | None = None

    if cutoff_idx is not None:
        cutoff_timestamp = timestamps[cutoff_idx].isoformat()
        active_sec = (timestamps[cutoff_idx] - timestamps[0]).total_seconds()
        active_duration_min = round(active_sec / 60, 1)
        # avg_mv only over active period
        avg_mv = round(sum(mvs[: cutoff_idx + 1]) / (cutoff_idx + 1), 1)
    else:
        avg_mv = round(sum(mvs) / len(mvs), 1)

    # Heating rates by temp band (only during heating phase — up to max temp)
    max_idx = pvs.index(max_temp)
    heating_rates: dict[str, float] = {}
    for label, low, high in TEMP_BANDS:
        # Find readings in this band during heat-up
        band_readings = [
            (timestamps[i], pvs[i]) for i in range(max_idx + 1) if low <= pvs[i] < high
        ]
        if len(band_readings) >= 2:
            dt = (band_readings[-1][0] - band_readings[0][0]).total_seconds() / 60
            dpv = band_readings[-1][1] - band_readings[0][1]
            if dt > 0:
                heating_rates[label] = round(dpv / dt, 2)

    # Cooling rate from max temp down
    cooling_rate = 0.0
    if max_idx < len(readings) - 1:
        cool_dt = (timestamps[-1] - timestamps[max_idx]).total_seconds() / 60
        cool_dpv = pvs[max_idx] - pvs[-1]
        if cool_dt > 0:
            cooling_rate = round(cool_dpv / cool_dt, 2)

    return {
        "duration_min": duration_min,
        "max_temp": max_temp,
        "avg_mv": avg_mv,
        "heating_rates": heating_rates,
        "cooling_rate": cooling_rate,
        "active_duration_min": active_duration_min,
        "cutoff_timestamp": cutoff_timestamp,
    }


@router.get("/stats/summary")
async def stats_summary(session: AsyncSession = Depends(get_session)) -> dict:
    # Total firings
    result = await session.execute(
        select(func.count(Firing.id)).where(Firing.status == "completed")
    )
    total_firings: int = result.scalar() or 0

    # Total firing hours (use active duration when sitter cutoff detected)
    completed_firings = await session.execute(
        select(Firing).where(Firing.status == "completed", Firing.ended_at.isnot(None))
    )
    total_hours = 0.0
    for (firing_row,) in completed_firings.all():
        try:
            readings_result = await session.execute(
                select(Reading)
                .where(Reading.firing_id == firing_row.id)
                .order_by(Reading.timestamp)
            )
            rlist = list(readings_result.scalars().all())
            if rlist:
                stats = _compute_firing_stats(rlist)
                active = stats.get("active_duration_min")
                if active is not None:
                    total_hours += active / 60
                else:
                    total_hours += stats["duration_min"] / 60
            else:
                dt = (
                    _parse_ts(firing_row.ended_at) - _parse_ts(firing_row.started_at)
                ).total_seconds() / 3600
                total_hours += dt
        except (ValueError, TypeError):
            pass
    total_hours = round(total_hours, 1)

    # By program
    result = await session.execute(
        select(
            Firing.program_name,
            func.count(Firing.id).label("count"),
        )
        .where(Firing.status == "completed", Firing.program_name.isnot(None))
        .group_by(Firing.program_name)
    )
    by_program = []
    for name, count in result.all():
        # Get avg duration and avg max temp for this program
        prog_firings = await session.execute(
            select(Firing.id, Firing.started_at, Firing.ended_at).where(
                Firing.status == "completed", Firing.program_name == name
            )
        )
        durations = []
        max_temps = []
        for fid, started_at, ended_at in prog_firings.all():
            if ended_at:
                try:
                    dt = (_parse_ts(ended_at) - _parse_ts(started_at)).total_seconds() / 60
                    durations.append(dt)
                except (ValueError, TypeError):
                    pass
            # Get max PV for this firing
            max_pv_result = await session.execute(
                select(func.max(Reading.pv)).where(Reading.firing_id == fid)
            )
            max_pv = max_pv_result.scalar()
            if max_pv is not None:
                max_temps.append(max_pv)

        by_program.append(
            {
                "name": name,
                "count": count,
                "avg_duration_min": round(sum(durations) / len(durations), 1) if durations else 0,
                "avg_max_temp": round(sum(max_temps) / len(max_temps), 1) if max_temps else 0,
            }
        )

    return {
        "total_firings": total_firings,
        "total_hours": total_hours,
        "by_program": by_program,
    }


@router.get("/stats/firing/{firing_id}")
async def firing_stats(firing_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    firing = await session.get(Firing, firing_id)
    if not firing:
        raise HTTPException(status_code=404, detail="Firing not found")

    result = await session.execute(
        select(Reading).where(Reading.firing_id == firing_id).order_by(Reading.timestamp)
    )
    readings = list(result.scalars().all())
    return _compute_firing_stats(readings)


@router.get("/stats/health")
async def health_trend(session: AsyncSession = Depends(get_session)) -> list[dict]:
    # Get recent completed firings
    result = await session.execute(
        select(Firing)
        .where(Firing.status == "completed")
        .order_by(Firing.started_at.desc())
        .limit(50)
    )
    firings = list(result.scalars().all())

    # Build per-band time series (heating + cooling)
    band_data: dict[str, list[dict]] = {label: [] for label, _, _ in TEMP_BANDS}
    cooling_data: list[dict] = []

    for firing in reversed(firings):  # chronological order
        readings_result = await session.execute(
            select(Reading).where(Reading.firing_id == firing.id).order_by(Reading.timestamp)
        )
        readings = list(readings_result.scalars().all())
        stats = _compute_firing_stats(readings)

        for label in band_data:
            if label in stats["heating_rates"]:
                band_data[label].append(
                    {
                        "firing_id": firing.id,
                        "date": firing.started_at,
                        "rate": stats["heating_rates"][label],
                    }
                )

        if stats["cooling_rate"] > 0:
            cooling_data.append(
                {
                    "firing_id": firing.id,
                    "date": firing.started_at,
                    "rate": stats["cooling_rate"],
                }
            )

    bands: list[dict] = [
        {"band": label, "datapoints": band_data[label]} for label in band_data if band_data[label]
    ]
    if cooling_data:
        bands.append({"band": "Cooling", "datapoints": cooling_data})
    return bands

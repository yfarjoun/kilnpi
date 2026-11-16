"""Per-firing stats service: pure compute + persist helper.

Stats are fixed once a firing's readings are in — none of max_temp,
duration, heating rates, cooling rate, sitter cutoff, or avg_mv depend
on anything that can change later. compute_and_store is called from the
recorder at firing-end and from the stats endpoints as a lazy backfill
for firings that predate this service. Idempotent: re-running against
a firing that already has a stats row overwrites it with the same
values (and bumps computed_at).
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.schemas import FiringStats, Reading

# Heating-rate bands. The 1000+ band captures finishing glaze firings;
# the lower bands catch problems early in a ramp (e.g. a water-smoke
# segment running too fast).
TEMP_BANDS: list[tuple[str, float, float]] = [
    ("0-200", 0, 200),
    ("200-400", 200, 400),
    ("400-600", 400, 600),
    ("600-800", 600, 800),
    ("800-1000", 800, 1000),
    ("1000+", 1000, float("inf")),
]


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _find_sitter_cutoff(pvs: list[float], mvs: list[float]) -> int | None:
    """Detect kiln sitter cutoff: temp dropping sharply while MV is still high.

    The sitter is a mechanical safety device that interrupts power when the
    witness cone slumps. When it trips, PV drops but the controller keeps
    calling for heat (MV high). We look for a >10°C drop over a 3-sample
    window after the peak with average MV above 50%.
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


def compute_firing_stats_from_readings(readings: list[Reading]) -> dict:
    """Compute stats for a single firing's readings. Pure; no DB access.

    Returns a dict with keys duration_min, max_temp, avg_mv, heating_rates,
    cooling_rate, active_duration_min, cutoff_timestamp. Empty readings
    returns a zero-valued dict so the caller doesn't need to special-case it.
    """
    if not readings:
        return {
            "duration_min": 0.0,
            "max_temp": 0.0,
            "avg_mv": 0.0,
            "heating_rates": {},
            "cooling_rate": 0.0,
            "active_duration_min": None,
            "cutoff_timestamp": None,
        }

    timestamps = [_parse_ts(r.timestamp) for r in readings]
    pvs = [r.pv for r in readings]
    mvs = [r.mv for r in readings]

    duration_sec = (timestamps[-1] - timestamps[0]).total_seconds()
    duration_min = round(duration_sec / 60, 1)
    max_temp = max(pvs)

    cutoff_idx = _find_sitter_cutoff(pvs, mvs)
    cutoff_timestamp: str | None = None
    active_duration_min: float | None = None

    if cutoff_idx is not None:
        cutoff_timestamp = timestamps[cutoff_idx].isoformat()
        active_sec = (timestamps[cutoff_idx] - timestamps[0]).total_seconds()
        active_duration_min = round(active_sec / 60, 1)
        # avg_mv is over the active period only — after the sitter trips, the
        # controller may still be calling for heat into a cut circuit, which
        # would skew the average if included.
        avg_mv = round(sum(mvs[: cutoff_idx + 1]) / (cutoff_idx + 1), 1)
    else:
        avg_mv = round(sum(mvs) / len(mvs), 1)

    max_idx = pvs.index(max_temp)
    heating_rates: dict[str, float] = {}
    for label, low, high in TEMP_BANDS:
        band_readings = [
            (timestamps[i], pvs[i]) for i in range(max_idx + 1) if low <= pvs[i] < high
        ]
        if len(band_readings) >= 2:
            dt = (band_readings[-1][0] - band_readings[0][0]).total_seconds() / 60
            dpv = band_readings[-1][1] - band_readings[0][1]
            if dt > 0:
                heating_rates[label] = round(dpv / dt, 2)

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


async def compute_and_store(session: AsyncSession, firing_id: int) -> FiringStats | None:
    """Compute per-firing stats from this firing's readings and upsert to
    firing_stats. Returns the stats row, or None if the firing has no
    readings to compute from (nothing to write).

    Commits on the given session. Caller supplies the session so this can
    be composed with other writes under one transaction when desired."""
    result = await session.execute(
        select(Reading).where(Reading.firing_id == firing_id).order_by(Reading.timestamp)
    )
    readings = list(result.scalars().all())
    if not readings:
        return None

    computed = compute_firing_stats_from_readings(readings)
    now = datetime.now(UTC).isoformat()

    existing = await session.get(FiringStats, firing_id)
    if existing is None:
        stats = FiringStats(
            firing_id=firing_id,
            max_temp=computed["max_temp"],
            duration_min=computed["duration_min"],
            active_duration_min=computed["active_duration_min"],
            cutoff_timestamp=computed["cutoff_timestamp"],
            avg_mv=computed["avg_mv"],
            cooling_rate=computed["cooling_rate"],
            computed_at=now,
        )
        stats.heating_rates = computed["heating_rates"]
        session.add(stats)
    else:
        existing.max_temp = computed["max_temp"]
        existing.duration_min = computed["duration_min"]
        existing.active_duration_min = computed["active_duration_min"]
        existing.cutoff_timestamp = computed["cutoff_timestamp"]
        existing.avg_mv = computed["avg_mv"]
        existing.cooling_rate = computed["cooling_rate"]
        existing.heating_rates = computed["heating_rates"]
        existing.computed_at = now
        stats = existing

    await session.commit()
    return stats

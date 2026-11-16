"""Per-firing stats compute and persist.

Stats are keyed 1:1 to a Firing and derived from its readings. The recorder
writes them at firing end; the Statistics endpoints lazy-backfill any
missing rows. compute_and_store is idempotent: a second run against the
same firing overwrites with the same values.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.schemas import FiringStats, Reading

# Heating-rate bands. The 1000+ band captures finishing glaze firings; the
# lower bands catch problems early in a ramp (e.g. a water-smoke segment
# running too fast).
TEMP_BANDS: list[tuple[str, float, float]] = [
    ("0-200", 0, 200),
    ("200-400", 200, 400),
    ("400-600", 400, 600),
    ("600-800", 600, 800),
    ("800-1000", 800, 1000),
    ("1000+", 1000, float("inf")),
]

# Thermocouple-open sentinel: when the TC is disconnected the controller
# returns 0x7FFF scaled, which in degrees-C reads as 3276.7. Any PV at or
# above this cutoff is a sensor artifact, not a real temperature — poller
# interpolation already guards for it, and the stats compute drops matching
# readings so max_temp/cutoff/cooling_rate don't inherit the sentinel.
_TC_OPEN_PV = 3000.0


@dataclass(slots=True)
class _ReadingTuple:
    """Lightweight (timestamp, pv, mv) used by the pure compute.

    Taking tuples instead of ORM Reading instances keeps compute_and_store's
    memory footprint small when backfilling a large firing on the Pi — each
    ORM Reading is ~1 KB in the identity map, a tuple of three primitives
    is a fraction of that.
    """

    timestamp: str
    pv: float
    mv: float


def _parse_minutes(ts_a: str, ts_b: str) -> float:
    """Return (ts_b - ts_a) in minutes, parsed from ISO strings."""
    from datetime import datetime

    return (datetime.fromisoformat(ts_b) - datetime.fromisoformat(ts_a)).total_seconds() / 60


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


def _drop_sentinel_pvs(
    readings: list[_ReadingTuple] | list[Reading],
) -> list[_ReadingTuple]:
    """Project to _ReadingTuple and strip TC-open sentinel rows.

    Accepts either lightweight tuples or ORM Reading instances so callers
    (recorder end-of-firing, lazy backfill, /stats/firing/{id}) share one
    implementation.
    """
    out: list[_ReadingTuple] = []
    for r in readings:
        if r.pv >= _TC_OPEN_PV:
            continue
        out.append(_ReadingTuple(timestamp=r.timestamp, pv=r.pv, mv=r.mv))
    return out


def compute_firing_stats_from_readings(
    readings: list[_ReadingTuple] | list[Reading],
) -> dict:
    """Compute stats for a single firing's readings. Pure; no DB access.

    Accepts either `_ReadingTuple` or ORM `Reading` instances. Returns a
    dict with keys duration_min, max_temp, avg_mv, heating_rates,
    cooling_rate, active_duration_min, cutoff_timestamp. Empty readings
    returns a zero-valued dict.
    """
    clean = _drop_sentinel_pvs(readings)
    if not clean:
        return {
            "duration_min": 0.0,
            "max_temp": 0.0,
            "avg_mv": 0.0,
            "heating_rates": {},
            "cooling_rate": 0.0,
            "active_duration_min": None,
            "cutoff_timestamp": None,
        }

    timestamps = [r.timestamp for r in clean]
    pvs = [r.pv for r in clean]
    mvs = [r.mv for r in clean]

    duration_min = round(_parse_minutes(timestamps[0], timestamps[-1]), 1)
    max_temp = max(pvs)

    cutoff_idx = _find_sitter_cutoff(pvs, mvs)
    cutoff_timestamp: str | None = None
    active_duration_min: float | None = None

    if cutoff_idx is not None:
        cutoff_timestamp = timestamps[cutoff_idx]
        active_duration_min = round(_parse_minutes(timestamps[0], cutoff_timestamp), 1)
        # Average MV over the active period: after the sitter trips, the
        # controller may still be calling for heat into a cut circuit, which
        # would skew the mean if included.
        avg_mv = round(sum(mvs[: cutoff_idx + 1]) / (cutoff_idx + 1), 1)
    else:
        avg_mv = round(sum(mvs) / len(mvs), 1)

    max_idx = pvs.index(max_temp)
    heating_rates: dict[str, float] = {}
    for label, low, high in TEMP_BANDS:
        band: list[tuple[str, float]] = [
            (timestamps[i], pvs[i]) for i in range(max_idx + 1) if low <= pvs[i] < high
        ]
        if len(band) >= 2:
            dt = _parse_minutes(band[0][0], band[-1][0])
            dpv = band[-1][1] - band[0][1]
            if dt > 0:
                heating_rates[label] = round(dpv / dt, 2)

    cooling_rate = 0.0
    if max_idx < len(clean) - 1:
        cool_dt = _parse_minutes(timestamps[max_idx], timestamps[-1])
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
    """Compute per-firing stats and upsert the firing_stats row.

    Commits on the given session (so a caller inside its own
    `async with async_session()` block sees the row land immediately).
    Returns the stats row, or None when the firing has no readings to
    compute from — in that case no row is written and _backfill_missing_stats
    skips the firing rather than retrying it on every request.

    Selects only (timestamp, pv, mv) rather than full ORM Reading instances
    so even a large legacy firing backfills within Pi memory.
    """
    rows = (
        await session.execute(
            select(Reading.timestamp, Reading.pv, Reading.mv)
            .where(Reading.firing_id == firing_id)
            .order_by(Reading.timestamp)
        )
    ).all()
    tuples = [_ReadingTuple(timestamp=r[0], pv=r[1], mv=r[2]) for r in rows]
    if not tuples:
        return None

    computed = compute_firing_stats_from_readings(tuples)

    existing = await session.get(FiringStats, firing_id)
    stats = existing or FiringStats(firing_id=firing_id)
    stats.max_temp = computed["max_temp"]
    stats.duration_min = computed["duration_min"]
    stats.active_duration_min = computed["active_duration_min"]
    stats.cutoff_timestamp = computed["cutoff_timestamp"]
    stats.avg_mv = computed["avg_mv"]
    stats.cooling_rate = computed["cooling_rate"]
    stats.heating_rates = computed["heating_rates"]
    if existing is None:
        session.add(stats)

    await session.commit()
    return stats

"""History API endpoints: firings list, detail, CSV export."""

import csv
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dto import (
    FiringDetailResponse,
    FiringNotesUpdate,
    FiringResponse,
    PowerReadingResponse,
    ReadingResponse,
)
from backend.models.database import get_session
from backend.models.schemas import Firing, Reading

router = APIRouter()

# Default cap on points returned by the firing-detail endpoint. Long firings
# accumulate thousands of polls (every 2s for hours); sending them all is slow
# to transfer, slow to render, and lethal on mobile. Bucket-mean downsampling
# to ~500 points also has the side effect of smoothing the SSR-cycle bipolar
# noise in MV / current / power — a single average per bucket gives a clean
# "average load" trace rather than the on/off staircase of raw samples.
DEFAULT_MAX_POINTS = 500

# Lexicographic bounds for the COALESCE trick — timestamps stored as ISO 8601
# strings all start with the year, so empty-string and all-nines bracket any
# realistic value and the planner can turn them into index range bounds.
_SINCE_MIN = ""
_UNTIL_MAX = "9999"

# Bucket SQL: timestamp is the bucket START (MIN), segment is the bucket's
# EARLIEST value. AVG skips NULLs the same way the removed Python version did.
# COALESCE on the range bounds lets the SQLite planner turn `since`/`until`
# into true index-range constraints on idx_{readings,power_readings}_firing_ts
# (the `(:p IS NULL OR col >= :p)` form only narrows by firing_id).
_READINGS_BUCKET_SQL = text("""
    WITH filtered AS (
        SELECT timestamp, pv, sp, mv, segment, program_target_temp,
               NTILE(:n) OVER (ORDER BY timestamp) AS bkt
        FROM readings
        WHERE firing_id = :firing_id
          AND timestamp >= COALESCE(:since, :since_min)
          AND timestamp <= COALESCE(:until, :until_max)
    )
    SELECT MIN(timestamp) AS timestamp,
           AVG(pv) AS pv,
           AVG(sp) AS sp,
           AVG(mv) AS mv,
           MIN(segment) AS segment,
           AVG(program_target_temp) AS program_target_temp
    FROM filtered
    GROUP BY bkt
    ORDER BY bkt
""")


_POWER_BUCKET_SQL = text("""
    WITH filtered AS (
        SELECT timestamp, l1_voltage, l1_current, l1_power,
               NTILE(:n) OVER (ORDER BY timestamp) AS bkt
        FROM power_readings
        WHERE firing_id = :firing_id
          AND timestamp >= COALESCE(:since, :since_min)
          AND timestamp <= COALESCE(:until, :until_max)
    )
    SELECT MIN(timestamp) AS timestamp,
           AVG(l1_voltage) AS l1_voltage,
           AVG(l1_current) AS l1_current,
           AVG(l1_power) AS l1_power
    FROM filtered
    GROUP BY bkt
    ORDER BY bkt
""")


def _normalize_bound(value: datetime | None) -> str | None:
    """Convert a FastAPI-parsed datetime to the recorder's storage format
    (`datetime.now(UTC).isoformat()`) so SQLite's lexicographic comparison
    matches rows written with any ISO offset or sub-second precision.
    Naive inputs are assumed UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


async def _bucket_readings(
    session: AsyncSession,
    firing_id: int,
    max_points: int,
    since: str | None,
    until: str | None,
) -> list[ReadingResponse]:
    """SQL-side bucket-mean of readings. When row count <= max_points,
    NTILE gives each row its own bucket so AVG(x) == x — pass-through."""
    result = await session.execute(
        _READINGS_BUCKET_SQL,
        {
            "n": max_points,
            "firing_id": firing_id,
            "since": since,
            "until": until,
            "since_min": _SINCE_MIN,
            "until_max": _UNTIL_MAX,
        },
    )
    return [ReadingResponse(**_row_dict(row)) for row in result]


async def _bucket_power(
    session: AsyncSession,
    firing_id: int,
    max_points: int,
    since: str | None,
    until: str | None,
) -> list[PowerReadingResponse]:
    """SQL-side bucket-mean of power readings; same NTILE/pass-through shape."""
    result = await session.execute(
        _POWER_BUCKET_SQL,
        {
            "n": max_points,
            "firing_id": firing_id,
            "since": since,
            "until": until,
            "since_min": _SINCE_MIN,
            "until_max": _UNTIL_MAX,
        },
    )
    return [PowerReadingResponse(**_row_dict(row)) for row in result]


def _row_dict(row: object) -> dict:
    return dict(row._mapping)  # type: ignore[attr-defined]


def _firing_to_response(f: Firing) -> FiringResponse:
    return FiringResponse(
        id=f.id,
        program_id=f.program_id,
        program_name=f.program_name,
        started_at=f.started_at,
        ended_at=f.ended_at,
        status=f.status,
        notes=f.notes,
    )


@router.get("/firings", response_model=list[FiringResponse])
async def list_firings(session: AsyncSession = Depends(get_session)) -> list[FiringResponse]:
    result = await session.execute(select(Firing).order_by(Firing.started_at.desc()))
    return [_firing_to_response(f) for f in result.scalars().all()]


@router.get("/firings/{firing_id}", response_model=FiringDetailResponse)
async def get_firing(
    firing_id: int,
    max_points: int = Query(
        DEFAULT_MAX_POINTS,
        ge=10,
        le=10000,
        description=(
            "Cap on returned readings (downsample via bucket mean). Set higher for full detail."
        ),
    ),
    since: datetime | None = Query(
        None,
        description=(
            "ISO-8601 timestamp (e.g. 2026-11-11T12:00:00Z); drop readings older "
            "than this. Naive values are treated as UTC."
        ),
    ),
    until: datetime | None = Query(
        None,
        description="ISO-8601 timestamp; drop readings newer than this.",
    ),
    session: AsyncSession = Depends(get_session),
) -> FiringDetailResponse:
    firing = await session.get(Firing, firing_id)
    if not firing:
        raise HTTPException(status_code=404, detail="Firing not found")
    if since is not None and until is not None and since > until:
        raise HTTPException(status_code=422, detail="since must be <= until")
    since_s = _normalize_bound(since)
    until_s = _normalize_bound(until)
    readings = await _bucket_readings(session, firing_id, max_points, since_s, until_s)
    power_readings = await _bucket_power(session, firing_id, max_points, since_s, until_s)
    return FiringDetailResponse(
        firing=_firing_to_response(firing),
        readings=readings,
        power_readings=power_readings,
    )


@router.get("/firings/{firing_id}/csv")
async def export_firing_csv(
    firing_id: int, session: AsyncSession = Depends(get_session)
) -> StreamingResponse:
    firing = await session.get(Firing, firing_id)
    if not firing:
        raise HTTPException(status_code=404, detail="Firing not found")
    result = await session.execute(
        select(Reading).where(Reading.firing_id == firing_id).order_by(Reading.timestamp)
    )
    readings = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "pv", "sp", "mv", "segment"])
    for r in readings:
        writer.writerow([r.timestamp, r.pv, r.sp, r.mv, r.segment])

    output.seek(0)
    filename = f"firing_{firing_id}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/firings/{firing_id}")
async def delete_firing(firing_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    firing = await session.get(Firing, firing_id)
    if not firing:
        raise HTTPException(status_code=404, detail="Firing not found")
    await session.delete(firing)
    await session.commit()
    return {"ok": True}


@router.patch("/firings/{firing_id}/notes", response_model=FiringResponse)
async def update_firing_notes(
    firing_id: int,
    body: FiringNotesUpdate,
    session: AsyncSession = Depends(get_session),
) -> FiringResponse:
    firing = await session.get(Firing, firing_id)
    if not firing:
        raise HTTPException(status_code=404, detail="Firing not found")
    firing.notes = body.notes
    await session.commit()
    await session.refresh(firing)
    return _firing_to_response(firing)

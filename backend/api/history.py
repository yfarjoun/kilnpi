"""History API endpoints: firings list, detail, CSV export."""

import csv
import io
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dto import (
    FiringDetailResponse,
    FiringNotesUpdate,
    FiringResponse,
    PowerReadingResponse,
    ReadingResponse,
)
from backend.models.database import get_session
from backend.models.schemas import Firing, PowerReading, Reading

router = APIRouter()

# Default cap on points returned by the firing-detail endpoint. Long firings
# accumulate thousands of polls (every 2s for hours); sending them all is slow
# to transfer, slow to render, and lethal on mobile. Bucket-mean downsampling
# to ~500 points also has the side effect of smoothing the SSR-cycle bipolar
# noise in MV / current / power — a single average per bucket gives a clean
# "average load" trace rather than the on/off staircase of raw samples.
DEFAULT_MAX_POINTS = 500

T = TypeVar("T", ReadingResponse, PowerReadingResponse)


def _bucket_mean(items: list[T], target: int) -> list[T]:
    """Downsample a sorted-by-time list to roughly `target` items via bucket mean.

    Each bucket aggregates ~len(items)/target consecutive items: numeric
    fields are averaged (Nones skipped), the bucket's middle item provides
    the timestamp and any non-numeric / discrete fields.
    """
    if len(items) <= target or target <= 0:
        return items
    bucket_size = len(items) / target
    out: list[T] = []
    if isinstance(items[0], ReadingResponse):
        mean_fields = ("pv", "sp", "mv", "program_target_temp")
        carry_fields = ("segment",)
    else:  # PowerReadingResponse
        mean_fields = ("l1_voltage", "l1_current", "l1_power")
        carry_fields = ()
    for i in range(target):
        start = int(i * bucket_size)
        end = max(start + 1, int((i + 1) * bucket_size))
        bucket = items[start:end]
        if not bucket:
            continue
        mid = bucket[len(bucket) // 2]
        avg: dict[str, float | int | str | None] = {"timestamp": mid.timestamp}
        for f in mean_fields:
            vals = [v for v in (getattr(b, f) for b in bucket) if v is not None]
            avg[f] = sum(vals) / len(vals) if vals else None
        for f in carry_fields:
            avg[f] = getattr(mid, f)
        # mypy/pyright happy: model_validate handles the dict
        out.append(type(items[0]).model_validate(avg))
    return out


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
    session: AsyncSession = Depends(get_session),
) -> FiringDetailResponse:
    firing = await session.get(Firing, firing_id)
    if not firing:
        raise HTTPException(status_code=404, detail="Firing not found")
    result = await session.execute(
        select(Reading).where(Reading.firing_id == firing_id).order_by(Reading.timestamp)
    )
    readings = [
        ReadingResponse(
            timestamp=r.timestamp,
            pv=r.pv,
            sp=r.sp,
            mv=r.mv,
            segment=r.segment,
            program_target_temp=r.program_target_temp,
        )
        for r in result.scalars().all()
    ]
    power_result = await session.execute(
        select(PowerReading)
        .where(PowerReading.firing_id == firing_id)
        .order_by(PowerReading.timestamp)
    )
    power_readings = [
        PowerReadingResponse.model_validate(pr) for pr in power_result.scalars().all()
    ]
    return FiringDetailResponse(
        firing=_firing_to_response(firing),
        readings=_bucket_mean(readings, max_points),
        power_readings=_bucket_mean(power_readings, max_points),
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

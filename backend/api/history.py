"""History API endpoints: firings list, detail, CSV export."""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dto import FiringDetailResponse, FiringNotesUpdate, FiringResponse, PowerReadingResponse, ReadingResponse
from backend.models.database import get_session
from backend.models.schemas import Firing, PowerReading, Reading

router = APIRouter()


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
    firing_id: int, session: AsyncSession = Depends(get_session)
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

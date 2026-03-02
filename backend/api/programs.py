"""Program CRUD API endpoints."""

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dto import ProgramCreate, ProgramResponse, ProgramUpdate, Segment
from backend.models.database import get_session
from backend.models.schemas import Program

router = APIRouter()


def _program_to_response(p: Program) -> ProgramResponse:
    return ProgramResponse(
        id=p.id,
        name=p.name,
        description=p.description,
        segments=[Segment(**s) for s in p.segments],
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("/programs", response_model=list[ProgramResponse])
async def list_programs(session: AsyncSession = Depends(get_session)) -> list[ProgramResponse]:
    result = await session.execute(select(Program).order_by(Program.updated_at.desc()))
    return [_program_to_response(p) for p in result.scalars().all()]


@router.post("/programs", response_model=ProgramResponse, status_code=201)
async def create_program(
    data: ProgramCreate, session: AsyncSession = Depends(get_session)
) -> ProgramResponse:
    now = datetime.now(UTC).isoformat()
    program = Program(
        name=data.name,
        description=data.description,
        segments_json=json.dumps([s.model_dump() for s in data.segments]),
        created_at=now,
        updated_at=now,
    )
    session.add(program)
    await session.commit()
    await session.refresh(program)
    return _program_to_response(program)


@router.get("/programs/{program_id}", response_model=ProgramResponse)
async def get_program(
    program_id: int, session: AsyncSession = Depends(get_session)
) -> ProgramResponse:
    program = await session.get(Program, program_id)
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")
    return _program_to_response(program)


@router.put("/programs/{program_id}", response_model=ProgramResponse)
async def update_program(
    program_id: int, data: ProgramUpdate, session: AsyncSession = Depends(get_session)
) -> ProgramResponse:
    program = await session.get(Program, program_id)
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")
    if data.name is not None:
        program.name = data.name
    if data.description is not None:
        program.description = data.description
    if data.segments is not None:
        program.segments_json = json.dumps([s.model_dump() for s in data.segments])
    program.updated_at = datetime.now(UTC).isoformat()
    await session.commit()
    await session.refresh(program)
    return _program_to_response(program)


@router.delete("/programs/{program_id}")
async def delete_program(
    program_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    program = await session.get(Program, program_id)
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")
    await session.delete(program)
    await session.commit()
    return {"ok": True}

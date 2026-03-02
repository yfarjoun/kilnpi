"""Program CRUD API endpoints."""

import csv
import io
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
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


@router.get("/programs/{program_id}/csv")
async def export_program_csv(
    program_id: int, session: AsyncSession = Depends(get_session)
) -> StreamingResponse:
    program = await session.get(Program, program_id)
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")

    output = io.StringIO()
    output.write(f"#name,{program.name}\n")
    if program.description:
        output.write(f"#description,{program.description}\n")
    writer = csv.writer(output)
    writer.writerow(["ramp_min", "soak_min", "target_temp"])
    for seg in program.segments:
        writer.writerow([seg["ramp_min"], seg["soak_min"], seg["target_temp"]])

    output.seek(0)
    filename = f"{program.name.replace(' ', '_')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/programs/import", response_model=ProgramResponse, status_code=201)
async def import_program_csv(
    file: UploadFile, session: AsyncSession = Depends(get_session)
) -> ProgramResponse:
    content = (await file.read()).decode("utf-8")
    lines = content.strip().splitlines()

    name = "Imported Program"
    description: str | None = None
    data_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#name,"):
            name = stripped.split(",", 1)[1].strip()
        elif stripped.startswith("#description,"):
            description = stripped.split(",", 1)[1].strip()
        elif not stripped.startswith("#"):
            data_lines.append(stripped)

    if len(data_lines) < 2:
        raise HTTPException(status_code=400, detail="CSV must have a header row and at least one segment")

    reader = csv.DictReader(data_lines)
    segments: list[Segment] = []
    for row in reader:
        try:
            segments.append(Segment(
                ramp_min=int(row["ramp_min"]),
                soak_min=int(row["soak_min"]),
                target_temp=float(row["target_temp"]),
            ))
        except (KeyError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"Invalid CSV row: {e}")

    if not segments:
        raise HTTPException(status_code=400, detail="No valid segments found in CSV")

    now = datetime.now(UTC).isoformat()
    program = Program(
        name=name,
        description=description,
        segments_json=json.dumps([s.model_dump() for s in segments]),
        created_at=now,
        updated_at=now,
    )
    session.add(program)
    await session.commit()
    await session.refresh(program)
    return _program_to_response(program)

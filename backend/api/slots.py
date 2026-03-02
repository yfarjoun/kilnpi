"""Slots API — assign library programs to controller slots A/B and fire them."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from backend.dto import ProgramResponse, Segment, SlotAssignRequest, SlotResponse
from backend.modbus.controller import ControllerInterface
from backend.models.database import async_session
from backend.models.schemas import Program, SlotAssignment
from backend.services.poller import ControllerState

router = APIRouter(prefix="/slots", tags=["slots"])

_controller: ControllerInterface | None = None
_state: ControllerState | None = None

VALID_SLOTS = ("A", "B")


def set_controller(controller: ControllerInterface) -> None:
    global _controller
    _controller = controller


def set_state(state: ControllerState) -> None:
    global _state
    _state = state


def _program_to_response(prog: Program) -> ProgramResponse:
    return ProgramResponse(
        id=prog.id,
        name=prog.name,
        description=prog.description,
        segments=[Segment(**s) for s in prog.segments],
        created_at=prog.created_at,
        updated_at=prog.updated_at,
    )


async def _get_slot_assignments() -> dict[str, SlotAssignment | None]:
    """Load both slot assignments from DB."""
    async with async_session() as session:
        result = await session.execute(
            select(SlotAssignment).where(SlotAssignment.slot.in_(VALID_SLOTS))
        )
        rows = result.scalars().all()
        assignments: dict[str, SlotAssignment | None] = {"A": None, "B": None}
        for row in rows:
            # Eagerly load the program relationship
            await session.refresh(row, ["program"])
            assignments[row.slot] = row
        return assignments


async def _upload_slots_to_controller() -> None:
    """Build combined segment list from both slots and write to controller."""
    assert _controller is not None
    assignments = await _get_slot_assignments()

    combined: list[Segment] = []
    for slot_name in ("A", "B"):
        assignment = assignments[slot_name]
        if assignment and assignment.program:
            prog_segments = [Segment(**s) for s in assignment.program.segments]
            combined.extend(prog_segments)
            # End marker: a segment with ramp=0
            combined.append(Segment(ramp_min=0, soak_min=0, target_temp=0))

    if combined:
        _controller.write_program(combined)
    else:
        # Clear controller program
        _controller.write_program([])


def _calculate_start_segment(
    assignments: dict[str, SlotAssignment | None], slot: str
) -> int:
    """Calculate the 0-based index into the combined program for a slot."""
    if slot == "A":
        return 0
    # Slot B starts after slot A's segments + end marker
    a = assignments["A"]
    if a and a.program:
        return len(a.program.segments) + 1  # +1 for end marker
    return 0


@router.get("", response_model=list[SlotResponse])
async def get_slots() -> list[SlotResponse]:
    assignments = await _get_slot_assignments()
    result: list[SlotResponse] = []
    for slot_name in VALID_SLOTS:
        assignment = assignments[slot_name]
        prog = None
        if assignment and assignment.program:
            prog = _program_to_response(assignment.program)
        result.append(SlotResponse(slot=slot_name, program=prog))
    return result


@router.put("/{slot}/assign", response_model=SlotResponse)
async def assign_slot(slot: str, req: SlotAssignRequest) -> SlotResponse:
    slot = slot.upper()
    if slot not in VALID_SLOTS:
        raise HTTPException(400, f"Invalid slot: {slot}. Must be A or B.")

    async with async_session() as session:
        # Verify program exists
        program = await session.get(Program, req.program_id)
        if not program:
            raise HTTPException(404, f"Program {req.program_id} not found")

        # Upsert slot assignment
        existing = await session.get(SlotAssignment, slot)
        if existing:
            existing.program_id = req.program_id
            existing.assigned_at = datetime.now(UTC).isoformat()
        else:
            assignment = SlotAssignment(
                slot=slot,
                program_id=req.program_id,
                assigned_at=datetime.now(UTC).isoformat(),
            )
            session.add(assignment)
        await session.commit()

    # Re-upload both slots to controller
    await _upload_slots_to_controller()

    # Return updated slot info
    assignments = await _get_slot_assignments()
    assignment = assignments[slot]
    prog = None
    if assignment and assignment.program:
        prog = _program_to_response(assignment.program)
    return SlotResponse(slot=slot, program=prog)


@router.delete("/{slot}/assign")
async def unassign_slot(slot: str) -> dict:
    slot = slot.upper()
    if slot not in VALID_SLOTS:
        raise HTTPException(400, f"Invalid slot: {slot}. Must be A or B.")

    async with async_session() as session:
        existing = await session.get(SlotAssignment, slot)
        if existing:
            await session.delete(existing)
            await session.commit()

    # Re-upload remaining slot to controller
    await _upload_slots_to_controller()
    return {"ok": True}


@router.post("/{slot}/fire")
async def fire_slot(slot: str) -> dict:
    assert _controller is not None
    assert _state is not None

    slot = slot.upper()
    if slot not in VALID_SLOTS:
        raise HTTPException(400, f"Invalid slot: {slot}. Must be A or B.")

    # Check not already running (read directly from controller for accuracy)
    from backend.modbus.registers import RunMode

    if _controller.read_run_status() == RunMode.RUNNING:
        raise HTTPException(409, "A program is already running")

    # Look up slot assignment
    assignments = await _get_slot_assignments()
    assignment = assignments[slot]
    if not assignment or not assignment.program:
        raise HTTPException(400, f"Slot {slot} has no program assigned")

    # Ensure controller has the latest program (survives server restarts)
    await _upload_slots_to_controller()

    # Set active program info on state for the recorder
    _state.active_program_id = assignment.program_id
    _state.active_program_name = assignment.program.name

    # Calculate starting segment and fire
    start_seg = _calculate_start_segment(assignments, slot)
    _controller.write_start_segment(start_seg)
    _controller.start_program()

    return {
        "ok": True,
        "slot": slot,
        "program": assignment.program.name,
        "start_segment": start_seg,
    }

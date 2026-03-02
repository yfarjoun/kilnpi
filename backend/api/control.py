"""Control API endpoints: setpoint, start/stop, PID, autotune."""

from fastapi import APIRouter

from backend.dto import AutotuneRequest, PIDParams, Segment, SetpointRequest
from backend.modbus.controller import ControllerInterface

router = APIRouter()

# Set by main.py at startup
_controller: ControllerInterface | None = None


def set_controller(controller: ControllerInterface) -> None:
    global _controller
    _controller = controller


@router.post("/setpoint")
async def set_setpoint(req: SetpointRequest) -> dict:
    assert _controller is not None
    _controller.write_sp(req.value)
    return {"ok": True, "sp": req.value}


@router.post("/program/start")
async def start_program() -> dict:
    assert _controller is not None
    _controller.start_program()
    return {"ok": True}


@router.post("/program/stop")
async def stop_program() -> dict:
    assert _controller is not None
    _controller.stop_program()
    return {"ok": True}


@router.get("/pid", response_model=PIDParams)
async def get_pid() -> PIDParams:
    assert _controller is not None
    return _controller.read_pid()


@router.put("/pid")
async def set_pid(params: PIDParams) -> dict:
    assert _controller is not None
    _controller.write_pid(params)
    return {"ok": True}


@router.post("/autotune")
async def autotune(req: AutotuneRequest) -> dict:
    assert _controller is not None
    if req.start:
        _controller.start_autotune()
    else:
        _controller.stop_autotune()
    return {"ok": True, "autotuning": req.start}


@router.get("/controller/program", response_model=list[Segment])
async def get_controller_program() -> list[Segment]:
    assert _controller is not None
    return _controller.read_program()


@router.put("/controller/program")
async def set_controller_program(segments: list[Segment]) -> dict:
    assert _controller is not None
    _controller.write_program(segments)
    return {"ok": True, "segments": len(segments)}

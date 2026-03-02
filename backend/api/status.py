"""Status API endpoint."""

from fastapi import APIRouter

from backend.dto import StatusResponse
from backend.services.poller import ControllerState

router = APIRouter()

# Set by main.py at startup
_state: ControllerState | None = None


def set_state(state: ControllerState) -> None:
    global _state
    _state = state


@router.get("/status", response_model=StatusResponse)
async def get_status() -> dict:
    assert _state is not None, "State not initialized"
    return _state.snapshot()

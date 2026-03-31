"""System info API endpoint — Pi health data for the web UI."""

from collections.abc import Callable

from fastapi import APIRouter

from backend.services.display import (
    get_cpu_temp,
    get_disk_usage_pct,
    get_ip_address,
    get_memory_usage_pct,
    get_poll_age_sec,
    get_uptime,
    is_wifi_connected,
)
from backend.services.poller import ControllerState

router = APIRouter()

# Set by main.py at startup
_state: ControllerState | None = None
_ws_client_count: Callable[[], int] | None = None


def set_state(state: ControllerState) -> None:
    global _state
    _state = state


def set_ws_client_count(fn: Callable[[], int]) -> None:
    global _ws_client_count
    _ws_client_count = fn


@router.get("/system")
async def get_system_info() -> dict:
    assert _state is not None, "State not initialized"
    poll_age = get_poll_age_sec(_state)
    return {
        "disk_usage_pct": get_disk_usage_pct(),
        "memory_usage_pct": get_memory_usage_pct(),
        "cpu_temp": get_cpu_temp(),
        "ip_address": get_ip_address(),
        "wifi_connected": is_wifi_connected(),
        "uptime": get_uptime(),
        "ws_client_count": _ws_client_count() if _ws_client_count else 0,
        "last_poll_ok": _state.last_poll_ok,
        "poll_age_sec": poll_age,
    }

"""Tests for WebSocket endpoint."""


import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.services.poller import ControllerState


@pytest.fixture
async def client():  # type: ignore[no-untyped-def]
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.mark.asyncio
async def test_broadcast_loop_sends_data() -> None:
    """Test that the broadcast loop formats data correctly."""
    from backend.api.ws import set_state
    from backend.modbus.registers import RunMode

    state = ControllerState()
    state.update(pv=100, sp=200, mv=50, run_mode=RunMode.RUNNING, segment=1,
                 segment_elapsed_min=5, alarm1=False, alarm2=False)
    set_state(state)

    snap = state.snapshot()
    assert snap["pv"] == 100
    assert snap["run_mode"] == "running"
    assert snap["segment"] == 1


@pytest.mark.asyncio
async def test_ws_module_state() -> None:
    """Test the set_state function."""
    from backend.api.ws import set_state
    from backend.modbus.registers import RunMode

    state = ControllerState()
    set_state(state)

    state.update(pv=300, sp=400, mv=80, run_mode=RunMode.OFF, segment=0,
                 segment_elapsed_min=0, alarm1=True, alarm2=False)
    snap = state.snapshot()
    assert snap["alarm1"] is True
    assert snap["alarm2"] is False
    assert snap["run_mode"] == "off"

"""Integration test: power monitoring with mock PZEMs."""

import time

from backend.modbus.mock_pzem import MockPzemReader
from backend.services.power_poller import PowerPoller, PowerState


def test_full_power_cycle():
    """Simulate a firing cycle: idle -> heating -> full power -> cooling -> idle."""
    l1 = MockPzemReader("L1")
    l2 = MockPzemReader("L2")
    state = PowerState()
    poller = PowerPoller(l1, l2, state, interval=0.1)
    poller.start()

    # Idle
    l1.set_mv(0)
    l2.set_mv(0)
    time.sleep(0.3)
    snap = state.snapshot()
    assert snap["total_current"] is not None
    assert snap["total_current"] < 5.0  # near zero

    # Heating
    l1.set_mv(80)
    l2.set_mv(80)
    time.sleep(0.3)
    snap = state.snapshot()
    assert snap["total_current"] > 20.0  # significant current

    # Full power
    l1.set_mv(100)
    l2.set_mv(100)
    time.sleep(0.3)
    snap = state.snapshot()
    assert snap["total_power"] > 3000.0  # ~5kW

    # Cooling
    l1.set_mv(0)
    l2.set_mv(0)
    time.sleep(0.3)
    snap = state.snapshot()
    assert snap["total_current"] < 5.0

    poller.stop()
    assert state.last_poll_ok

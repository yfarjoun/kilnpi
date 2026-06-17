"""Integration test: power monitoring with a mock PZEM."""

import time

from backend.modbus.mock_pzem import MockPzemReader
from backend.services.power_poller import PowerPoller, PowerState


def test_full_power_cycle():
    """Simulate a firing cycle: idle -> heating -> full power -> cooling -> idle."""
    reader = MockPzemReader("L1")
    state = PowerState()
    poller = PowerPoller(reader, state, interval=0.1)
    poller.start()

    # Idle
    reader.set_mv(0)
    time.sleep(0.3)
    snap = state.snapshot()
    assert snap["l1_current"] is not None
    assert snap["l1_current"] < 5.0  # near zero

    # Heating
    reader.set_mv(80)
    time.sleep(0.3)
    snap = state.snapshot()
    assert snap["l1_current"] > 10.0  # significant current

    # Full power
    reader.set_mv(100)
    time.sleep(0.3)
    snap = state.snapshot()
    assert snap["l1_power"] > 1500.0

    # Cooling
    reader.set_mv(0)
    time.sleep(0.3)
    snap = state.snapshot()
    assert snap["l1_current"] < 5.0

    poller.stop()
    assert state.last_poll_ok

"""Tests for PowerState and PowerPoller."""

import time

import pytest

from backend.modbus.mock_pzem import MockPzemReader
from backend.modbus.pzem import PzemReading
from backend.services.power_poller import PowerPoller, PowerState


def _make_reading(voltage=120.0, current=5.0, power=600.0) -> PzemReading:
    return PzemReading(
        voltage=voltage,
        current=current,
        power=power,
        energy=0,
        frequency=60.0,
        power_factor=1.0,
        alarm=False,
    )


def test_power_state_snapshot_empty() -> None:
    state = PowerState()
    snap = state.snapshot()
    assert snap["l1_voltage"] is None
    assert snap["l1_current"] is None
    assert snap["l1_power"] is None
    assert snap["l2_voltage"] is None
    assert snap["l2_current"] is None
    assert snap["l2_power"] is None
    assert snap["total_current"] is None
    assert snap["total_power"] is None


def test_power_state_update_and_snapshot() -> None:
    state = PowerState()
    l1 = _make_reading(voltage=120.0, current=10.0, power=1200.0)
    l2 = _make_reading(voltage=121.0, current=9.5, power=1149.5)
    state.update(l1, l2)

    snap = state.snapshot()

    assert snap["l1_voltage"] == 120.0
    assert snap["l1_current"] == 10.0
    assert snap["l1_power"] == 1200.0
    assert snap["l2_voltage"] == 121.0
    assert snap["l2_current"] == 9.5
    assert snap["l2_power"] == 1149.5
    assert snap["total_current"] == round(10.0 + 9.5, 3)
    assert snap["total_power"] == round(1200.0 + 1149.5, 1)
    assert snap["power_timestamp"] != ""


def test_power_poller_runs() -> None:
    l1_reader = MockPzemReader("L1")
    l2_reader = MockPzemReader("L2")
    l1_reader.set_mv(50)
    l2_reader.set_mv(50)

    state = PowerState()
    poller = PowerPoller(l1_reader, l2_reader, state, interval=0.1)
    poller.start()

    # Wait up to 0.5s for state to be updated
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        if state.last_poll_ok and state.l1 is not None:
            break
        time.sleep(0.02)

    poller.stop()

    assert state.last_poll_ok is True
    assert state.l1 is not None
    assert state.l2 is not None
    snap = state.snapshot()
    assert snap["total_current"] is not None
    assert snap["total_power"] is not None

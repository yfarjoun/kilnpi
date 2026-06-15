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


class _FailingReader:
    """Stand-in PZEM reader that always raises — simulates an unreachable PZEM."""

    def read(self) -> PzemReading:
        raise RuntimeError("simulated PZEM failure")


def test_power_poller_isolates_per_pzem_failure() -> None:
    """If only one PZEM is reachable, the other's failure must not blank the
    surviving channel. PowerState.l1 stays fresh; l2 ends up None; last_poll_ok
    is False (degraded mode)."""
    l1_reader = MockPzemReader("L1")
    l1_reader.set_mv(50)
    l2_reader = _FailingReader()

    state = PowerState()
    poller = PowerPoller(l1_reader, l2_reader, state, interval=0.05)
    poller.start()

    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        if state.l1 is not None:
            break
        time.sleep(0.02)

    poller.stop()

    assert state.l1 is not None, "L1's successful read must be preserved"
    assert state.l2 is None, "L2's failure must surface as None, not stale data"
    assert state.last_poll_ok is False, "any reader failure flags the poll as not-ok"


def test_power_poller_clears_stale_after_disconnect() -> None:
    """If a previously-fresh channel starts failing, its reading must be
    cleared to None — not left as a stale 'last good value' that the OLED
    would keep displaying."""

    class FlakyReader:
        """First read succeeds, subsequent reads raise — simulates a disconnect mid-session."""

        def __init__(self) -> None:
            self._calls = 0

        def read(self) -> PzemReading:
            self._calls += 1
            if self._calls == 1:
                return _make_reading(voltage=120.0, current=3.0, power=360.0)
            raise RuntimeError("disconnected")

    l1_reader = FlakyReader()
    l2_reader = MockPzemReader("L2")
    l2_reader.set_mv(50)

    state = PowerState()
    poller = PowerPoller(l1_reader, l2_reader, state, interval=0.05)
    poller.start()

    # Wait long enough for several poll iterations
    time.sleep(0.4)
    poller.stop()

    # L1 went bad after the first poll; subsequent polls should have cleared it.
    assert state.l1 is None, "stale L1 reading must be cleared once it starts failing"
    assert state.l2 is not None, "L2 keeps working independently"
    assert state.last_poll_ok is False


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

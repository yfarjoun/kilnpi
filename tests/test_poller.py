"""Tests for the polling loop and controller state."""

import time

from backend.modbus.mock_controller import MockController
from backend.modbus.registers import RunMode
from backend.services.poller import ControllerState, Poller


def test_controller_state_snapshot() -> None:
    state = ControllerState()
    state.update(
        pv=850.3, sp=900.0, mv=78.5,
        run_mode=RunMode.RUNNING, segment=5, segment_elapsed_min=12, alarm=False,
    )
    snap = state.snapshot()
    assert snap["pv"] == 850.3
    assert snap["sp"] == 900.0
    assert snap["mv"] == 78.5
    assert snap["run_mode"] == "running"
    assert snap["segment"] == 5
    assert snap["segment_elapsed_min"] == 12
    assert snap["alarm"] is False
    assert snap["timestamp"] != ""


def test_controller_state_default() -> None:
    state = ControllerState()
    snap = state.snapshot()
    assert snap["pv"] == 0.0
    assert snap["run_mode"] == "off"


def test_poller_start_stop() -> None:
    ctrl = MockController()
    state = ControllerState()
    poller = Poller(ctrl, state, interval=0.1)
    poller.start()
    time.sleep(0.3)
    poller.stop()
    # After polling, state should have been updated
    snap = state.snapshot()
    assert snap["timestamp"] != ""
    assert isinstance(snap["pv"], float)


def test_poller_reads_values() -> None:
    ctrl = MockController()
    ctrl.write_sp(500.0)
    state = ControllerState()
    poller = Poller(ctrl, state, interval=0.05)
    poller.start()
    time.sleep(0.2)
    poller.stop()
    snap = state.snapshot()
    assert snap["sp"] == 500.0

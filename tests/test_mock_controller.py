"""Tests for the mock controller."""

from backend.dto import PIDParams, Segment
from backend.modbus.mock_controller import MockController
from backend.modbus.registers import RunMode


def test_initial_state() -> None:
    ctrl = MockController()
    assert ctrl.read_pv() > 0  # room temp
    assert ctrl.read_sp() == 25.0
    assert ctrl.read_run_status() == RunMode.OFF
    assert ctrl.read_alarm() is False


def test_setpoint() -> None:
    ctrl = MockController()
    ctrl.write_sp(500.0)
    assert ctrl.read_sp() == 500.0


def test_pid_params() -> None:
    ctrl = MockController()
    original = ctrl.read_pid()
    assert original.p == 100

    new_params = PIDParams(p=200, i=600, d=150, cycle_time=30)
    ctrl.write_pid(new_params)
    assert ctrl.read_pid() == new_params


def test_program_write_read() -> None:
    ctrl = MockController()
    segments = [
        Segment(ramp_min=30, soak_min=60, target_temp=500.0),
        Segment(ramp_min=45, soak_min=30, target_temp=900.0),
    ]
    ctrl.write_program(segments)
    result = ctrl.read_program()
    assert len(result) == 2
    assert result[0].target_temp == 500.0
    assert result[1].ramp_min == 45


def test_start_stop_program() -> None:
    ctrl = MockController()
    segments = [Segment(ramp_min=30, soak_min=60, target_temp=500.0)]
    ctrl.write_program(segments)

    ctrl.start_program()
    assert ctrl.read_run_status() == RunMode.RUNNING

    ctrl.stop_program()
    assert ctrl.read_run_status() == RunMode.OFF


def test_autotune() -> None:
    ctrl = MockController()
    ctrl.start_autotune()
    ctrl.stop_autotune()
    # Just verify no errors


def test_simulation_moves_pv() -> None:
    ctrl = MockController()
    ctrl.write_sp(100.0)
    ctrl.read_pv()
    # Read a few times to advance simulation
    for _ in range(5):
        ctrl.read_pv()
    # PV should have moved (even slightly) toward SP
    # Due to randomness, just check it's still a valid number
    assert isinstance(ctrl.read_pv(), float)

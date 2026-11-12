"""Tests for the polling loop and controller state."""

import time
from typing import cast

from backend.dto import Segment
from backend.modbus.controller import ControllerInterface
from backend.modbus.mock_controller import MockController
from backend.modbus.registers import RunMode
from backend.services.poller import ControllerState, Poller


def test_controller_state_snapshot() -> None:
    state = ControllerState()
    state.update(
        pv=850.3,
        sp=900.0,
        mv=78.5,
        run_mode=RunMode.RUNNING,
        segment=5,
        segment_elapsed_min=12,
        alarm1=False,
        alarm2=False,
    )
    snap = state.snapshot()
    assert snap["pv"] == 850.3
    assert snap["sp"] == 900.0
    assert snap["mv"] == 78.5
    assert snap["run_mode"] == "running"
    assert snap["segment"] == 5
    assert snap["segment_elapsed_min"] == 12
    assert snap["alarm1"] is False
    assert snap["alarm2"] is False
    assert snap["timestamp"] != ""
    assert snap["total_elapsed_min"] >= 0


def test_controller_state_default() -> None:
    state = ControllerState()
    snap = state.snapshot()
    assert snap["pv"] == 0.0
    assert snap["run_mode"] == "off"
    assert snap["total_elapsed_min"] == 0


def test_total_elapsed_tracks_run_start() -> None:
    state = ControllerState()
    state.update(
        pv=25,
        sp=25,
        mv=0,
        run_mode=RunMode.OFF,
        segment=0,
        segment_elapsed_min=0,
        alarm1=False,
        alarm2=False,
    )
    assert state.snapshot()["total_elapsed_min"] == 0

    state.update(
        pv=100,
        sp=500,
        mv=50,
        run_mode=RunMode.RUNNING,
        segment=1,
        segment_elapsed_min=0,
        alarm1=False,
        alarm2=False,
    )
    assert state.snapshot()["total_elapsed_min"] == 0

    state.update(
        pv=100,
        sp=500,
        mv=0,
        run_mode=RunMode.OFF,
        segment=0,
        segment_elapsed_min=0,
        alarm1=False,
        alarm2=False,
    )
    assert state.snapshot()["total_elapsed_min"] == 0


def test_poller_start_stop() -> None:
    ctrl = MockController()
    state = ControllerState()
    poller = Poller(ctrl, state, interval=0.1)
    poller.start()
    time.sleep(0.3)
    poller.stop()
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


class _ProbeController(MockController):
    """MockController preloaded with a fixed segment program; used only to
    drive `_refresh_live_sp` deterministically. Inherits the full
    ControllerInterface protocol from MockController."""

    def __init__(self, program: list[Segment]) -> None:
        super().__init__()
        self._program = list(program)


def _program() -> list[Segment]:
    # seg 1: ramp 100 min → 500°C; soak 30 min
    # seg 2: ramp 200 min → 1000°C; soak 60 min
    return [
        Segment(ramp_min=100, soak_min=30, target_temp=500.0),
        Segment(ramp_min=200, soak_min=60, target_temp=1000.0),
    ]


def _poller_for(program: list[Segment], state: ControllerState) -> Poller:
    return Poller(cast(ControllerInterface, _ProbeController(program)), state)


def test_live_sp_ramp1_midpoint_uses_captured_pv() -> None:
    """Seg 1 ramp → PV at first observation is captured as C_prev,
    interpolation runs from there to C_1 over r_1 minutes."""
    state = ControllerState()
    poller = _poller_for(_program(), state)
    poller._refresh_live_sp(RunMode.OFF, 0, 0, pv=25.0)
    poller._refresh_live_sp(RunMode.RUNNING, 1, 0, pv=25.0)
    assert state.live_setpoint == 25.0
    poller._refresh_live_sp(RunMode.RUNNING, 1, 50, pv=260.0)
    assert state.live_setpoint == 262.5  # 25 + (500-25)*0.5
    poller._refresh_live_sp(RunMode.RUNNING, 1, 100, pv=500.0)
    assert state.live_setpoint == 500.0


def test_live_sp_soak_holds_c_n() -> None:
    state = ControllerState()
    poller = _poller_for(_program(), state)
    poller._refresh_live_sp(RunMode.RUNNING, 2, 15, pv=500.0)
    assert state.live_setpoint == 500.0


def test_live_sp_ramp2_uses_c_prev_from_controller() -> None:
    """Mid-program ramp: C_prev comes from the previous segment's endpoint,
    not from the current PV."""
    state = ControllerState()
    poller = _poller_for(_program(), state)
    poller._refresh_live_sp(RunMode.RUNNING, 3, 0, pv=800.0)  # PV deliberately wrong
    assert state.live_setpoint == 500.0  # read C_1, not PV
    poller._refresh_live_sp(RunMode.RUNNING, 3, 100, pv=750.0)
    assert state.live_setpoint == 750.0  # 500 + (1000-500)*(100/200)


def test_live_sp_ramp1_mid_firing_observe_uses_current_pv() -> None:
    """Poller started mid-firing with PRO already == 1: the first poll is
    the first PV we see, so that's what seeds C_prev. Not strictly
    accurate, but matches the controller's own display within a few C
    once the kiln is warm, and avoids a flat C_1 line."""
    state = ControllerState()
    poller = _poller_for(_program(), state)
    poller._refresh_live_sp(RunMode.RUNNING, 1, 30, pv=200.0)
    # C_prev = 200 (captured), live_sp = 200 + (500-200)*(30/100) = 290
    assert state.live_setpoint == 290.0


def test_live_sp_clears_on_stop() -> None:
    state = ControllerState()
    poller = _poller_for(_program(), state)
    poller._refresh_live_sp(RunMode.OFF, 0, 0, pv=25.0)
    poller._refresh_live_sp(RunMode.RUNNING, 1, 50, pv=260.0)
    assert state.live_setpoint is not None
    poller._refresh_live_sp(RunMode.OFF, 0, 0, pv=260.0)
    assert state.live_setpoint is None
    # Fresh run: new C_prev captured from new PV
    poller._refresh_live_sp(RunMode.RUNNING, 1, 0, pv=50.0)
    assert state.live_setpoint == 50.0


def test_live_sp_elapsed_past_ramp_time_clamps() -> None:
    state = ControllerState()
    poller = _poller_for(_program(), state)
    poller._refresh_live_sp(RunMode.OFF, 0, 0, pv=25.0)
    poller._refresh_live_sp(RunMode.RUNNING, 1, 150, pv=490.0)
    # elapsed>r_n → frac clamped to 1 → live_sp = C_n
    assert state.live_setpoint == 500.0


def test_live_sp_skip_ramp_sentinel_holds_c_n() -> None:
    """r_n=2000 is the controller's 'skip ramp' sentinel: it jumps straight
    to C_n. Code must hold live_sp at C_n, not interpolate over 2000 min."""
    skip_program = [
        Segment(ramp_min=100, soak_min=0, target_temp=500.0),
        Segment(ramp_min=2000, soak_min=0, target_temp=1000.0),  # skip ramp
    ]
    state = ControllerState()
    poller = _poller_for(skip_program, state)
    # Seed from program start
    poller._refresh_live_sp(RunMode.OFF, 0, 0, pv=25.0)
    poller._refresh_live_sp(RunMode.RUNNING, 1, 100, pv=500.0)
    # Enter seg 2 ramp (PRO=3). r_2=2000 → hold at C_2.
    poller._refresh_live_sp(RunMode.RUNNING, 3, 0, pv=500.0)
    assert state.live_setpoint == 1000.0
    poller._refresh_live_sp(RunMode.RUNNING, 3, 30, pv=990.0)
    assert state.live_setpoint == 1000.0


def test_live_sp_slot_b_start_after_end_marker_uses_pv() -> None:
    """Slot-B firings start at a PRO offset past an end-marker (ramp=0).
    The first ramp of slot B must interpolate from PV, not from the
    end-marker's temp=0."""
    slot_a_plus_b = [
        Segment(ramp_min=50, soak_min=0, target_temp=200.0),  # slot A seg 1
        Segment(ramp_min=0, soak_min=0, target_temp=0.0),  # end marker
        Segment(ramp_min=100, soak_min=0, target_temp=800.0),  # slot B seg 1
        Segment(ramp_min=80, soak_min=0, target_temp=1200.0),  # slot B seg 2
    ]
    state = ControllerState()
    poller = _poller_for(slot_a_plus_b, state)
    # Slot B fires with pro_offset = 5 (PRO=5 is ramp of seg_n=3).
    poller._refresh_live_sp(RunMode.OFF, 0, 0, pv=25.0)
    poller._refresh_live_sp(RunMode.RUNNING, 5, 0, pv=25.0)
    # is_program_start fires because seg_2 (the previous register) has r=0.
    # c_prev = PV = 25, not C_2 = 0.
    assert state.live_setpoint == 25.0
    poller._refresh_live_sp(RunMode.RUNNING, 5, 50, pv=400.0)
    # 25 + (800-25) * 0.5 = 412.5
    assert state.live_setpoint == 412.5


def test_live_sp_cleared_on_segment_read_failure() -> None:
    """If the segment-parameter reads raise, live_setpoint must be cleared
    — a stale value from the previous segment would masquerade as current."""

    class _FailingController(_ProbeController):
        def __init__(self, program: list[Segment]) -> None:
            super().__init__(program)
            self._fail = False

        def read_segment_target_temp(self, seg_n: int) -> float:
            if self._fail:
                raise RuntimeError("bus error")
            return super().read_segment_target_temp(seg_n)

    ctrl = _FailingController(_program())
    state = ControllerState()
    poller = Poller(cast(ControllerInterface, ctrl), state)
    # Prime a successful seg_n=1 interpolation.
    poller._refresh_live_sp(RunMode.OFF, 0, 0, pv=25.0)
    poller._refresh_live_sp(RunMode.RUNNING, 1, 30, pv=25.0)
    assert state.live_setpoint is not None
    # Now transition to seg_n=2 with the controller throwing.
    ctrl._fail = True
    poller._refresh_live_sp(RunMode.RUNNING, 3, 0, pv=500.0)
    assert state.live_setpoint is None


def test_live_sp_wait_holds_previous_value() -> None:
    """WAIT means the controller paused for PV to catch up. Hold whatever
    live_setpoint we had; don't clear it to None, don't advance it."""
    state = ControllerState()
    poller = _poller_for(_program(), state)
    poller._refresh_live_sp(RunMode.OFF, 0, 0, pv=25.0)
    poller._refresh_live_sp(RunMode.RUNNING, 1, 0, pv=25.0)  # fill cache: c_prev=25
    poller._refresh_live_sp(RunMode.RUNNING, 1, 50, pv=260.0)  # interp at elapsed=50
    held = state.live_setpoint
    assert held == 262.5
    poller._refresh_live_sp(RunMode.WAIT, 1, 60, pv=275.0)
    assert state.live_setpoint == held  # unchanged


def test_live_sp_tc_open_sentinel_falls_back() -> None:
    """If PV reads the 3276.7 TC-open sentinel at a program start,
    don't use it as C_prev — fall back to live_sp = C_n."""
    state = ControllerState()
    poller = _poller_for(_program(), state)
    poller._refresh_live_sp(RunMode.OFF, 0, 0, pv=3276.7)
    poller._refresh_live_sp(RunMode.RUNNING, 1, 30, pv=3276.7)
    # c_prev=None → live_sp = C_1
    assert state.live_setpoint == 500.0

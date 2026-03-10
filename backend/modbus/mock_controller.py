"""Mock controller for development on Mac (no hardware)."""

import random
import time

from backend.dto import PIDParams, Segment
from backend.modbus.registers import RunMode


class MockController:
    """Simulates a PID-RS kiln controller with a simple thermal model."""

    def __init__(self) -> None:
        self._pv: float = 25.0  # room temperature
        self._sp: float = 25.0
        self._mv: float = 0.0
        self._pid = PIDParams(p=100, i=500, d=100, cycle_time=20)
        self._program: list[Segment] = []
        self._run_mode = RunMode.OFF
        self._current_segment: int = 0
        self._segment_elapsed: int = 0
        self._alarm1: bool = False
        self._alarm2: bool = False
        self._autotuning: bool = False
        self._last_update = time.time()

        # Program execution state
        self._program_start_time: float = 0
        self._segment_start_time: float = 0
        self._start_segment: int = 0  # offset into _program for slot firing

    def _update_simulation(self) -> None:
        """Advance the thermal simulation."""
        now = time.time()
        dt = now - self._last_update
        self._last_update = now

        if self._run_mode == RunMode.RUNNING and self._program:
            self._advance_program(now)

        # Simple thermal model: PV moves toward SP
        error = self._sp - self._pv
        if abs(error) > 0.1:
            # Heating rate ~5°C/sec when far from target, slower when close
            rate = min(5.0, abs(error) * 0.05)
            if error > 0:
                self._mv = min(100.0, abs(error) / 10.0 * 100.0)
                self._pv += rate * dt + random.gauss(0, 0.1)
            else:
                # Cooling is slower
                self._mv = 0.0
                self._pv -= rate * 0.3 * dt + random.gauss(0, 0.1)
        else:
            self._mv = max(0.0, min(100.0, 50.0 + random.gauss(0, 5)))
            self._pv += random.gauss(0, 0.2)

        self._pv = max(0.0, self._pv)

    def _advance_program(self, now: float) -> None:
        """Advance through program segments."""
        if self._current_segment >= len(self._program):
            self._run_mode = RunMode.OFF
            self._current_segment = 0
            return

        seg = self._program[self._current_segment]

        # End marker: ramp=0 means program is done (matches real controller)
        if seg.ramp_min == 0:
            self._run_mode = RunMode.OFF
            self._current_segment = 0
            return

        self._segment_elapsed = int((now - self._segment_start_time) / 60)

        total_seg_time = seg.ramp_min + seg.soak_min
        if self._segment_elapsed >= total_seg_time:
            # Move to next segment
            self._current_segment += 1
            self._segment_start_time = now
            self._segment_elapsed = 0
            if self._current_segment < len(self._program):
                next_seg = self._program[self._current_segment]
                if next_seg.ramp_min == 0:
                    self._run_mode = RunMode.OFF
                else:
                    self._sp = next_seg.target_temp
            else:
                self._run_mode = RunMode.OFF
        else:
            self._sp = seg.target_temp

    def read_pv(self) -> float:
        self._update_simulation()
        return round(self._pv, 1)

    def read_sp(self) -> float:
        return round(self._sp, 1)

    def read_mv(self) -> float:
        self._update_simulation()
        return round(self._mv, 1)

    def write_sp(self, value: float) -> None:
        self._sp = value

    def read_pid(self) -> PIDParams:
        return self._pid

    def write_pid(self, params: PIDParams) -> None:
        self._pid = params

    def read_program(self) -> list[Segment]:
        return list(self._program)

    def write_program(self, segments: list[Segment]) -> None:
        self._program = list(segments)

    def write_start_segment(self, segment: int) -> None:
        self._start_segment = segment

    def start_program(self) -> None:
        if not self._program:
            return
        self._run_mode = RunMode.RUNNING
        self._current_segment = self._start_segment
        self._segment_elapsed = 0
        now = time.time()
        self._program_start_time = now
        self._segment_start_time = now
        if self._current_segment < len(self._program):
            self._sp = self._program[self._current_segment].target_temp

    def stop_program(self) -> None:
        self._run_mode = RunMode.OFF
        self._current_segment = 0
        self._segment_elapsed = 0
        self._start_segment = 0

    def pause_program(self) -> None:
        if self._run_mode == RunMode.RUNNING:
            self._run_mode = RunMode.STANDBY

    def resume_program(self) -> None:
        if self._run_mode == RunMode.STANDBY:
            self._run_mode = RunMode.RUNNING

    def read_run_status(self) -> RunMode:
        return self._run_mode

    def read_segment(self) -> int:
        return self._current_segment

    def read_segment_elapsed(self) -> int:
        return self._segment_elapsed

    def read_alarm(self) -> tuple[bool, bool]:
        return (self._alarm1, self._alarm2)

    def start_autotune(self) -> None:
        self._autotuning = True

    def stop_autotune(self) -> None:
        self._autotuning = False

"""Background polling loop that reads controller state periodically."""

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

import minimalmodbus  # type: ignore[import-untyped]

from backend.modbus.controller import ControllerInterface
from backend.modbus.registers import RunMode

logger = logging.getLogger(__name__)


@dataclass
class ControllerState:
    """Thread-safe snapshot of the latest controller readings."""

    pv: float = 0.0
    sp: float = 0.0
    mv: float = 0.0
    run_mode: RunMode = RunMode.OFF
    segment: int = 0
    segment_elapsed_min: int = 0
    alarm1: bool = False
    alarm2: bool = False
    timestamp: str = ""
    last_poll_ok: bool = False
    active_program_id: int | None = None
    active_program_name: str | None = None
    _active_segments: list[dict] | None = field(default=None, repr=False)
    _pro_offset: int = field(default=1, repr=False)
    _run_started_at: datetime | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(
        self,
        pv: float,
        sp: float,
        mv: float,
        run_mode: RunMode,
        segment: int,
        segment_elapsed_min: int,
        alarm1: bool,
        alarm2: bool,
    ) -> None:
        with self._lock:
            # Track when the program started running
            # STANDBY (paused) is still "program active" — don't clear state
            was_active = self.run_mode in (RunMode.RUNNING, RunMode.STANDBY)
            now_active = run_mode in (RunMode.RUNNING, RunMode.STANDBY)
            if run_mode == RunMode.RUNNING and not was_active:
                self._run_started_at = datetime.now(UTC)
            elif not now_active and was_active:
                self._run_started_at = None
                self.active_program_id = None
                self.active_program_name = None
                self._active_segments = None
                self._pro_offset = 1

            self.pv = pv
            self.sp = sp
            self.mv = mv
            self.run_mode = run_mode
            self.segment = segment
            self.segment_elapsed_min = segment_elapsed_min
            self.alarm1 = alarm1
            self.alarm2 = alarm2
            self.timestamp = datetime.now(UTC).isoformat()

    def snapshot(self) -> dict:
        with self._lock:
            total_elapsed = 0
            if self._run_started_at is not None:
                delta = datetime.now(UTC) - self._run_started_at
                total_elapsed = int(delta.total_seconds() / 60)

            # Interpolate the current ramp/soak target from stored program.
            # Each register segment = 2 PRO values: odd=ramp, even=soak.
            program_target_temp: float | None = None
            if self._active_segments and self.segment >= self._pro_offset:
                relative = self.segment - self._pro_offset
                idx = relative // 2  # program segment index
                is_ramp = relative % 2 == 0  # odd PRO = ramp, even = soak
                if 0 <= idx < len(self._active_segments):
                    seg = self._active_segments[idx]
                    target = seg["target_temp"]
                    if is_ramp:
                        ramp_min = seg["ramp_min"]
                        if idx > 0:
                            prev_temp = self._active_segments[idx - 1]["target_temp"]
                        else:
                            prev_temp = 0.0
                        elapsed = self.segment_elapsed_min
                        if ramp_min > 0 and elapsed < ramp_min:
                            frac = elapsed / ramp_min
                            program_target_temp = prev_temp + (target - prev_temp) * frac
                        else:
                            program_target_temp = target
                    else:
                        # Soak phase: hold at target
                        program_target_temp = target

            # User-facing segment number (1-based) from PRO value
            program_segment: int | None = None
            if self._active_segments and self.segment >= self._pro_offset:
                relative = self.segment - self._pro_offset
                program_segment = relative // 2 + 1  # 1-based

            return {
                "pv": self.pv,
                "sp": self.sp,
                "mv": self.mv,
                "run_mode": self.run_mode.name.lower(),
                "segment": self.segment,
                "program_segment": program_segment,
                "segment_elapsed_min": self.segment_elapsed_min,
                "total_elapsed_min": total_elapsed,
                "alarm1": self.alarm1,
                "alarm2": self.alarm2,
                "timestamp": self.timestamp,
                "active_program_name": self.active_program_name,
                "program_target_temp": program_target_temp,
            }


class Poller:
    """Periodically polls the controller and updates shared state."""

    def __init__(
        self,
        controller: ControllerInterface,
        state: ControllerState,
        interval: float = 2.0,
    ) -> None:
        self._controller = controller
        self._state = state
        self._interval = interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._first_poll_done = threading.Event()
        # Track whether we've already attempted to recover program segments
        # from the controller this firing — avoids re-reading every poll if
        # the program area happens to be empty.
        self._tried_segment_recovery = False

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="poller")
        self._thread.start()
        logger.info("Poller started (interval=%.1fs)", self._interval)

    def wait_for_first_poll(self, timeout: float = 10.0) -> bool:
        """Block until the first poll completes. Returns True if poll succeeded."""
        self._first_poll_done.wait(timeout)
        return self._state.last_poll_ok

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("Poller stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                pv = self._controller.read_pv()
                sp = self._controller.read_sp()
                mv = self._controller.read_mv()
                run_mode = self._controller.read_run_status()
                segment = self._controller.read_segment()
                elapsed = self._controller.read_segment_elapsed()
                alarm1, alarm2 = self._controller.read_alarm()

                self._state.update(pv, sp, mv, run_mode, segment, elapsed, alarm1, alarm2)
                self._state.last_poll_ok = True

                # If the controller is running a program but we don't have
                # its segments cached (e.g., firing started via the
                # controller's physical buttons rather than the web UI),
                # read them from the controller so program_target_temp
                # interpolation works. One-shot per firing.
                self._maybe_recover_program_segments(run_mode)
            except Exception as exc:
                self._state.last_poll_ok = False
                logger.exception("Polling error")
                # Reconnect only on OS-level disconnects, NOT on Modbus
                # protocol errors. minimalmodbus.ModbusException inherits
                # from IOError/OSError but indicates the slave didn't reply
                # or replied wrong — the FD is fine. Reconnecting closes
                # the serial port that minimalmodbus shares across all
                # Instruments on the same /dev path, breaking other readers
                # on the same bus (e.g. the PZEMs).
                if (
                    isinstance(exc, OSError)
                    and not isinstance(exc, minimalmodbus.ModbusException)
                    and hasattr(self._controller, "reconnect")
                ):
                    try:
                        self._controller.reconnect()  # type: ignore[attr-defined]
                    except Exception:
                        logger.exception("Reconnect failed")
            finally:
                self._first_poll_done.set()

            self._stop_event.wait(self._interval)

    def _maybe_recover_program_segments(self, run_mode: RunMode) -> None:
        """If the controller is running a program but we have no segment
        data cached, read it from the controller. Handles firings started
        from the controller's physical buttons or any other path that
        bypasses the web UI's slot-fire endpoint.
        """
        # When the kiln returns to OFF, reset so a future manual firing
        # gets another recovery attempt.
        if run_mode not in (RunMode.RUNNING, RunMode.STANDBY):
            if self._tried_segment_recovery and self._state._active_segments is not None:
                # Don't clear segments mid-firing unless run actually stops.
                pass
            self._tried_segment_recovery = False
            return

        if self._state._active_segments is not None or self._tried_segment_recovery:
            return

        self._tried_segment_recovery = True
        try:
            segments = self._controller.read_program()
        except Exception:
            logger.exception("Auto-recover: failed to read program from controller")
            return
        if not segments:
            logger.warning("Auto-recover: controller has no program segments stored")
            return

        # Use model_dump for Pydantic models; assume list[Segment].
        self._state._active_segments = [s.model_dump() for s in segments]
        # No way to know which slot was used from the physical fire — assume
        # the program is at the start of the segment array (PRO offset = 1).
        # If the slot-B program is the running one, target interpolation may
        # be off until the user re-fires via the web UI.
        self._state._pro_offset = 1
        if self._state.active_program_name is None:
            self._state.active_program_name = "(manual)"
        logger.info(
            "Auto-recovered %d program segments from controller (assumed slot-A offset)",
            len(segments),
        )

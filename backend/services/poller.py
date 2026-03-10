"""Background polling loop that reads controller state periodically."""

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

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
    _active_slot_offset: int = field(default=0, repr=False)
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
                self._active_slot_offset = 0

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
            # During ramp: linearly interpolate between prev and target temp.
            # During soak: hold at target temp.
            program_target_temp: float | None = None
            if self._active_segments and self.segment > 0:
                idx = self.segment - self._active_slot_offset - 1
                if 0 <= idx < len(self._active_segments):
                    seg = self._active_segments[idx]
                    target = seg["target_temp"]
                    ramp_min = seg["ramp_min"]
                    # Previous segment's target (or 0 for first segment)
                    if idx > 0:
                        prev_temp = self._active_segments[idx - 1]["target_temp"]
                    else:
                        prev_temp = 0.0
                    elapsed = self.segment_elapsed_min
                    if ramp_min > 0 and elapsed < ramp_min:
                        # Linearly interpolate through the ramp
                        frac = elapsed / ramp_min
                        program_target_temp = prev_temp + (target - prev_temp) * frac
                    else:
                        # In soak phase (or ramp=0) — hold at target
                        program_target_temp = target

            return {
                "pv": self.pv,
                "sp": self.sp,
                "mv": self.mv,
                "run_mode": self.run_mode.name.lower(),
                "segment": self.segment,
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

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="poller")
        self._thread.start()
        logger.info("Poller started (interval=%.1fs)", self._interval)

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
            except Exception as exc:
                self._state.last_poll_ok = False
                logger.exception("Polling error")
                # USB disconnect leaves a stale fd — try to reconnect
                if isinstance(exc, OSError) and hasattr(self._controller, "reconnect"):
                    try:
                        self._controller.reconnect()  # type: ignore[attr-defined]
                    except Exception:
                        logger.exception("Reconnect failed")

            self._stop_event.wait(self._interval)

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
    # Target temp of the segment the controller is currently in (i.e., C_n
    # where n = (PRO+1)//2). The poller refreshes this on each PRO change.
    # Snapshot uses this as program_target_temp regardless of how the firing
    # was started, with no slot assumption.
    current_segment_target_temp: float | None = None
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

            # Dynamic target the controller is heading toward in the current
            # segment. Read live from the controller by the poller
            # (current_segment_target_temp); no slot assumption.
            program_target_temp: float | None = self.current_segment_target_temp

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
        # Cache last-known PRO so we only re-read the segment target register
        # when the PRO advances to a new segment.
        self._last_seg_for_target: int | None = None

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

                # Read the current segment's target temperature directly
                # from the controller (no slot assumption — works whether
                # the user fired via web UI, physical buttons, or anything
                # else). Stored on state for the snapshot to expose as
                # program_target_temp.
                self._refresh_segment_target(run_mode, segment)
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

    def _refresh_segment_target(self, run_mode: RunMode, pro: int) -> None:
        """Read the current segment's target temp (C_n) from the controller
        whenever PRO advances to a new segment. PRO encodes ramp+soak as
        two consecutive steps per segment, so segment_n = (PRO + 1) // 2.
        Stored on state so snapshot() can surface it as program_target_temp
        without depending on any slot assumption or program-list cache.
        """
        if run_mode not in (RunMode.RUNNING, RunMode.STANDBY) or pro <= 0:
            self._last_seg_for_target = None
            self._state.current_segment_target_temp = None
            return

        seg_n = (pro + 1) // 2
        if seg_n == self._last_seg_for_target:
            return  # cached value still valid

        try:
            target = self._controller.read_segment_target_temp(seg_n)
        except Exception:
            logger.exception("Failed to read segment %d target temp", seg_n)
            return
        self._state.current_segment_target_temp = target
        self._last_seg_for_target = seg_n

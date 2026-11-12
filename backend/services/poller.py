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
    # Live interpolated setpoint the controller is driving toward right now.
    # On a ramp (PRO odd): C_prev + (C_n - C_prev) * elapsed/r_n, where C_prev
    # is the previous segment's endpoint or — at a program start, i.e. seg_n==1
    # or when the register before seg_n is an end-marker (r==0) — the PV the
    # poller observed when this segment first appeared. On a soak (PRO even),
    # or on the skip-ramp sentinel r_n==2000, this holds C_n directly.
    # Updated every poll; set to None when the controller is stopped or the
    # segment-parameter reads fail.
    live_setpoint: float | None = None
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
            # segment (interpolated on ramps, held on soaks, see `live_setpoint`).
            program_target_temp: float | None = self.live_setpoint

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
        # Per-segment-transition cache of the parameters driving live-SP
        # interpolation; refreshed only when PRO moves to a new seg_n.
        # Tuple is (seg_n, C_n, C_prev, r_n_min). C_prev is either the
        # previous segment's endpoint or, at a program start, the PV we
        # observed at the transition (see _refresh_live_sp).
        self._seg_cache: tuple[int, float, float | None, int] | None = None

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

                # Interpolate the live SP the way the controller does on
                # its own display. Works regardless of how the firing was
                # started (no slot assumption). Stored on state as
                # `live_setpoint`.
                self._refresh_live_sp(run_mode, segment, elapsed, pv)
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

    def _refresh_live_sp(self, run_mode: RunMode, pro: int, elapsed_min: int, pv: float) -> None:
        """Compute the live interpolated SP the controller is heading toward.

        PRO encodes ramp(odd)+soak(even) per segment, so seg_n = (pro+1)//2
        and is_ramp = (pro % 2 == 1). A ramp interpolates linearly from
        C_prev to C_n over r_n minutes; a soak holds at C_n. Segment
        parameters are read once per seg_n transition and cached; the
        interpolation itself recomputes every poll as elapsed_min advances.

        C_prev selection, at each PRO→new-seg_n transition:
          * If seg_n == 1, or the register before seg_n is an end-marker
            (r == 0, i.e. a previous slot's terminator), this is a program
            start — use the PV the poller observes at this transition.
          * Otherwise this is a mid-program transition — use the previous
            segment's endpoint C_(n-1).

        Sentinels (`docs/research/thermomart_pid_rs485_protocol.md`):
          * r_n == 0 → "program ends here"; no ramp in progress.
          * r_n == 2000 → "skip ramp": controller jumps straight to C_n.
          In both cases live_sp is held at C_n, not interpolated.

        WAIT holds the previous value — the controller has paused while PV
        catches up, and elapsed_min stops advancing meaningfully until it
        returns to RUNNING. OFF clears everything.
        """
        if run_mode not in (RunMode.RUNNING, RunMode.STANDBY, RunMode.WAIT) or pro <= 0:
            self._seg_cache = None
            self._state.live_setpoint = None
            return

        if run_mode == RunMode.WAIT:
            # Keep the cache and whatever live_setpoint we already have;
            # just don't recompute until we see RUNNING/STANDBY again.
            return

        seg_n = (pro + 1) // 2
        if self._seg_cache is None or self._seg_cache[0] != seg_n:
            try:
                c_n = self._controller.read_segment_target_temp(seg_n)
                r_n = self._controller.read_segment_ramp_min(seg_n)
                # C_prev selection — see docstring. For seg_n==1 we're always
                # at a program start; for seg_n>=2 we check the preceding
                # register's ramp to tell a mid-program transition from a
                # slot-B-style start that lives after an end marker.
                is_program_start = seg_n == 1 or (
                    self._controller.read_segment_ramp_min(seg_n - 1) == 0
                )
                if is_program_start:
                    # Guard against the TC-open sentinel (PV ~ 3276.7 °C
                    # when no thermocouple is connected). Leaving c_prev
                    # None falls back to live_sp = C_n.
                    c_prev: float | None = pv if pv < _TC_OPEN_PV else None
                else:
                    c_prev = self._controller.read_segment_target_temp(seg_n - 1)
            except Exception:
                logger.exception("Failed to read segment %d params", seg_n)
                # Don't leave a stale interpolation from the previous
                # segment as the "current" value — frontends falling back
                # on sp is strictly better than showing a lie.
                self._state.live_setpoint = None
                return
            self._seg_cache = (seg_n, c_n, c_prev, r_n)

        _, c_n, c_prev, r_n = self._seg_cache
        is_ramp = pro % 2 == 1
        if is_ramp and c_prev is not None and 0 < r_n < _RAMP_SKIP_MIN:
            frac = min(1.0, max(0.0, elapsed_min / r_n))
            live_sp: float = c_prev + (c_n - c_prev) * frac
        else:
            live_sp = c_n
        self._state.live_setpoint = live_sp


# TC open-circuit sentinel: PV register reads 0x7FFF -> 3276.7 °C when the
# thermocouple is unplugged. Any ramp-start capture above this is not a
# real temperature. 3000 leaves plenty of headroom above kiln max (~1400).
_TC_OPEN_PV = 3000.0

# r_n register sentinels from the Thermomart protocol doc.
_RAMP_SKIP_MIN = 2000

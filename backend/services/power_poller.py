"""Background power-meter polling loop for the PZEM-016 reader."""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import minimalmodbus  # type: ignore[import-untyped]

from backend.modbus.pzem import PzemReading

logger = logging.getLogger(__name__)


def _needs_reconnect(exc: BaseException) -> bool:
    """True only for OS-level errors that indicate a stale file descriptor.

    Crucially excludes minimalmodbus.ModbusException (NoResponseError,
    InvalidResponseError, SlaveDeviceBusyError, etc.). Those inherit from
    OSError because IOError is OSError in Python 3, but they are protocol-
    level — the FD is fine, the slave just didn't reply or replied wrong.

    Why this matters: minimalmodbus caches one serial.Serial per port name
    across all Instruments. Calling reconnect() closes that shared port,
    which leaves every *other* Instrument on the same port with a stale FD
    that next reads as "Bad file descriptor". So we must only reconnect for
    truly hardware-level failures.
    """
    if isinstance(exc, minimalmodbus.ModbusException):
        return False
    return isinstance(exc, OSError)


@dataclass
class PowerState:
    """Thread-safe holder for the latest PZEM-016 power reading."""

    l1: PzemReading | None = None
    timestamp: str = ""
    last_poll_ok: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, l1: PzemReading | None) -> None:
        with self._lock:
            self.l1 = l1
            self.timestamp = datetime.now(UTC).isoformat()

    def snapshot(self) -> dict:
        with self._lock:
            l1 = self.l1
            ts = self.timestamp

        if l1 is None:
            return {
                "power_timestamp": ts or None,
                "l1_voltage": None,
                "l1_current": None,
                "l1_power": None,
            }

        return {
            "power_timestamp": ts,
            "l1_voltage": l1.voltage,
            "l1_current": l1.current,
            "l1_power": l1.power,
        }


class PowerPoller:
    """Periodically reads the PZEM-016 and updates the shared PowerState."""

    # Quiet-bus wait after acquiring bus_lock and before the PZEM read. Lets
    # the bus settle for ≥ PZEM's 100ms inter-command requirement when the
    # kiln controller's poller has just released the lock.
    BUS_QUIET_WAIT_SEC = 0.15

    def __init__(
        self,
        l1_reader,
        state: PowerState,
        interval: float = 5.0,
        bus_lock: threading.Lock | None = None,
    ) -> None:
        self._l1_reader = l1_reader
        self._state = state
        self._interval = interval
        self._bus_lock = bus_lock
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="power_poller")
        self._thread.start()
        logger.info("PowerPoller started (interval=%.1fs)", self._interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("PowerPoller stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            l1: PzemReading | None = None
            l1_err: Exception | None = None

            # Reconnect must happen INSIDE the bus lock: minimalmodbus caches
            # one serial.Serial per port name across Instruments, so closing
            # the underlying port races with concurrent controller reads.
            if self._bus_lock is not None:
                with self._bus_lock:
                    # Bus quiet window — the kiln poller's last request may
                    # have just finished, and the PZEM needs ≥100ms between
                    # commands on the bus.
                    time.sleep(self.BUS_QUIET_WAIT_SEC)
                    l1, l1_err = self._safe_read(self._l1_reader)
                    self._maybe_reconnect(self._l1_reader, l1_err)
            else:
                l1, l1_err = self._safe_read(self._l1_reader)
                self._maybe_reconnect(self._l1_reader, l1_err)

            # update() with None clears stale data; display falls back to
            # the poll-age view instead of showing yesterday's reading.
            self._state.update(l1)
            self._state.last_poll_ok = l1_err is None

            self._stop_event.wait(self._interval)

    @staticmethod
    def _maybe_reconnect(reader, err: Exception | None) -> None:
        if err is None or not _needs_reconnect(err) or not hasattr(reader, "reconnect"):
            return
        try:
            reader.reconnect()
        except Exception:
            logger.exception("PowerPoller reconnect failed")

    @staticmethod
    def _safe_read(reader) -> tuple["PzemReading | None", "Exception | None"]:
        try:
            return reader.read(), None
        except Exception as e:
            logger.exception("PowerPoller read failed")
            return None, e

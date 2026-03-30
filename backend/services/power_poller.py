"""Background power-meter polling loop for PZEM-016 readers."""

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

from backend.modbus.pzem import PzemReading

logger = logging.getLogger(__name__)


@dataclass
class PowerState:
    """Thread-safe holder for the latest L1/L2 power readings."""

    l1: PzemReading | None = None
    l2: PzemReading | None = None
    timestamp: str = ""
    last_poll_ok: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, l1: PzemReading | None, l2: PzemReading | None) -> None:
        with self._lock:
            self.l1 = l1
            self.l2 = l2
            self.timestamp = datetime.now(UTC).isoformat()

    def snapshot(self) -> dict:
        with self._lock:
            l1 = self.l1
            l2 = self.l2
            ts = self.timestamp

        if l1 is None and l2 is None:
            return {
                "power_timestamp": ts or None,
                "l1_voltage": None,
                "l1_current": None,
                "l1_power": None,
                "l2_voltage": None,
                "l2_current": None,
                "l2_power": None,
                "total_current": None,
                "total_power": None,
            }

        return {
            "power_timestamp": ts,
            "l1_voltage": l1.voltage if l1 is not None else None,
            "l1_current": l1.current if l1 is not None else None,
            "l1_power": l1.power if l1 is not None else None,
            "l2_voltage": l2.voltage if l2 is not None else None,
            "l2_current": l2.current if l2 is not None else None,
            "l2_power": l2.power if l2 is not None else None,
            "total_current": round(
                (l1.current if l1 is not None else 0.0)
                + (l2.current if l2 is not None else 0.0),
                3,
            ),
            "total_power": round(
                (l1.power if l1 is not None else 0.0)
                + (l2.power if l2 is not None else 0.0),
                1,
            ),
        }


class PowerPoller:
    """Periodically reads both PZEM meters and updates shared PowerState."""

    def __init__(
        self,
        l1_reader,
        l2_reader,
        state: PowerState,
        interval: float = 5.0,
        bus_lock: threading.Lock | None = None,
    ) -> None:
        self._l1_reader = l1_reader
        self._l2_reader = l2_reader
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
            try:
                if self._bus_lock is not None:
                    with self._bus_lock:
                        l1 = self._l1_reader.read()
                        l2 = self._l2_reader.read()
                else:
                    l1 = self._l1_reader.read()
                    l2 = self._l2_reader.read()

                self._state.update(l1, l2)
                self._state.last_poll_ok = True
            except Exception as exc:
                self._state.last_poll_ok = False
                logger.exception("PowerPoller error")
                if isinstance(exc, OSError):
                    for reader in (self._l1_reader, self._l2_reader):
                        if hasattr(reader, "reconnect"):
                            try:
                                reader.reconnect()
                            except Exception:
                                logger.exception("PowerPoller reconnect failed")

            self._stop_event.wait(self._interval)

"""Tests for PowerState and PowerPoller (single PZEM)."""

import time

import minimalmodbus  # type: ignore[import-untyped]
import serial  # type: ignore[import-untyped]

from backend.modbus.mock_pzem import MockPzemReader
from backend.modbus.pzem import PzemReading
from backend.services.power_poller import PowerPoller, PowerState


def _make_reading(voltage=120.0, current=5.0, power=600.0) -> PzemReading:
    return PzemReading(
        voltage=voltage,
        current=current,
        power=power,
        energy=0,
        frequency=60.0,
        power_factor=1.0,
        alarm=False,
    )


def test_power_state_snapshot_empty() -> None:
    state = PowerState()
    snap = state.snapshot()
    assert snap["l1_voltage"] is None
    assert snap["l1_current"] is None
    assert snap["l1_power"] is None


def test_power_state_update_and_snapshot() -> None:
    state = PowerState()
    l1 = _make_reading(voltage=120.0, current=10.0, power=1200.0)
    state.update(l1)

    snap = state.snapshot()

    assert snap["l1_voltage"] == 120.0
    assert snap["l1_current"] == 10.0
    assert snap["l1_power"] == 1200.0
    assert snap["power_timestamp"] != ""


class _RecordingReader:
    """Reader that records read/reconnect calls; configurable failure mode."""

    def __init__(self, exc_factory=None) -> None:
        self.read_calls = 0
        self.reconnect_calls = 0
        self._exc_factory = exc_factory

    def read(self) -> PzemReading:
        self.read_calls += 1
        if self._exc_factory is not None:
            raise self._exc_factory()
        return _make_reading()

    def reconnect(self) -> None:
        self.reconnect_calls += 1


def test_no_response_error_does_not_trigger_reconnect() -> None:
    """minimalmodbus.NoResponseError is protocol-level, not a stale FD. It
    inherits from IOError/OSError but must NOT trigger reconnect — doing so
    closes the serial port shared across Instruments via minimalmodbus's
    internal cache and leaves the kiln controller with a bad FD.
    """
    reader = _RecordingReader(lambda: minimalmodbus.NoResponseError("no answer"))
    state = PowerState()
    poller = PowerPoller(reader, state, interval=0.05)
    poller.start()
    time.sleep(0.3)
    poller.stop()

    assert reader.read_calls > 0, "poller should still attempt reads"
    assert reader.reconnect_calls == 0, "NoResponseError must not trigger reconnect"
    assert state.last_poll_ok is False


def test_serial_exception_does_trigger_reconnect() -> None:
    """pyserial SerialException (real hardware disconnect) SHOULD trigger
    reconnect — that's the case the recovery path was built for."""
    reader = _RecordingReader(lambda: serial.SerialException("device removed"))
    state = PowerState()
    poller = PowerPoller(reader, state, interval=0.05)
    poller.start()
    time.sleep(0.3)
    poller.stop()

    assert reader.reconnect_calls > 0, "SerialException must trigger reconnect"


def test_power_poller_clears_stale_after_disconnect() -> None:
    """If the reader starts failing, the channel must be cleared to None —
    not left as a stale 'last good value' that the OLED would keep displaying.
    """

    class FlakyReader:
        """First read succeeds, subsequent reads raise — simulates a disconnect mid-session."""

        def __init__(self) -> None:
            self._calls = 0

        def read(self) -> PzemReading:
            self._calls += 1
            if self._calls == 1:
                return _make_reading(voltage=120.0, current=3.0, power=360.0)
            raise RuntimeError("disconnected")

    reader = FlakyReader()
    state = PowerState()
    poller = PowerPoller(reader, state, interval=0.05)
    poller.start()
    time.sleep(0.4)
    poller.stop()

    assert state.l1 is None, "stale reading must be cleared once polls start failing"
    assert state.last_poll_ok is False


def test_power_poller_runs() -> None:
    reader = MockPzemReader("L1")
    reader.set_mv(50)

    state = PowerState()
    poller = PowerPoller(reader, state, interval=0.1)
    poller.start()

    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        if state.last_poll_ok and state.l1 is not None:
            break
        time.sleep(0.02)

    poller.stop()

    assert state.last_poll_ok is True
    assert state.l1 is not None
    snap = state.snapshot()
    assert snap["l1_voltage"] is not None
    assert snap["l1_current"] is not None

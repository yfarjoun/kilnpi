"""Tests for RealController's lazy/offline behavior when the serial port is missing.

The Pi's kilnpi service must keep running even when the FTDI adapter is
unplugged at boot — otherwise the OLED app and web UI also go down, and the
user has no visibility. RealController should construct successfully without
a port present; reads/writes then raise (poller catches → MB- on OLED) until
the port reappears.
"""

import pytest

from backend.modbus.real_controller import RealController

# A path that's reliably not a real serial port on any of the platforms we run.
NONEXISTENT_PORT = "/dev/nonexistent_test_port_42"


def test_init_tolerates_missing_port() -> None:
    """Constructor must not raise when the serial port is absent."""
    # This used to crash the entire kilnpi service at startup.
    ctrl = RealController(port=NONEXISTENT_PORT)
    assert ctrl._instrument is None  # type: ignore[attr-defined]


def test_read_raises_when_port_still_missing() -> None:
    """After offline init, reads should raise — surfacing as MB- via the poller."""
    ctrl = RealController(port=NONEXISTENT_PORT)
    with pytest.raises(Exception):  # noqa: B017 — minimalmodbus/pyserial OSError variant
        ctrl.read_pv()


def test_reconnect_raises_when_hardware_absent() -> None:
    """reconnect() should raise when the port is still unavailable; the
    poller's exception handler logs this and proceeds — no crash."""
    ctrl = RealController(port=NONEXISTENT_PORT)
    with pytest.raises(Exception):  # noqa: B017
        ctrl.reconnect()

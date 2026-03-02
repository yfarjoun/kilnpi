"""Tests for the OLED display service (Pi system info)."""

import time
from unittest.mock import patch

from backend.services.display import (
    DisplayService,
    MockDisplay,
    get_cpu_temp,
    get_disk_usage_pct,
    get_ip_address,
    get_memory_usage_pct,
    get_poll_age_sec,
    is_wifi_connected,
)
from backend.services.poller import ControllerState


def test_mock_display_show() -> None:
    display = MockDisplay()
    display.show(["Line 1", "Line 2"])  # should not raise


def test_get_disk_usage_returns_int() -> None:
    pct = get_disk_usage_pct()
    assert isinstance(pct, int)
    assert 0 <= pct <= 100


def test_get_memory_usage_returns_int() -> None:
    pct = get_memory_usage_pct()
    assert isinstance(pct, int)
    assert 0 <= pct <= 100


def test_get_cpu_temp_returns_float() -> None:
    temp = get_cpu_temp()
    assert isinstance(temp, float)
    assert temp >= 0.0


def test_get_ip_address_returns_string() -> None:
    ip = get_ip_address()
    assert isinstance(ip, str)
    assert len(ip) > 0


def test_is_wifi_connected_returns_bool() -> None:
    result = is_wifi_connected()
    assert isinstance(result, bool)


def test_get_ip_address_fallback_on_error() -> None:
    with patch(
        "backend.services.display.subprocess.run",
        side_effect=OSError("fail"),
    ):
        ip = get_ip_address()
    assert ip == "--"


def test_is_wifi_connected_fallback_on_error() -> None:
    with patch(
        "backend.services.display.subprocess.run",
        side_effect=OSError("fail"),
    ):
        result = is_wifi_connected()
    assert result is False


def test_get_poll_age_no_timestamp() -> None:
    state = ControllerState()
    age = get_poll_age_sec(state)
    assert age == -1


def test_get_poll_age_after_update() -> None:
    from backend.modbus.registers import RunMode

    state = ControllerState()
    state.update(
        pv=100, sp=200, mv=50, run_mode=RunMode.RUNNING,
        segment=1, segment_elapsed_min=0, alarm1=False, alarm2=False,
    )
    age = get_poll_age_sec(state)
    assert age >= 0
    assert age < 5  # just updated, should be <5s


def test_display_service_start_stop() -> None:
    state = ControllerState()
    service = DisplayService(state, lambda: 0, interval=0.1)
    service.start()
    time.sleep(0.3)
    service.stop()


def test_display_service_formats_lines() -> None:
    """Verify that the display receives 3 lines of Pi info."""
    from backend.modbus.registers import RunMode

    shown_lines: list[list[str]] = []

    class CapturingDisplay:
        def show(self, lines: list[str]) -> None:
            shown_lines.append(lines)

    state = ControllerState()
    state.update(
        pv=100, sp=200, mv=50, run_mode=RunMode.RUNNING,
        segment=1, segment_elapsed_min=0, alarm1=False, alarm2=False,
    )

    service = DisplayService(state, lambda: 2, interval=0.05)
    service._display = CapturingDisplay()  # type: ignore[assignment]
    service.start()
    time.sleep(0.2)
    service.stop()

    assert len(shown_lines) >= 1
    lines = shown_lines[0]
    assert len(lines) == 3
    assert "D:" in lines[0]
    assert "M:" in lines[0]
    assert "CPU:" in lines[0]
    assert "W" in lines[1]
    assert "B+" in lines[1]  # lambda returns 2 > 0
    assert "Poll:" in lines[2]


def test_display_shows_browser_disconnected() -> None:
    """B- when no browsers connected."""
    shown_lines: list[list[str]] = []

    class CapturingDisplay:
        def show(self, lines: list[str]) -> None:
            shown_lines.append(lines)

    state = ControllerState()
    service = DisplayService(state, lambda: 0, interval=0.05)
    service._display = CapturingDisplay()  # type: ignore[assignment]
    service.start()
    time.sleep(0.15)
    service.stop()

    assert len(shown_lines) >= 1
    assert "B-" in shown_lines[0][1]


def test_display_poll_age_no_data() -> None:
    """Poll line shows -- when no data yet."""
    shown_lines: list[list[str]] = []

    class CapturingDisplay:
        def show(self, lines: list[str]) -> None:
            shown_lines.append(lines)

    state = ControllerState()  # no update → no timestamp
    service = DisplayService(state, lambda: 0, interval=0.05)
    service._display = CapturingDisplay()  # type: ignore[assignment]
    service.start()
    time.sleep(0.15)
    service.stop()

    assert len(shown_lines) >= 1
    assert "Poll: --" in shown_lines[0][2]

"""Tests for the OLED display service (Pi system info)."""

import time
from unittest.mock import patch

from backend.services.display import (
    DisplayService,
    MockDisplay,
    get_cpu_temp,
    get_ip_address,
    get_uptime,
    get_wifi_info,
)


def test_mock_display_show() -> None:
    display = MockDisplay()
    display.show(["Line 1", "Line 2"])  # should not raise


def test_get_wifi_info_returns_tuple() -> None:
    ssid, signal = get_wifi_info()
    assert isinstance(ssid, str)
    assert isinstance(signal, int)
    assert 0 <= signal <= 100


def test_get_cpu_temp_returns_float() -> None:
    temp = get_cpu_temp()
    assert isinstance(temp, float)
    assert temp >= 0.0


def test_get_ip_address_returns_string() -> None:
    ip = get_ip_address()
    assert isinstance(ip, str)
    assert len(ip) > 0


def test_get_uptime_returns_string() -> None:
    uptime = get_uptime()
    assert isinstance(uptime, str)
    assert len(uptime) > 0


def test_get_wifi_info_fallback_on_error() -> None:
    with patch("backend.services.display.subprocess.run", side_effect=OSError("fail")):
        ssid, signal = get_wifi_info()
    assert ssid == "--"
    assert signal == 0


def test_get_ip_address_fallback_on_error() -> None:
    with patch("backend.services.display.subprocess.run", side_effect=OSError("fail")):
        ip = get_ip_address()
    assert ip == "--"


def test_get_uptime_fallback_on_error() -> None:
    with patch("backend.services.display.time.monotonic", side_effect=OSError("fail")):
        uptime = get_uptime()
    assert uptime == "--"


def test_display_service_start_stop() -> None:
    service = DisplayService(interval=0.1)
    service.start()
    time.sleep(0.3)
    service.stop()
    # Should not raise and should have run at least once


def test_display_service_formats_lines() -> None:
    """Verify that the display receives 4 lines of Pi info."""
    shown_lines: list[list[str]] = []

    class CapturingDisplay:
        def show(self, lines: list[str]) -> None:
            shown_lines.append(lines)

    service = DisplayService(interval=0.05)
    service._display = CapturingDisplay()  # type: ignore[assignment]
    service.start()
    time.sleep(0.2)
    service.stop()

    assert len(shown_lines) >= 1
    lines = shown_lines[0]
    assert len(lines) == 4
    assert lines[0].startswith("WiFi:")
    assert "Sig:" in lines[1]
    assert "CPU:" in lines[1]
    assert lines[2].startswith("IP:")
    assert lines[3].startswith("Up:")

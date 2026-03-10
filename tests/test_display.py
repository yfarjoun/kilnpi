"""Tests for the OLED display service (Pi system info)."""

import time
from unittest.mock import patch

from backend.services.buttons import ButtonState
from backend.services.display import (
    DisplayService,
    MockDisplay,
    get_cpu_temp,
    get_disk_usage_pct,
    get_ip_address,
    get_memory_usage_pct,
    get_poll_age_sec,
    get_uptime,
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
        pv=100,
        sp=200,
        mv=50,
        run_mode=RunMode.RUNNING,
        segment=1,
        segment_elapsed_min=0,
        alarm1=False,
        alarm2=False,
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
    """Verify that the display receives 4 lines of Pi info."""
    from backend.modbus.registers import RunMode

    shown_lines: list[list[str]] = []

    class CapturingDisplay:
        def show(self, lines: list[str]) -> None:
            shown_lines.append(lines)

    state = ControllerState()
    state.update(
        pv=100,
        sp=200,
        mv=50,
        run_mode=RunMode.RUNNING,
        segment=1,
        segment_elapsed_min=0,
        alarm1=False,
        alarm2=False,
    )
    state.last_poll_ok = True
    state.active_program_name = "Bisque"

    service = DisplayService(state, lambda: 2, interval=0.05)
    service._display = CapturingDisplay()  # type: ignore[assignment]
    service.start()
    time.sleep(0.2)
    service.stop()

    assert len(shown_lines) >= 1
    lines = shown_lines[0]
    assert len(lines) == 4
    assert "D:" in lines[0]
    assert "M:" in lines[0]
    assert "CPU:" in lines[0]
    assert "W" in lines[1]
    assert "B+" in lines[1]  # lambda returns 2 > 0
    assert "MB+" in lines[1]  # state was updated → poll ok
    assert "Poll:" in lines[2]
    assert "Bisque" in lines[3]
    assert "S1" in lines[3]
    assert "100" in lines[3]  # pv
    assert "200" in lines[3]  # sp


def test_display_shows_idle_when_not_running() -> None:
    """Line 4 shows 'Idle' when no program running."""
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
    assert len(shown_lines[0]) == 4
    assert shown_lines[0][3] == "Idle"


def test_display_truncates_long_program_name() -> None:
    """Long program names get truncated to fit 21 chars."""
    from backend.modbus.registers import RunMode

    shown_lines: list[list[str]] = []

    class CapturingDisplay:
        def show(self, lines: list[str]) -> None:
            shown_lines.append(lines)

    state = ControllerState()
    state.update(
        pv=1200,
        sp=1300,
        mv=80,
        run_mode=RunMode.RUNNING,
        segment=3,
        segment_elapsed_min=0,
        alarm1=False,
        alarm2=False,
    )
    state.active_program_name = "VeryLongProgramName"

    service = DisplayService(state, lambda: 0, interval=0.05)
    service._display = CapturingDisplay()  # type: ignore[assignment]
    service.start()
    time.sleep(0.15)
    service.stop()

    assert len(shown_lines) >= 1
    line4 = shown_lines[0][3]
    assert len(line4) <= 21
    assert "S3" in line4
    assert "1200" in line4
    assert "1300" in line4


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


def test_display_modbus_disconnected() -> None:
    """MB- when last poll failed."""
    shown_lines: list[list[str]] = []

    class CapturingDisplay:
        def show(self, lines: list[str]) -> None:
            shown_lines.append(lines)

    state = ControllerState()  # last_poll_ok defaults to False
    service = DisplayService(state, lambda: 0, interval=0.05)
    service._display = CapturingDisplay()  # type: ignore[assignment]
    service.start()
    time.sleep(0.15)
    service.stop()

    assert len(shown_lines) >= 1
    assert "MB-" in shown_lines[0][1]


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


# --- Detail mode tests ---


def _make_capturing_service(
    state: ControllerState,
    button_state: ButtonState,
    ws_count: int = 0,
) -> tuple["DisplayService", list[list[str]]]:
    """Helper: create a DisplayService with a capturing display and button state."""
    shown: list[list[str]] = []

    class CapturingDisplay:
        def show(self, lines: list[str]) -> None:
            shown.append(lines)

    service = DisplayService(state, lambda: ws_count, interval=0.05, button_state=button_state)
    service._display = CapturingDisplay()  # type: ignore[assignment]
    return service, shown


def test_system_detail_mode() -> None:
    """KEY1 → expanded system info (disk, memory, CPU, uptime)."""
    state = ControllerState()
    bs = ButtonState()
    bs.press("system")

    service, shown = _make_capturing_service(state, bs)
    service.start()
    time.sleep(0.15)
    service.stop()

    assert len(shown) >= 1
    lines = shown[0]
    assert len(lines) == 4
    assert lines[0].startswith("Disk:")
    assert lines[1].startswith("Memory:")
    assert lines[2].startswith("CPU:")
    assert lines[3].startswith("Uptime:")


def test_network_detail_mode() -> None:
    """KEY2 → expanded network info (IP, WiFi, browsers, Modbus)."""
    from backend.modbus.registers import RunMode

    state = ControllerState()
    state.update(
        pv=100,
        sp=200,
        mv=50,
        run_mode=RunMode.OFF,
        segment=0,
        segment_elapsed_min=0,
        alarm1=False,
        alarm2=False,
    )
    state.last_poll_ok = True

    bs = ButtonState()
    bs.press("network")

    service, shown = _make_capturing_service(state, bs, ws_count=3)
    service.start()
    time.sleep(0.15)
    service.stop()

    assert len(shown) >= 1
    lines = shown[0]
    assert len(lines) == 4
    assert lines[0].startswith("IP:")
    assert lines[1].startswith("WiFi:")
    assert lines[2] == "Browsers: 3"
    assert lines[3].startswith("Modbus: OK")


def test_program_detail_mode_running() -> None:
    """KEY3 → expanded program info when running."""
    from backend.modbus.registers import RunMode

    state = ControllerState()
    state.update(
        pv=850,
        sp=900,
        mv=70,
        run_mode=RunMode.RUNNING,
        segment=1,
        segment_elapsed_min=45,
        alarm1=False,
        alarm2=False,
    )
    state.active_program_name = "Bisque"

    bs = ButtonState()
    bs.press("program")

    service, shown = _make_capturing_service(state, bs)
    service.start()
    time.sleep(0.15)
    service.stop()

    assert len(shown) >= 1
    lines = shown[0]
    assert len(lines) == 4
    assert "Bisque" in lines[0]
    assert "Segment 1" == lines[1]
    assert "PV: 850" in lines[2]
    assert "SP: 900" in lines[2]
    assert "Elapsed: 45 min" == lines[3]


def test_program_detail_mode_idle() -> None:
    """KEY3 when not running → shows 'No program'."""
    state = ControllerState()
    bs = ButtonState()
    bs.press("program")

    service, shown = _make_capturing_service(state, bs)
    service.start()
    time.sleep(0.15)
    service.stop()

    assert len(shown) >= 1
    assert "No program" in shown[0][1]


def test_no_button_state_shows_compact() -> None:
    """Without ButtonState, display uses compact lines (backward compat)."""
    shown: list[list[str]] = []

    class CapturingDisplay:
        def show(self, lines: list[str]) -> None:
            shown.append(lines)

    state = ControllerState()
    service = DisplayService(state, lambda: 0, interval=0.05)
    service._display = CapturingDisplay()  # type: ignore[assignment]
    service.start()
    time.sleep(0.15)
    service.stop()

    assert len(shown) >= 1
    assert "D:" in shown[0][0]  # compact format


def test_get_uptime_returns_string() -> None:
    result = get_uptime()
    assert isinstance(result, str)
    assert len(result) > 0

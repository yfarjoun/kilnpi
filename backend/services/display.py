"""OLED display service — shows Raspberry Pi system info on SH1106 128x64.

Displays disk/memory health, CPU temp, IP address, WiFi and browser
connection status, and seconds since last Modbus poll.
Uses luma.oled on Raspberry Pi, falls back to a console-based mock on Mac.

Supports drill-down detail views triggered by HAT buttons (KEY1/KEY2/KEY3).
"""

import logging
import platform
import shutil
import subprocess
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from backend.modbus.registers import RunMode
from backend.services.buttons import ButtonState
from backend.services.poller import ControllerState

logger = logging.getLogger(__name__)


class MockDisplay:
    """Console-based mock for development without hardware."""

    def show(
        self,
        lines: list[str],
        reversed_lines: set[int] | None = None,
        bold_lines: set[int] | None = None,
    ) -> None:
        logger.debug("OLED: %s", " | ".join(lines))


class OledDisplay:
    """Real SH1106 OLED display via luma.oled (Waveshare 1.3" HAT, SPI)."""

    def __init__(self) -> None:
        from luma.core.interface.serial import spi  # type: ignore[import-untyped]
        from luma.oled.device import sh1106  # type: ignore[import-untyped]
        from PIL import ImageFont  # type: ignore[import-untyped]

        serial = spi(device=0, port=0, gpio_DC=24, gpio_RST=25)
        self._device = sh1106(serial)
        self._device.contrast(255)
        # Load regular and bold DejaVu Sans Mono (10px); fall back to default
        default = ImageFont.load_default()
        self._font = default
        self._font_bold = default
        font_dir = "/usr/share/fonts/truetype/dejavu"
        try:
            self._font = ImageFont.truetype(f"{font_dir}/DejaVuSansMono.ttf", 10)
        except OSError:
            pass
        try:
            self._font_bold = ImageFont.truetype(f"{font_dir}/DejaVuSansMono-Bold.ttf", 10)
        except OSError:
            self._font_bold = self._font  # fall back to regular

    def show(
        self,
        lines: list[str],
        reversed_lines: set[int] | None = None,
        bold_lines: set[int] | None = None,
    ) -> None:
        from luma.core.render import canvas  # type: ignore[import-untyped]

        with canvas(self._device) as draw:
            y = 0
            line_h = 14
            for i, line in enumerate(lines):
                font = self._font_bold if bold_lines and i in bold_lines else self._font
                if reversed_lines and i in reversed_lines:
                    # White background, black text for error emphasis
                    draw.rectangle([(0, y), (self._device.width, y + line_h)], fill="white")
                    draw.text((0, y), line, fill="black", font=font)
                else:
                    draw.text((0, y), line, fill="white", font=font)
                y += line_h


def _create_display() -> MockDisplay | OledDisplay:
    if platform.system() == "Darwin":
        return MockDisplay()
    # Retry a few times — the splash service may still be releasing SPI/GPIO
    for attempt in range(3):
        try:
            return OledDisplay()
        except Exception as exc:
            if attempt < 2:
                import time

                logger.info("OLED init attempt %d failed (%s), retrying...", attempt + 1, exc)
                time.sleep(1)
            else:
                logger.warning("Failed to init OLED after 3 attempts (%s), using mock display", exc)
                return MockDisplay()
    return MockDisplay()  # unreachable, keeps type checker happy


def create_display_and_splash() -> MockDisplay | OledDisplay:
    """Create display hardware and immediately show a splash screen.

    Call this early in app startup so the user sees feedback quickly.
    Pass the returned display to DisplayService via its `display` parameter.
    """
    display = _create_display()
    display.show(["", "    KilnPi", "", "    Starting..."])
    logger.info("Splash screen shown")
    return display


def get_disk_usage_pct() -> int:
    """Return disk usage percentage for the root filesystem."""
    try:
        usage = shutil.disk_usage("/")
        return int(usage.used * 100 / usage.total)
    except Exception:
        return 0


def get_memory_usage_pct() -> int:
    """Return memory usage percentage."""
    try:
        if platform.system() == "Darwin":
            # macOS: use vm_stat (rough approximation)
            result = subprocess.run(
                ["vm_stat"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            pages_free = 0
            pages_active = 0
            pages_spec = 0
            for line in result.stdout.splitlines():
                if "Pages free:" in line:
                    pages_free = int(line.split()[-1].rstrip("."))
                elif "Pages active:" in line:
                    pages_active = int(line.split()[-1].rstrip("."))
                elif "Pages speculative:" in line:
                    pages_spec = int(line.split()[-1].rstrip("."))
            total = pages_free + pages_active + pages_spec
            if total == 0:
                return 0
            return int(pages_active * 100 / total)
        else:
            # Linux: read /proc/meminfo
            mem: dict[str, int] = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        mem[parts[0].rstrip(":")] = int(parts[1])
            total = mem.get("MemTotal", 1)
            available = mem.get("MemAvailable", 0)
            return int((total - available) * 100 / total)
    except Exception:
        return 0


def get_cpu_temp() -> float:
    """Return CPU temperature in Celsius."""
    try:
        if platform.system() != "Darwin":
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return int(f.read().strip()) / 1000.0
        return 0.0
    except Exception:
        return 0.0


def get_ip_address() -> str:
    """Return the primary IP address."""
    try:
        if platform.system() == "Darwin":
            cmd = ["ipconfig", "getifaddr", "en0"]
        else:
            cmd = ["hostname", "-I"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3,
        )
        parts = result.stdout.strip().split()
        return parts[0] if parts else "--"
    except Exception:
        return "--"


def is_wifi_connected() -> bool:
    """Check if WiFi is connected."""
    try:
        if platform.system() == "Darwin":
            result = subprocess.run(
                [
                    "/System/Library/PrivateFrameworks"
                    "/Apple80211.framework"
                    "/Versions/Current/Resources/airport",
                    "-I",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            for line in result.stdout.splitlines():
                if "SSID:" in line and "AirPort" not in line:
                    return True
            return False
        else:
            result = subprocess.run(
                ["iwgetid", "-r"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            return bool(result.stdout.strip())
    except Exception:
        return False


def get_poll_age_sec(state: ControllerState) -> int:
    """Seconds since the last successful Modbus poll."""
    snap = state.snapshot()
    ts = snap.get("timestamp", "")
    if not ts:
        return -1
    try:
        last = datetime.fromisoformat(ts)
        age = (datetime.now(UTC) - last).total_seconds()
        return int(age)
    except Exception:
        return -1


def get_uptime() -> str:
    """Return human-readable uptime string (e.g. '3d 2h')."""
    try:
        if platform.system() != "Darwin":
            with open("/proc/uptime") as f:
                seconds = float(f.read().split()[0])
        else:
            result = subprocess.run(
                ["sysctl", "-n", "kern.boottime"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            # Output: "{ sec = 1234567890, usec = 0 } ..."
            import re

            m = re.search(r"sec\s*=\s*(\d+)", result.stdout)
            if m:
                import time

                seconds = time.time() - int(m.group(1))
            else:
                return "?"
    except Exception:
        return "?"

    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    if days > 0:
        return f"{days}d {hours}h"
    minutes = int((seconds % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


class DisplayService:
    """Background thread that updates the OLED display with Pi info."""

    def __init__(
        self,
        state: ControllerState,
        ws_client_count: Callable[[], int],
        interval: float = 5.0,
        button_state: ButtonState | None = None,
        display: MockDisplay | OledDisplay | None = None,
    ) -> None:
        self._state = state
        self._ws_client_count = ws_client_count
        self._interval = interval
        self._button_state = button_state
        self._display = display or _create_display()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="display",
        )
        self._thread.start()
        logger.info("Display service started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("Display service stopped")

    def _run(self) -> None:
        mode: str | None = None
        while not self._stop_event.is_set():
            try:
                mode = self._button_state.active_mode() if self._button_state else None
                reversed_lines: set[int] = set()  # inverse: error states
                bold_lines: set[int] = set()  # bold: variable/changing data
                if mode == "system":
                    lines = self._system_detail()
                elif mode == "network":
                    lines = self._network_detail()
                    # Inverse Modbus line on error
                    if not self._state.last_poll_ok:
                        reversed_lines.add(3)
                elif mode == "program":
                    lines = self._program_detail()
                    # Bold the live PV/SP line when program is active
                    if self._state.run_mode in (RunMode.RUNNING, RunMode.STANDBY):
                        bold_lines.add(2)
                else:
                    lines = self._compact_lines()
                    # Bold running program info (variable data)
                    if self._state.run_mode in (RunMode.RUNNING, RunMode.STANDBY):
                        bold_lines.add(3)
                    # Inverse connectivity line on Modbus error
                    if not self._state.last_poll_ok:
                        reversed_lines.add(1)
                self._display.show(
                    lines,
                    reversed_lines=reversed_lines or None,
                    bold_lines=bold_lines or None,
                )
            except Exception:
                logger.exception("Display update error")
            # Poll every 0.5s so button presses feel responsive,
            # but only redraw at the full interval when in compact mode.
            elapsed = 0.0
            while elapsed < self._interval and not self._stop_event.is_set():
                self._stop_event.wait(0.5)
                elapsed += 0.5
                if self._button_state and self._button_state.active_mode() != mode:
                    break  # button state changed, redraw now

    def _compact_lines(self) -> list[str]:
        """Default 4-line compact view."""
        disk = get_disk_usage_pct()
        mem = get_memory_usage_pct()
        cpu = get_cpu_temp()

        ip = get_ip_address()
        # Show only last octet to save space (e.g. ".105")
        ip_short = "." + ip.rsplit(".", 1)[-1] if "." in ip else ip
        wifi = "W+" if is_wifi_connected() else "W-"
        browsers = self._ws_client_count()
        browser = "B+" if browsers > 0 else "B-"

        poll_age = get_poll_age_sec(self._state)
        modbus = "MB+" if self._state.last_poll_ok else "MB-"
        if poll_age < 0:
            poll_str = "Poll: --"
        else:
            poll_str = f"Poll: {poll_age}s ago"

        # Line 4: running/paused program info or "Idle"
        if self._state.run_mode in (RunMode.RUNNING, RunMode.STANDBY):
            name = self._state.active_program_name or "Program"
            seg = self._state.segment
            pv = self._state.pv
            snap = self._state.snapshot()
            sp = snap.get("program_target_temp") or self._state.sp
            paused = "||" if self._state.run_mode == RunMode.STANDBY else ""
            suffix = f"S{seg} {pv:.0f}/{sp:.0f}{paused}"
            max_name = 21 - len(suffix) - 1
            if len(name) > max_name:
                name = name[:max_name]
            line4 = f"{name} {suffix}"
        else:
            line4 = "Idle"

        return [
            f"D:{disk}% M:{mem}% CPU:{cpu:.0f}C",
            f"{ip_short} {wifi} {browser} {modbus}",
            poll_str,
            line4,
        ]

    def _system_detail(self) -> list[str]:
        """Expanded system info: disk, memory, CPU temp, uptime."""
        return [
            f"Disk: {get_disk_usage_pct()}% used",
            f"Memory: {get_memory_usage_pct()}% used",
            f"CPU: {get_cpu_temp():.1f}\u00b0C",
            f"Uptime: {get_uptime()}",
        ]

    def _network_detail(self) -> list[str]:
        """Expanded network info: IP, WiFi, browsers, Modbus."""
        wifi_str = "Connected" if is_wifi_connected() else "Disconnected"
        browsers = self._ws_client_count()
        poll_age = get_poll_age_sec(self._state)
        if not self._state.last_poll_ok:
            modbus_str = "Error"
        elif poll_age < 0:
            modbus_str = "No data"
        else:
            modbus_str = f"OK ({poll_age}s ago)"
        return [
            f"IP: {get_ip_address()}",
            f"WiFi: {wifi_str}",
            f"Browsers: {browsers}",
            f"Modbus: {modbus_str}",
        ]

    def _program_detail(self) -> list[str]:
        """Expanded program info: name, segment, PV/SP, elapsed."""
        if self._state.run_mode not in (RunMode.RUNNING, RunMode.STANDBY):
            return ["Prog: --", "No program", "running", ""]
        name = self._state.active_program_name or "Unknown"
        seg = self._state.segment
        pv = self._state.pv
        snap = self._state.snapshot()
        sp = snap.get("program_target_temp") or self._state.sp
        elapsed = self._state.segment_elapsed_min
        status = "PAUSED" if self._state.run_mode == RunMode.STANDBY else ""
        return [
            f"Prog: {name} {status}".strip(),
            f"Segment {seg}",
            f"PV: {pv:.0f} SP: {sp:.0f}",
            f"Elapsed: {elapsed} min",
        ]

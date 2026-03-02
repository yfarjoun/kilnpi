"""OLED display service — shows Raspberry Pi system info on SSD1306 128x64.

Displays disk/memory health, CPU temp, IP address, WiFi and browser
connection status, and seconds since last Modbus poll.
Uses luma.oled on Raspberry Pi, falls back to a console-based mock on Mac.
"""

import logging
import platform
import shutil
import subprocess
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from backend.services.poller import ControllerState

logger = logging.getLogger(__name__)


class MockDisplay:
    """Console-based mock for development without hardware."""

    def show(self, lines: list[str]) -> None:
        logger.debug("OLED: %s", " | ".join(lines))


class OledDisplay:
    """Real SSD1306 OLED display via luma.oled."""

    def __init__(self) -> None:
        from luma.core.interface.serial import i2c  # type: ignore[import-untyped]
        from luma.oled.device import ssd1306  # type: ignore[import-untyped]
        from PIL import ImageFont  # type: ignore[import-untyped]

        serial = i2c(port=1, address=0x3C)
        self._device = ssd1306(serial)
        self._font = ImageFont.load_default()

    def show(self, lines: list[str]) -> None:
        from PIL import Image, ImageDraw  # type: ignore[import-untyped]

        image = Image.new("1", (self._device.width, self._device.height), "black")
        draw = ImageDraw.Draw(image)
        y = 0
        for line in lines:
            draw.text((0, y), line, fill="white", font=self._font)
            y += 14
        self._device.display(image)


def _create_display() -> MockDisplay | OledDisplay:
    if platform.system() == "Darwin":
        return MockDisplay()
    try:
        return OledDisplay()
    except Exception:
        logger.warning("Failed to init OLED, using mock display")
        return MockDisplay()


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


class DisplayService:
    """Background thread that updates the OLED display with Pi info."""

    def __init__(
        self,
        state: ControllerState,
        ws_client_count: Callable[[], int],
        interval: float = 5.0,
    ) -> None:
        self._state = state
        self._ws_client_count = ws_client_count
        self._interval = interval
        self._display = _create_display()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="display",
        )
        self._thread.start()
        logger.info("Display service started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("Display service stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                disk = get_disk_usage_pct()
                mem = get_memory_usage_pct()
                cpu = get_cpu_temp()

                ip = get_ip_address()
                wifi = "W+" if is_wifi_connected() else "W-"
                browsers = self._ws_client_count()
                browser = "B+" if browsers > 0 else "B-"

                poll_age = get_poll_age_sec(self._state)
                if poll_age < 0:
                    poll_str = "Poll: --"
                else:
                    poll_str = f"Poll: {poll_age}s ago"

                lines = [
                    f"D:{disk}% M:{mem}% CPU:{cpu:.0f}C",
                    f"{ip} {wifi} {browser}",
                    poll_str,
                ]
                self._display.show(lines)
            except Exception:
                logger.exception("Display update error")
            self._stop_event.wait(self._interval)

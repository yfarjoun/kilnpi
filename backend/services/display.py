"""OLED display service — shows Raspberry Pi system info on SSD1306 128x64.

Displays WiFi SSID/signal, CPU temperature, IP address, and uptime.
Uses luma.oled on Raspberry Pi, falls back to a console-based mock on Mac.
"""

import logging
import platform
import re
import subprocess
import threading
import time

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


def get_wifi_info() -> tuple[str, int]:
    """Return (SSID, signal_percent). Falls back to ('--', 0) on error."""
    system = platform.system()
    try:
        if system == "Darwin":
            # macOS: use airport command
            result = subprocess.run(
                [
                    "/System/Library/PrivateFrameworks/Apple80211.framework"
                    "/Versions/Current/Resources/airport",
                    "-I",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            ssid = "--"
            rssi = -100
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("SSID:"):
                    ssid = line.split(":", 1)[1].strip()
                elif line.startswith("agrCtlRSSI:"):
                    rssi = int(line.split(":", 1)[1].strip())
            # Convert RSSI to percentage (rough: -30=100%, -90=0%)
            signal = max(0, min(100, (rssi + 90) * 100 // 60))
            return ssid, signal
        else:
            # Linux (Raspberry Pi)
            result = subprocess.run(
                ["iwgetid", "-r"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            ssid = result.stdout.strip() or "--"
            # Get signal strength
            result2 = subprocess.run(
                ["iwconfig", "wlan0"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            signal = 0
            match = re.search(r"Signal level=(-?\d+)", result2.stdout)
            if match:
                rssi = int(match.group(1))
                signal = max(0, min(100, (rssi + 90) * 100 // 60))
            return ssid, signal
    except Exception:
        return "--", 0


def get_cpu_temp() -> float:
    """Return CPU temperature in Celsius. Falls back to 0.0 on error."""
    system = platform.system()
    try:
        if system == "Darwin":
            # macOS doesn't have a simple CPU temp file; return 0
            return 0.0
        else:
            # Linux: read from thermal zone
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return int(f.read().strip()) / 1000.0
    except Exception:
        return 0.0


def get_ip_address() -> str:
    """Return the primary IP address. Falls back to '--' on error."""
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
        ip = result.stdout.strip().split()[0] if result.stdout.strip() else "--"
        return ip
    except Exception:
        return "--"


def get_uptime() -> str:
    """Return uptime as a short human-readable string."""
    try:
        secs = time.monotonic()
        # Use process uptime as a proxy (close enough for Pi that starts at boot)
        if platform.system() != "Darwin":
            with open("/proc/uptime") as f:
                secs = float(f.read().split()[0])
        hours = int(secs) // 3600
        minutes = (int(secs) % 3600) // 60
        if hours >= 24:
            days = hours // 24
            hours = hours % 24
            return f"{days}d {hours}h"
        return f"{hours}h {minutes}m"
    except Exception:
        return "--"


class DisplayService:
    """Background thread that updates the OLED display with Pi system info."""

    def __init__(self, interval: float = 5.0) -> None:
        self._interval = interval
        self._display = _create_display()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="display")
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
                ssid, signal = get_wifi_info()
                cpu_temp = get_cpu_temp()
                ip = get_ip_address()
                uptime = get_uptime()

                lines = [
                    f"WiFi: {ssid[:10]}",
                    f"Sig: {signal}%  CPU: {cpu_temp:.0f}C",
                    f"IP: {ip}",
                    f"Up: {uptime}",
                ]
                self._display.show(lines)
            except Exception:
                logger.exception("Display update error")
            self._stop_event.wait(self._interval)

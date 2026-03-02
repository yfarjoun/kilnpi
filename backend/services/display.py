"""OLED display service — shows status on SSD1306 128x64 display.

Uses luma.oled on Raspberry Pi, falls back to a console-based mock on Mac.
"""

import logging
import platform
import threading

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
        from PIL import Image, ImageDraw, ImageFont  # type: ignore[import-untyped]

        serial = i2c(port=1, address=0x3C)
        self._device = ssd1306(serial)
        self._font = ImageFont.load_default()
        self._Image = Image
        self._ImageDraw = ImageDraw

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


class DisplayService:
    """Background thread that updates the OLED display with controller state."""

    def __init__(self, state: ControllerState, interval: float = 2.0) -> None:
        self._state = state
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
                snap = self._state.snapshot()
                lines = [
                    f"PV: {snap['pv']:.1f}C  SP: {snap['sp']:.1f}C",
                    f"Output: {snap['mv']:.1f}%",
                    f"Mode: {snap['run_mode']}",
                    f"Seg: {snap['segment']}  T: {snap['segment_elapsed_min']}m",
                ]
                self._display.show(lines)
            except Exception:
                logger.exception("Display update error")
            self._stop_event.wait(self._interval)

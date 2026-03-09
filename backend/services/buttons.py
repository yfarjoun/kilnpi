"""Button service — GPIO listener for Waveshare 1.3" OLED HAT buttons.

KEY1 (GPIO 21) → system detail
KEY2 (GPIO 20) → network detail
KEY3 (GPIO 16) → program detail

Press toggles the detail view; auto-reverts after 10 seconds.
Uses gpiozero (chardev interface) which works on modern Pi OS (Debian 13+).
"""

import logging
import platform
import threading
import time

logger = logging.getLogger(__name__)

DETAIL_TIMEOUT = 10.0  # seconds before reverting to default display

# GPIO pin → detail mode mapping
BUTTON_MAP: dict[int, str] = {
    21: "system",
    20: "network",
    16: "program",
}


class ButtonState:
    """Thread-safe shared state between button callbacks and display thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._detail_mode: str | None = None
        self._detail_until: float = 0.0

    def press(self, mode: str) -> None:
        """Toggle detail mode. If already showing this mode, revert to default."""
        with self._lock:
            if self._detail_mode == mode and time.monotonic() < self._detail_until:
                # Already showing this mode → toggle off
                self._detail_mode = None
                self._detail_until = 0.0
            else:
                self._detail_mode = mode
                self._detail_until = time.monotonic() + DETAIL_TIMEOUT

    def active_mode(self) -> str | None:
        """Return current detail mode, or None if expired/inactive."""
        with self._lock:
            if self._detail_mode is not None and time.monotonic() < self._detail_until:
                return self._detail_mode
            return None


class ButtonService:
    """Background GPIO listener using gpiozero (works on modern Pi OS)."""

    def __init__(self, button_state: ButtonState) -> None:
        self._button_state = button_state
        self._buttons: list[object] = []

    def start(self) -> None:
        try:
            from gpiozero import Button  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("gpiozero not available, buttons disabled")
            return

        try:
            for pin, mode in BUTTON_MAP.items():
                btn = Button(pin, pull_up=True, bounce_time=0.05)
                btn.when_pressed = self._make_callback(mode)
                self._buttons.append(btn)
            logger.info("Button service started (pins: %s)", list(BUTTON_MAP.keys()))
        except Exception:
            logger.warning("GPIO button setup failed — buttons disabled", exc_info=True)
            self._buttons = []

    def stop(self) -> None:
        for btn in self._buttons:
            btn.close()  # type: ignore[attr-defined]
        if self._buttons:
            logger.info("Button service stopped")
        self._buttons = []

    def _make_callback(self, mode: str):  # type: ignore[no-untyped-def]
        def _cb() -> None:
            logger.debug("Button press: %s", mode)
            self._button_state.press(mode)
        return _cb


class MockButtonService:
    """No-op button service for development on Mac."""

    def __init__(self, button_state: ButtonState) -> None:  # noqa: ARG002
        pass

    def start(self) -> None:
        logger.debug("Mock button service (no-op)")

    def stop(self) -> None:
        pass


def create_button_service(button_state: ButtonState) -> ButtonService | MockButtonService:
    """Factory: real GPIO on Linux/Pi, mock on Mac."""
    if platform.system() == "Darwin":
        return MockButtonService(button_state)
    try:
        import gpiozero  # type: ignore[import-untyped]  # noqa: F401
        return ButtonService(button_state)
    except ImportError:
        logger.warning("gpiozero not available, using mock button service")
        return MockButtonService(button_state)

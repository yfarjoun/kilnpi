"""Application configuration with auto-detection of mock vs real mode."""

import os
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _detect_serial_port() -> str | None:
    """Try to find a USB-RS485 adapter."""
    candidates = ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0"]
    for port in candidates:
        if Path(port).exists():
            return port
    return None


def _is_mock_mode() -> bool:
    if os.environ.get("MOCK_CONTROLLER", "").strip() in ("1", "true", "yes"):
        return True
    if "--mock" in sys.argv:
        return True
    # Auto-detect: no serial port available → mock mode
    if platform.system() == "Darwin":
        return True
    return _detect_serial_port() is None


@dataclass
class Settings:
    # Modbus
    serial_port: str = field(default_factory=lambda: _detect_serial_port() or "/dev/ttyUSB0")
    baud_rate: int = 9600
    slave_address: int = 1
    min_request_interval_ms: int = 300

    # Database
    db_path: str = field(
        default_factory=lambda: os.environ.get(
            "DB_PATH",
            str(Path(__file__).parent.parent / "data" / "kiln.db"),
        )
    )

    # Polling
    poll_interval_sec: float = 2.0

    # Mode
    mock_mode: bool = field(default_factory=_is_mock_mode)

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"


settings = Settings()

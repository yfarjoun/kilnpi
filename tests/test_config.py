"""Tests for configuration module."""

from backend.config import Settings, settings


def test_settings_defaults() -> None:
    assert settings.baud_rate == 9600
    assert settings.slave_address == 1
    assert settings.poll_interval_sec == 2.0
    assert settings.mock_mode is True  # Running on Mac


def test_settings_db_url() -> None:
    s = Settings(db_path="/tmp/test.db")
    assert s.db_url == "sqlite+aiosqlite:////tmp/test.db"


def test_settings_mock_from_env() -> None:
    # settings.mock_mode should be True since we set MOCK_CONTROLLER=1 in conftest
    assert settings.mock_mode is True

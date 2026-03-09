"""Tests for ButtonState toggle and timeout logic."""

import time

from backend.services.buttons import ButtonState, MockButtonService


def test_initial_state_is_none() -> None:
    bs = ButtonState()
    assert bs.active_mode() is None


def test_press_activates_mode() -> None:
    bs = ButtonState()
    bs.press("system")
    assert bs.active_mode() == "system"


def test_press_same_mode_toggles_off() -> None:
    bs = ButtonState()
    bs.press("system")
    assert bs.active_mode() == "system"
    bs.press("system")
    assert bs.active_mode() is None


def test_press_different_mode_switches() -> None:
    bs = ButtonState()
    bs.press("system")
    assert bs.active_mode() == "system"
    bs.press("network")
    assert bs.active_mode() == "network"


def test_timeout_expires() -> None:
    bs = ButtonState()
    bs.press("system")
    # Manually expire the deadline
    bs._detail_until = time.monotonic() - 1.0
    assert bs.active_mode() is None


def test_toggle_off_then_press_again() -> None:
    bs = ButtonState()
    bs.press("program")
    bs.press("program")  # toggle off
    assert bs.active_mode() is None
    bs.press("program")  # press again → on
    assert bs.active_mode() == "program"


def test_mock_button_service_is_noop() -> None:
    bs = ButtonState()
    mock = MockButtonService(bs)
    mock.start()  # should not raise
    mock.stop()

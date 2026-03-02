"""Tests for register definitions."""

from backend.modbus.registers import (
    MAX_SEGMENTS,
    MV,
    PV,
    RUN,
    SP,
    RunMode,
    segment_ramp_addr,
    segment_soak_addr,
    segment_temp_addr,
)


def test_status_register_addresses() -> None:
    assert PV.address == 0x1001
    assert MV.address == 0x1101
    assert PV.has_decimal is True
    assert MV.has_decimal is False


def test_sp_register() -> None:
    assert SP.address == 0x0000
    assert SP.writable is True
    assert SP.has_decimal is True


def test_run_register() -> None:
    assert RUN.address == 0x001D
    assert RUN.writable is True


def test_run_mode_enum() -> None:
    assert RunMode.OFF == 0
    assert RunMode.RUNNING == 3
    assert RunMode(3) == RunMode.RUNNING


def test_segment_addresses() -> None:
    assert segment_ramp_addr(1) == 0x20
    assert segment_soak_addr(1) == 0x21
    assert segment_temp_addr(1) == 0x22

    assert segment_ramp_addr(2) == 0x23
    assert segment_soak_addr(2) == 0x24
    assert segment_temp_addr(2) == 0x25

    assert segment_ramp_addr(32) == 0x7D
    assert segment_soak_addr(32) == 0x7E
    assert segment_temp_addr(32) == 0x7F


def test_max_segments() -> None:
    assert MAX_SEGMENTS == 32

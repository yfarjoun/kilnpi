"""Tests for the PZEM-016 Modbus driver (backend/modbus/pzem.py)."""

import dataclasses
from unittest.mock import MagicMock, patch

import pytest

from backend.modbus.pzem import PzemReading, PzemReader, set_pzem_address


# ---------------------------------------------------------------------------
# PzemReading dataclass
# ---------------------------------------------------------------------------


def test_pzem_reading_stores_fields() -> None:
    reading = PzemReading(
        voltage=230.5,
        current=3.141,
        power=722.8,
        energy=12345,
        frequency=50.0,
        power_factor=0.98,
        alarm=False,
    )
    assert reading.voltage == 230.5
    assert reading.current == 3.141
    assert reading.power == 722.8
    assert reading.energy == 12345
    assert reading.frequency == 50.0
    assert reading.power_factor == 0.98
    assert reading.alarm is False


def test_pzem_reading_alarm_true() -> None:
    reading = PzemReading(
        voltage=0.0, current=0.0, power=0.0, energy=0,
        frequency=0.0, power_factor=0.0, alarm=True,
    )
    assert reading.alarm is True


def test_pzem_reading_is_frozen() -> None:
    """PzemReading must be immutable (frozen dataclass)."""
    reading = PzemReading(
        voltage=230.5, current=1.0, power=230.5, energy=100,
        frequency=50.0, power_factor=1.0, alarm=False,
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        reading.voltage = 999.9  # type: ignore[misc]


def test_pzem_reading_is_dataclass() -> None:
    assert dataclasses.is_dataclass(PzemReading)


# ---------------------------------------------------------------------------
# PzemReader.read() – unit tests with mocked serial/instrument
# ---------------------------------------------------------------------------


def _make_raw_regs(
    voltage_raw: int = 2305,   # 230.5 V
    current_low: int = 3141,   # 3.141 A (low 16)
    current_high: int = 0,
    power_low: int = 7228,     # 722.8 W (low 16)
    power_high: int = 0,
    energy_low: int = 12345,   # 12345 Wh (low 16)
    energy_high: int = 0,
    frequency_raw: int = 500,  # 50.0 Hz
    pf_raw: int = 98,          # 0.98
    alarm_raw: int = 0,        # off
) -> list[int]:
    return [
        voltage_raw,
        current_low,
        current_high,
        power_low,
        power_high,
        energy_low,
        energy_high,
        frequency_raw,
        pf_raw,
        alarm_raw,
    ]


def _make_reader_with_mock_instrument(regs: list[int]) -> tuple[PzemReader, MagicMock]:
    """Return a PzemReader whose internal instrument is replaced by a MagicMock."""
    with patch("backend.modbus.pzem.minimalmodbus.Instrument") as MockInstrument:
        mock_instrument = MagicMock()
        mock_instrument.serial = MagicMock()
        MockInstrument.return_value = mock_instrument
        reader = PzemReader(port="/dev/ttyUSB0", address=1, baud_rate=9600)

    mock_instrument.read_registers.return_value = regs
    return reader, mock_instrument


def test_read_parses_voltage() -> None:
    reader, mock_instr = _make_reader_with_mock_instrument(_make_raw_regs(voltage_raw=2305))
    reading = reader.read()
    assert abs(reading.voltage - 230.5) < 1e-6


def test_read_parses_current_low_only() -> None:
    reader, mock_instr = _make_reader_with_mock_instrument(
        _make_raw_regs(current_low=3141, current_high=0)
    )
    reading = reader.read()
    assert abs(reading.current - 3.141) < 1e-6


def test_read_parses_current_with_high_word() -> None:
    # 65536 + 1 = 65537 raw → 65.537 A
    reader, mock_instr = _make_reader_with_mock_instrument(
        _make_raw_regs(current_low=1, current_high=1)
    )
    reading = reader.read()
    assert abs(reading.current - 65.537) < 1e-6


def test_read_parses_power() -> None:
    reader, mock_instr = _make_reader_with_mock_instrument(
        _make_raw_regs(power_low=7228, power_high=0)
    )
    reading = reader.read()
    assert abs(reading.power - 722.8) < 1e-6


def test_read_parses_energy() -> None:
    reader, mock_instr = _make_reader_with_mock_instrument(
        _make_raw_regs(energy_low=12345, energy_high=0)
    )
    reading = reader.read()
    assert reading.energy == 12345


def test_read_parses_energy_with_high_word() -> None:
    reader, mock_instr = _make_reader_with_mock_instrument(
        _make_raw_regs(energy_low=0, energy_high=1)
    )
    reading = reader.read()
    assert reading.energy == 65536


def test_read_parses_frequency() -> None:
    reader, mock_instr = _make_reader_with_mock_instrument(
        _make_raw_regs(frequency_raw=500)
    )
    reading = reader.read()
    assert abs(reading.frequency - 50.0) < 1e-6


def test_read_parses_power_factor() -> None:
    reader, mock_instr = _make_reader_with_mock_instrument(_make_raw_regs(pf_raw=98))
    reading = reader.read()
    assert abs(reading.power_factor - 0.98) < 1e-6


def test_read_alarm_off() -> None:
    reader, mock_instr = _make_reader_with_mock_instrument(_make_raw_regs(alarm_raw=0))
    reading = reader.read()
    assert reading.alarm is False


def test_read_alarm_on() -> None:
    reader, mock_instr = _make_reader_with_mock_instrument(_make_raw_regs(alarm_raw=0xFFFF))
    reading = reader.read()
    assert reading.alarm is True


def test_read_uses_fc4() -> None:
    """read() must call read_registers with functioncode=4."""
    reader, mock_instr = _make_reader_with_mock_instrument(_make_raw_regs())
    reader.read()
    mock_instr.read_registers.assert_called_once_with(0x0000, 10, functioncode=4)


def test_read_returns_frozen_pzem_reading() -> None:
    reader, _ = _make_reader_with_mock_instrument(_make_raw_regs())
    reading = reader.read()
    assert isinstance(reading, PzemReading)
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        reading.voltage = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# set_pzem_address
# ---------------------------------------------------------------------------


def test_set_pzem_address_uses_fc6() -> None:
    with patch("backend.modbus.pzem.minimalmodbus.Instrument") as MockInstrument:
        mock_instr = MagicMock()
        mock_instr.serial = MagicMock()
        MockInstrument.return_value = mock_instr

        set_pzem_address("/dev/ttyUSB0", current_address=1, new_address=2)

        mock_instr.write_register.assert_called_once_with(0x0002, 2, functioncode=6)


def test_set_pzem_address_rejects_invalid_address() -> None:
    with pytest.raises(ValueError):
        set_pzem_address("/dev/ttyUSB0", current_address=1, new_address=0)

    with pytest.raises(ValueError):
        set_pzem_address("/dev/ttyUSB0", current_address=1, new_address=248)

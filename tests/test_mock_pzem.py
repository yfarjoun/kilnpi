"""Tests for MockPzemReader (backend/modbus/mock_pzem.py)."""

from backend.modbus.mock_pzem import MockPzemReader
from backend.modbus.pzem import PzemReading


def test_mock_pzem_zero_mv() -> None:
    """With MV=0, current should be near zero (< 2 A) across many reads."""
    reader = MockPzemReader(label="L1")
    reader.set_mv(0.0)

    readings = [reader.read() for _ in range(20)]
    for r in readings:
        assert isinstance(r, PzemReading)
        assert r.current < 2.0, f"Expected current < 2A at MV=0, got {r.current:.3f}A"
        assert r.alarm is False
        assert r.energy == 0


def test_mock_pzem_full_mv() -> None:
    """With MV=100, current should exceed 15 A and power should exceed 1000 W."""
    reader = MockPzemReader(label="L1")
    reader.set_mv(100.0)

    readings = [reader.read() for _ in range(20)]
    for r in readings:
        assert isinstance(r, PzemReading)
        assert r.current > 15.0, f"Expected current > 15A at MV=100, got {r.current:.3f}A"
        assert r.power > 1000.0, f"Expected power > 1000W at MV=100, got {r.power:.1f}W"
        assert r.alarm is False
        assert r.energy == 0


def test_mock_pzem_power_proportional() -> None:
    """Higher MV should produce higher average power (averaged to smooth noise)."""
    n_reads = 30
    reader = MockPzemReader(label="L2")

    reader.set_mv(25.0)
    avg_power_25 = sum(reader.read().power for _ in range(n_reads)) / n_reads

    reader.set_mv(75.0)
    avg_power_75 = sum(reader.read().power for _ in range(n_reads)) / n_reads

    assert avg_power_75 > avg_power_25, (
        f"Expected power at MV=75 ({avg_power_75:.1f}W) > power at MV=25 ({avg_power_25:.1f}W)"
    )

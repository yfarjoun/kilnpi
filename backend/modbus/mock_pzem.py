"""Mock PZEM-016 reader for development on macOS (no hardware required)."""

import random

from backend.modbus.pzem import PzemReading

# Nominal electrical parameters
_NOMINAL_VOLTAGE = 110.0   # V (North American single-phase)
_FULL_POWER_CURRENT = 24.0  # A per leg at 100% MV
_NOMINAL_FREQUENCY = 60.0   # Hz
_NOMINAL_PF = 0.98          # power factor when current is flowing

# Noise levels (1-sigma)
_CURRENT_NOISE = 0.2   # A
_VOLTAGE_NOISE = 1.0   # V
_FREQUENCY_NOISE = 0.05  # Hz
_PF_NOISE = 0.005


class MockPzemReader:
    """Simulates a PZEM-016 power meter with current proportional to kiln MV."""

    def __init__(self, label: str) -> None:
        self.label = label
        self._mv: float = 0.0

    def set_mv(self, mv: float) -> None:
        """Update the reference MV (0–100%) from the kiln controller state."""
        self._mv = max(0.0, min(100.0, mv))

    def read(self) -> PzemReading:
        """Return a simulated PzemReading based on the current MV setting."""
        fraction = self._mv / 100.0

        current = fraction * _FULL_POWER_CURRENT + random.gauss(0, _CURRENT_NOISE)
        current = max(0.0, current)

        voltage = _NOMINAL_VOLTAGE + random.gauss(0, _VOLTAGE_NOISE)
        frequency = _NOMINAL_FREQUENCY + random.gauss(0, _FREQUENCY_NOISE)

        if current > 0.1:
            power_factor = _NOMINAL_PF + random.gauss(0, _PF_NOISE)
            power_factor = max(0.0, min(1.0, power_factor))
        else:
            power_factor = 1.0

        power = voltage * current * power_factor

        return PzemReading(
            voltage=voltage,
            current=current,
            power=power,
            energy=0,
            frequency=frequency,
            power_factor=power_factor,
            alarm=False,
        )

    def reconnect(self) -> None:
        """No-op: mock reader has no real connection."""

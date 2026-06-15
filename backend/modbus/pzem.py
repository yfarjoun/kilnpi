"""PZEM-016 Modbus RTU driver for power monitoring."""

import logging
import threading
import time
from dataclasses import dataclass

import minimalmodbus  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Input register addresses (FC=0x04)
_REG_VOLTAGE = 0x0000
_NUM_INPUT_REGS = 10  # 0x0000 through 0x0009

# Holding register addresses (FC=0x03)
_REG_ALARM_THRESHOLD = 0x0001
_REG_SLAVE_ADDRESS = 0x0002


@dataclass(frozen=True)
class PzemReading:
    """A single snapshot of PZEM-016 measurements."""

    voltage: float        # V
    current: float        # A
    power: float          # W
    energy: int           # Wh
    frequency: float      # Hz
    power_factor: float   # dimensionless (0.00–1.00)
    alarm: bool           # True if high-power alarm is active


class PzemReader:
    """Communicates with a PZEM-016 via RS485/Modbus RTU."""

    def __init__(self, port: str, address: int = 1, baud_rate: int = 9600) -> None:
        self._port = port
        self._address = address
        self._baud_rate = baud_rate
        self._min_interval = 0.3  # 300 ms between requests
        self._last_request_time = 0.0
        self._lock = threading.Lock()
        self._instrument: minimalmodbus.Instrument | None = None
        # Try eagerly so the happy path logs success at startup, but never
        # crash here: if the FTDI is unplugged at boot, _ensure_open() will
        # retry on first read. Otherwise the whole kilnpi service goes down
        # along with the OLED app and web UI.
        try:
            self._instrument = self._make_instrument()
            logger.info("PZEM-016 opened on %s (addr %d)", self._port, self._address)
        except Exception as e:
            logger.warning(
                "PZEM-016 port %s unavailable at startup (%s); will retry on first read",
                self._port,
                e,
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _make_instrument(self) -> minimalmodbus.Instrument:
        instrument = minimalmodbus.Instrument(self._port, self._address)
        ser = instrument.serial
        assert ser is not None  # minimalmodbus opens the port in __init__
        ser.baudrate = self._baud_rate
        ser.bytesize = 8
        ser.parity = minimalmodbus.serial.PARITY_NONE
        ser.stopbits = 1
        ser.timeout = 1.0
        return instrument

    def _ensure_open(self) -> minimalmodbus.Instrument:
        """Return the open instrument, opening it lazily if needed. Raises if it can't open."""
        if self._instrument is None:
            self._instrument = self._make_instrument()
        return self._instrument

    def _throttle(self) -> None:
        """Ensure at least 300 ms between successive Modbus requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reconnect(self) -> None:
        """Close any stale serial connection and re-open the Modbus instrument."""
        with self._lock:
            if self._instrument is not None:
                ser = self._instrument.serial
                if ser is not None:
                    try:
                        ser.close()
                    except Exception:
                        pass
                self._instrument = None
            self._instrument = self._make_instrument()  # raises if hardware still absent
            logger.info("Reconnected PZEM-016 instrument on %s (addr %d)", self._port, self._address)

    def read(self) -> PzemReading:
        """Read all 10 input registers in a single FC=4 call and return a PzemReading."""
        with self._lock:
            inst = self._ensure_open()
            self._throttle()
            regs = inst.read_registers(_REG_VOLTAGE, _NUM_INPUT_REGS, functioncode=4)

        # Parse raw register values according to the PZEM-016 register map.
        voltage = regs[0] * 0.1                                        # ×0.1 V
        current = (regs[1] | (regs[2] << 16)) * 0.001                  # low+high ×0.001 A
        power = (regs[3] | (regs[4] << 16)) * 0.1                      # low+high ×0.1 W
        energy = regs[5] | (regs[6] << 16)                             # low+high ×1 Wh
        frequency = regs[7] * 0.1                                       # ×0.1 Hz
        power_factor = regs[8] * 0.01                                   # ×0.01
        alarm = regs[9] == 0xFFFF                                       # 0=off, 0xFFFF=on

        return PzemReading(
            voltage=voltage,
            current=current,
            power=power,
            energy=energy,
            frequency=frequency,
            power_factor=power_factor,
            alarm=alarm,
        )


def set_pzem_address(
    port: str,
    current_address: int,
    new_address: int,
    baud_rate: int = 9600,
) -> None:
    """Write a new Modbus slave address to the PZEM-016's holding register 0x0002 (FC=6).

    The device will begin responding at *new_address* after the write.
    Valid addresses are 1–247.
    """
    if not (1 <= new_address <= 247):
        raise ValueError(f"new_address must be 1–247, got {new_address}")

    instrument = minimalmodbus.Instrument(port, current_address)
    ser = instrument.serial
    assert ser is not None  # minimalmodbus opens the port in __init__
    ser.baudrate = baud_rate
    ser.bytesize = 8
    ser.parity = minimalmodbus.serial.PARITY_NONE
    ser.stopbits = 1
    ser.timeout = 1.0

    instrument.write_register(_REG_SLAVE_ADDRESS, new_address, functioncode=6)
    logger.info(
        "PZEM-016 on %s: changed slave address %d → %d",
        port,
        current_address,
        new_address,
    )

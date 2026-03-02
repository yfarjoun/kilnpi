"""Real Modbus RTU controller using minimalmodbus."""

import logging
import time

import minimalmodbus  # type: ignore[import-untyped]

from backend.dto import PIDParams, Segment
from backend.modbus import registers
from backend.modbus.registers import RunMode

logger = logging.getLogger(__name__)


class RealController:
    """Communicates with the Thermomart PID-RS controller via RS485/Modbus RTU."""

    def __init__(self, port: str, slave_address: int = 1, baud_rate: int = 9600) -> None:
        self._instrument = minimalmodbus.Instrument(port, slave_address)
        self._instrument.serial.baudrate = baud_rate
        self._instrument.serial.bytesize = 8
        self._instrument.serial.parity = minimalmodbus.serial.PARITY_NONE
        self._instrument.serial.stopbits = 1
        self._instrument.serial.timeout = 1.0
        self._min_interval = 0.3  # 300ms between requests
        self._last_request_time = 0.0

    def _throttle(self) -> None:
        """Ensure minimum interval between Modbus requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _read_reg(self, reg: registers.Register) -> int | float:
        self._throttle()
        decimals = 1 if reg.has_decimal else 0
        result: int | float = self._instrument.read_register(
            reg.address, number_of_decimals=decimals, signed=True
        )
        return result

    def _write_reg(self, reg: registers.Register, value: int | float) -> None:
        self._throttle()
        decimals = 1 if reg.has_decimal else 0
        self._instrument.write_register(
            reg.address, value, number_of_decimals=decimals, signed=True
        )

    def read_pv(self) -> float:
        return float(self._read_reg(registers.PV))

    def read_sp(self) -> float:
        return float(self._read_reg(registers.SP))

    def read_mv(self) -> float:
        raw = int(self._read_reg(registers.MV))
        return raw / 2.0  # 0-200 → 0-100%

    def write_sp(self, value: float) -> None:
        self._write_reg(registers.SP, value)

    def read_pid(self) -> PIDParams:
        return PIDParams(
            p=int(self._read_reg(registers.P)),
            i=int(self._read_reg(registers.INT)),
            d=int(self._read_reg(registers.D)),
            cycle_time=int(self._read_reg(registers.T)),
        )

    def write_pid(self, params: PIDParams) -> None:
        self._write_reg(registers.P, params.p)
        self._write_reg(registers.INT, params.i)
        self._write_reg(registers.D, params.d)
        self._write_reg(registers.T, params.cycle_time)

    def read_program(self) -> list[Segment]:
        segments: list[Segment] = []
        for i in range(1, registers.MAX_SEGMENTS + 1):
            self._throttle()
            ramp = int(self._instrument.read_register(registers.segment_ramp_addr(i), 0))
            if ramp == 0:
                break
            self._throttle()
            soak = int(self._instrument.read_register(registers.segment_soak_addr(i), 0))
            self._throttle()
            temp = float(
                self._instrument.read_register(registers.segment_temp_addr(i), 1, signed=True)
            )
            segments.append(Segment(ramp_min=ramp, soak_min=soak, target_temp=temp))
        return segments

    def write_program(self, segments: list[Segment]) -> None:
        for i, seg in enumerate(segments, 1):
            if i > registers.MAX_SEGMENTS:
                break
            self._throttle()
            self._instrument.write_register(registers.segment_ramp_addr(i), seg.ramp_min, 0)
            self._throttle()
            self._instrument.write_register(registers.segment_soak_addr(i), seg.soak_min, 0)
            self._throttle()
            self._instrument.write_register(
                registers.segment_temp_addr(i), seg.target_temp, 1, signed=True
            )
        # Terminate with ramp=0 in the next segment
        next_seg = len(segments) + 1
        if next_seg <= registers.MAX_SEGMENTS:
            self._throttle()
            self._instrument.write_register(registers.segment_ramp_addr(next_seg), 0, 0)

    def start_program(self) -> None:
        self._write_reg(registers.RUN, RunMode.RUNNING)

    def stop_program(self) -> None:
        self._write_reg(registers.RUN, RunMode.OFF)

    def read_run_status(self) -> RunMode:
        val = int(self._read_reg(registers.RUN))
        return RunMode(val)

    def read_segment(self) -> int:
        return int(self._read_reg(registers.PRO))

    def read_segment_elapsed(self) -> int:
        return int(self._read_reg(registers.TE))

    def read_alarm(self) -> tuple[bool, bool]:
        raw = int(self._read_reg(registers.ALARM_STATUS))
        alarm1 = bool(raw & 0x01)
        alarm2 = bool(raw & 0x02)
        return (alarm1, alarm2)

    def write_start_segment(self, segment: int) -> None:
        self._write_reg(registers.PRO, segment)

    def start_autotune(self) -> None:
        self._write_reg(registers.AT, 1)

    def stop_autotune(self) -> None:
        self._write_reg(registers.AT, 0)

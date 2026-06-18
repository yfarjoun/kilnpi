"""Real Modbus RTU controller using minimalmodbus."""

import logging
import threading
import time

import minimalmodbus  # type: ignore[import-untyped]

from backend.dto import PIDParams, Segment
from backend.modbus import registers
from backend.modbus.registers import RunMode

logger = logging.getLogger(__name__)


class RealController:
    """Communicates with the Thermomart PID-RS controller via RS485/Modbus RTU."""

    def __init__(self, port: str, slave_address: int = 1, baud_rate: int = 9600) -> None:
        self._port = port
        self._slave_address = slave_address
        self._baud_rate = baud_rate
        self._instrument: minimalmodbus.Instrument | None = None
        self._min_interval = 0.3  # 300ms between requests
        self._last_request_time = 0.0
        self._lock = threading.Lock()
        # Try opening eagerly so happy-path startup logs the connection,
        # but never crash here: if the FTDI is unplugged at boot, polls
        # will retry _open() lazily and surface MB- on the OLED until it
        # comes back.
        try:
            self._open()
            logger.info("Modbus instrument opened on %s", self._port)
        except Exception as e:
            logger.warning(
                "Serial port %s unavailable at startup (%s); will retry on first poll",
                self._port,
                e,
            )

    def _open(self) -> None:
        """Open the serial port and configure the Modbus instrument. Raises on failure."""
        inst = minimalmodbus.Instrument(self._port, self._slave_address)
        ser = inst.serial
        assert ser is not None  # minimalmodbus opens the port in __init__
        ser.baudrate = self._baud_rate
        ser.bytesize = 8
        ser.parity = minimalmodbus.serial.PARITY_NONE
        ser.stopbits = 1
        ser.timeout = 1.0
        self._instrument = inst

    def _ensure_open(self) -> minimalmodbus.Instrument:
        """Return the open instrument, opening it lazily if needed. Raises if it can't open."""
        if self._instrument is None:
            self._open()
        assert self._instrument is not None  # for type-checkers
        return self._instrument

    @property
    def bus_lock(self) -> threading.Lock:
        """Expose the serial bus lock for coordination with other Modbus devices."""
        return self._lock

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
            self._open()  # raises if hardware still absent — caller logs
            logger.info("Reconnected Modbus instrument on %s", self._port)

    def _throttle(self) -> None:
        """Ensure minimum interval between Modbus requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _read_reg(self, reg: registers.Register) -> int | float:
        inst = self._ensure_open()
        self._throttle()
        decimals = 1 if reg.has_decimal else 0
        result: int | float = inst.read_register(
            reg.address, number_of_decimals=decimals, signed=True
        )
        return result

    def _write_reg(self, reg: registers.Register, value: int | float) -> None:
        inst = self._ensure_open()
        self._throttle()
        decimals = 1 if reg.has_decimal else 0
        inst.write_register(
            reg.address, value, number_of_decimals=decimals, functioncode=6, signed=True
        )

    def read_pv(self) -> float:
        with self._lock:
            return float(self._read_reg(registers.PV))

    def read_sp(self) -> float:
        with self._lock:
            return float(self._read_reg(registers.SP))

    def read_mv(self) -> float:
        with self._lock:
            # MV register returns 0-100 directly (% output). The Thermomart
            # protocol doc claims "0-200 = 0-100%" but empirical test on this
            # firmware: PV=197, SP=1000 (full-power demand) → MV_raw=100.
            # The /2 we used to apply made the browser cap at 50% on full.
            return float(self._read_reg(registers.MV))

    def write_sp(self, value: float) -> None:
        with self._lock:
            self._write_reg(registers.SP, value)

    def read_pid(self) -> PIDParams:
        with self._lock:
            return PIDParams(
                p=int(self._read_reg(registers.P)),
                i=int(self._read_reg(registers.INT)),
                d=int(self._read_reg(registers.D)),
                cycle_time=int(self._read_reg(registers.T)),
            )

    def write_pid(self, params: PIDParams) -> None:
        with self._lock:
            self._write_reg(registers.P, params.p)
            self._write_reg(registers.INT, params.i)
            self._write_reg(registers.D, params.d)
            self._write_reg(registers.T, params.cycle_time)

    def read_program(self) -> list[Segment]:
        with self._lock:
            inst = self._ensure_open()
            segments: list[Segment] = []
            for i in range(1, registers.MAX_SEGMENTS + 1):
                self._throttle()
                ramp = int(inst.read_register(registers.segment_ramp_addr(i), 0))
                if ramp == 0:
                    break
                self._throttle()
                soak = int(inst.read_register(registers.segment_soak_addr(i), 0))
                self._throttle()
                temp = float(
                    inst.read_register(registers.segment_temp_addr(i), 1, signed=True)
                )
                segments.append(Segment(ramp_min=ramp, soak_min=soak, target_temp=temp))
            return segments

    def _raw_write(
        self,
        address: int,
        value: int | float,
        decimals: int = 0,
        signed: bool = False,
    ) -> None:
        """Write a single register using function code 6."""
        inst = self._ensure_open()
        self._throttle()
        inst.write_register(
            address,
            value,
            decimals,
            functioncode=6,
            signed=signed,
        )

    def write_program(self, segments: list[Segment]) -> None:
        with self._lock:
            for i, seg in enumerate(segments, 1):
                if i > registers.MAX_SEGMENTS:
                    break
                self._raw_write(registers.segment_ramp_addr(i), seg.ramp_min)
                self._raw_write(registers.segment_soak_addr(i), seg.soak_min)
                self._raw_write(
                    registers.segment_temp_addr(i),
                    seg.target_temp,
                    decimals=1,
                    signed=True,
                )
            # Terminate with ramp=0 in the next segment
            next_seg = len(segments) + 1
            if next_seg <= registers.MAX_SEGMENTS:
                self._raw_write(registers.segment_ramp_addr(next_seg), 0)

    def start_program(self) -> None:
        with self._lock:
            self._write_reg(registers.RUN, RunMode.RUNNING)

    def stop_program(self) -> None:
        with self._lock:
            self._write_reg(registers.RUN, RunMode.OFF)

    def pause_program(self) -> None:
        with self._lock:
            self._write_reg(registers.RUN, RunMode.STANDBY)

    def resume_program(self) -> None:
        with self._lock:
            self._write_reg(registers.RUN, RunMode.RUNNING)

    def read_run_status(self) -> RunMode:
        with self._lock:
            val = int(self._read_reg(registers.RUN))
            return RunMode(val)

    def read_segment(self) -> int:
        with self._lock:
            return int(self._read_reg(registers.PRO))

    def read_segment_elapsed(self) -> int:
        with self._lock:
            return int(self._read_reg(registers.TE))

    def read_segment_target_temp(self, seg_n: int) -> float:
        """Read C_n — segment N's target temperature."""
        if not 1 <= seg_n <= registers.MAX_SEGMENTS:
            raise ValueError(f"segment {seg_n} out of range 1..{registers.MAX_SEGMENTS}")
        inst = self._ensure_open()
        self._throttle()
        return float(inst.read_register(
            registers.segment_temp_addr(seg_n),
            number_of_decimals=1,
            signed=True,
        ))

    def read_alarm(self) -> tuple[bool, bool]:
        with self._lock:
            try:
                raw = int(self._read_reg(registers.ALARM_STATUS))
                alarm1 = bool(raw & 0x01)
                alarm2 = bool(raw & 0x02)
                return (alarm1, alarm2)
            except Exception:
                logger.debug("Alarm register (0x1200) not supported by this controller")
                return (False, False)

    def write_start_segment(self, segment: int) -> None:
        with self._lock:
            self._write_reg(registers.PRO, segment)

    def start_autotune(self) -> None:
        with self._lock:
            self._write_reg(registers.AT, 1)

    def stop_autotune(self) -> None:
        with self._lock:
            self._write_reg(registers.AT, 0)

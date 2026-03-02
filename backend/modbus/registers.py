"""Modbus register addresses and definitions for the Thermomart PID-RS controller.

All hex addresses match the protocol documentation. Registers marked with
has_decimal=True transmit values multiplied by 10 (e.g., 25.3°C → 253).
"""

from dataclasses import dataclass
from enum import IntEnum


@dataclass(frozen=True)
class Register:
    address: int
    name: str
    description: str
    has_decimal: bool = False
    writable: bool = False
    min_value: int | None = None
    max_value: int | None = None


# --- Read-only status registers ---

PV = Register(0x1001, "PV", "Process value (current temperature)", has_decimal=True)
MV = Register(0x1101, "MV", "Manipulated output 0-200 = 0-100%")
ALARM_STATUS = Register(0x1200, "Alarm", "Current alarm status")

# --- Controller parameters (R/W) ---

SP = Register(0x0000, "SP", "Setpoint temperature", has_decimal=True, writable=True)
AL1 = Register(0x0001, "AL-1", "Alarm 1 threshold", has_decimal=True, writable=True)
AL2 = Register(0x0002, "AL-2", "Alarm 2 threshold", has_decimal=True, writable=True)
PB = Register(0x0003, "Pb", "PV bias (input offset)", has_decimal=True, writable=True)
P = Register(0x0004, "P", "Proportional band", writable=True, min_value=1, max_value=9999)
INT = Register(0x0005, "I", "Integral time", writable=True, min_value=0, max_value=3000)
D = Register(0x0006, "d", "Derivative time (seconds)", writable=True, min_value=0, max_value=2000)
T = Register(0x0007, "T", "Control cycle time (seconds)", writable=True, min_value=2, max_value=120)
FILT = Register(0x0008, "FILT", "Digital filter", writable=True, min_value=0, max_value=99)
HY = Register(0x0009, "Hy", "Hysteresis (ON/OFF mode)", has_decimal=True, writable=True)
DP = Register(0x000A, "dp", "Decimal point position", writable=True, min_value=0, max_value=3)
OUT_H = Register(0x000B, "outH", "Output limiter high", writable=True)
OUT_L = Register(0x000C, "outL", "Output limiter low", writable=True)
AT = Register(
    0x000D, "AT", "Auto tuning (0=stop, 1=start)", writable=True, min_value=0, max_value=1
)
LOCK = Register(0x000E, "LocK", "Data lock", writable=True, min_value=0, max_value=1)
SN = Register(0x000F, "Sn", "Input type (sensor)", writable=True)
OP_A = Register(0x0010, "OP-A", "Main output option (read-only)")
CF = Register(0x0011, "C/F", "Celsius/Fahrenheit", writable=True, min_value=0, max_value=1)
ALP = Register(0x0012, "ALP", "Alarm function type", writable=True, min_value=0, max_value=10)
COOL = Register(0x0013, "COOL", "Heat/Cool select", writable=True, min_value=0, max_value=1)
P_SH = Register(0x0014, "P-SH", "Range high limit", has_decimal=True, writable=True)
P_SL = Register(0x0015, "P-SL", "Range low limit", has_decimal=True, writable=True)
ADDR = Register(0x0016, "Addr", "Modbus slave address", writable=True, min_value=0, max_value=63)
BAUD = Register(0x0017, "bAud", "Baud rate", writable=True)
M_A = Register(0x0018, "m-A", "Manual output power", writable=True)

# --- Ramp/Soak control registers ---

SEC = Register(
    0x0019, "SEC", "Time unit (0=minutes, 1=seconds)", writable=True, min_value=0, max_value=1
)
LOOP = Register(
    0x001A, "LOOP", "Cycle mode (0=stop, 1=repeat)", writable=True, min_value=0, max_value=1
)
PED = Register(0x001B, "PED", "Power-down behavior", writable=True, min_value=0, max_value=3)
AL_P = Register(0x001C, "AL_P", "Wait zone tolerance", has_decimal=True, writable=True)
RUN = Register(0x001D, "run", "Program control", writable=True, min_value=0, max_value=3)
PRO = Register(0x001E, "Pro", "Current segment number", writable=True, min_value=0, max_value=64)
TE = Register(0x001F, "TE", "Elapsed time in current segment")

# --- Ramp/soak segment addresses ---

MAX_SEGMENTS = 32
SEGMENT_BASE = 0x0020  # 3 registers per segment: ramp, soak, target temp


def segment_ramp_addr(seg: int) -> int:
    """Return the register address for segment N ramp time (1-based)."""
    assert 1 <= seg <= MAX_SEGMENTS
    return SEGMENT_BASE + (seg - 1) * 3


def segment_soak_addr(seg: int) -> int:
    """Return the register address for segment N soak time (1-based)."""
    assert 1 <= seg <= MAX_SEGMENTS
    return SEGMENT_BASE + (seg - 1) * 3 + 1


def segment_temp_addr(seg: int) -> int:
    """Return the register address for segment N target temperature (1-based)."""
    assert 1 <= seg <= MAX_SEGMENTS
    return SEGMENT_BASE + (seg - 1) * 3 + 2


class RunMode(IntEnum):
    OFF = 0
    STANDBY = 1
    WAIT = 2
    RUNNING = 3


class InputType(IntEnum):
    Cu50 = 0
    Pt1 = 1
    Pt2 = 2
    K = 3
    E = 4
    J = 5
    T = 6
    S = 7
    R = 8
    B = 9

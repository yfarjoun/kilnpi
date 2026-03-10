#!/usr/bin/env python3
"""Read and display all known registers from the Thermomart PID-RS controller.

Usage (on the Pi — stop kilnpi service first!):
    sudo systemctl --user stop kilnpi.service
    uv run python scripts/read_all_registers.py
"""

import sys
import time
from pathlib import Path

# Add project root to sys.path so `backend` is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import minimalmodbus  # type: ignore[import-untyped]  # noqa: E402

from backend.config import settings  # noqa: E402
from backend.modbus import registers  # noqa: E402

PORT = settings.serial_port
SLAVE = settings.slave_address
BAUD = settings.baud_rate
DELAY = 0.35  # seconds between reads (300ms min per protocol)

# Named registers to read: (Register, signed)
NAMED_REGISTERS: list[tuple[registers.Register, bool]] = [
    (registers.PV, True),
    (registers.SP, True),
    (registers.MV, False),
    (registers.AL1, True),
    (registers.AL2, True),
    (registers.PB, True),
    (registers.P, False),
    (registers.INT, False),
    (registers.D, False),
    (registers.T, False),
    (registers.FILT, False),
    (registers.HY, True),
    (registers.DP, False),
    (registers.OUT_H, False),
    (registers.OUT_L, False),
    (registers.AT, False),
    (registers.LOCK, False),
    (registers.SN, False),
    (registers.OP_A, False),
    (registers.CF, False),
    (registers.ALP, False),
    (registers.COOL, False),
    (registers.P_SH, True),
    (registers.P_SL, True),
    (registers.ADDR, False),
    (registers.BAUD, False),
    (registers.M_A, False),
    (registers.SEC, False),
    (registers.LOOP, False),
    (registers.PED, False),
    (registers.AL_P, True),
    (registers.RUN, False),
    (registers.PRO, False),
    (registers.TE, False),
]


def main() -> None:
    print(f"Connecting to {PORT} (slave={SLAVE}, baud={BAUD})...")
    inst = minimalmodbus.Instrument(PORT, SLAVE)
    inst.serial.baudrate = BAUD
    inst.serial.bytesize = 8
    inst.serial.parity = minimalmodbus.serial.PARITY_NONE
    inst.serial.stopbits = 1
    inst.serial.timeout = 1.0

    print()
    print(f"{'Addr':>6}  {'Name':<8}  {'Raw':>6}  {'Value':>10}  Description")
    print("-" * 70)

    # Read all named registers
    for reg, signed in NAMED_REGISTERS:
        time.sleep(DELAY)
        try:
            decimals = 1 if reg.has_decimal else 0
            raw = inst.read_register(reg.address, 0, signed=signed)
            value = inst.read_register(reg.address, decimals, signed=signed)
            print(f"0x{reg.address:04X}  {reg.name:<8}  {raw:>6}  {value:>10}  {reg.description}")
        except Exception as e:
            print(f"0x{reg.address:04X}  {reg.name:<8}  {'ERROR':>6}  {'':>10}  {e}")

    # Read segment registers (first 8 segments or until ramp=0)
    print()
    print("--- Segment registers ---")
    print(f"{'Seg':>4}  {'Ramp addr':>10}  {'Ramp':>6}  {'Soak':>6}  {'Temp':>8}")
    print("-" * 45)
    for i in range(1, 9):
        time.sleep(DELAY)
        try:
            ramp = inst.read_register(registers.segment_ramp_addr(i), 0)
        except Exception as e:
            print(f"  {i:>2}  0x{registers.segment_ramp_addr(i):04X}      ERROR  {e}")
            continue
        if ramp == 0:
            print(f"  {i:>2}  0x{registers.segment_ramp_addr(i):04X}      {ramp:>5}  (end marker)")
            break
        time.sleep(DELAY)
        try:
            soak = inst.read_register(registers.segment_soak_addr(i), 0)
        except Exception as e:
            soak = f"ERR({e})"
        time.sleep(DELAY)
        try:
            temp = inst.read_register(registers.segment_temp_addr(i), 1, signed=True)
        except Exception as e:
            temp = f"ERR({e})"
        addr_hex = f"0x{registers.segment_ramp_addr(i):04X}"
        print(f"  {i:>2}  {addr_hex}      {ramp:>5}  {soak:>5}  {temp:>7}")

    # Scan for undocumented registers in the 0x1000-0x1300 range
    print()
    print("--- Scanning status registers (0x1000-0x1300) ---")
    for addr in range(0x1000, 0x1300):
        time.sleep(DELAY)
        try:
            raw = inst.read_register(addr, 0)
            # Also try with decimal
            val_dec = inst.read_register(addr, 1, signed=True)
            # Skip if raw is 0 and not a known register (reduce noise)
            known_addrs = (
                registers.PV.address,
                registers.MV.address,
                registers.ALARM_STATUS.address,
            )
            known = addr in known_addrs
            if raw != 0 or known:
                print(f"  0x{addr:04X}  raw={raw:>6}  decimal={val_dec:>10}")
        except Exception:
            pass  # Most addresses won't respond — that's expected

    print()
    print("Done.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Test how the PRO register counts segments during a running program.

Determines whether each program segment (ramp+soak+temp) counts as
1 or 2 PRO segments (one for ramp phase, one for soak phase).

This writes a short 2-segment test program with SEC=1 (seconds) so
each phase only takes a few seconds. It then polls PRO and TE rapidly
to see how the controller counts.

Usage (on the Pi — stop kilnpi service first!):
    sudo systemctl --user stop kilnpi.service
    uv run python scripts/test_pro_counting.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import minimalmodbus  # type: ignore[import-untyped]  # noqa: E402

from backend.config import settings  # noqa: E402
from backend.modbus import registers  # noqa: E402

PORT = settings.serial_port
SLAVE = settings.slave_address
BAUD = settings.baud_rate
DELAY = 0.35  # 300ms min between Modbus requests


def main() -> None:
    print(f"Connecting to {PORT} (slave={SLAVE}, baud={BAUD})...")
    inst = minimalmodbus.Instrument(PORT, SLAVE)
    inst.serial.baudrate = BAUD
    inst.serial.bytesize = 8
    inst.serial.parity = minimalmodbus.serial.PARITY_NONE
    inst.serial.stopbits = 1
    inst.serial.timeout = 1.0

    def read_reg(addr: int, decimals: int = 0, signed: bool = False) -> int | float:
        time.sleep(DELAY)
        return inst.read_register(addr, decimals, signed=signed)

    def write_reg(addr: int, value: int | float, decimals: int = 0, signed: bool = False) -> None:
        time.sleep(DELAY)
        inst.write_register(addr, value, decimals, functioncode=6, signed=signed)

    # Step 1: Read current SEC setting and save it
    old_sec = int(read_reg(registers.SEC.address))
    print(f"Current SEC (time unit): {old_sec} ({'seconds' if old_sec else 'minutes'})")

    # Step 2: Set SEC=1 (seconds) for fast testing
    print("Setting SEC=1 (seconds) for fast test...")
    write_reg(registers.SEC.address, 1)

    # Step 3: Stop any running program
    print("Stopping any running program...")
    write_reg(registers.RUN.address, 0)

    # Step 4: Write a simple 2-segment test program
    # Seg 1: ramp 10s, soak 10s, target 50°C
    # Seg 2: ramp 10s, soak 10s, target 30°C
    # Seg 3: end marker (ramp=0)
    print("\nWriting test program:")
    print("  Seg 1: ramp=10s, soak=10s, target=50.0°C")
    print("  Seg 2: ramp=10s, soak=10s, target=30.0°C")
    print("  Seg 3: end marker (ramp=0)")

    for seg_num, (ramp, soak, temp) in enumerate(
        [(10, 10, 50.0), (10, 10, 30.0), (0, 0, 0.0)], start=1
    ):
        write_reg(registers.segment_ramp_addr(seg_num), ramp)
        write_reg(registers.segment_soak_addr(seg_num), soak)
        write_reg(registers.segment_temp_addr(seg_num), temp, decimals=1, signed=True)

    # Step 5: Set PRO=0 (start from beginning) and start
    print("\nSetting PRO=0, starting program...")
    write_reg(registers.PRO.address, 0)
    write_reg(registers.RUN.address, 3)  # RUNNING

    # Step 6: Poll PRO, TE, PV, SP, RUN rapidly
    print("\nPolling PRO, TE, RUN, PV, SP every ~0.7s...")
    print(f"{'Time':>6}  {'RUN':>4}  {'PRO':>4}  {'TE':>4}  {'PV':>8}  {'SP':>8}")
    print("-" * 50)

    start = time.time()
    last_pro = -1
    try:
        while True:
            elapsed = time.time() - start
            run = int(read_reg(registers.RUN.address))
            pro = int(read_reg(registers.PRO.address))
            te = int(read_reg(registers.TE.address))
            pv = read_reg(registers.PV.address, 1, signed=True)
            sp = read_reg(registers.SP.address, 1, signed=True)

            marker = " <-- PRO changed!" if pro != last_pro else ""
            print(f"{elapsed:6.1f}  {run:>4}  {pro:>4}  {te:>4}  {pv:>8}  {sp:>8}{marker}")
            last_pro = pro

            # Stop if program ended (RUN=0) or after 2 minutes max
            if run == 0 or elapsed > 120:
                break

    except KeyboardInterrupt:
        print("\nInterrupted!")

    # Step 7: Stop and restore SEC
    print("\nStopping program...")
    write_reg(registers.RUN.address, 0)
    print(f"Restoring SEC={old_sec}...")
    write_reg(registers.SEC.address, old_sec)

    print("\nDone. Check the PRO column above to see how segments are counted.")
    print("If PRO goes 1,2,3,4 for 2 program segments → 2 PRO per program segment (ramp+soak)")
    print("If PRO goes 1,2 for 2 program segments → 1 PRO per program segment")


if __name__ == "__main__":
    main()

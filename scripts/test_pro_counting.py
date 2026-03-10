#!/usr/bin/env python3
"""Test how the PRO register counts segments during a running program.

Test 1: Counts PRO values for a 2-segment program starting from PRO=0.
Test 2: Starts from PRO=3 to verify write-PRO semantics (does PRO=X
        start AT segment X, or at X+1?).

Uses SEC=1 (seconds) so each phase only takes a few seconds.

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

    def write_reg(
        addr: int, value: int | float, decimals: int = 0, signed: bool = False
    ) -> None:
        time.sleep(DELAY)
        inst.write_register(addr, value, decimals, functioncode=6, signed=signed)

    def poll_until_done(label: str, max_seconds: float = 50) -> None:
        """Poll PRO/TE/RUN and print until program ends or timeout."""
        print(f"\n--- {label} ---")
        print(f"{'Time':>6}  {'RUN':>4}  {'PRO':>4}  {'TE':>4}")
        print("-" * 30)
        start = time.time()
        last_pro = -1
        while True:
            elapsed = time.time() - start
            run = int(read_reg(registers.RUN.address))
            pro = int(read_reg(registers.PRO.address))
            te = int(read_reg(registers.TE.address))
            marker = " <-- PRO changed!" if pro != last_pro else ""
            print(f"{elapsed:6.1f}  {run:>4}  {pro:>4}  {te:>4}{marker}")
            last_pro = pro
            if run == 0 or elapsed > max_seconds:
                break

    # Save and set SEC=1 (seconds)
    old_sec = int(read_reg(registers.SEC.address))
    old_loop = int(read_reg(registers.LOOP.address))
    print(f"Saving: SEC={old_sec}, LOOP={old_loop}")
    print("Setting SEC=1 (seconds), LOOP=0 (no repeat)...")
    write_reg(registers.SEC.address, 1)
    write_reg(registers.LOOP.address, 0)
    write_reg(registers.RUN.address, 0)

    # Write 2-segment test program: each phase 5s for speed
    print("\nWriting test program:")
    print("  Seg 1: ramp=5s, soak=5s, target=50°C")
    print("  Seg 2: ramp=5s, soak=5s, target=30°C")
    print("  Seg 3: end marker (ramp=0)")
    for seg_num, (ramp, soak, temp) in enumerate(
        [(5, 5, 50.0), (5, 5, 30.0), (0, 0, 0.0)], start=1
    ):
        write_reg(registers.segment_ramp_addr(seg_num), ramp)
        write_reg(registers.segment_soak_addr(seg_num), soak)
        write_reg(registers.segment_temp_addr(seg_num), temp, decimals=1, signed=True)

    # ---- Test 1: Start from PRO=0 (beginning) ----
    print("\n=== Test 1: Write PRO=0, start program ===")
    write_reg(registers.PRO.address, 0)
    write_reg(registers.RUN.address, 3)
    poll_until_done("PRO=0 (start from beginning)")
    write_reg(registers.RUN.address, 0)
    time.sleep(1)

    # ---- Test 2: Start from PRO=3 ----
    # If PRO=X starts AT X: first read should be PRO=3 (seg 2 ramp)
    # If PRO=X starts at X+1: first read should be PRO=4 (seg 2 soak)
    print("\n=== Test 2: Write PRO=3, start program ===")
    print("(expecting to skip seg 1 entirely and start at seg 2)")
    write_reg(registers.PRO.address, 3)
    write_reg(registers.RUN.address, 3)
    poll_until_done("PRO=3 (should skip to seg 2)")
    write_reg(registers.RUN.address, 0)

    # Restore settings
    print(f"\nRestoring: SEC={old_sec}, LOOP={old_loop}...")
    write_reg(registers.SEC.address, old_sec)
    write_reg(registers.LOOP.address, old_loop)

    print("\n=== Summary ===")
    print("Test 1 confirms: 2 PRO steps per register segment (ramp+soak)")
    print("Test 2 reveals: does writing PRO=3 start AT PRO=3 or PRO=4?")
    print("  If first read was PRO=3 → write X starts AT X")
    print("  If first read was PRO=4 → write X starts at X+1")


if __name__ == "__main__":
    main()

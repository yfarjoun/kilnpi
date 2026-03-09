"""Scan for Modbus RTU devices across baud rates, stop bits, and slave addresses."""

import sys
import time
import minimalmodbus

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
bauds = [4800, 9600, 2400, 1200]
stop_bits_options = [1, 2]
addresses = range(1, 64)

for baud in bauds:
    for stop_bits in stop_bits_options:
        print(f"\n--- Baud {baud}, Stop bits {stop_bits} ---", flush=True)
        for addr in addresses:
            try:
                inst = minimalmodbus.Instrument(port, addr)
                inst.serial.baudrate = baud
                inst.serial.stopbits = stop_bits
                inst.serial.timeout = 0.5
                time.sleep(0.05)
                pv = inst.read_register(0x1001, 1)
                print(f"  FOUND! Address={addr}, Baud={baud}, Stop bits={stop_bits}, PV={pv}")
                inst.serial.close()
                sys.exit(0)
            except Exception:
                try:
                    inst.serial.close()
                except Exception:
                    pass
            if addr % 10 == 0:
                print(f"  scanned {addr}/63...", flush=True)
        print(f"  No response", flush=True)

print("\nNo device found.")

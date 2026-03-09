"""Scan for Modbus RTU devices across baud rates and slave addresses."""

import sys
import time
import serial
import minimalmodbus

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
bauds = [4800, 9600, 2400, 1200]
addresses = range(1, 64)

for baud in bauds:
    print(f"\n--- Baud {baud} ---", flush=True)
    for addr in addresses:
        try:
            ser = serial.Serial(port, baudrate=baud, timeout=0.5)
            inst = minimalmodbus.Instrument(port, addr)
            inst.serial = ser
            inst.serial.timeout = 0.5
            time.sleep(0.05)  # small gap between requests
            pv = inst.read_register(0x1001, 1)
            print(f"  FOUND! Address={addr}, Baud={baud}, PV={pv}")
            ser.close()
            sys.exit(0)
        except Exception:
            pass
        finally:
            try:
                ser.close()
            except Exception:
                pass
        if addr % 10 == 0:
            print(f"  scanned {addr}/63...", flush=True)
    print(f"  No response at baud {baud}", flush=True)

print("\nNo device found on any baud/address combination.")

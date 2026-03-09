"""Scan for Modbus RTU devices across baud rates and slave addresses."""

import sys
import minimalmodbus

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
bauds = [4800, 9600, 2400, 1200]
addresses = range(1, 64)

for baud in bauds:
    print(f"\n--- Baud {baud} ---")
    for addr in addresses:
        try:
            inst = minimalmodbus.Instrument(port, addr)
            inst.serial.baudrate = baud
            inst.serial.timeout = 0.5
            pv = inst.read_register(0x1001, 1)
            print(f"  FOUND! Address={addr}, Baud={baud}, PV={pv}")
            inst.serial.close()
            sys.exit(0)
        except Exception:
            pass
        finally:
            try:
                inst.serial.close()
            except Exception:
                pass
    print(f"  No response at baud {baud}")

print("\nNo device found on any baud/address combination.")

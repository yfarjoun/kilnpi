"""Probe which Modbus registers the controller actually responds to."""

import sys
import time

import minimalmodbus

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
addr = int(sys.argv[2]) if len(sys.argv) > 2 else 1

inst = minimalmodbus.Instrument(port, addr)
inst.serial.baudrate = 9600
inst.serial.timeout = 1.0

# All registers from the protocol doc
regs = [
    (0x1001, "PV", 1),
    (0x1101, "MV", 0),
    (0x1200, "Alarm", 0),
    (0x0000, "SP", 1),
    (0x0001, "AL-1", 1),
    (0x0002, "AL-2", 1),
    (0x0004, "P", 0),
    (0x0005, "I", 0),
    (0x0006, "d", 0),
    (0x0007, "T", 0),
    (0x000D, "AT", 0),
    (0x001D, "run", 0),
    (0x001E, "Pro", 0),
    (0x001F, "TE", 0),
    (0x0020, "Seg1 ramp", 0),
]

for reg_addr, name, decimals in regs:
    time.sleep(0.5)
    try:
        val = inst.read_register(reg_addr, decimals, signed=True)
        print(f"  OK  0x{reg_addr:04X} {name:12s} = {val}")
    except Exception as e:
        print(f"  FAIL 0x{reg_addr:04X} {name:12s} — {e}")

inst.serial.close()

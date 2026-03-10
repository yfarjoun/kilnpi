"""Raw serial test — send a known Modbus request and print any response."""

import sys
import time

import serial

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"

# Read PV (register 0x1001) from slave 1, matching protocol doc exactly:
# 01 03 10 01 00 01 D1 0A
request = bytes([0x01, 0x03, 0x10, 0x01, 0x00, 0x01, 0xD1, 0x0A])

for baud in [4800, 9600]:
    print(f"\n--- Baud {baud} ---", flush=True)
    ser = serial.Serial(port, baudrate=baud, timeout=2.0, bytesize=8, parity="N", stopbits=1)
    time.sleep(0.1)  # let port settle
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    print(f"  Sending: {request.hex(' ')}", flush=True)
    written = ser.write(request)
    print(f"  Wrote {written} bytes", flush=True)

    time.sleep(0.5)  # wait for response
    available = ser.in_waiting
    print(f"  Bytes waiting: {available}", flush=True)

    response = ser.read(20)  # read whatever comes back
    hex_str = response.hex(" ") if response else "empty"
    print(f"  Response ({len(response)} bytes): {hex_str}", flush=True)

    ser.close()
    time.sleep(0.2)

print("\nDone.")

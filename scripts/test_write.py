#!/usr/bin/env python3
"""Quick test: can we read and write to the controller?"""

from backend.config import settings
from backend.modbus.real_controller import RealController

c = RealController(settings.serial_port, settings.slave_address, settings.baud_rate)
print("Reading PV:", c.read_pv())
print("Reading SP:", c.read_sp())
pid = c.read_pid()
print("PID:", pid)
print("Writing PID back...")
c.write_pid(pid)
print("Write succeeded")

# Thermomart PID-RS Controller - RS485/Modbus Protocol Research

## Overview

Thermomart controllers (sold by Dinico Global Inc., Toronto) are **rebranded Chinese OEM PID controllers** with Modbus RTU communication over RS485 via a CH340/CH341 USB adapter.

## Communication Settings

| Parameter | Value |
|-----------|-------|
| Protocol | Modbus RTU |
| Data bits | 8 |
| Stop bits | 1 or 2 |
| Parity | None |
| Baud rate | 1200 / 2400 / 4800 / **9600** (default) |
| Slave address | 1-63 (default: **1**) |
| Min interval | **300ms** between requests |
| Max cable length | 150m |

## Supported Function Codes

| Code | Function | Notes |
|------|----------|-------|
| 0x03 | Read holding register | Quantity **must be 1** |
| 0x06 | Write single register | Response is echo of request |

## Message Format

```
[Slave Addr 1B] [Function Code 1B] [Register Addr 2B] [Data 2B] [CRC-16 2B]
```

### Read Example (PV from slave 1)

```
Query:    01 03 10 01 00 01 D1 0A
Response: 01 03 02 00 FD 79 C5
          (0x00FD = 253, with 1 decimal place = 25.3°C)
```

### Write Example (AL-1 = -20.0 to slave 1)

```
Query:    01 06 00 02 FF 38 68 28
Response: 01 06 00 02 FF 38 68 28  (echo)
          (-20.0 → -200 → two's complement 0xFF38)
```

## Decimal Point Handling

Values marked "Decimal point = YES" are transmitted as integers × 10^(decimal places).
- 25.3°C → transmitted as 253
- Negative values use 16-bit two's complement

## No Response Conditions

The controller silently ignores requests when:
- Slave address mismatch
- CRC mismatch
- Transmission error
- Request interval < 300ms

## EEPROM Warning

Write lifespan < **1,000,000 cycles**. Avoid continuous writes in tight loops.

---

## Register Map

### Read-Only Status Registers

| Symbol | Description | Hex Addr | Decimal Pt | Notes |
|--------|------------|----------|------------|-------|
| PV | Process Value (temperature) | 0x1001 | YES | Current reading |
| MV | Manipulated output | 0x1101 | NO | 0-200 = 0-100% |
| Alarm | Alarm status | 0x1200 | NO | Current alarm state |

### Controller Parameters (R/W)

| Hex Addr | Code | Description | Range | Default | Dec.Pt |
|----------|------|-------------|-------|---------|--------|
| 0x00 | SP | Setpoint temperature | P-SL to P-SH | 100 | YES |
| 0x01 | AL-1 | Alarm 1 threshold | P-SL to P-SH | 300 | YES |
| 0x02 | AL-2 | Alarm 2 threshold | P-SL to P-SH | 100 | YES |
| 0x03 | Pb | PV bias (input offset) | ±20.0 | 0.0 | YES |
| 0x04 | P | Proportional band | 1-9999 | 100 | NO |
| 0x05 | I | Integral time | 0-3000 | 500 | NO |
| 0x06 | d | Derivative time | 0-2000s | 100s | NO |
| 0x07 | T | Control cycle time | 2-120s | 20s | NO |
| 0x08 | FILT | Digital filter | 0-99 | 20 | NO |
| 0x09 | Hy | Hysteresis (ON/OFF) | 0.1-50.0 | 0.5 | YES |
| 0x0A | dp | Decimal point position | 0-3 | 0 | NO |
| 0x0B | outH | Output limiter high | outL-200 | 200 | NO |
| 0x0C | outL | Output limiter low | 0-outH | 0 | NO |
| 0x0D | AT | Auto tuning | 0=stop, 1=start | 0 | NO |
| 0x0E | LocK | Data lock | 0=all, 1=SV only | 0 | NO |
| 0x0F | Sn | Input type (sensor) | see table | K | NO |
| 0x10 | OP-A | Main output option | 0-7 | READ ONLY | NO |
| 0x11 | C/F | Celsius/Fahrenheit | 0=C, 1=F | C | NO |
| 0x12 | ALP | Alarm function type | 0-10 | 1 | NO |
| 0x13 | COOL | Heat/Cool select | 0=heat, 1=cool | 0 | NO |
| 0x14 | P-SH | Range high limit | P-SL to 9999 | 1300 | YES |
| 0x15 | P-SL | Range low limit | -1999 to P-SH | 0 | YES |
| 0x16 | Addr | Modbus slave address | 0-63 | 1 | NO |
| 0x17 | bAud | Baud rate | 1200/2400/4800/9600 | 9600 | NO |
| 0x18 | m-A | Manual output power | — | — | NO |

### Ramp/Soak Control Registers (PID-RS only)

| Hex Addr | Code | Description | Range | Dec.Pt |
|----------|------|-------------|-------|--------|
| 0x19 | SEC | Time unit | 0=minutes, 1=seconds | NO |
| 0x1A | LOOP | Cycle mode | 0=stop, 1=repeat | NO |
| 0x1B | PED | Power-down behavior | 0-3 | NO |
| 0x1C | AL_P | Wait zone tolerance | 0-100.0 | YES |
| 0x1D | run | Program control | 0=off, 1=standby, 2=wait, 3=running | NO |
| 0x1E | Pro | Current segment number | 0-64 | NO |
| 0x1F | TE | Elapsed time in segment | — | NO |

### Ramp/Soak Segment Data (32 segments)

Pattern repeats for segments 1-32:

| Hex Addr | Code | Description | Range | Dec.Pt |
|----------|------|-------------|-------|--------|
| 0x20 | r1 | Ramp time seg 1 | 0-2000 min | NO |
| 0x21 | t1 | Soak time seg 1 | 0-9999 min | NO |
| 0x22 | C1 | Target temp seg 1 | P-SL to P-SH | YES |
| 0x23 | r2 | Ramp time seg 2 | … | NO |
| 0x24 | t2 | Soak time seg 2 | … | NO |
| 0x25 | C2 | Target temp seg 2 | … | YES |
| … | … | … | … | … |
| 0x7D | r32 | Ramp time seg 32 | … | NO |
| 0x7E | t32 | Soak time seg 32 | … | NO |
| 0x7F | C32 | Target temp seg 32 | … | YES |

**Special ramp values:**
- `r = 0` → Program ends here
- `r = 2000` → Skip ramp (jump to target immediately)
- `t = 0` → Skip the soak phase

### Input Type Codes (register 0x0F)

| Code | Sensor | Range |
|------|--------|-------|
| Cu50 | Copper RTD | -50.0 to 150.0°C |
| Pt1 | Pt100 (low) | -199.9 to 200.0°C |
| Pt2 | Pt100 (high) | -199.9 to 600.0°C |
| K | K thermocouple | -30.0 to 1300°C |
| E | E thermocouple | -30.0 to 700.0°C |
| J | J thermocouple | -30.0 to 900.0°C |
| T | T thermocouple | -199.9 to 400.0°C |
| S | S thermocouple | -30 to 1600°C |
| R | R thermocouple | similar to S |
| B | B thermocouple | PID-SSR only |

### Alarm Mode Codes (register 0x12)

| Value | Mode |
|-------|------|
| 0 | Alarm OFF |
| 1 | Process high alarm |
| 2 | Process low alarm |
| 3 | Process high AND low |
| 4 | Deviation high alarm |
| 5 | Deviation low alarm |
| 6 | Deviation high AND low |
| 7 | Deviation high/low |
| 8 | Band alarm |

---

## Existing Open-Source References

### Python Libraries for Modbus
- **minimalmodbus** — lightweight, ideal for single-register reads/writes
- **pymodbus** — full-featured, supports RTU/ASCII/TCP

### Related Kiln Controller Projects
- **jbruce12000/kiln-controller** — RPi kiln controller with web UI (uses direct thermocouple, not Modbus)
- **pvarney/PiLN** — RPi kiln controller in Python
- **Saur0o0n/PIDKiln** — ESP32 kiln controller with web UI

### Basic Python Example (minimalmodbus)

```python
import minimalmodbus

instrument = minimalmodbus.Instrument('/dev/ttyUSB0', 1)  # port, slave addr
instrument.serial.baudrate = 9600
instrument.serial.bytesize = 8
instrument.serial.parity = minimalmodbus.serial.PARITY_NONE
instrument.serial.stopbits = 1
instrument.serial.timeout = 1.0

# Read
pv = instrument.read_register(0x1001, 1)    # PV with 1 decimal
sp = instrument.read_register(0x0000, 1)    # Setpoint
mv = instrument.read_register(0x1101, 0)    # Output %

# Write
instrument.write_register(0x0000, 100.0, 1) # Set SP to 100.0°C

# Ramp/soak control
instrument.write_register(0x001D, 3, 0)     # Start program (run=3)
instrument.write_register(0x001D, 0, 0)     # Stop program (run=0)
```

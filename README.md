# KilnPi

A Raspberry Pi web interface for the Thermomart PID-RS kiln controller.
Communicates over RS485/Modbus RTU, provides a real-time web dashboard,
program management, firing history, and kiln health analytics. A Waveshare
1.3" SH1106 OLED HAT (with joystick and buttons) shows system vitals on the
Pi itself.

## Architecture

```
┌───────────────┐ RS485/Modbus RTU  ┌────────────────┐
│  Raspberry Pi │◄─────────────────►│ PID-RS Kiln    │
│  Zero 2W      │ 9600 baud, 8N1    │ Controller     │
│  ┌──────────┐ │                   └────────────────┘
│  │ FastAPI  │ │ HTTP / WebSocket
│  │ Backend  ├─┼──────────────────► Browser (React)
│  └────┬─────┘ │
│       │       │ SPI
│  ┌────▼─────┐ ├──────────────────► SH1106 OLED
│  │ SQLite   │ │                    128×64 display
│  │ Database │ │
│  └──────────┘ │
└───────────────┘
```

**Backend** (Python / FastAPI):
- **Poller** — reads PV, SP, MV, alarms, and segment info from the
  controller every 2 seconds via Modbus RTU.
- **Recorder** — detects program start/stop transitions and logs
  timestamped readings into SQLite.
- **Display** — renders system health (disk, memory, IP, poll age) on the
  OLED via SPI.
- **WebSocket** — streams live status to all connected browsers.
- **REST API** — program CRUD, firing history (with notes and delete), slot
  management, PID tuning, statistics with kiln sitter cutoff detection,
  CSV export/import.

**Frontend** (React / TypeScript / Tailwind / Recharts):
- Dashboard with temperature gauges and two quick-fire program slots.
- Live monitor with real-time charting.
- Program library with a draggable profile editor.
- Firing history with per-firing charts, notes, delete, and CSV download.
- Statistics dashboard with kiln health trend analysis.
- Dark / light mode toggle.

**Mock mode** — on macOS (or when no USB-RS485 adapter is detected), the
backend automatically uses a mock controller with a simple thermal
simulation. No hardware needed for development.

## Hardware

- Raspberry Pi Zero 2W
- Waveshare 1.3" OLED HAT (SH1106, SPI, 128×64, joystick + 3 buttons)
- USB-RS485 adapter (for Modbus RTU to kiln controller)
- Thermomart PID-RS kiln controller

## Raspberry Pi Setup

### 1. Flash the OS

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) on your
Mac/PC:

- **OS**: Raspberry Pi OS Lite (64-bit, Debian 13 Trixie)
- **Settings** (gear icon / Cmd+Shift+X):
  - Set hostname (e.g. `kilnpi`)
  - Enable SSH with password authentication
  - Set username and password
  - Configure WiFi SSID and password
  - Set locale and timezone

Write the image to a micro SD card, insert into the Pi, and power on.

### 2. SSH in

```bash
ssh <username>@<hostname>.local
# or use the IP address from your router's admin page
```

### 3. Install system dependencies

```bash
sudo apt update
sudo apt install -y git i2c-tools python3-dev libopenjp2-7 libtiff6 nodejs npm swig just
```

### 4. Enable SPI and I2C

```bash
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0
```

### 5. Install uv (Python package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env
```

### 6. Clone and install

```bash
git clone https://github.com/yfarjoun/kilnpi.git
cd kilnpi
uv sync
```

### 7. Build the frontend

```bash
cd ~/kilnpi/frontend
npm install
npm run build
cd ..
```

### 8. Run

```bash
cd ~/kilnpi

# With real controller (auto-detected if USB-RS485 adapter is connected):
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000

# With mock controller (for testing without hardware):
MOCK_CONTROLLER=1 uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

The app is available at **http://\<pi-ip\>:8000**.

### 9. Auto-start with systemd

The repo includes `kilnpi.service` (a systemd **user** service). Install it:

```bash
mkdir -p ~/.config/systemd/user
ln -sf ~/kilnpi/kilnpi.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now kilnpi.service

# Check status / logs
systemctl --user status kilnpi
journalctl --user -u kilnpi -f
```

Optional: install the OLED boot splash screen (system service, shows
progress bar during boot):

```bash
sudo ~/kilnpi/scripts/install-splash.sh
```

## Development (Mac)

No Pi needed — mock mode runs automatically on macOS.

### Prerequisites

- Python 3.11+
- Node.js 20+ and npm
- [uv](https://docs.astral.sh/uv/)
- [just](https://github.com/casey/just) (task runner)

### Setup

```bash
git clone https://github.com/yfarjoun/kilnpi.git
cd kilnpi
just install        # installs backend (uv) + frontend (npm) deps
```

### Running

```bash
just dev-backend    # backend with auto-reload (mock mode on Mac)
just dev-frontend   # frontend dev server (in a second terminal)
```

Open **http://localhost:5173** in your browser.

### Environment variables

| Variable           | Default            | Description                       |
|--------------------|--------------------|-----------------------------------|
| `MOCK_CONTROLLER`  | auto-detected      | Set to `1` to force mock mode     |
| `DB_PATH`          | `data/kiln.db`     | SQLite database file path         |

### Common tasks

```bash
just                # list all available recipes
just check          # lint + test (everything)
just lint           # ruff + eslint
just lint-fix       # auto-fix ruff issues
just typecheck      # mypy
just test           # pytest (pass args: just test -x -q)
just build          # build frontend for production
just ci             # run the full CI pipeline locally
```

### Deploying to the Pi

```bash
just deploy                     # build frontend + rsync + git pull + restart
just deploy-frontend            # build + rsync frontend only + restart
just deploy kilnpi.local        # override host (default: kilnpi)
```

### Pi management

```bash
just status         # show service status
just logs           # tail service logs
just restart        # restart kilnpi service
```

## Project Structure

```
backend/
  main.py                  App entry point, service orchestration
  config.py                Settings, mock/real auto-detection
  dto.py                   Pydantic request/response models
  modbus/
    controller.py          ControllerInterface protocol
    real_controller.py     Modbus RTU via minimalmodbus
    mock_controller.py     Mock with thermal simulation
    registers.py           Register map and enums
  api/
    status.py              GET /api/status
    control.py             Setpoint, start/stop, PID, autotune
    programs.py            Program CRUD + CSV export/import
    history.py             Firing history, notes, delete + CSV export
    slots.py               Quick-fire slot management
    stats.py               Kiln statistics, health trends, sitter cutoff detection
    ws.py                  WebSocket live broadcast
  services/
    poller.py              Background controller polling
    recorder.py            Firing/reading auto-recorder
    display.py             OLED display service (SH1106/SPI)
  models/
    database.py            Async SQLAlchemy engine + session
    schemas.py             ORM: Program, Firing, Reading, SlotAssignment

frontend/src/
  App.tsx                  Router, navigation, theme toggle
  api/client.ts            Typed fetch wrapper
  api/websocket.ts         WebSocket connection
  types/index.ts           TypeScript interfaces
  hooks/                   useStatus, usePrograms, useTheme
  pages/                   Dashboard, Monitor, Programs, History, Statistics, Settings
  components/              TempGauge, FiringChart, ProfileEditor, SegmentTable, StatusBar

justfile                         Task runner recipes (just)

scripts/
  deploy-frontend.sh       Build + rsync frontend to Pi
  splash.py                OLED boot splash screen
  install-splash.sh        Install splash as system service
  test_display.py          Quick OLED display test
  test_write.py            Quick Modbus read/write test

docs/research/
  thermomart_pid_rs485_protocol.md   Full Modbus register reference
```

## Modbus Protocol Reference

The PID-RS communicates via Modbus RTU at 9600/8N1 with a 300 ms minimum
interval between requests. See
[`docs/research/thermomart_pid_rs485_protocol.md`](docs/research/thermomart_pid_rs485_protocol.md)
for the full register map, function codes, and segment programming details.

## License

[MIT](LICENSE)

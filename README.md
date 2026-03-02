# Thermomart Kiln Controller

A Raspberry Pi web interface for the Thermomart PID-RS kiln controller.
Communicates over RS485/Modbus RTU, provides a real-time web dashboard,
program management, firing history, and kiln health analytics. An SSD1306
OLED display shows system vitals on the Pi itself.

## Architecture

```
┌──────────────┐   RS485/Modbus RTU    ┌────────────────┐
│  Raspberry Pi│◄──────────────────────►│ PID-RS Kiln    │
│              │   9600 baud, 8N1       │ Controller     │
│  ┌─────────┐ │                        └────────────────┘
│  │ FastAPI  │ │   HTTP / WebSocket
│  │ Backend  │◄├──────────────────────► Browser (React)
│  └────┬─────┘ │
│       │       │
│  ┌────▼─────┐ │
│  │ SQLite   │ │   I2C
│  │ Database │ │──────────────────────► SSD1306 OLED
│  └──────────┘ │                        128×64 display
└──────────────┘
```

**Backend** (Python / FastAPI):
- **Poller** — reads PV, SP, MV, alarms, and segment info from the
  controller every 2 seconds via Modbus RTU.
- **Recorder** — detects program start/stop transitions and logs
  timestamped readings into SQLite.
- **Display** — renders system health (disk, memory, IP, poll age) on the
  OLED.
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

## Prerequisites

- Python 3.14+
- Node.js 20+ and npm
- On the Pi: a USB-RS485 adapter connected to the PID-RS controller

## Installation

```bash
# Clone the repository
git clone <repo-url> && cd themomart_controller

# Python backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# React frontend
cd frontend
npm install
cd ..
```

## Running (Development)

Start the backend and frontend dev servers separately. The Vite dev server
proxies `/api` requests to the backend automatically.

```bash
# Terminal 1 — backend (auto-detects mock mode on Mac)
source .venv/bin/activate
python -m uvicorn backend.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

### Environment variables

| Variable           | Default            | Description                       |
|--------------------|--------------------|-----------------------------------|
| `MOCK_CONTROLLER`  | auto-detected      | Set to `1` to force mock mode     |
| `DB_PATH`          | `data/kiln.db`     | SQLite database file path         |

You can also pass `--mock` as a CLI argument to force mock mode.

## Running (Production on Raspberry Pi)

Build the frontend, then run the backend which serves the static files:

```bash
# Build frontend
cd frontend && npm run build && cd ..

# Run (real controller auto-detected on Linux with USB-RS485)
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

The app is then available at **http://<pi-ip>:8000**.

### Auto-start with systemd

Create `/etc/systemd/system/kiln-controller.service`:

```ini
[Unit]
Description=Kiln Controller
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/themomart_controller
Environment=PATH=/home/pi/themomart_controller/.venv/bin:/usr/bin
ExecStart=/home/pi/themomart_controller/.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable kiln-controller
sudo systemctl start kiln-controller

# Check status / logs
sudo systemctl status kiln-controller
journalctl -u kiln-controller -f
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
    display.py             OLED display service
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

docs/research/
  thermomart_pid_rs485_protocol.md   Full Modbus register reference
```

## Testing

```bash
# Backend tests
source .venv/bin/activate
python -m pytest tests/ -v

# Frontend type check
cd frontend && npx tsc --noEmit
```

## Modbus Protocol Reference

The PID-RS communicates via Modbus RTU at 9600/8N1 with a 300 ms minimum
interval between requests. See
[`docs/research/thermomart_pid_rs485_protocol.md`](docs/research/thermomart_pid_rs485_protocol.md)
for the full register map, function codes, and segment programming details.

## License

Private project — not currently licensed for redistribution.

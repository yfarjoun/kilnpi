"""FastAPI application — startup, shutdown, route mounting."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api import control, history, programs, slots, stats, status, ws
from backend.config import settings
from backend.modbus.controller import ControllerInterface
from backend.modbus.mock_controller import MockController
from backend.models.database import init_db
from backend.services.buttons import ButtonState, create_button_service
from backend.services.display import DisplayService, create_display_and_splash
from backend.services.poller import ControllerState, Poller
from backend.services.recorder import Recorder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _create_controller() -> ControllerInterface:
    """Create the appropriate controller based on config."""
    if settings.mock_mode:
        logger.info("Using MOCK controller")
        return MockController()
    else:
        from backend.modbus.real_controller import RealController

        logger.info("Using REAL Modbus controller on %s", settings.serial_port)
        return RealController(
            port=settings.serial_port,
            slave_address=settings.slave_address,
            baud_rate=settings.baud_rate,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    # Signal the splash service to stop — we're taking over the display
    Path("/tmp/kilnpi-ready").touch()

    oled = create_display_and_splash()
    await init_db()

    controller = _create_controller()
    state = ControllerState()

    # Wire up API modules
    status.set_state(state)
    control.set_controller(controller)
    slots.set_controller(controller)
    slots.set_state(state)

    # Start background services
    poller = Poller(controller, state, interval=settings.poll_interval_sec)
    poller.start()

    recorder = Recorder(state, interval=settings.poll_interval_sec)
    recorder_task = asyncio.create_task(recorder.run())

    button_state = ButtonState()
    buttons = create_button_service(button_state)
    buttons.start()

    display = DisplayService(
        state, ws.client_count, interval=5.0, button_state=button_state, display=oled,
    )
    display.start()

    broadcast_task = asyncio.create_task(
        ws.broadcast_loop(state, interval=settings.poll_interval_sec)
    )

    logger.info("All services started (mock=%s)", settings.mock_mode)

    yield

    # Shutdown
    broadcast_task.cancel()
    recorder_task.cancel()
    display.stop()
    buttons.stop()
    poller.stop()
    logger.info("All services stopped")


app = FastAPI(title="Thermomart Kiln Controller", version="0.1.0", lifespan=lifespan)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(status.router, prefix="/api")
app.include_router(control.router, prefix="/api")
app.include_router(programs.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(slots.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(ws.router, prefix="/api")

# Serve frontend static files if built
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

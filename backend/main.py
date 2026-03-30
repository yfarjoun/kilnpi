"""FastAPI application — startup, shutdown, route mounting."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api import control, history, programs, slots, stats, status, system_info, ws
from backend.api.slots import calculate_pro_offset, get_slot_assignments
from backend.config import settings
from backend.modbus.controller import ControllerInterface
from backend.modbus.mock_controller import MockController
from backend.models.database import async_session, init_db
from backend.models.schemas import Firing
from backend.services.buttons import ButtonState, create_button_service
from backend.services.display import DisplayService, create_display_and_splash
from backend.services.poller import ControllerState, Poller
from backend.services.power_poller import PowerPoller, PowerState
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


async def _restore_program_state(state: ControllerState) -> None:
    """After restart, restore active program info from the resumed firing record."""
    from sqlalchemy import select

    from backend.models.schemas import Program

    async with async_session() as session:
        # Find the active firing (set by recorder.recover_from_restart)
        result = await session.execute(
            select(Firing).where(Firing.status == "running").order_by(Firing.id.desc()).limit(1)
        )
        firing = result.scalar_one_or_none()
        if firing is None or firing.program_id is None:
            return

        state.active_program_id = firing.program_id
        state.active_program_name = firing.program_name

        # Load program segments
        program = await session.get(Program, firing.program_id)
        if program:
            state._active_segments = [dict(s) for s in program.segments]

            # Compute slot offset so segment indexing is correct
            assignments = await get_slot_assignments()
            for slot_name in ("A", "B"):
                a = assignments[slot_name]
                if a and a.program_id == firing.program_id:
                    state._pro_offset = calculate_pro_offset(assignments, slot_name)
                    break

        logger.info("Restored program state: %s (id=%s)", firing.program_name, firing.program_id)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    # Signal the splash service to stop — we're taking over the display
    Path("/tmp/kilnpi-ready").touch()

    oled = create_display_and_splash()
    await init_db()

    controller = _create_controller()
    state = ControllerState()

    # Power monitoring
    power_state = PowerState()
    if settings.mock_mode:
        from backend.modbus.mock_pzem import MockPzemReader
        pzem_l1 = MockPzemReader("L1")
        pzem_l2 = MockPzemReader("L2")
        bus_lock = None
    else:
        from backend.modbus.pzem import PzemReader
        pzem_l1 = PzemReader(settings.serial_port, settings.pzem_l1_address, settings.baud_rate)
        pzem_l2 = PzemReader(settings.serial_port, settings.pzem_l2_address, settings.baud_rate)
        bus_lock = controller.bus_lock  # type: ignore[union-attr]

    # Wire up API modules
    status.set_state(state)
    system_info.set_state(state)
    system_info.set_ws_client_count(ws.client_count)
    control.set_controller(controller)
    slots.set_controller(controller)
    slots.set_state(state)

    # Start background services
    poller = Poller(controller, state, interval=settings.poll_interval_sec)
    poller.start()
    # Wait for first poll so recover_from_restart sees actual controller state
    poller.wait_for_first_poll()

    power_poller = PowerPoller(
        pzem_l1, pzem_l2, power_state,
        interval=settings.pzem_poll_interval_sec,
        bus_lock=bus_lock,
    )
    power_poller.start()

    async def _update_mock_pzem_mv() -> None:
        while True:
            if settings.mock_mode and hasattr(pzem_l1, 'set_mv'):
                pzem_l1.set_mv(state.mv)
                pzem_l2.set_mv(state.mv)
            await asyncio.sleep(1)

    mock_pzem_task = asyncio.create_task(_update_mock_pzem_mv())

    recorder = Recorder(state, interval=settings.poll_interval_sec, power_state=power_state)

    # Restore program info from stale firing first (before recover potentially closes it)
    await _restore_program_state(state)
    await recorder.recover_from_restart()

    recorder_task = asyncio.create_task(recorder.run())

    button_state = ButtonState()
    buttons = create_button_service(button_state)
    buttons.start()

    display = DisplayService(
        state,
        ws.client_count,
        interval=5.0,
        button_state=button_state,
        display=oled,
        # TODO: pass power_state=power_state once DisplayService supports it
    )
    display.start()

    broadcast_task = asyncio.create_task(
        ws.broadcast_loop(state, power_state=power_state, interval=settings.poll_interval_sec)
    )

    logger.info("All services started (mock=%s)", settings.mock_mode)

    yield

    # Shutdown
    mock_pzem_task.cancel()
    broadcast_task.cancel()
    recorder_task.cancel()
    display.stop()
    buttons.stop()
    power_poller.stop()
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
app.include_router(system_info.router, prefix="/api")
app.include_router(ws.router, prefix="/api")

# Serve frontend static files if built
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

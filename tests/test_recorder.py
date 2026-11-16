"""Tests for the firing recorder service."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from backend.modbus.registers import RunMode
from backend.models.database import async_session, init_db
from backend.models.schemas import Firing, Reading
from backend.services.poller import ControllerState
from backend.services.recorder import (
    POLL_STALE_CLOSE_SEC,
    RESTART_STALE_READING_SEC,
    Recorder,
)


@pytest.fixture(autouse=True)
async def setup_db() -> None:
    await init_db()


async def _count_firings() -> int:
    async with async_session() as session:
        result = await session.execute(select(func.count()).select_from(Firing))
        return result.scalar() or 0


@pytest.mark.asyncio
async def test_recorder_starts_firing_on_run() -> None:
    state = ControllerState()
    recorder = Recorder(state, interval=0.05)

    # Simulate running state
    state.update(
        pv=100,
        sp=500,
        mv=50,
        run_mode=RunMode.RUNNING,
        segment=1,
        segment_elapsed_min=0,
        alarm1=False,
        alarm2=False,
    )

    task = asyncio.create_task(recorder.run())
    await asyncio.sleep(0.2)

    # Check that a new firing was created
    async with async_session() as session:
        result = await session.execute(
            select(Firing).where(Firing.status == "running").order_by(Firing.id.desc())
        )
        firings = result.scalars().all()
        assert len(firings) >= 1

        # Check readings were recorded for this firing
        result = await session.execute(select(Reading).where(Reading.firing_id == firings[0].id))
        readings = result.scalars().all()
        assert len(readings) >= 1

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_recorder_ends_firing_on_stop() -> None:
    state = ControllerState()
    recorder = Recorder(state, interval=0.05)

    # Start running
    state.update(
        pv=100,
        sp=500,
        mv=50,
        run_mode=RunMode.RUNNING,
        segment=1,
        segment_elapsed_min=0,
        alarm1=False,
        alarm2=False,
    )

    task = asyncio.create_task(recorder.run())
    await asyncio.sleep(0.15)

    # Stop
    state.update(
        pv=100,
        sp=500,
        mv=0,
        run_mode=RunMode.OFF,
        segment=0,
        segment_elapsed_min=0,
        alarm1=False,
        alarm2=False,
    )
    await asyncio.sleep(0.15)

    async with async_session() as session:
        result = await session.execute(
            select(Firing).where(Firing.status == "completed").order_by(Firing.id.desc())
        )
        firings = result.scalars().all()
        assert len(firings) >= 1

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_manual_firing_has_null_program_name() -> None:
    """A firing started without Pi-side program context (physical buttons,
    or mid-crash) must leave program_name=NULL in the DB so it stays out of
    /api/stats by_program aggregation. The display label is a frontend
    concern — baking it here would conflate "no program" with a program
    literally named "(manual)"."""
    state = ControllerState()  # active_program_name stays None
    recorder = Recorder(state, interval=0.05)

    state.update(
        pv=200,
        sp=800,
        mv=50,
        run_mode=RunMode.RUNNING,
        segment=1,
        segment_elapsed_min=0,
        alarm1=False,
        alarm2=False,
    )

    task = asyncio.create_task(recorder.run())
    await asyncio.sleep(0.2)

    async with async_session() as session:
        result = await session.execute(
            select(Firing).where(Firing.status == "running").order_by(Firing.id.desc())
        )
        firing = result.scalars().first()
        assert firing is not None
        assert firing.program_name is None
        assert firing.program_id is None

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_recorder_no_firing_when_idle() -> None:
    before_count = await _count_firings()

    state = ControllerState()
    recorder = Recorder(state, interval=0.05)

    # Stay idle
    state.update(
        pv=25,
        sp=25,
        mv=0,
        run_mode=RunMode.OFF,
        segment=0,
        segment_elapsed_min=0,
        alarm1=False,
        alarm2=False,
    )

    task = asyncio.create_task(recorder.run())
    await asyncio.sleep(0.15)

    after_count = await _count_firings()
    assert after_count == before_count  # No new firings

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_recover_from_restart_closes_long_gap_stale_firing() -> None:
    """A 'running' firing whose last reading is older than
    RESTART_STALE_READING_SEC must be closed as stale even when the
    controller currently reads active — a long gap means the Pi was down,
    not that the kiln has been firing all along."""
    state = ControllerState()
    recorder = Recorder(state, interval=0.05)

    old_ts = datetime.now(UTC) - timedelta(seconds=RESTART_STALE_READING_SEC + 300)
    async with async_session() as session:
        firing = Firing(started_at=old_ts.isoformat(), status="running", program_name="Old")
        session.add(firing)
        await session.commit()
        await session.refresh(firing)
        session.add(
            Reading(
                firing_id=firing.id,
                timestamp=old_ts.isoformat(),
                pv=500.0,
                sp=800.0,
                mv=80.0,
                segment=1,
            )
        )
        await session.commit()

    # Simulate the controller currently reporting "running" with a good poll —
    # recovery should STILL close as stale because of the reading gap.
    state.update(
        pv=500,
        sp=800,
        mv=80,
        run_mode=RunMode.RUNNING,
        segment=1,
        segment_elapsed_min=0,
        alarm1=False,
        alarm2=False,
    )
    state.last_poll_ok = True

    await recorder.recover_from_restart()

    async with async_session() as session:
        firings = (
            (await session.execute(select(Firing).order_by(Firing.id.desc()).limit(1)))
            .scalars()
            .all()
        )
        assert firings[0].status == "completed"
        # ended_at should be the last reading's timestamp, not "now".
        assert firings[0].ended_at == old_ts.isoformat()


@pytest.mark.asyncio
async def test_watchdog_closes_firing_after_poll_timeout() -> None:
    """When an active firing's polls have been failing longer than
    POLL_STALE_CLOSE_SEC, the recorder's main loop must auto-close it."""
    state = ControllerState()
    recorder = Recorder(state, interval=0.05)

    # Start a real firing.
    state.update(
        pv=500,
        sp=800,
        mv=80,
        run_mode=RunMode.RUNNING,
        segment=1,
        segment_elapsed_min=0,
        alarm1=False,
        alarm2=False,
    )
    state.last_poll_ok = True

    task = asyncio.create_task(recorder.run())
    await asyncio.sleep(0.15)
    assert recorder._current_firing_id is not None
    fid = recorder._current_firing_id

    # Simulate polls failing with a stale snapshot timestamp (older than
    # the watchdog threshold).
    state.last_poll_ok = False
    state.timestamp = (datetime.now(UTC) - timedelta(seconds=POLL_STALE_CLOSE_SEC + 60)).isoformat()

    await asyncio.sleep(0.2)

    async with async_session() as session:
        firing = await session.get(Firing, fid)
        assert firing is not None
        assert firing.status == "completed"

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

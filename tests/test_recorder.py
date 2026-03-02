"""Tests for the firing recorder service."""

import asyncio

import pytest
from sqlalchemy import func, select

from backend.modbus.registers import RunMode
from backend.models.database import async_session, init_db
from backend.models.schemas import Firing, Reading
from backend.services.poller import ControllerState
from backend.services.recorder import Recorder


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
        pv=100, sp=500, mv=50, run_mode=RunMode.RUNNING,
        segment=1, segment_elapsed_min=0, alarm=False,
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
        result = await session.execute(
            select(Reading).where(Reading.firing_id == firings[0].id)
        )
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
        pv=100, sp=500, mv=50, run_mode=RunMode.RUNNING,
        segment=1, segment_elapsed_min=0, alarm=False,
    )

    task = asyncio.create_task(recorder.run())
    await asyncio.sleep(0.15)

    # Stop
    state.update(
        pv=100, sp=500, mv=0, run_mode=RunMode.OFF,
        segment=0, segment_elapsed_min=0, alarm=False,
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
async def test_recorder_no_firing_when_idle() -> None:
    before_count = await _count_firings()

    state = ControllerState()
    recorder = Recorder(state, interval=0.05)

    # Stay idle
    state.update(
        pv=25, sp=25, mv=0, run_mode=RunMode.OFF,
        segment=0, segment_elapsed_min=0, alarm=False,
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

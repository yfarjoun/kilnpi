"""Firing recorder service — logs readings to DB during active firings."""

import asyncio
import logging
from datetime import UTC, datetime

from backend.models.database import async_session
from backend.models.schemas import Firing, Reading
from backend.services.poller import ControllerState

logger = logging.getLogger(__name__)


class Recorder:
    """Monitors controller state and records readings when a program is running."""

    def __init__(self, state: ControllerState, interval: float = 2.0) -> None:
        self._state = state
        self._interval = interval
        self._current_firing_id: int | None = None
        self._was_running = False

    async def run(self) -> None:
        """Main recording loop — runs as an asyncio task."""
        while True:
            try:
                snapshot = self._state.snapshot()
                is_running = snapshot["run_mode"] == "running"

                if is_running and not self._was_running:
                    await self._start_firing(snapshot)
                elif not is_running and self._was_running:
                    await self._end_firing()
                elif is_running and self._current_firing_id is not None:
                    await self._record_reading(snapshot)

                self._was_running = is_running
            except Exception:
                logger.exception("Recorder error")

            await asyncio.sleep(self._interval)

    async def _start_firing(self, snapshot: dict) -> None:
        now = datetime.now(UTC).isoformat()
        async with async_session() as session:
            firing = Firing(
                started_at=now,
                status="running",
                program_id=self._state.active_program_id,
                program_name=self._state.active_program_name,
            )
            session.add(firing)
            await session.commit()
            await session.refresh(firing)
            self._current_firing_id = firing.id
        logger.info("Started recording firing #%d", self._current_firing_id)
        await self._record_reading(snapshot)

    async def _end_firing(self) -> None:
        if self._current_firing_id is None:
            return
        now = datetime.now(UTC).isoformat()
        async with async_session() as session:
            firing = await session.get(Firing, self._current_firing_id)
            if firing:
                firing.ended_at = now
                firing.status = "completed"
                await session.commit()
        logger.info("Ended recording firing #%d", self._current_firing_id)
        self._current_firing_id = None

    async def _record_reading(self, snapshot: dict) -> None:
        if self._current_firing_id is None:
            return
        now = datetime.now(UTC).isoformat()
        async with async_session() as session:
            reading = Reading(
                firing_id=self._current_firing_id,
                timestamp=now,
                pv=snapshot["pv"],
                sp=snapshot["sp"],
                mv=snapshot["mv"],
                segment=snapshot["segment"],
            )
            session.add(reading)
            await session.commit()

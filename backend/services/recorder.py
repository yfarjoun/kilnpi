"""Firing recorder service — logs readings to DB during active firings."""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

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

    async def recover_from_restart(self) -> None:
        """Resume or close stale 'running' firings left by a previous process."""
        async with async_session() as session:
            result = await session.execute(
                select(Firing).where(Firing.status == "running").order_by(Firing.id.desc()).limit(1)
            )
            stale = result.scalar_one_or_none()
            if stale is None:
                return

            snapshot = self._state.snapshot()
            is_active = snapshot["run_mode"] in ("running", "standby")

            if is_active and self._state.last_poll_ok:
                # Controller is still running — resume recording into existing firing
                self._current_firing_id = stale.id
                self._was_running = True
                logger.info("Resumed firing #%d after restart", stale.id)
            else:
                # Controller not running (or no poll yet) — close the stale firing
                stale.ended_at = datetime.now(UTC).isoformat()
                stale.status = "completed"
                await session.commit()
                logger.info("Closed stale firing #%d after restart", stale.id)

    async def run(self) -> None:
        """Main recording loop — runs as an asyncio task."""
        while True:
            try:
                snapshot = self._state.snapshot()
                # Treat standby (paused) as still active — keep recording
                is_active = snapshot["run_mode"] in ("running", "standby")

                if is_active and not self._was_running:
                    await self._start_firing(snapshot)
                elif not is_active and self._was_running:
                    await self._end_firing()
                elif is_active and self._current_firing_id is not None:
                    await self._record_reading(snapshot)

                self._was_running = is_active
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
                sp=snapshot.get("program_target_temp") or snapshot["sp"],
                mv=snapshot["mv"],
                segment=snapshot["segment"],
            )
            session.add(reading)
            await session.commit()

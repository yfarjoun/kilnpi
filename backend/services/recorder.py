"""Firing recorder service — logs readings and manages firing lifecycle."""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import async_session
from backend.models.schemas import Firing, PowerReading, Reading
from backend.services import firing_stats
from backend.services.poller import ControllerState
from backend.services.power_poller import PowerState

logger = logging.getLogger(__name__)

# Close an active firing automatically when the poller has been failing this
# long. Covers "user flips the kiln breaker but leaves the Pi on" — the
# Thermomart dies, polls start failing, and after this window the firing
# gets ended with ended_at = last successful poll timestamp.
POLL_STALE_CLOSE_SEC = 30 * 60

# Close a "running" firing found at startup when its most recent reading is
# older than this. Covers "user shut down Pi + kiln together" — the recorded
# firing is from a prior session, not something to resume into.
RESTART_STALE_READING_SEC = 4 * 60 * 60


class Recorder:
    """Monitors controller state and records readings when a program is running."""

    def __init__(
        self,
        state: ControllerState,
        interval: float = 2.0,
        power_state: PowerState | None = None,
    ) -> None:
        self._state = state
        self._interval = interval
        self._power_state = power_state
        self._current_firing_id: int | None = None
        self._was_running = False

    async def _safe_compute_stats(self, session: AsyncSession, firing_id: int) -> None:
        """Compute and store firing_stats; log and swallow any failure so a
        stats error can't block the firing-end write path."""
        try:
            await firing_stats.compute_and_store(session, firing_id)
        except Exception:
            # Session may be mid-transaction after a flush error; roll back
            # so the next commit on this session (there isn't one in the
            # current callers, but be defensive) sees a clean state.
            try:
                await session.rollback()
            except Exception:
                pass
            logger.exception("Failed to compute firing_stats for #%d", firing_id)

    @staticmethod
    def _read_iso(ts: str) -> datetime:
        return datetime.fromisoformat(ts)

    async def recover_from_restart(self) -> None:
        """Handle a 'running' firing left in the DB by a previous process.

        Three paths:
        - Reading gap > RESTART_STALE_READING_SEC: close as stale even if the
          controller currently reads running. A long gap means the Pi was
          down; whatever the Thermomart is doing now belongs to a new firing
          that the main loop will pick up at the next OFF→RUNNING edge.
        - Controller currently active and recent reading: resume.
        - Otherwise: close as stale.

        In every "close as stale" path, firing_stats is precomputed from
        whatever readings are in the DB so the Statistics page doesn't need
        to scan them at request time.
        """
        async with async_session() as session:
            result = await session.execute(
                select(Firing).where(Firing.status == "running").order_by(Firing.id.desc()).limit(1)
            )
            stale = result.scalar_one_or_none()
            if stale is None:
                return

            last_ts = await self._last_reading_timestamp(session, stale.id)
            long_gap = (
                last_ts is not None
                and (datetime.now(UTC) - last_ts).total_seconds() > RESTART_STALE_READING_SEC
            )

            snapshot = self._state.snapshot()
            is_active = snapshot["run_mode"] in ("running", "standby")

            if is_active and self._state.last_poll_ok and not long_gap:
                self._current_firing_id = stale.id
                self._was_running = True
                logger.info("Resumed firing #%d after restart", stale.id)
                return

            # Close as stale. Use the last reading's timestamp (if any) as
            # ended_at so stats reflect the real end of observed activity
            # rather than this restart moment.
            stale.ended_at = last_ts.isoformat() if last_ts else datetime.now(UTC).isoformat()
            stale.status = "completed"
            await session.commit()
            stale_id = stale.id
            if long_gap:
                logger.info(
                    "Closed stale firing #%d after restart (reading gap > %d min)",
                    stale_id,
                    RESTART_STALE_READING_SEC // 60,
                )
            else:
                logger.info("Closed stale firing #%d after restart", stale_id)
            await self._safe_compute_stats(session, stale_id)

    async def _last_reading_timestamp(
        self, session: AsyncSession, firing_id: int
    ) -> datetime | None:
        """Return the newest reading timestamp for a firing, or None if the
        firing has no readings."""
        result = await session.execute(
            select(Reading.timestamp)
            .where(Reading.firing_id == firing_id)
            .order_by(Reading.timestamp.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._read_iso(row)

    async def run(self) -> None:
        """Main recording loop — runs as an asyncio task."""
        while True:
            try:
                snapshot = self._state.snapshot()
                # STANDBY (paused) counts as still active — keep recording.
                is_active = snapshot["run_mode"] in ("running", "standby")

                if is_active and not self._was_running:
                    await self._start_firing(snapshot)
                elif not is_active and self._was_running:
                    await self._end_firing()
                elif is_active and self._current_firing_id is not None:
                    if await self._poll_stale_should_close(snapshot):
                        await self._end_firing()
                    else:
                        await self._record_reading(snapshot)

                self._was_running = is_active and self._current_firing_id is not None
            except Exception:
                logger.exception("Recorder error")

            await asyncio.sleep(self._interval)

    async def _poll_stale_should_close(self, snapshot: dict) -> bool:
        """Return True when the active firing should auto-close because polls
        have been failing for too long. Compares `now` against the last
        snapshot timestamp; the poller only updates `state.timestamp` on a
        successful read, so a stale timestamp signals a dead controller."""
        last_ts_str = snapshot.get("timestamp") or ""
        if not last_ts_str or self._state.last_poll_ok:
            return False
        try:
            last_ts = self._read_iso(last_ts_str)
        except ValueError:
            return False
        if (datetime.now(UTC) - last_ts).total_seconds() < POLL_STALE_CLOSE_SEC:
            return False
        logger.info(
            "Closing firing #%d: poller has been failing for >%d min",
            self._current_firing_id,
            POLL_STALE_CLOSE_SEC // 60,
        )
        return True

    async def _start_firing(self, snapshot: dict) -> None:
        now = datetime.now(UTC).isoformat()
        # program_name stays None for firings without Pi-side program context
        # (physical buttons, manual sp writes, server crash before the HTTP
        # caller's name reached state). Storing a placeholder would leak
        # into /api/stats aggregation.
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
        logger.info(
            "Started recording firing #%d (%s)",
            self._current_firing_id,
            self._state.active_program_name or "manual",
        )
        await self._record_reading(snapshot)

    async def _end_firing(self) -> None:
        if self._current_firing_id is None:
            return
        fid = self._current_firing_id
        now = datetime.now(UTC).isoformat()
        async with async_session() as session:
            firing = await session.get(Firing, fid)
            if firing:
                firing.ended_at = now
                firing.status = "completed"
                await session.commit()
            await self._safe_compute_stats(session, fid)
        logger.info("Ended recording firing #%d", fid)
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
                # sp is the controller's static SP register ("soak target");
                # program_target_temp is the dynamic ramp-interpolated target.
                # The frontend displays program_target_temp ?? sp.
                sp=snapshot["sp"],
                mv=snapshot["mv"],
                segment=snapshot.get("program_segment") or snapshot["segment"],
                program_target_temp=snapshot.get("program_target_temp"),
            )
            session.add(reading)
            await self._record_power_reading(session, now)
            await session.commit()

    async def _record_power_reading(self, session: AsyncSession, timestamp: str) -> None:
        if self._current_firing_id is None or self._power_state is None:
            return
        snap = self._power_state.snapshot()
        if snap["l1_current"] is None:
            return
        pr = PowerReading(
            firing_id=self._current_firing_id,
            timestamp=timestamp,
            l1_voltage=snap["l1_voltage"],
            l1_current=snap["l1_current"],
            l1_power=snap["l1_power"],
        )
        session.add(pr)

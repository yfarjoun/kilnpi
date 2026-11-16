"""Tests for the firing_stats precompute service."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from backend.models.database import async_session, init_db
from backend.models.schemas import Firing, FiringStats, Reading
from backend.services.firing_stats import (
    compute_and_store,
    compute_firing_stats_from_readings,
)


@pytest.fixture(autouse=True)
async def _setup_db() -> None:
    await init_db()


async def _seed_firing(minutes_span: int = 90, pv_profile: list[float] | None = None) -> int:
    """Insert a completed firing with 1-min-spaced readings. Returns firing_id.
    PV defaults to a 0..800 linear ramp if no profile is given."""
    base = datetime(2025, 1, 1, tzinfo=UTC)
    async with async_session() as session:
        firing = Firing(
            started_at=base.isoformat(),
            ended_at=(base + timedelta(minutes=minutes_span)).isoformat(),
            status="completed",
            program_name="Test",
        )
        session.add(firing)
        await session.commit()
        await session.refresh(firing)
        fid: int = firing.id

        if pv_profile is None:
            pv_profile = [25 + (800 - 25) * i / (minutes_span - 1) for i in range(minutes_span)]
        for i, pv in enumerate(pv_profile):
            session.add(
                Reading(
                    firing_id=fid,
                    timestamp=(base + timedelta(minutes=i)).isoformat(),
                    pv=float(pv),
                    sp=800.0,
                    mv=80.0,
                    segment=1,
                )
            )
        await session.commit()
    return fid


def test_pure_compute_empty_readings_returns_zeroed_dict() -> None:
    result = compute_firing_stats_from_readings([])
    assert result["duration_min"] == 0.0
    assert result["max_temp"] == 0.0
    assert result["heating_rates"] == {}
    assert result["active_duration_min"] is None
    assert result["cutoff_timestamp"] is None


@pytest.mark.asyncio
async def test_compute_and_store_creates_row() -> None:
    fid = await _seed_firing(minutes_span=60)
    async with async_session() as session:
        stats = await compute_and_store(session, fid)
        assert stats is not None
        assert stats.firing_id == fid
        assert stats.max_temp > 0
        assert stats.duration_min > 0
        assert isinstance(stats.heating_rates, dict)
        assert stats.cutoff_timestamp is None  # linear ramp, no sitter


@pytest.mark.asyncio
async def test_compute_and_store_idempotent_upserts() -> None:
    """Second call must not create a duplicate row and must update computed_at."""
    fid = await _seed_firing(minutes_span=60)
    async with async_session() as session:
        first = await compute_and_store(session, fid)
        assert first is not None
        first_computed_at = first.computed_at

    # Bump by inserting another reading, re-compute, verify the row was updated
    # in place (same PK) and computed_at advanced.
    async with async_session() as session:
        later_ts = (datetime(2025, 1, 1, tzinfo=UTC) + timedelta(minutes=120)).isoformat()
        session.add(
            Reading(firing_id=fid, timestamp=later_ts, pv=1050.0, sp=800.0, mv=10.0, segment=1)
        )
        await session.commit()

    async with async_session() as session:
        second = await compute_and_store(session, fid)
        assert second is not None
        # Only one stats row exists for this firing.
        rows = (
            (await session.execute(select(FiringStats).where(FiringStats.firing_id == fid)))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert second.max_temp == 1050.0  # the new reading raised the max
        assert second.computed_at >= first_computed_at


@pytest.mark.asyncio
async def test_compute_and_store_no_readings_returns_none() -> None:
    """A firing with no readings yet can't be summarized; must not write a row."""
    async with async_session() as session:
        firing = Firing(started_at=datetime.now(UTC).isoformat(), status="running")
        session.add(firing)
        await session.commit()
        await session.refresh(firing)
        fid = firing.id

    async with async_session() as session:
        result = await compute_and_store(session, fid)
        assert result is None
        rows = (
            (await session.execute(select(FiringStats).where(FiringStats.firing_id == fid)))
            .scalars()
            .all()
        )
        assert rows == []


@pytest.mark.asyncio
async def test_firing_delete_cascades_to_stats() -> None:
    fid = await _seed_firing()
    async with async_session() as session:
        await compute_and_store(session, fid)

    async with async_session() as session:
        firing = await session.get(Firing, fid)
        assert firing is not None
        await session.delete(firing)
        await session.commit()

    async with async_session() as session:
        remaining = (
            (await session.execute(select(FiringStats).where(FiringStats.firing_id == fid)))
            .scalars()
            .all()
        )
        assert remaining == []


@pytest.mark.asyncio
async def test_lazy_backfill_via_summary_endpoint() -> None:
    """First call to /stats/summary against a DB with pre-existing completed
    firings (but no firing_stats rows) must populate them so the next call is
    index-only aggregates. Mirrors the migration case."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    fid = await _seed_firing()

    # Confirm no stats row exists yet — this is the pre-backfill state.
    async with async_session() as session:
        pre = (
            (await session.execute(select(FiringStats).where(FiringStats.firing_id == fid)))
            .scalars()
            .all()
        )
        assert pre == []

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/stats/summary")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_firings"] >= 1
            assert data["total_hours"] > 0

    # Row must exist after the call — that's the whole point of lazy backfill.
    async with async_session() as session:
        post = (
            (await session.execute(select(FiringStats).where(FiringStats.firing_id == fid)))
            .scalars()
            .all()
        )
        assert len(post) == 1
        assert post[0].max_temp > 0

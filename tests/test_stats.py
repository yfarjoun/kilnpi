"""Tests for kiln statistics endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.models.database import async_session
from backend.models.schemas import Firing, Reading


@pytest.fixture
async def client():  # type: ignore[no-untyped-def]
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
async def firing_with_readings(client: AsyncClient) -> int:
    """Create a completed firing with readings spanning a temperature range."""
    from datetime import UTC, datetime, timedelta

    base = datetime(2025, 1, 1, tzinfo=UTC)
    async with async_session() as session:
        firing = Firing(
            started_at=base.isoformat(),
            ended_at=(base + timedelta(hours=3)).isoformat(),
            status="completed",
            program_name="Test Program",
        )
        session.add(firing)
        await session.commit()
        await session.refresh(firing)
        fid: int = firing.id

        # Simulate heating then cooling: 25 -> 800 -> 200
        temps = (
            [(base + timedelta(minutes=i * 5), 25 + i * 50, 800.0, 80.0) for i in range(16)]  # heat up
            + [
                (base + timedelta(minutes=80 + i * 10), 800 - i * 60, 200.0, 0.0)
                for i in range(1, 11)
            ]  # cool down
        )
        for ts, pv, sp, mv in temps:
            reading = Reading(
                firing_id=fid,
                timestamp=ts.isoformat(),
                pv=float(pv),
                sp=sp,
                mv=mv,
                segment=1,
            )
            session.add(reading)
        await session.commit()
    return fid


@pytest.mark.asyncio
async def test_stats_summary(client: AsyncClient, firing_with_readings: int) -> None:
    resp = await client.get("/api/stats/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_firings"] >= 1
    assert data["total_hours"] > 0
    assert isinstance(data["by_program"], list)


@pytest.mark.asyncio
async def test_stats_summary_by_program(
    client: AsyncClient, firing_with_readings: int
) -> None:
    resp = await client.get("/api/stats/summary")
    data = resp.json()
    test_prog = next((p for p in data["by_program"] if p["name"] == "Test Program"), None)
    assert test_prog is not None
    assert test_prog["count"] >= 1
    assert test_prog["avg_max_temp"] > 0


@pytest.mark.asyncio
async def test_firing_stats(client: AsyncClient, firing_with_readings: int) -> None:
    resp = await client.get(f"/api/stats/firing/{firing_with_readings}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["duration_min"] > 0
    assert data["max_temp"] > 0
    assert data["avg_mv"] >= 0
    assert isinstance(data["heating_rates"], dict)
    assert data["cooling_rate"] > 0


@pytest.mark.asyncio
async def test_firing_stats_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/stats/firing/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_health_trend(client: AsyncClient, firing_with_readings: int) -> None:
    resp = await client.get("/api/stats/health")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # Should have at least some bands with data
    if data:
        assert "band" in data[0]
        assert "datapoints" in data[0]
        assert len(data[0]["datapoints"]) >= 1
        dp = data[0]["datapoints"][0]
        assert "firing_id" in dp
        assert "date" in dp
        assert "rate" in dp


@pytest.fixture
async def sitter_cutoff_firing(client: AsyncClient) -> int:
    """Firing where the kiln sitter trips: temp drops sharply while MV stays high."""
    from datetime import UTC, datetime, timedelta

    base = datetime(2025, 2, 1, tzinfo=UTC)
    async with async_session() as session:
        firing = Firing(
            started_at=base.isoformat(),
            ended_at=(base + timedelta(hours=4)).isoformat(),
            status="completed",
            program_name="Sitter Test",
        )
        session.add(firing)
        await session.commit()
        await session.refresh(firing)
        fid: int = firing.id

        readings_data = (
            # Heat up: 25 -> 800 over 80 min, MV=80
            [(base + timedelta(minutes=i * 5), 25 + i * 50, 800.0, 80.0) for i in range(16)]
            # Sitter trips at peak: temp drops sharply but MV stays high
            + [
                (base + timedelta(minutes=80 + i * 5), 800 - i * 40, 800.0, 85.0)
                for i in range(1, 11)
            ]
            # Eventually MV drops too as controller gives up
            + [
                (base + timedelta(minutes=130 + i * 10), 400 - i * 30, 200.0, 5.0)
                for i in range(1, 6)
            ]
        )
        for ts, pv, sp, mv in readings_data:
            session.add(
                Reading(firing_id=fid, timestamp=ts.isoformat(), pv=float(pv), sp=sp, mv=mv, segment=1)
            )
        await session.commit()
    return fid


@pytest.fixture
async def normal_firing(client: AsyncClient) -> int:
    """Normal firing where MV drops with temperature (no sitter cutoff)."""
    from datetime import UTC, datetime, timedelta

    base = datetime(2025, 3, 1, tzinfo=UTC)
    async with async_session() as session:
        firing = Firing(
            started_at=base.isoformat(),
            ended_at=(base + timedelta(hours=3)).isoformat(),
            status="completed",
            program_name="Normal Test",
        )
        session.add(firing)
        await session.commit()
        await session.refresh(firing)
        fid: int = firing.id

        readings_data = (
            # Heat up: 25 -> 800, MV=80
            [(base + timedelta(minutes=i * 5), 25 + i * 50, 800.0, 80.0) for i in range(16)]
            # Cool down: program ended normally, MV drops immediately to 0
            + [
                (base + timedelta(minutes=80 + i * 10), 800 - i * 60, 200.0, 0.0)
                for i in range(1, 11)
            ]
        )
        for ts, pv, sp, mv in readings_data:
            session.add(
                Reading(firing_id=fid, timestamp=ts.isoformat(), pv=float(pv), sp=sp, mv=float(mv), segment=1)
            )
        await session.commit()
    return fid


@pytest.mark.asyncio
async def test_sitter_cutoff_detected(client: AsyncClient, sitter_cutoff_firing: int) -> None:
    resp = await client.get(f"/api/stats/firing/{sitter_cutoff_firing}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cutoff_timestamp"] is not None
    assert data["active_duration_min"] is not None
    assert data["active_duration_min"] < data["duration_min"]


@pytest.mark.asyncio
async def test_no_false_cutoff(client: AsyncClient, normal_firing: int) -> None:
    """Normal firing should NOT trigger sitter cutoff detection."""
    resp = await client.get(f"/api/stats/firing/{normal_firing}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cutoff_timestamp"] is None
    assert data["active_duration_min"] is None

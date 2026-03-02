"""Tests for firing history endpoints."""

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
    """Create a firing with readings directly in the DB."""
    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()
    async with async_session() as session:
        firing = Firing(started_at=now, ended_at=now, status="completed", program_name="Test")
        session.add(firing)
        await session.commit()
        await session.refresh(firing)
        fid: int = firing.id

        for i in range(5):
            reading = Reading(
                firing_id=fid, timestamp=now, pv=100.0 + i, sp=200.0, mv=50.0, segment=1
            )
            session.add(reading)
        await session.commit()
    return fid


@pytest.mark.asyncio
async def test_firings_list_with_data(
    client: AsyncClient, firing_with_readings: int
) -> None:
    resp = await client.get("/api/firings")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(f["id"] == firing_with_readings for f in data)


@pytest.mark.asyncio
async def test_firing_detail(
    client: AsyncClient, firing_with_readings: int
) -> None:
    resp = await client.get(f"/api/firings/{firing_with_readings}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["firing"]["id"] == firing_with_readings
    assert data["firing"]["status"] == "completed"
    assert len(data["readings"]) == 5


@pytest.mark.asyncio
async def test_firing_csv_export(
    client: AsyncClient, firing_with_readings: int
) -> None:
    resp = await client.get(f"/api/firings/{firing_with_readings}/csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    content = resp.text
    lines = content.strip().splitlines()
    assert lines[0].strip() == "timestamp,pv,sp,mv,segment"
    assert len(lines) == 6  # header + 5 readings

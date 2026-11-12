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
async def test_firings_list_with_data(client: AsyncClient, firing_with_readings: int) -> None:
    resp = await client.get("/api/firings")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(f["id"] == firing_with_readings for f in data)


@pytest.mark.asyncio
async def test_firing_detail(client: AsyncClient, firing_with_readings: int) -> None:
    resp = await client.get(f"/api/firings/{firing_with_readings}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["firing"]["id"] == firing_with_readings
    assert data["firing"]["status"] == "completed"
    assert len(data["readings"]) == 5


@pytest.mark.asyncio
async def test_firing_csv_export(client: AsyncClient, firing_with_readings: int) -> None:
    resp = await client.get(f"/api/firings/{firing_with_readings}/csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    content = resp.text
    lines = content.strip().splitlines()
    assert lines[0].strip() == "timestamp,pv,sp,mv,segment"
    assert len(lines) == 6  # header + 5 readings


@pytest.mark.asyncio
async def test_delete_firing(client: AsyncClient, firing_with_readings: int) -> None:
    resp = await client.delete(f"/api/firings/{firing_with_readings}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    # Verify gone
    resp = await client.get(f"/api/firings/{firing_with_readings}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_firing_not_found(client: AsyncClient) -> None:
    resp = await client.delete("/api/firings/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_notes(client: AsyncClient, firing_with_readings: int) -> None:
    resp = await client.patch(
        f"/api/firings/{firing_with_readings}/notes",
        json={"notes": "Test glaze — cone 6"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["notes"] == "Test glaze — cone 6"
    assert data["id"] == firing_with_readings
    # Verify persisted
    resp = await client.get(f"/api/firings/{firing_with_readings}")
    assert resp.json()["firing"]["notes"] == "Test glaze — cone 6"


@pytest.mark.asyncio
async def test_update_notes_not_found(client: AsyncClient) -> None:
    resp = await client.patch("/api/firings/99999/notes", json={"notes": "nope"})
    assert resp.status_code == 404


@pytest.fixture
async def long_firing(client: AsyncClient) -> int:
    """Firing with 1000 readings spaced 1s apart, pv ramping linearly."""
    from datetime import UTC, datetime, timedelta

    t0 = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=1000)
    async with async_session() as session:
        firing = Firing(started_at=t0.isoformat(), status="running", program_name="LongTest")
        session.add(firing)
        await session.commit()
        await session.refresh(firing)
        fid: int = firing.id

        for i in range(1000):
            ts = (t0 + timedelta(seconds=i)).isoformat()
            session.add(
                Reading(
                    firing_id=fid,
                    timestamp=ts,
                    pv=float(i),
                    sp=1000.0,
                    mv=50.0,
                    segment=1,
                    program_target_temp=float(i) + 10.0,
                )
            )
        await session.commit()
    return fid


@pytest.mark.asyncio
async def test_bucket_downsample_cap(client: AsyncClient, long_firing: int) -> None:
    """1000 rows with max_points=100 should bucket-mean to ~100 rows."""
    resp = await client.get(f"/api/firings/{long_firing}?max_points=100")
    assert resp.status_code == 200
    readings = resp.json()["readings"]
    # NTILE(100) over 1000 rows → exactly 100 buckets
    assert len(readings) == 100
    # First bucket averages pv=0..9 → 4.5; last → 990..999 → 994.5
    assert readings[0]["pv"] == pytest.approx(4.5)
    assert readings[-1]["pv"] == pytest.approx(994.5)
    # program_target_temp averaged the same way (+10 offset)
    assert readings[0]["program_target_temp"] == pytest.approx(14.5)


@pytest.mark.asyncio
async def test_bucket_passthrough_when_below_cap(client: AsyncClient, long_firing: int) -> None:
    """max_points > row count → each row its own bucket, values pass through."""
    resp = await client.get(f"/api/firings/{long_firing}?max_points=10000")
    assert resp.status_code == 200
    readings = resp.json()["readings"]
    assert len(readings) == 1000
    assert readings[0]["pv"] == 0.0
    assert readings[-1]["pv"] == 999.0


@pytest.mark.asyncio
async def test_since_filter(client: AsyncClient, long_firing: int) -> None:
    """`since` crops older rows before bucketing. Params go through httpx's
    `params=` so '+' in the ISO offset is URL-encoded correctly; passing the
    timestamp via f-string decodes '+' as a space on the server side."""
    resp = await client.get(f"/api/firings/{long_firing}", params={"max_points": 10000})
    all_readings = resp.json()["readings"]
    midpoint = all_readings[500]["timestamp"]
    resp = await client.get(
        f"/api/firings/{long_firing}",
        params={"max_points": 10000, "since": midpoint},
    )
    assert resp.status_code == 200
    kept = resp.json()["readings"]
    assert len(kept) == 500  # rows 500..999
    assert kept[0]["pv"] == 500.0


@pytest.mark.asyncio
async def test_until_filter(client: AsyncClient, long_firing: int) -> None:
    """`until` crops newer rows before bucketing."""
    resp = await client.get(f"/api/firings/{long_firing}", params={"max_points": 10000})
    all_readings = resp.json()["readings"]
    midpoint = all_readings[500]["timestamp"]
    resp = await client.get(
        f"/api/firings/{long_firing}",
        params={"max_points": 10000, "until": midpoint},
    )
    assert resp.status_code == 200
    kept = resp.json()["readings"]
    assert len(kept) == 501  # rows 0..500 inclusive


@pytest.mark.asyncio
async def test_garbage_since_rejected(client: AsyncClient, long_firing: int) -> None:
    """Non-ISO `since` returns 422, not a silent empty 200."""
    resp = await client.get(f"/api/firings/{long_firing}", params={"since": "yesterday"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_since_after_until_rejected(client: AsyncClient, long_firing: int) -> None:
    """since > until is a client error, not a silent empty 200."""
    resp = await client.get(
        f"/api/firings/{long_firing}",
        params={
            "since": "2026-11-11T12:00:00Z",
            "until": "2026-11-11T11:00:00Z",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_since_with_z_suffix_matches_storage_format(
    client: AsyncClient, long_firing: int
) -> None:
    """Frontend sends ISO with 'Z' suffix; storage uses '+00:00'. The
    normalization layer must make lexical comparison equivalent so rows at
    the cutoff second aren't silently dropped."""
    resp = await client.get(f"/api/firings/{long_firing}", params={"max_points": 10000})
    all_readings = resp.json()["readings"]
    midpoint_ts = all_readings[500]["timestamp"]  # has '+00:00'
    # Convert to the 'Z' form the frontend uses.
    from datetime import datetime

    z_form = (
        datetime.fromisoformat(midpoint_ts).isoformat().replace("+00:00", "Z")
        if "+00:00" in midpoint_ts
        else midpoint_ts
    )
    resp = await client.get(
        f"/api/firings/{long_firing}",
        params={"max_points": 10000, "since": z_form},
    )
    assert resp.status_code == 200
    kept = resp.json()["readings"]
    # Same cutoff regardless of 'Z' vs '+00:00' spelling.
    assert len(kept) == 500
    assert kept[0]["pv"] == 500.0

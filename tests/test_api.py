"""Tests for API endpoints using FastAPI test client."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.fixture
async def client():  # type: ignore[no-untyped-def]
    """Create an async test client with lifespan events triggered."""
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.mark.asyncio
async def test_get_status(client: AsyncClient) -> None:
    resp = await client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "pv" in data
    assert "sp" in data
    assert "mv" in data
    assert "run_mode" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_set_and_read_setpoint(client: AsyncClient) -> None:
    resp = await client.post("/api/setpoint", json={"value": 500.0})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["sp"] == 500.0


@pytest.mark.asyncio
async def test_pid_read(client: AsyncClient) -> None:
    resp = await client.get("/api/pid")
    assert resp.status_code == 200
    data = resp.json()
    assert "p" in data
    assert "i" in data
    assert "d" in data
    assert "cycle_time" in data


@pytest.mark.asyncio
async def test_pid_write(client: AsyncClient) -> None:
    resp = await client.put("/api/pid", json={"p": 200, "i": 600, "d": 150, "cycle_time": 30})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_program_crud(client: AsyncClient) -> None:
    # Create
    prog = {
        "name": "Test Firing",
        "description": "A test program",
        "segments": [
            {"ramp_min": 30, "soak_min": 60, "target_temp": 500.0},
            {"ramp_min": 60, "soak_min": 120, "target_temp": 1000.0},
        ],
    }
    resp = await client.post("/api/programs", json=prog)
    assert resp.status_code == 201
    created = resp.json()
    prog_id = created["id"]
    assert created["name"] == "Test Firing"
    assert len(created["segments"]) == 2

    # List
    resp = await client.get("/api/programs")
    assert resp.status_code == 200
    assert any(p["id"] == prog_id for p in resp.json())

    # Read
    resp = await client.get(f"/api/programs/{prog_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test Firing"

    # Update
    resp = await client.put(f"/api/programs/{prog_id}", json={"name": "Updated Firing"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Firing"

    # Delete
    resp = await client.delete(f"/api/programs/{prog_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify deleted
    resp = await client.get(f"/api/programs/{prog_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_program_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/programs/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_firings_list(client: AsyncClient) -> None:
    resp = await client.get("/api/firings")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_firing_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/firings/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_firing_csv_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/firings/99999/csv")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_controller_program(client: AsyncClient) -> None:
    segments = [{"ramp_min": 30, "soak_min": 60, "target_temp": 500.0}]
    resp = await client.put("/api/controller/program", json=segments)
    assert resp.status_code == 200
    assert resp.json()["segments"] == 1

    resp = await client.get("/api/controller/program")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["target_temp"] == 500.0


@pytest.mark.asyncio
async def test_start_stop_program(client: AsyncClient) -> None:
    segments = [{"ramp_min": 30, "soak_min": 60, "target_temp": 500.0}]
    await client.put("/api/controller/program", json=segments)

    resp = await client.post("/api/program/start")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    resp = await client.post("/api/program/stop")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_autotune(client: AsyncClient) -> None:
    resp = await client.post("/api/autotune", json={"start": True})
    assert resp.status_code == 200
    assert resp.json()["autotuning"] is True

    resp = await client.post("/api/autotune", json={"start": False})
    assert resp.status_code == 200
    assert resp.json()["autotuning"] is False

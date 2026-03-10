"""Tests for slot assignment and firing API."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.fixture
async def client():  # type: ignore[no-untyped-def]
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _create_program(client: AsyncClient, name: str, segs: int = 2) -> int:
    segments = [
        {"ramp_min": 30 * (i + 1), "soak_min": 60, "target_temp": 500.0 + i * 200}
        for i in range(segs)
    ]
    resp = await client.post("/api/programs", json={"name": name, "segments": segments})
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_get_slots_initial(client: AsyncClient) -> None:
    resp = await client.get("/api/slots")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["slot"] == "A"
    assert data[0]["program"] is None
    assert data[1]["slot"] == "B"
    assert data[1]["program"] is None


@pytest.mark.asyncio
async def test_assign_slot(client: AsyncClient) -> None:
    prog_id = await _create_program(client, "Bisque Test")

    resp = await client.put("/api/slots/A/assign", json={"program_id": prog_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["slot"] == "A"
    assert data["program"]["id"] == prog_id
    assert data["program"]["name"] == "Bisque Test"


@pytest.mark.asyncio
async def test_assign_both_slots(client: AsyncClient) -> None:
    bisque_id = await _create_program(client, "Bisque", segs=2)
    glaze_id = await _create_program(client, "Glaze", segs=3)

    await client.put("/api/slots/A/assign", json={"program_id": bisque_id})
    await client.put("/api/slots/B/assign", json={"program_id": glaze_id})

    resp = await client.get("/api/slots")
    data = resp.json()
    assert data[0]["program"]["name"] == "Bisque"
    assert data[1]["program"]["name"] == "Glaze"


@pytest.mark.asyncio
async def test_assign_invalid_slot(client: AsyncClient) -> None:
    resp = await client.put("/api/slots/C/assign", json={"program_id": 1})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_assign_nonexistent_program(client: AsyncClient) -> None:
    resp = await client.put("/api/slots/A/assign", json={"program_id": 99999})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unassign_slot(client: AsyncClient) -> None:
    prog_id = await _create_program(client, "To Remove")
    await client.put("/api/slots/A/assign", json={"program_id": prog_id})

    resp = await client.delete("/api/slots/A/assign")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    resp = await client.get("/api/slots")
    data = resp.json()
    assert data[0]["program"] is None


@pytest.mark.asyncio
async def test_fire_slot(client: AsyncClient) -> None:
    prog_id = await _create_program(client, "Fire Test")
    await client.put("/api/slots/A/assign", json={"program_id": prog_id})

    resp = await client.post("/api/slots/A/fire")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["slot"] == "A"
    assert data["program"] == "Fire Test"
    assert data["pro_value"] == 0  # PRO=0 = start from beginning

    # Stop so other tests aren't affected
    await client.post("/api/program/stop")


@pytest.mark.asyncio
async def test_fire_slot_b_start_segment(client: AsyncClient) -> None:
    bisque_id = await _create_program(client, "Bisque Fire", segs=2)
    glaze_id = await _create_program(client, "Glaze Fire", segs=3)
    await client.put("/api/slots/A/assign", json={"program_id": bisque_id})
    await client.put("/api/slots/B/assign", json={"program_id": glaze_id})

    resp = await client.post("/api/slots/B/fire")
    assert resp.status_code == 200
    data = resp.json()
    # Slot B: skip A's 2 segs (4 PRO) + end marker (1 PRO) = PRO 7
    assert data["pro_value"] == 7

    await client.post("/api/program/stop")


@pytest.mark.asyncio
async def test_fire_unassigned_slot(client: AsyncClient) -> None:
    # Ensure slot B is unassigned
    await client.delete("/api/slots/B/assign")
    resp = await client.post("/api/slots/B/fire")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_fire_when_running_409(client: AsyncClient) -> None:
    prog_id = await _create_program(client, "Running Test")
    await client.put("/api/slots/A/assign", json={"program_id": prog_id})

    # Start via slot fire
    resp = await client.post("/api/slots/A/fire")
    assert resp.status_code == 200

    # Try to fire again while running
    resp = await client.post("/api/slots/A/fire")
    assert resp.status_code == 409

    await client.post("/api/program/stop")


@pytest.mark.asyncio
async def test_reassign_slot(client: AsyncClient) -> None:
    prog1 = await _create_program(client, "First")
    prog2 = await _create_program(client, "Second")

    await client.put("/api/slots/A/assign", json={"program_id": prog1})
    resp = await client.put("/api/slots/A/assign", json={"program_id": prog2})
    assert resp.status_code == 200
    assert resp.json()["program"]["name"] == "Second"


@pytest.mark.asyncio
async def test_mock_controller_start_segment() -> None:
    from backend.dto import Segment
    from backend.modbus.mock_controller import MockController

    ctrl = MockController()
    # Write a combined program: 2 segments for A, end marker, 2 for B, end marker
    combined = [
        Segment(ramp_min=30, soak_min=60, target_temp=500),
        Segment(ramp_min=30, soak_min=60, target_temp=800),
        Segment(ramp_min=0, soak_min=0, target_temp=0),  # end marker
        Segment(ramp_min=60, soak_min=120, target_temp=1000),
        Segment(ramp_min=30, soak_min=60, target_temp=1200),
        Segment(ramp_min=0, soak_min=0, target_temp=0),  # end marker
    ]
    ctrl.write_program(combined)

    # Fire slot B (starts at index 3)
    ctrl.write_start_segment(3)
    ctrl.start_program()

    assert ctrl._current_segment == 3
    assert ctrl._sp == 1000.0

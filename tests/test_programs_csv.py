"""Tests for program CSV export/import endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.fixture
async def client():  # type: ignore[no-untyped-def]
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
async def program_id(client: AsyncClient) -> int:
    """Create a test program and return its ID."""
    prog = {
        "name": "Bisque",
        "description": "A bisque firing program",
        "segments": [
            {"ramp_min": 30, "soak_min": 60, "target_temp": 500.0},
            {"ramp_min": 60, "soak_min": 120, "target_temp": 1000.0},
        ],
    }
    resp = await client.post("/api/programs", json=prog)
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_export_csv(client: AsyncClient, program_id: int) -> None:
    resp = await client.get(f"/api/programs/{program_id}/csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]

    lines = resp.text.strip().splitlines()
    assert lines[0] == "#name,Bisque"
    assert lines[1] == "#description,A bisque firing program"
    assert lines[2].strip() == "ramp_min,soak_min,target_temp"
    assert len(lines) == 5  # 2 metadata + header + 2 segments


@pytest.mark.asyncio
async def test_export_csv_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/programs/99999/csv")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_import_csv(client: AsyncClient) -> None:
    csv_content = (
        "#name,Imported Test\n"
        "#description,Imported desc\n"
        "ramp_min,soak_min,target_temp\n"
        "30,60,500.0\n"
        "60,120,1000.0\n"
    )
    resp = await client.post(
        "/api/programs/import",
        files={"file": ("test.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Imported Test"
    assert data["description"] == "Imported desc"
    assert len(data["segments"]) == 2
    assert data["segments"][0]["ramp_min"] == 30
    assert data["segments"][1]["target_temp"] == 1000.0


@pytest.mark.asyncio
async def test_roundtrip_export_import(client: AsyncClient, program_id: int) -> None:
    """Export a program as CSV, then import it back and verify segments match."""
    # Export
    resp = await client.get(f"/api/programs/{program_id}/csv")
    assert resp.status_code == 200
    csv_content = resp.text

    # Import
    resp = await client.post(
        "/api/programs/import",
        files={"file": ("roundtrip.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 201
    imported = resp.json()

    # Get original
    resp = await client.get(f"/api/programs/{program_id}")
    original = resp.json()

    assert len(imported["segments"]) == len(original["segments"])
    for imp_seg, orig_seg in zip(imported["segments"], original["segments"]):
        assert imp_seg["ramp_min"] == orig_seg["ramp_min"]
        assert imp_seg["soak_min"] == orig_seg["soak_min"]
        assert imp_seg["target_temp"] == orig_seg["target_temp"]


@pytest.mark.asyncio
async def test_import_invalid_csv(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/programs/import",
        files={"file": ("bad.csv", "just a line\n", "text/csv")},
    )
    assert resp.status_code == 400

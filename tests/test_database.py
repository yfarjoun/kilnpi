"""Tests for the init_db migrations."""

import os
import tempfile

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_composite_indexes_backfilled_on_legacy_db() -> None:
    """Simulate a Pi DB whose readings/power_readings tables predate the
    ORM composite-index declarations. init_db() must create them, and a
    second run must be a no-op (idempotent)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        # Build a legacy schema: tables exist, indexes do not.
        legacy_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}")
        async with legacy_engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TABLE firings (id INTEGER PRIMARY KEY, "
                    "program_id INTEGER, program_name TEXT, started_at TEXT, "
                    "ended_at TEXT, status TEXT, notes TEXT)"
                )
            )
            await conn.execute(
                text(
                    "CREATE TABLE readings (id INTEGER PRIMARY KEY, "
                    "firing_id INTEGER NOT NULL, timestamp TEXT NOT NULL, "
                    "pv REAL NOT NULL, sp REAL NOT NULL, mv REAL NOT NULL, "
                    "segment INTEGER)"
                )
            )
            await conn.execute(
                text(
                    "CREATE TABLE power_readings (id INTEGER PRIMARY KEY, "
                    "firing_id INTEGER NOT NULL, timestamp TEXT NOT NULL, "
                    "l1_voltage REAL NOT NULL, l1_current REAL NOT NULL, "
                    "l1_power REAL NOT NULL)"
                )
            )
        await legacy_engine.dispose()

        # Now re-point init_db at that file and run the migrations. We can't
        # just call init_db() directly because the global engine was bound
        # at import time — build a parallel one from the same migration
        # callables.
        from backend.models import database

        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}")
        async with engine.begin() as conn:
            await database._add_composite_indexes(conn)

        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")
                )
            ).fetchall()
        names = {r[0] for r in rows}
        assert "idx_readings_firing_ts" in names
        assert "idx_power_readings_firing_ts" in names

        # Second run: idempotent.
        async with engine.begin() as conn:
            await database._add_composite_indexes(conn)
        async with engine.connect() as conn:
            rows = (
                await conn.execute(text("PRAGMA index_info(idx_readings_firing_ts)"))
            ).fetchall()
        cols = [r[2] for r in rows]  # (seqno, cid, name)
        assert cols == ["firing_id", "timestamp"]
        await engine.dispose()
    finally:
        os.unlink(tmp.name)

"""SQLAlchemy async engine and session setup."""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.db_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Create all tables and run idempotent in-place migrations."""
    from backend.models.schemas import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _drop_legacy_power_l2_columns(conn)


async def _drop_legacy_power_l2_columns(conn) -> None:
    """Drop l2_voltage/l2_current/l2_power from power_readings if a pre-existing
    DB still has them. Single-PZEM setups have no use for them, and their
    NOT NULL constraint would block new inserts after the schema change.

    Requires SQLite >= 3.35 (Trixie/Debian 13 ships 3.46+). Idempotent: skips
    any column that is already absent.
    """
    rows = (await conn.execute(text("PRAGMA table_info(power_readings)"))).fetchall()
    present = {row[1] for row in rows}  # row[1] is the column name
    for col in ("l2_voltage", "l2_current", "l2_power"):
        if col in present:
            logger.info("Migrating: dropping legacy column power_readings.%s", col)
            await conn.execute(text(f"ALTER TABLE power_readings DROP COLUMN {col}"))


async def get_session() -> AsyncSession:  # type: ignore[misc]
    async with async_session() as session:
        yield session  # type: ignore[misc]

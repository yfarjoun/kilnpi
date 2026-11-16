"""SQLAlchemy async engine and session setup."""

import logging

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.db_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# SQLite PRAGMAs applied on every new raw connection.
#   - busy_timeout: any statement waits up to 5s for the write lock instead
#     of SQLITE_BUSY immediately. Set first so the WAL conversion below has
#     a timeout in its own pocket if another writer holds the lock.
#   - journal_mode=WAL: concurrent readers don't block the recorder's
#     writes on the Pi's single core.
#   - synchronous=NORMAL: the standard pairing with WAL. Commit fsync drops
#     from per-commit to on checkpoint; at most the last transaction is lost
#     on power loss, the DB stays consistent.
#   - foreign_keys=ON: enforces ondelete semantics (notably firing_stats
#     CASCADE) at the DB level, not only through the ORM relationship.
@event.listens_for(engine.sync_engine, "connect")
def _enable_sqlite_pragmas(dbapi_conn: object, _record: object) -> None:
    cur = dbapi_conn.cursor()  # type: ignore[attr-defined]
    cur.execute("PRAGMA busy_timeout=5000")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


async def init_db() -> None:
    """Create all tables and run idempotent in-place migrations."""
    from backend.models.schemas import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _drop_legacy_power_l2_columns(conn)
        await _add_program_target_temp_column(conn)
        await _backfill_declared_indexes(conn)


async def _backfill_declared_indexes(conn: AsyncConnection) -> None:
    """Backfill ORM-declared indexes on pre-existing tables.

    `create_all` only builds indexes alongside fresh tables, so a legacy DB
    whose tables predate current index declarations won't have them. Iterate
    the ORM metadata (rather than hardcoding names) so the two sources can't
    drift — new indexes added to any model's __table_args__ get backfilled
    automatically on next startup.
    """
    from backend.models.schemas import Base

    def _create_sync(sync_conn) -> None:  # type: ignore[no-untyped-def]
        for table in Base.metadata.sorted_tables:
            for index in table.indexes:
                index.create(sync_conn, checkfirst=True)

    await conn.run_sync(_create_sync)


async def _add_program_target_temp_column(conn: AsyncConnection) -> None:
    """Add readings.program_target_temp if missing — preserves old firing
    data while letting new readings store the ramp-interpolated target."""
    rows = (await conn.execute(text("PRAGMA table_info(readings)"))).fetchall()
    present = {row[1] for row in rows}
    if "program_target_temp" not in present:
        logger.info("Migrating: adding readings.program_target_temp column")
        await conn.execute(text("ALTER TABLE readings ADD COLUMN program_target_temp REAL"))


async def _drop_legacy_power_l2_columns(conn: AsyncConnection) -> None:
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

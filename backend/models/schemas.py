"""SQLAlchemy ORM models."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    segments_json: Mapped[str] = mapped_column("segments", String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, default=lambda: datetime.now(UTC).isoformat())
    updated_at: Mapped[str] = mapped_column(String, default=lambda: datetime.now(UTC).isoformat())

    firings: Mapped[list[Firing]] = relationship(back_populates="program")

    @property
    def segments(self) -> list[dict]:  # type: ignore[type-arg]
        result: list[dict] = json.loads(self.segments_json)  # type: ignore[type-arg]
        return result

    @segments.setter
    def segments(self, value: list[dict]) -> None:  # type: ignore[type-arg]
        self.segments_json = json.dumps(value)


class SlotAssignment(Base):
    __tablename__ = "slot_assignments"

    slot: Mapped[str] = mapped_column(String, primary_key=True)  # "A" or "B"
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"), nullable=False)
    assigned_at: Mapped[str] = mapped_column(String, default=lambda: datetime.now(UTC).isoformat())

    program: Mapped[Program] = relationship()


class Firing(Base):
    __tablename__ = "firings"

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int | None] = mapped_column(ForeignKey("programs.id"), nullable=True)
    program_name: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[str] = mapped_column(String, nullable=False)
    ended_at: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="running")
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    program: Mapped[Program | None] = relationship(back_populates="firings")
    readings: Mapped[list[Reading]] = relationship(
        back_populates="firing", cascade="all, delete-orphan"
    )
    power_readings: Mapped[list[PowerReading]] = relationship(
        back_populates="firing", cascade="all, delete-orphan"
    )
    # FiringStats is defined later in this module; the quoted annotation is a
    # forward reference (ruff UP037 wants it unquoted, but pyright can't resolve
    # it unquoted since the class isn't declared yet at this point in the file).
    stats: Mapped["FiringStats | None"] = relationship(  # noqa: UP037
        back_populates="firing", cascade="all, delete-orphan", uselist=False
    )

    # /api/stats/* queries filter on status='completed'.
    __table_args__ = (Index("idx_firings_status", "status"),)


class Reading(Base):
    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    firing_id: Mapped[int] = mapped_column(ForeignKey("firings.id"), nullable=False)
    timestamp: Mapped[str] = mapped_column(String, nullable=False)
    pv: Mapped[float] = mapped_column(nullable=False)
    sp: Mapped[float] = mapped_column(nullable=False)
    mv: Mapped[float] = mapped_column(nullable=False)
    segment: Mapped[int | None] = mapped_column(nullable=True)
    # Dynamic target the controller is interpolating toward during a ramp.
    # Nullable: old rows and manual firings without _active_segments leave it None.
    # When None, frontends fall back to displaying `sp`.
    program_target_temp: Mapped[float | None] = mapped_column(nullable=True)

    firing: Mapped[Firing] = relationship(back_populates="readings")

    __table_args__ = (Index("idx_readings_firing_ts", "firing_id", "timestamp"),)


class PowerReading(Base):
    __tablename__ = "power_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    firing_id: Mapped[int] = mapped_column(ForeignKey("firings.id"), nullable=False)
    timestamp: Mapped[str] = mapped_column(String, nullable=False)
    # Single-PZEM setup: one meter measures total voltage/current/power.
    # Field names retain the l1_ prefix for DB and API compatibility; an L2
    # column set used to exist, dropped by the init_db migration.
    l1_voltage: Mapped[float] = mapped_column(nullable=False)
    l1_current: Mapped[float] = mapped_column(nullable=False)
    l1_power: Mapped[float] = mapped_column(nullable=False)

    firing: Mapped[Firing] = relationship(back_populates="power_readings")

    __table_args__ = (Index("idx_power_readings_firing_ts", "firing_id", "timestamp"),)


class FiringStats(Base):
    """Per-firing summary aggregates (max_temp, duration, heating/cooling
    rates, sitter cutoff), keyed 1:1 to a Firing. The Statistics endpoints
    aggregate over this table instead of scanning the readings.

    Deletion through the Firing.stats ORM relationship removes this row
    (cascade="all, delete-orphan"); the FK's ondelete=CASCADE extends the
    same semantics to raw-SQL deletes on connections where PRAGMA
    foreign_keys is ON.
    """

    __tablename__ = "firing_stats"

    firing_id: Mapped[int] = mapped_column(
        ForeignKey("firings.id", ondelete="CASCADE"), primary_key=True
    )
    max_temp: Mapped[float] = mapped_column(nullable=False)
    duration_min: Mapped[float] = mapped_column(nullable=False)
    # Active duration runs from firing start to detected sitter cutoff. NULL
    # when no sitter trip was detected (normal firings).
    active_duration_min: Mapped[float | None] = mapped_column(nullable=True)
    cutoff_timestamp: Mapped[str | None] = mapped_column(String, nullable=True)
    avg_mv: Mapped[float] = mapped_column(nullable=False)
    cooling_rate: Mapped[float] = mapped_column(nullable=False, default=0.0)
    # Per-band {label: deg_per_min}; bands the firing never crossed are
    # absent from the dict.
    heating_rates_json: Mapped[str] = mapped_column(String, nullable=False, default="{}")

    firing: Mapped[Firing] = relationship(back_populates="stats")

    @property
    def heating_rates(self) -> dict[str, float]:
        return json.loads(self.heating_rates_json)

    @heating_rates.setter
    def heating_rates(self, value: dict[str, float]) -> None:
        self.heating_rates_json = json.dumps(value)

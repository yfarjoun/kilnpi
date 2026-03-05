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


class Reading(Base):
    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    firing_id: Mapped[int] = mapped_column(ForeignKey("firings.id"), nullable=False)
    timestamp: Mapped[str] = mapped_column(String, nullable=False)
    pv: Mapped[float] = mapped_column(nullable=False)
    sp: Mapped[float] = mapped_column(nullable=False)
    mv: Mapped[float] = mapped_column(nullable=False)
    segment: Mapped[int | None] = mapped_column(nullable=True)

    firing: Mapped[Firing] = relationship(back_populates="readings")

    __table_args__ = (Index("idx_readings_firing_ts", "firing_id", "timestamp"),)

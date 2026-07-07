from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.actor import Actor
    from app.models.event import CrisisEvent
    from app.models.source import Source


class CrisisStatus(str, enum.Enum):
    active = "active"
    frozen = "frozen"
    resolved = "resolved"


class ActorRole(str, enum.Enum):
    party = "party"
    mediator = "mediator"
    observer = "observer"
    affected = "affected"


class Crisis(Base):
    __tablename__ = "crises"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    geom: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CrisisStatus] = mapped_column(
        Enum(CrisisStatus, name="crisis_status"),
        default=CrisisStatus.active,
        index=True,
    )
    conflict_type: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    intensity_last_week_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_id: Mapped[str | None] = mapped_column(String(200), index=True)
    source_name: Mapped[str | None] = mapped_column(String(80), index=True)
    country_iso3: Mapped[str | None] = mapped_column(String(3), index=True)
    admin1: Mapped[str | None] = mapped_column(String(120))
    admin1_norm: Mapped[str | None] = mapped_column(String(120))
    # Phase 1 flag: existing admin1-keyed rows are flipped to True during the
    # conflict-registry migration and hidden from the public API surface.
    legacy: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    actor_links: Mapped[list[CrisisActor]] = relationship(
        back_populates="crisis", cascade="all, delete-orphan"
    )
    sources: Mapped[list[Source]] = relationship(
        back_populates="crisis", cascade="all, delete-orphan"
    )
    events: Mapped[list[CrisisEvent]] = relationship(
        back_populates="crisis", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_crises_source_external", "source_name", "external_id", unique=True),
        Index(
            "ix_crises_iso3_admin1",
            "country_iso3",
            "admin1_norm",
            unique=True,
            postgresql_where="admin1_norm IS NOT NULL",
        ),
    )


class CrisisActor(Base):
    __tablename__ = "crisis_actors"

    crisis_id: Mapped[int] = mapped_column(
        ForeignKey("crises.id", ondelete="CASCADE"), primary_key=True
    )
    actor_id: Mapped[int] = mapped_column(
        ForeignKey("actors.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[ActorRole] = mapped_column(
        Enum(ActorRole, name="actor_role"), default=ActorRole.party
    )
    notes: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
    admin_curated: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    crisis: Mapped[Crisis] = relationship(back_populates="actor_links")
    actor: Mapped[Actor] = relationship(back_populates="crisis_links")
    source: Mapped[Source | None] = relationship()

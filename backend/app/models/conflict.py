"""Conflict-registry ORM models.

A `Conflict` is the new dot-on-the-globe entity — one row per coherent
storyline (Russo-Ukrainian War, Sudanese civil war, etc.), as opposed to
the per-admin1 `Crisis` rows the older pipeline emits. `ConflictFootprint`
maps a conflict to the admin1 cells it spans; `ConflictParty` is the
curated party list (collapsing ACLED's variant strings); `ConflictRoutingRule`
drives the ingest-time event→conflict assignment.

`crises` rows persist alongside this for one cycle behind `crises.legacy=true`;
`crisis_events.conflict_id` links the event back to its assigned conflict.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from geoalchemy2 import Geometry
from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.crisis import ActorRole

if TYPE_CHECKING:
    from app.models.actor import Actor
    from app.models.source import Source


class ConflictStatus(str, enum.Enum):
    active = "active"
    frozen = "frozen"
    resolved = "resolved"
    emerging = "emerging"


class Conflict(Base):
    __tablename__ = "conflicts"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    conflict_type: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[ConflictStatus] = mapped_column(
        Enum(ConflictStatus, name="conflict_status"),
        default=ConflictStatus.emerging,
        index=True,
    )
    primary_iso3: Mapped[str | None] = mapped_column(String(3), index=True)
    secondary_iso3s: Mapped[list[str]] = mapped_column(
        ARRAY(String(3)), default=list, server_default="{}"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    geom: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    # Which fallback tier produced lat/lng: event_centroid | footprint_centroid
    # | curated_coordinate | country_fallback. country_fallback is an
    # approximate display-only position and must never back an `active` dot.
    coord_source: Mapped[str | None] = mapped_column(String(20))
    summary: Mapped[str | None] = mapped_column(Text)
    wikipedia_url: Mapped[str | None] = mapped_column(String(500))
    ucdp_conflict_id: Mapped[str | None] = mapped_column(String(40))
    # yaml | wiki-auto | ucdp-auto | admin
    registry_source: Mapped[str] = mapped_column(String(20), default="yaml")
    admin_curated: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    intensity_4w_events: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    intensity_4w_fatalities: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    footprints: Mapped[list[ConflictFootprint]] = relationship(
        back_populates="conflict", cascade="all, delete-orphan"
    )
    party_links: Mapped[list[ConflictParty]] = relationship(
        back_populates="conflict", cascade="all, delete-orphan"
    )
    routing_rules: Mapped[list[ConflictRoutingRule]] = relationship(
        back_populates="conflict", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "ix_conflicts_ucdp_id",
            "ucdp_conflict_id",
            postgresql_where="ucdp_conflict_id IS NOT NULL",
        ),
    )


class ConflictFootprint(Base):
    __tablename__ = "conflict_footprints"

    conflict_id: Mapped[int] = mapped_column(
        ForeignKey("conflicts.id", ondelete="CASCADE"), primary_key=True
    )
    country_iso3: Mapped[str] = mapped_column(String(3), primary_key=True)
    admin1_norm: Mapped[str] = mapped_column(String(120), primary_key=True)
    confidence: Mapped[float] = mapped_column(
        Float, default=1.0, server_default="1.0", nullable=False
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conflict: Mapped[Conflict] = relationship(back_populates="footprints")

    __table_args__ = (
        Index("ix_footprints_iso3_admin1", "country_iso3", "admin1_norm"),
    )


class ConflictParty(Base):
    __tablename__ = "conflict_parties"

    conflict_id: Mapped[int] = mapped_column(
        ForeignKey("conflicts.id", ondelete="CASCADE"), primary_key=True
    )
    actor_id: Mapped[int] = mapped_column(
        ForeignKey("actors.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[ActorRole] = mapped_column(
        Enum(ActorRole, name="actor_role", create_type=False),
        default=ActorRole.party,
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

    conflict: Mapped[Conflict] = relationship(back_populates="party_links")
    actor: Mapped[Actor] = relationship()
    source: Mapped[Source | None] = relationship()


class ConflictRoutingRule(Base):
    """Drives ingest-time event→conflict assignment.

    `rule_type`:
      - "actor"   — `pattern` is a SQL-LIKE pattern matched against any of
                    actor1/actor2/assoc_actor_* on the inbound event.
      - "admin1"  — `pattern` is "<iso3>:<admin1_norm>".
      - "country" — `pattern` is "<iso3>".

    Lower `priority` wins first when multiple rules match. Actor rules
    typically priority=1, admin1=2, country=3.
    """

    __tablename__ = "conflict_routing_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    conflict_id: Mapped[int] = mapped_column(
        ForeignKey("conflicts.id", ondelete="CASCADE"), index=True
    )
    rule_type: Mapped[str] = mapped_column(String(20), index=True)
    pattern: Mapped[str] = mapped_column(String(400))
    priority: Mapped[int] = mapped_column(
        Integer, default=100, server_default="100", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conflict: Mapped[Conflict] = relationship(back_populates="routing_rules")

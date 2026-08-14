"""Ingestion source contract.

Every external data source (ACLED aggregated, ACLED lagged, GDELT, UCDP,
fixtures, etc.) implements `IngestionSource`. Upsert key is now
`(country_iso3, admin1_norm)` — every dot represents one admin1 region.

Sources can be split into "identity owners" (which decide a crisis exists,
e.g. ACLED aggregated) and "content contributors" (which add events/actors/
sources to existing crises, e.g. ACLED lagged, UCDP, GDELT). The
`owns_*` flags on `IngestionSource` let one record land at a crisis without
wiping the other side's content.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class SourceRef:
    title: str
    url: str
    publisher: str | None = None
    published_at: datetime | None = None
    source_type: str = "news"
    body_text: str | None = None


@dataclass
class ActorRef:
    name: str
    type: str = "other"
    role: str = "party"
    description: str | None = None
    wikipedia_url: str | None = None
    notes: str | None = None
    # index into the parent CrisisRecord.sources list; None if not attributed
    attributing_source_index: int | None = None


@dataclass
class EventRef:
    """One incident attached to a crisis. `description` should be verbatim
    prose copied from the cited source — never LLM-generated."""

    external_id: str
    occurred_at: datetime
    event_type: str | None = None
    description: str | None = None
    fatalities: int | None = None
    location_name: str | None = None
    lat: float | None = None
    lng: float | None = None
    # index into the parent CrisisRecord.sources list; None if not attributed
    source_index: int | None = None


@dataclass
class IntensityRow:
    """One ACLED weekly aggregate cell — events, fatalities, exposure for
    a single (week, event_type) within one admin1."""

    week_start: date
    event_type: str
    event_count: int
    fatalities: int
    population_exposure: int | None = None


@dataclass
class CrisisRecord:
    external_id: str
    slug: str
    name: str
    country: str | None
    region: str | None
    lat: float
    lng: float
    summary: str
    status: str  # active | frozen | resolved
    conflict_type: str
    country_iso3: str | None = None
    admin1: str | None = None
    admin1_norm: str | None = None
    started_at: datetime | None = None
    last_event_at: datetime | None = None
    intensity_last_week_at: datetime | None = None
    actors: list[ActorRef] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    events: list[EventRef] = field(default_factory=list)
    intensity_rows: list[IntensityRow] = field(default_factory=list)


class IngestionSource(ABC):
    name: str
    # If True, the runner calls `attach_events(db)` instead of upserting
    # crises. Used for content contributors that only enrich existing dots.
    attach_only: bool = False
    # Content-ownership flags. When False the runner does NOT replace that
    # slice of content for crises this source touches — empty `actors=[]` from
    # a non-owning source is treated as "no opinion," not "wipe."
    owns_actors: bool = True
    owns_events: bool = True
    owns_sources: bool = True

    @abstractmethod
    def fetch(self) -> list[CrisisRecord]: ...

    def before_run(self, db) -> None:  # type: ignore[no-untyped-def]
        # Hook for purge / prep before fetch(). Default no-op.
        return None

    def attach_events(self, db, routing_idx=None) -> dict:  # type: ignore[no-untyped-def]
        # `routing_idx` is a prebuilt `app.conflicts.routing.RoutingIndex`;
        # attach-only sources use it to set `conflict_id` at insert time so
        # events are routed even if the post-ingest tail never runs.
        return {"attached": 0, "skipped": 0}

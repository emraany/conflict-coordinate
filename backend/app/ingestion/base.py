"""Ingestion source contract.

Every external data source (ACLED, UN OCHA, curated fixtures, etc.) must implement
`IngestionSource` and return a list of `CrisisRecord`. The runner upserts them by
`(source_name, external_id)`, so records are idempotent across re-runs.

This is the single plug-in point where future ML enrichment (classification,
summarization) can be injected as a post-fetch transform before upsert.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SourceRef:
    title: str
    url: str
    publisher: str | None = None
    published_at: datetime | None = None
    source_type: str = "news"


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
    started_at: datetime | None = None
    last_event_at: datetime | None = None
    actors: list[ActorRef] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)


class IngestionSource(ABC):
    name: str
    # If True, the runner calls `attach_events(db)` instead of upserting
    # crises. Used for secondary sources (GDELT) that only add events.
    attach_only: bool = False

    @abstractmethod
    def fetch(self) -> list[CrisisRecord]: ...

    def attach_events(self, db) -> dict:  # type: ignore[no-untyped-def]
        return {"attached": 0, "skipped": 0}

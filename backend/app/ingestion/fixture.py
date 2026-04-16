"""Fixture ingestion source.

Reads `app/seed_data.json` and returns `CrisisRecord`s. The file is explicitly
dev-only fixture data flagged with `source_note`; it must never be treated as
authoritative.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.ingestion.base import ActorRef, CrisisRecord, IngestionSource, SourceRef

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "seed_data.json"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    # tolerate trailing Z
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


class FixtureSource(IngestionSource):
    name = "fixture"

    def __init__(self, path: Path = FIXTURE_PATH) -> None:
        self.path = path

    def fetch(self) -> list[CrisisRecord]:
        with self.path.open() as f:
            payload = json.load(f)
        out: list[CrisisRecord] = []
        for item in payload["crises"]:
            sources = [
                SourceRef(
                    title=s["title"],
                    url=s["url"],
                    publisher=s.get("publisher"),
                    published_at=_parse_dt(s.get("published_at")),
                    source_type=s.get("source_type", "news"),
                )
                for s in item.get("sources", [])
            ]
            actors = [
                ActorRef(
                    name=a["name"],
                    type=a.get("type", "other"),
                    role=a.get("role", "party"),
                    description=a.get("description"),
                    wikipedia_url=a.get("wikipedia_url"),
                    notes=a.get("notes"),
                    attributing_source_index=a.get("source_index"),
                )
                for a in item.get("actors", [])
            ]
            out.append(
                CrisisRecord(
                    external_id=item["external_id"],
                    slug=item["slug"],
                    name=item["name"],
                    country=item.get("country"),
                    region=item.get("region"),
                    lat=item["lat"],
                    lng=item["lng"],
                    summary=item["summary"],
                    status=item.get("status", "active"),
                    conflict_type=item.get("conflict_type", "other"),
                    started_at=_parse_dt(item.get("started_at")),
                    last_event_at=_parse_dt(item.get("last_event_at")),
                    actors=actors,
                    sources=sources,
                )
            )
        return out

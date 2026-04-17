"""Ingestion runner — iterates registered sources, upserts records idempotently.

Upsert key is (source_name, external_id) on the `crises` table, so re-runs
update rather than duplicate. Actors and sources are replaced wholesale on each
run for the owning crisis (simplest semantics for v1 fixture data; ACLED-style
incremental ingestion can refine this later).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.ingestion.acled import ACLEDSource
from app.ingestion.base import (
    ActorRef,
    CrisisRecord,
    EventRef,
    IngestionSource,
    SourceRef,
)
from app.ingestion.fixture import FixtureSource
from app.ingestion.gdelt import GDELTSource
from app.models import (
    Actor,
    ActorRole,
    ActorType,
    Crisis,
    CrisisActor,
    CrisisStatus,
    Source,
    SourceType,
)
from app.models.event import CrisisEvent

SOURCES: list[IngestionSource] = [
    FixtureSource(),
    ACLEDSource(),
    GDELTSource(),
]


def _upsert_actor(db: Session, ref: ActorRef) -> Actor:
    actor = db.scalar(select(Actor).where(Actor.name == ref.name))
    if actor is None:
        actor = Actor(
            name=ref.name,
            type=ActorType(ref.type),
            description=ref.description,
            wikipedia_url=ref.wikipedia_url,
        )
        db.add(actor)
        db.flush()
    else:
        # Only backfill empty fields; never overwrite an admin edit.
        if not actor.description and ref.description:
            actor.description = ref.description
        if not actor.wikipedia_url and ref.wikipedia_url:
            actor.wikipedia_url = ref.wikipedia_url
    return actor


def _replace_sources(
    db: Session, crisis: Crisis, refs: list[SourceRef], origin: str
) -> list[Source]:
    # Clear existing ingestion-owned sources for this crisis and re-insert.
    for existing in list(crisis.sources):
        db.delete(existing)
    db.flush()
    created: list[Source] = []
    for ref in refs:
        src = Source(
            crisis_id=crisis.id,
            title=ref.title,
            url=ref.url,
            publisher=ref.publisher,
            published_at=ref.published_at,
            retrieved_at=datetime.now(timezone.utc),
            source_type=SourceType(ref.source_type),
            origin=origin,
        )
        db.add(src)
        created.append(src)
    db.flush()
    return created


def _replace_actor_links(
    db: Session, crisis: Crisis, actor_refs: list[ActorRef], source_rows: list[Source]
) -> None:
    # Clear existing links on this crisis and re-create them from the record.
    for existing in list(crisis.actor_links):
        db.delete(existing)
    db.flush()
    for ref in actor_refs:
        actor = _upsert_actor(db, ref)
        source_id = (
            source_rows[ref.attributing_source_index].id
            if ref.attributing_source_index is not None
            and 0 <= ref.attributing_source_index < len(source_rows)
            else None
        )
        db.add(
            CrisisActor(
                crisis_id=crisis.id,
                actor_id=actor.id,
                role=ActorRole(ref.role),
                notes=ref.notes,
                source_id=source_id,
            )
        )
    db.flush()


def _replace_events(
    db: Session, crisis: Crisis, event_refs: list[EventRef], source_rows: list[Source]
) -> None:
    # Clear existing events for this crisis and re-insert. (For sources that
    # purge on before_run, crisis.events will be empty on fresh inserts; this
    # loop is then a no-op. For updating paths we still want to replace.)
    for existing in list(crisis.events):
        db.delete(existing)
    db.flush()
    for ref in event_refs:
        source_id = (
            source_rows[ref.source_index].id
            if ref.source_index is not None
            and 0 <= ref.source_index < len(source_rows)
            else None
        )
        db.add(
            CrisisEvent(
                crisis_id=crisis.id,
                occurred_at=ref.occurred_at,
                event_type=ref.event_type,
                description=ref.description,
                fatalities=ref.fatalities,
                location_name=ref.location_name,
                lat=ref.lat,
                lng=ref.lng,
                external_id=ref.external_id,
                source_id=source_id,
            )
        )
    db.flush()


def _upsert_crisis(db: Session, source_name: str, rec: CrisisRecord) -> tuple[Crisis, bool]:
    crisis = db.scalar(
        select(Crisis).where(
            Crisis.source_name == source_name, Crisis.external_id == rec.external_id
        )
    )
    created = False
    if crisis is None:
        crisis = Crisis(
            source_name=source_name,
            external_id=rec.external_id,
            slug=rec.slug,
            name=rec.name,
            country=rec.country,
            region=rec.region,
            lat=rec.lat,
            lng=rec.lng,
            summary=rec.summary,
            status=CrisisStatus(rec.status),
            conflict_type=rec.conflict_type,
            started_at=rec.started_at,
            last_event_at=rec.last_event_at,
        )
        crisis.geom = f"SRID=4326;POINT({rec.lng} {rec.lat})"
        db.add(crisis)
        db.flush()
        created = True
    else:
        crisis.slug = rec.slug
        crisis.name = rec.name
        crisis.country = rec.country
        crisis.region = rec.region
        crisis.lat = rec.lat
        crisis.lng = rec.lng
        crisis.summary = rec.summary
        crisis.status = CrisisStatus(rec.status)
        crisis.conflict_type = rec.conflict_type
        crisis.started_at = rec.started_at
        crisis.last_event_at = rec.last_event_at
        crisis.geom = f"SRID=4326;POINT({rec.lng} {rec.lat})"
        db.flush()
    return crisis, created


def run_all_sources(db: Session | None = None) -> dict:
    close_after = db is None
    db = db or SessionLocal()
    result: dict = {"sources": [], "total_inserted": 0, "total_updated": 0}
    try:
        for source in SOURCES:
            if getattr(source, "attach_only", False):
                counts = source.attach_events(db)
                db.commit()
                result["sources"].append(
                    {
                        "source": source.name,
                        "attached": counts.get("attached", 0),
                        "skipped": counts.get("skipped", 0),
                    }
                )
                continue
            source.before_run(db)
            records = source.fetch()
            inserted = 0
            updated = 0
            for rec in records:
                crisis, created = _upsert_crisis(db, source.name, rec)
                source_rows = _replace_sources(db, crisis, rec.sources, source.name)
                _replace_actor_links(db, crisis, rec.actors, source_rows)
                _replace_events(db, crisis, rec.events, source_rows)
                if created:
                    inserted += 1
                else:
                    updated += 1
            db.commit()
            result["sources"].append(
                {"source": source.name, "inserted": inserted, "updated": updated}
            )
            result["total_inserted"] += inserted
            result["total_updated"] += updated
    finally:
        if close_after:
            db.close()
    return result


if __name__ == "__main__":
    print(run_all_sources())

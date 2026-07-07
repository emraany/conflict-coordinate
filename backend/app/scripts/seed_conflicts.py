"""Seed the conflict registry from YAML into the database.

Idempotent. Re-running this:
  - upserts each Conflict by `slug`
  - upserts each Actor referenced from `actors_canon.yaml` by `name`
  - replaces `conflict_footprints`, `conflict_parties`, and
    `conflict_routing_rules` for each registry-sourced conflict (admin-curated
    rows survive — `admin_curated=true` is sacred)

Usage:
    uv run python -m app.scripts.seed_conflicts
    uv run python -m app.scripts.seed_conflicts --dry-run

The dry-run mode loads + validates + reports what would change without
touching the DB.
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.conflicts.loader import (
    ActorCanon,
    ConflictEntry,
    load_actors_canon,
    load_registry,
)
from app.db import SessionLocal
from app.models import (
    Actor,
    ActorRole,
    ActorType,
    Conflict,
    ConflictFootprint,
    ConflictParty,
    ConflictRoutingRule,
    ConflictStatus,
)

logger = logging.getLogger(__name__)


def _upsert_actor(db: Session, canon: ActorCanon) -> Actor:
    """Upsert a canonical actor by name. Description/wikipedia_url only get
    written when previously empty so admin edits aren't clobbered."""
    actor = db.scalar(select(Actor).where(Actor.name == canon.name))
    if actor is None:
        actor = Actor(
            name=canon.name,
            type=ActorType(canon.type),
            description=canon.description,
            wikipedia_url=canon.wikipedia_url,
        )
        db.add(actor)
        db.flush()
        return actor
    if not actor.description and canon.description:
        actor.description = canon.description
    if not actor.wikipedia_url and canon.wikipedia_url:
        actor.wikipedia_url = canon.wikipedia_url
    return actor


def _upsert_conflict(db: Session, entry: ConflictEntry) -> tuple[Conflict, bool]:
    conflict = db.scalar(select(Conflict).where(Conflict.slug == entry.slug))
    created = False
    if conflict is None:
        conflict = Conflict(
            slug=entry.slug,
            name=entry.name,
            conflict_type=entry.conflict_type,
            status=ConflictStatus(entry.status),
            primary_iso3=entry.primary_iso3,
            secondary_iso3s=list(entry.secondary_iso3s),
            started_at=entry.started_at,
            resolved_at=entry.resolved_at,
            summary=entry.summary,
            wikipedia_url=entry.wikipedia_url,
            ucdp_conflict_id=entry.ucdp_conflict_id,
            registry_source="yaml",
            admin_curated=True,
        )
        db.add(conflict)
        db.flush()
        created = True
    else:
        # YAML is authoritative for identity fields; admin-curated rows can
        # be promoted/edited via the API later.
        conflict.name = entry.name
        conflict.conflict_type = entry.conflict_type
        conflict.status = ConflictStatus(entry.status)
        conflict.primary_iso3 = entry.primary_iso3
        conflict.secondary_iso3s = list(entry.secondary_iso3s)
        if entry.started_at:
            conflict.started_at = entry.started_at
        if entry.resolved_at:
            conflict.resolved_at = entry.resolved_at
        conflict.summary = entry.summary
        conflict.wikipedia_url = entry.wikipedia_url
        conflict.ucdp_conflict_id = entry.ucdp_conflict_id
        conflict.registry_source = "yaml"
        conflict.admin_curated = True
    db.flush()
    return conflict, created


def _replace_footprints(
    db: Session, conflict: Conflict, entry: ConflictEntry
) -> int:
    db.execute(
        delete(ConflictFootprint).where(
            ConflictFootprint.conflict_id == conflict.id
        )
    )
    db.flush()
    for cell in entry.footprint:
        db.add(
            ConflictFootprint(
                conflict_id=conflict.id,
                country_iso3=cell.iso3,
                admin1_norm=cell.admin1_norm,
                confidence=cell.confidence,
            )
        )
    db.flush()
    return len(entry.footprint)


def _replace_parties(
    db: Session,
    conflict: Conflict,
    entry: ConflictEntry,
    canon: dict[str, ActorCanon],
) -> int:
    """Replace non-admin-curated party links from the YAML. Admin-curated
    links survive."""
    existing_curated_actor_ids = {
        row.actor_id
        for row in db.execute(
            select(ConflictParty.actor_id).where(
                ConflictParty.conflict_id == conflict.id,
                ConflictParty.admin_curated.is_(True),
            )
        ).all()
    }
    db.execute(
        delete(ConflictParty).where(
            ConflictParty.conflict_id == conflict.id,
            ConflictParty.admin_curated.is_(False),
        )
    )
    db.flush()

    inserted = 0
    for party in entry.parties:
        canon_entry = canon[party.actor_slug]  # validated by loader
        actor = _upsert_actor(db, canon_entry)
        if actor.id in existing_curated_actor_ids:
            continue
        db.add(
            ConflictParty(
                conflict_id=conflict.id,
                actor_id=actor.id,
                role=ActorRole(party.role),
                notes=party.notes,
                admin_curated=False,
            )
        )
        inserted += 1
    db.flush()
    return inserted


def _replace_routing_rules(
    db: Session, conflict: Conflict, entry: ConflictEntry
) -> int:
    db.execute(
        delete(ConflictRoutingRule).where(
            ConflictRoutingRule.conflict_id == conflict.id
        )
    )
    db.flush()
    for rule in entry.routing_rules:
        db.add(
            ConflictRoutingRule(
                conflict_id=conflict.id,
                rule_type=rule.rule_type,
                pattern=rule.pattern,
                priority=rule.priority,
            )
        )
    db.flush()
    return len(entry.routing_rules)


def seed(dry_run: bool = False) -> dict:
    canon = load_actors_canon()
    registry = load_registry(actors_canon=canon)

    if dry_run:
        return {
            "dry_run": True,
            "canon_actors": len(canon),
            "conflicts": [
                {
                    "slug": c.slug,
                    "name": c.name,
                    "footprint_cells": len(c.footprint),
                    "parties": len(c.parties),
                    "routing_rules": len(c.routing_rules),
                }
                for c in registry
            ],
        }

    db: Session = SessionLocal()
    summary = {
        "dry_run": False,
        "ran_at": datetime.now(UTC).isoformat(),
        "conflicts_upserted": 0,
        "conflicts_created": 0,
        "footprint_cells": 0,
        "parties": 0,
        "routing_rules": 0,
    }
    try:
        for entry in registry:
            conflict, created = _upsert_conflict(db, entry)
            summary["conflicts_upserted"] += 1
            if created:
                summary["conflicts_created"] += 1
            summary["footprint_cells"] += _replace_footprints(db, conflict, entry)
            summary["parties"] += _replace_parties(db, conflict, entry, canon)
            summary["routing_rules"] += _replace_routing_rules(db, conflict, entry)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description="Seed conflict registry from YAML.")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Load + validate without writing to the DB.",
    )
    args = p.parse_args()
    out = seed(dry_run=args.dry_run)
    import json

    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()

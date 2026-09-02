"""Route existing crisis_events to conflicts, and roll up per-conflict stats.

The historic `crises` table holds one row per admin1 cell. Each row has
events attached. This script:

  1. Loads the routing index from `conflict_routing_rules`.
  2. For each event, derives its routing fields:
       - actor strings → names from `crisis_actors → actors.name` for the
         parent crisis (best we can do at backfill time; future ingest will
         use the raw ACLED actor* fields directly).
       - iso3 / admin1_norm → from the parent crisis.
  3. Runs `route_event(...)`; sets `crisis_events.conflict_id` (NULL on miss).
  4. Per conflict, recomputes:
       - lat / lng (mean of routed event coords, fallback to footprint cell
         centroid → fallback to None)
       - last_event_at
       - intensity_4w_events, intensity_4w_fatalities (events.occurred_at
         within last 4 weeks of "now" or, when ACLED_REFERENCE_DATE is set,
         that reference date).
  5. Flips `crises.legacy = true` for all admin1-keyed rows so the public
     API can hide them in Phase 4. Admin-curated `CrisisActor` rows still
     survive on legacy crises.

Usage:
    uv run python -m app.scripts.backfill_routing            # dry-run, report only
    uv run python -m app.scripts.backfill_routing --commit   # persist
    uv run python -m app.scripts.backfill_routing --commit --no-legacy-flip

Dry-run is safe to run anytime; it touches nothing.
"""

from __future__ import annotations

import argparse
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import mean

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.conflicts.routing import build_routing_index, route_event
from app.db import SessionLocal
from app.models import (
    Actor,
    Conflict,
    ConflictFootprint,
    ConflictRoutingRule,
    Crisis,
    CrisisActor,
)
from app.models.event import CrisisEvent

logger = logging.getLogger(__name__)


def _reference_now() -> datetime:
    if settings.acled_reference_date:
        try:
            d = datetime.fromisoformat(settings.acled_reference_date).replace(
                tzinfo=UTC
            )
            return d
        except ValueError:
            pass
    return datetime.now(UTC)


def _load_routing_index(db: Session):
    """Build the routing index every caller shares — the two dossier label
    sites and the ingest runner all come through here, so the actor tier is
    bounded by the same geography wherever it is applied."""
    rules = db.execute(
        select(
            ConflictRoutingRule.conflict_id,
            ConflictRoutingRule.rule_type,
            ConflictRoutingRule.pattern,
            ConflictRoutingRule.priority,
        )
    ).all()
    conflict_iso3s: dict[int, set[str]] = {}
    for row in db.execute(
        select(Conflict.id, Conflict.primary_iso3, Conflict.secondary_iso3s)
    ).all():
        spans = {c.upper() for c in (row.secondary_iso3s or []) if c}
        if row.primary_iso3:
            spans.add(row.primary_iso3.upper())
        if spans:
            conflict_iso3s[row.id] = spans
    return build_routing_index(
        [(r.conflict_id, r.rule_type, r.pattern, r.priority) for r in rules],
        conflict_iso3s,
    )


def actor_names_for_crises(
    db: Session, crisis_ids: list[int] | None = None
) -> dict[int, list[str]]:
    """crisis_id -> [actor.name, …] in one query. Passing `crisis_ids` scopes
    it; omitting them loads every crisis."""
    stmt = select(CrisisActor.crisis_id, Actor.name).join(
        Actor, Actor.id == CrisisActor.actor_id
    )
    if crisis_ids is not None:
        if not crisis_ids:
            return {}
        stmt = stmt.where(CrisisActor.crisis_id.in_(crisis_ids))
    out: dict[int, list[str]] = defaultdict(list)
    for r in db.execute(stmt).all():
        out[r.crisis_id].append(r.name)
    return out


def _load_crisis_metadata(
    db: Session,
) -> tuple[dict[int, tuple[str | None, str | None]], dict[int, list[str]]]:
    """Return:
      crisis_meta:    crisis_id -> (iso3, admin1_norm)
      actors_by_crisis: crisis_id -> [actor.name, …]
    """
    crisis_meta = {
        row.id: (row.country_iso3, row.admin1_norm)
        for row in db.execute(
            select(Crisis.id, Crisis.country_iso3, Crisis.admin1_norm)
        ).all()
    }
    return crisis_meta, actor_names_for_crises(db)


def _load_country_centroids(db: Session) -> dict[str, tuple[float, float]]:
    """iso3 → mean(crises lat/lng). Tier-4 `country_fallback` coordinate —
    approximate, display-only; never backs an `active` dot."""
    rows = db.execute(
        select(
            Crisis.country_iso3,
            func.avg(Crisis.lat),
            func.avg(Crisis.lng),
        )
        .where(
            Crisis.country_iso3.is_not(None),
            Crisis.lat.is_not(None),
            Crisis.lng.is_not(None),
        )
        .group_by(Crisis.country_iso3)
    ).all()
    return {
        r[0]: (float(r[1]), float(r[2]))
        for r in rows
        if r[1] is not None and r[2] is not None
    }


def _load_footprint_centroids(db: Session) -> dict[int, tuple[float, float]]:
    """Conflict_id → mean(admin1 cell centroids) computed from the existing
    `crises` table. Used as a fallback when no events route to a conflict.

    We pull lat/lng from `crises` matching each footprint cell, average them.
    If no matching crises exist, the conflict's centroid stays None.
    """
    rows = db.execute(
        select(
            ConflictFootprint.conflict_id,
            ConflictFootprint.country_iso3,
            ConflictFootprint.admin1_norm,
            Crisis.lat,
            Crisis.lng,
        ).join(
            Crisis,
            (Crisis.country_iso3 == ConflictFootprint.country_iso3)
            & (Crisis.admin1_norm == ConflictFootprint.admin1_norm),
        )
    ).all()
    by_conf: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for r in rows:
        if r.lat is None or r.lng is None:
            continue
        by_conf[r.conflict_id].append((float(r.lat), float(r.lng)))
    out: dict[int, tuple[float, float]] = {}
    for cid, pts in by_conf.items():
        if not pts:
            continue
        out[cid] = (
            float(mean(p[0] for p in pts)),
            float(mean(p[1] for p in pts)),
        )
    return out


def backfill(commit: bool, flip_legacy: bool) -> dict:
    db: Session = SessionLocal()
    try:
        idx = _load_routing_index(db)
        crisis_meta, actors_by_crisis = _load_crisis_metadata(db)

        # Per-conflict accumulators
        routed_per_conflict: dict[int, int] = defaultdict(int)
        coords_per_conflict: dict[int, list[tuple[float, float]]] = defaultdict(list)
        last_event_per_conflict: dict[int, datetime] = {}
        crises_per_conflict: dict[int, set[int]] = defaultdict(set)
        # (occurred_at, fatalities) per conflict — the 4w intensity window is
        # anchored on each conflict's own latest event, not wall-clock now:
        # ACLED's event API is embargoed ~13 months, so a wall-clock window
        # would read 0 for every ACLED-only conflict.
        dated_events_per_conflict: dict[int, list[tuple[datetime, int]]] = defaultdict(
            list
        )
        ref_now = _reference_now()
        intensity_events: dict[int, int] = defaultdict(int)
        intensity_fatalities: dict[int, int] = defaultdict(int)

        # Stream events. SQLAlchemy yield_per keeps memory bounded.
        events_iter = db.execute(
            select(
                CrisisEvent.id,
                CrisisEvent.crisis_id,
                CrisisEvent.lat,
                CrisisEvent.lng,
                CrisisEvent.occurred_at,
                CrisisEvent.fatalities,
            )
        ).yield_per(2000)

        total_events = 0
        orphan_events = 0
        updates: list[tuple[int, int]] = []  # (event_id, conflict_id)

        for row in events_iter:
            total_events += 1
            meta = crisis_meta.get(row.crisis_id)
            if meta is None:
                orphan_events += 1
                continue
            iso3, admin1_norm = meta
            actor_names = actors_by_crisis.get(row.crisis_id, [])
            conflict_id = route_event(actor_names, iso3, admin1_norm, idx)
            if conflict_id is None:
                orphan_events += 1
                continue
            updates.append((row.id, conflict_id))
            routed_per_conflict[conflict_id] += 1
            crises_per_conflict[conflict_id].add(row.crisis_id)
            if row.lat is not None and row.lng is not None:
                coords_per_conflict[conflict_id].append(
                    (float(row.lat), float(row.lng))
                )
            if row.occurred_at is not None:
                prev = last_event_per_conflict.get(conflict_id)
                if prev is None or row.occurred_at > prev:
                    last_event_per_conflict[conflict_id] = row.occurred_at
                dated_events_per_conflict[conflict_id].append(
                    (row.occurred_at, int(row.fatalities or 0))
                )

        # 4w intensity, anchored per conflict on its own latest event.
        for cid, dated in dated_events_per_conflict.items():
            anchor = max(d for d, _ in dated)
            window_start = anchor - timedelta(weeks=4)
            for occurred, fatalities in dated:
                if occurred >= window_start:
                    intensity_events[cid] += 1
                    intensity_fatalities[cid] += fatalities

        # Pull conflict slugs so the report is human-readable.
        slug_by_id = {
            row.id: row.slug
            for row in db.execute(select(Conflict.id, Conflict.slug)).all()
        }

        report = {
            "ref_now": ref_now.isoformat(),
            "total_events": total_events,
            "orphan_events": orphan_events,
            "routed_events": total_events - orphan_events,
            "per_conflict": [
                {
                    "slug": slug_by_id.get(cid, f"#{cid}"),
                    "conflict_id": cid,
                    "events_routed": routed_per_conflict[cid],
                    "intensity_4w_events": intensity_events[cid],
                    "intensity_4w_fatalities": intensity_fatalities[cid],
                    "centroid_from_events": (
                        (
                            round(mean(p[0] for p in coords_per_conflict[cid]), 4),
                            round(mean(p[1] for p in coords_per_conflict[cid]), 4),
                        )
                        if coords_per_conflict[cid]
                        else None
                    ),
                    "last_event_at": (
                        last_event_per_conflict.get(cid).isoformat()
                        if cid in last_event_per_conflict
                        else None
                    ),
                }
                for cid in sorted(routed_per_conflict, key=lambda c: -routed_per_conflict[c])
            ],
        }

        if not commit:
            report["committed"] = False
            return report

        # ---- Persist phase ----

        # 1. Update crisis_events.conflict_id in batches.
        BATCH = 1000
        for i in range(0, len(updates), BATCH):
            chunk = updates[i : i + BATCH]
            # Group by conflict_id so we can do bulk updates.
            by_conf: dict[int, list[int]] = defaultdict(list)
            for ev_id, cid in chunk:
                by_conf[cid].append(ev_id)
            for cid, ids in by_conf.items():
                db.execute(
                    update(CrisisEvent)
                    .where(CrisisEvent.id.in_(ids))
                    .values(conflict_id=cid)
                )
            db.flush()

        # 2. Compute conflict centroids — events first, footprint cells fallback.
        footprint_centroids = _load_footprint_centroids(db)
        # crisis_id → latest aggregated week. The ACLED event API is embargoed
        # ~13 months but the aggregated weekly data is current; a conflict's
        # "last observed activity" must consider both, or the stale sweep
        # freezes conflicts whose aggregates show current activity.
        intensity_week_by_crisis: dict[int, datetime] = {
            row.id: row.intensity_last_week_at
            for row in db.execute(
                select(Crisis.id, Crisis.intensity_last_week_at).where(
                    Crisis.intensity_last_week_at.is_not(None)
                )
            ).all()
        }
        country_centroids = _load_country_centroids(db)
        conflicts = db.scalars(select(Conflict)).all()
        for c in conflicts:
            # Tiered placement — best available conflict-specific geography:
            # ① event centroid ② footprint centroid ③ curated coordinate
            # (set by seed_conflicts) ④ country centroid, approximate
            # display-only fallback.
            pts = coords_per_conflict.get(c.id, [])
            if pts:
                c.lat = float(mean(p[0] for p in pts))
                c.lng = float(mean(p[1] for p in pts))
                c.coord_source = "event_centroid"
            elif c.id in footprint_centroids:
                c.lat, c.lng = footprint_centroids[c.id]
                c.coord_source = "footprint_centroid"
            elif c.coord_source == "curated_coordinate" and c.lat is not None:
                pass  # keep the seeded curated coordinate
            elif c.primary_iso3 in country_centroids:
                c.lat, c.lng = country_centroids[c.primary_iso3]
                c.coord_source = "country_fallback"
            if c.lat is not None and c.lng is not None:
                c.geom = f"SRID=4326;POINT({c.lng} {c.lat})"

            last = last_event_per_conflict.get(c.id)
            for crisis_id in crises_per_conflict.get(c.id, ()):
                wk = intensity_week_by_crisis.get(crisis_id)
                if wk is not None and (last is None or wk > last):
                    last = wk
            if last is not None and (c.last_event_at is None or last > c.last_event_at):
                c.last_event_at = last
            c.intensity_4w_events = intensity_events.get(c.id, 0)
            c.intensity_4w_fatalities = intensity_fatalities.get(c.id, 0)
        db.flush()

        # 3. Flip crises.legacy = true (admin1 rows hidden from public API).
        legacy_flipped = 0
        if flip_legacy:
            result = db.execute(
                update(Crisis)
                .where(Crisis.admin1_norm.is_not(None), Crisis.legacy.is_(False))
                .values(legacy=True)
            )
            legacy_flipped = result.rowcount or 0

        db.commit()
        report["committed"] = True
        report["legacy_flipped"] = legacy_flipped
        return report
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(
        description="Route existing crisis_events to conflicts."
    )
    p.add_argument(
        "--commit",
        action="store_true",
        help="Persist routing assignments + conflict rollups. Default is dry-run.",
    )
    p.add_argument(
        "--no-legacy-flip",
        action="store_true",
        help="Skip flipping crises.legacy = true. Useful while developing.",
    )
    args = p.parse_args()

    out = backfill(commit=args.commit, flip_legacy=not args.no_legacy_flip)
    import json

    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()

"""Ingestion runner — iterates registered sources, upserts records idempotently.

Identity-owning sources (ACLED aggregated, fixtures) emit `CrisisRecord`s that
the runner upserts by `(country_iso3, admin1_norm)` when both are set, falling
back to `(source_name, external_id)`. Content-contributing sources have
`attach_only=True` and run `attach_events(db)` instead.

Per-source ownership flags (`owns_actors`, `owns_events`, `owns_sources`)
gate whether the runner replaces that slice of crisis content. False means
"this source has no opinion on this slice — leave it alone."
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.ingestion.acled import ACLEDLaggedEventSource
from app.ingestion.acled_aggregated import ACLEDAggregatedSource
from app.ingestion.base import (
    ActorRef,
    CrisisRecord,
    EventRef,
    IngestionSource,
    IntensityRow,
    SourceRef,
)
from app.ingestion.fixture import FixtureSource
from app.ingestion.gdelt import GDELTSource
from app.ingestion.ucdp import UCDPSource
from app.ml.ner import process_pending as ner_process_pending
from app.models import (
    Actor,
    ActorRole,
    ActorType,
    Conflict,
    ConflictStatus,
    Crisis,
    CrisisActor,
    CrisisIntensityWeekly,
    CrisisStatus,
    IngestRun,
    Source,
    SourceType,
)
from app.models.event import CrisisEvent

logger = logging.getLogger(__name__)

# Cap the per-run NER pass so a large description backlog can't stall the
# ingest cycle; the remainder drains on subsequent runs.
NER_MAX_EVENTS_PER_RUN = 5000

# --- Globe dot definition ---------------------------------------------------
# A dot is an admin1 region with recent violent activity in ACLED's weekly
# aggregates. Protests and strategic developments are excluded: they are
# recorded activity, not armed conflict, and would light up stable countries.
VIOLENT_EVENT_TYPES: tuple[str, ...] = (
    "Battles",
    "Violence against civilians",
    "Explosions/Remote violence",
    "Riots",
)
# Trailing window and thresholds. Tuning these changes the globe's density:
# >=5/>=5 yields ~350 dots, >=3/>=3 ~470, any activity ~844.
DOT_WINDOW_WEEKS = 4
DOT_MIN_EVENTS = 5
DOT_MIN_FATALITIES = 5

SOURCES: list[IngestionSource] = [
    FixtureSource(),
    ACLEDAggregatedSource(),
    ACLEDLaggedEventSource(),
    UCDPSource(),
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
        if not actor.description and ref.description:
            actor.description = ref.description
        if not actor.wikipedia_url and ref.wikipedia_url:
            actor.wikipedia_url = ref.wikipedia_url
    return actor


def _replace_sources(
    db: Session, crisis: Crisis, refs: list[SourceRef], origin: str
) -> list[Source]:
    """Replace sources owned by this origin only — preserves citations from
    other sources attached to the same crisis."""
    for existing in list(crisis.sources):
        if existing.origin == origin:
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
            retrieved_at=datetime.now(UTC),
            source_type=SourceType(ref.source_type),
            origin=origin,
            body_text=ref.body_text,
        )
        db.add(src)
        created.append(src)
    db.flush()
    return created


def _replace_actor_links(
    db: Session,
    crisis: Crisis,
    actor_refs: list[ActorRef],
    source_rows: list[Source],
    origin: str,
) -> None:
    """Replace ingestion-owned (non-admin-curated) actor links from this
    origin only. Admin-curated links and links from other origins survive."""
    existing_admin: set[int] = set()
    for existing in list(crisis.actor_links):
        if existing.admin_curated:
            existing_admin.add(existing.actor_id)
            continue
        # Drop links whose attributing source is from this origin (or has no
        # source attached — most likely from a single-owner source).
        link_origin = existing.source.origin if existing.source else None
        if link_origin == origin or link_origin is None:
            db.delete(existing)
    db.flush()
    for ref in actor_refs:
        actor = _upsert_actor(db, ref)
        if actor.id in existing_admin:
            continue
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
                admin_curated=False,
            )
        )
    db.flush()


def _replace_events(
    db: Session,
    crisis: Crisis,
    event_refs: list[EventRef],
    source_rows: list[Source],
    origin: str,
) -> None:
    """Replace events whose source is from this origin. Events attached by
    other sources (UCDP, GDELT) are preserved."""
    for existing in list(crisis.events):
        existing_origin = existing.source.origin if existing.source else None
        if existing_origin == origin:
            db.delete(existing)
    db.flush()
    for ref in event_refs:
        source_id = (
            source_rows[ref.source_index].id
            if ref.source_index is not None and 0 <= ref.source_index < len(source_rows)
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


def _replace_intensity_rows(db: Session, crisis_id: int, rows: list[IntensityRow]) -> int:
    """Replace weekly intensity rows for this crisis. Idempotent — same input
    yields same output. Wholesale replace because the aggregate xlsx is
    canonical for the entire 52w window."""
    db.query(CrisisIntensityWeekly).filter(CrisisIntensityWeekly.crisis_id == crisis_id).delete(
        synchronize_session=False
    )
    db.flush()
    for r in rows:
        db.add(
            CrisisIntensityWeekly(
                crisis_id=crisis_id,
                week_start=r.week_start,
                event_type=r.event_type,
                event_count=r.event_count,
                fatalities=r.fatalities,
                population_exposure=r.population_exposure,
            )
        )
    db.flush()
    return len(rows)


def _find_crisis(db: Session, source_name: str, rec: CrisisRecord) -> Crisis | None:
    """Look up an existing crisis. Prefer (country_iso3, admin1_norm) when
    both are set — that's the new natural key. Fall back to legacy
    (source_name, external_id), then to slug: slugs are unique and derived
    from display names, so they survive `_normalize_admin1` changes that
    shift the natural key (the upsert then migrates the row in place)."""
    if rec.country_iso3 and rec.admin1_norm:
        crisis = db.scalar(
            select(Crisis).where(
                Crisis.country_iso3 == rec.country_iso3,
                Crisis.admin1_norm == rec.admin1_norm,
            )
        )
        if crisis is not None:
            return crisis
    crisis = db.scalar(
        select(Crisis).where(
            Crisis.source_name == source_name, Crisis.external_id == rec.external_id
        )
    )
    if crisis is not None:
        return crisis
    return db.scalar(select(Crisis).where(Crisis.slug == rec.slug))


def _upsert_crisis(db: Session, source_name: str, rec: CrisisRecord) -> tuple[Crisis, bool]:
    crisis = _find_crisis(db, source_name, rec)
    created = False
    if crisis is None:
        crisis = Crisis(
            source_name=source_name,
            external_id=rec.external_id,
            slug=rec.slug,
            name=rec.name,
            country=rec.country,
            country_iso3=rec.country_iso3,
            admin1=rec.admin1,
            admin1_norm=rec.admin1_norm,
            region=rec.region,
            lat=rec.lat,
            lng=rec.lng,
            summary=rec.summary,
            status=CrisisStatus(rec.status),
            conflict_type=rec.conflict_type,
            started_at=rec.started_at,
            last_event_at=rec.last_event_at,
            intensity_last_week_at=rec.intensity_last_week_at,
        )
        crisis.geom = f"SRID=4326;POINT({rec.lng} {rec.lat})"
        db.add(crisis)
        db.flush()
        created = True
    else:
        # Update identity fields only when this source is authoritative for them.
        # ACLED aggregated owns admin1; lagged source owns event-derived
        # centroid. Last writer wins for the rest.
        crisis.slug = rec.slug
        crisis.external_id = rec.external_id
        crisis.name = rec.name
        crisis.country = rec.country
        if rec.country_iso3:
            crisis.country_iso3 = rec.country_iso3
        if rec.admin1:
            crisis.admin1 = rec.admin1
        if rec.admin1_norm:
            crisis.admin1_norm = rec.admin1_norm
        crisis.region = rec.region
        crisis.lat = rec.lat
        crisis.lng = rec.lng
        crisis.summary = rec.summary
        crisis.status = CrisisStatus(rec.status)
        crisis.conflict_type = rec.conflict_type
        if rec.started_at:
            crisis.started_at = rec.started_at
        if rec.last_event_at:
            crisis.last_event_at = rec.last_event_at
        if rec.intensity_last_week_at:
            crisis.intensity_last_week_at = rec.intensity_last_week_at
        crisis.geom = f"SRID=4326;POINT({rec.lng} {rec.lat})"
        db.flush()
    return crisis, created


def _refresh_crisis_activity_rollups(db: Session) -> dict:
    """Recompute each crisis's trailing-4-week violent-activity rollup from
    the ACLED weekly aggregates. This is what the globe reads.

    The window is anchored on the newest week present in the aggregate data,
    never wall-clock now: ACLED publishes weekly and lands ~1-2 weeks behind,
    so a wall-clock window would silently empty the globe between releases.

    Every crisis is recomputed, not only those with qualifying activity: a
    region whose violence stopped but whose protests continued still has rows
    in the window, so keying the zero-out on "no rows at all" left it holding
    a month-old count and standing on the globe as a dot that no current data
    justifies.
    """
    types_sql = ", ".join(f"'{t}'" for t in VIOLENT_EVENT_TYPES)
    result = db.execute(
        text(
            f"""
            WITH latest AS (
                SELECT max(week_start) AS w FROM crisis_intensity_weekly
            ),
            agg AS (
                SELECT w.crisis_id,
                       sum(w.event_count) AS ev,
                       sum(w.fatalities) AS fat,
                       max(w.population_exposure) AS pop,
                       max(w.week_start) AS last_week
                FROM crisis_intensity_weekly w, latest
                WHERE w.week_start > latest.w - make_interval(weeks => :weeks)
                  AND w.event_type IN ({types_sql})
                GROUP BY w.crisis_id
            ),
            src AS (
                SELECT c.id AS crisis_id, agg.ev, agg.fat, agg.pop, agg.last_week
                FROM crises c
                LEFT JOIN agg ON agg.crisis_id = c.id
            )
            UPDATE crises c
            SET violence_4w_events = coalesce(src.ev, 0),
                violence_4w_fatalities = coalesce(src.fat, 0),
                violence_4w_pop_exposure = src.pop,
                latest_agg_week = src.last_week
            FROM src
            WHERE c.id = src.crisis_id
              AND (c.violence_4w_events IS DISTINCT FROM coalesce(src.ev, 0)
                OR c.violence_4w_fatalities IS DISTINCT FROM coalesce(src.fat, 0)
                OR c.violence_4w_pop_exposure IS DISTINCT FROM src.pop
                OR c.latest_agg_week IS DISTINCT FROM src.last_week)
            """
        ),
        {"weeks": DOT_WINDOW_WEEKS},
    )
    updated = result.rowcount or 0
    db.commit()
    dots = db.scalar(
        select(func.count())
        .select_from(Crisis)
        .where(
            (Crisis.violence_4w_events >= DOT_MIN_EVENTS)
            | (Crisis.violence_4w_fatalities >= DOT_MIN_FATALITIES)
        )
    )
    return {"crises_updated": updated, "dots": int(dots or 0)}


def _classify_violence(db: Session) -> dict:
    """Label each dot with what kind of violence it is currently seeing.

    Runs on the dots the rollup just recomputed, so the event mix it reads is
    the same window the globe shows. Rules live in
    `app.conflicts.violence_class`; this step only gathers their two inputs —
    the window's event-type mix and the region's actor names — and writes the
    result back.
    """
    from app.conflicts.violence_class import classify_region
    from app.scripts.backfill_routing import actor_names_for_crises

    crises = db.scalars(
        select(Crisis).where(
            (Crisis.violence_4w_events >= DOT_MIN_EVENTS)
            | (Crisis.violence_4w_fatalities >= DOT_MIN_FATALITIES)
        )
    ).all()
    if not crises:
        return {"classified": 0}
    ids = [c.id for c in crises]

    # Every event type, not just the violent ones: the unrest read needs to
    # see how much of a region's activity is protest.
    mix: dict[int, dict[str, int]] = {}
    for row in db.execute(
        text(
            """
            WITH latest AS (
                SELECT max(week_start) AS w FROM crisis_intensity_weekly
            )
            SELECT w.crisis_id, w.event_type, sum(w.event_count) AS ev
            FROM crisis_intensity_weekly w, latest
            WHERE w.crisis_id = ANY(:ids)
              AND w.week_start > latest.w - make_interval(weeks => :weeks)
            GROUP BY w.crisis_id, w.event_type
            """
        ),
        {"ids": ids, "weeks": DOT_WINDOW_WEEKS},
    ).all():
        mix.setdefault(row.crisis_id, {})[row.event_type] = int(row.ev or 0)

    actor_names = actor_names_for_crises(db, ids)
    counts: dict[str, int] = {}
    for crisis in crises:
        cls, basis = classify_region(actor_names.get(crisis.id, []), mix.get(crisis.id, {}))
        crisis.violence_class = cls
        crisis.violence_class_basis = basis
        counts[cls] = counts.get(cls, 0) + 1
    db.commit()
    return {"classified": len(crises), **counts}


def _attach_field_reports(db: Session) -> dict:
    """Fetch recent ReliefWeb situation reports for every country that has a
    dot on the globe, stored once per (country, url) as country-scoped
    sources (origin='reliefweb').

    Country-scoped rather than conflict-scoped: a situation report covers a
    place, and every region dot in that country should be able to show it —
    not just the handful of regions a named conflict claims. Skipped when
    RELIEFWEB_APPNAME is unset.
    """
    from app.ingestion.reliefweb import fetch_situation_reports

    if not settings.reliefweb_appname.strip():
        return {"attached": 0}
    iso3s = [
        row[0]
        for row in db.execute(
            select(Crisis.country_iso3)
            .where(
                Crisis.country_iso3.is_not(None),
                (Crisis.violence_4w_events >= DOT_MIN_EVENTS)
                | (Crisis.violence_4w_fatalities >= DOT_MIN_FATALITIES),
            )
            .distinct()
        ).all()
    ]
    cache: dict[str, list] = {}
    attached = 0
    for iso3 in iso3s:
        for ref in fetch_situation_reports(iso3, cache):
            existing = db.scalar(
                select(Source).where(
                    Source.country_iso3 == iso3,
                    Source.url == ref.url,
                    Source.origin == "reliefweb",
                )
            )
            if existing is not None:
                continue
            db.add(
                Source(
                    country_iso3=iso3,
                    title=ref.title,
                    url=ref.url,
                    publisher=ref.publisher,
                    published_at=ref.published_at,
                    retrieved_at=datetime.now(UTC),
                    source_type=SourceType(ref.source_type),
                    origin="reliefweb",
                    body_text=ref.body_text,
                )
            )
            attached += 1
    db.commit()
    return {"attached": attached, "countries": len(iso3s)}


def _reference_now() -> datetime:
    """Anchor for staleness windows. Falls back to wall-clock UTC when
    ACLED_REFERENCE_DATE is unset. Matches the convention used by
    `app.scripts.backfill_routing._reference_now`."""
    if settings.acled_reference_date:
        try:
            return datetime.fromisoformat(settings.acled_reference_date).replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def _sweep_stale_active(db: Session, stale_days: int) -> int:
    """Demote active crises with no recent events to `frozen`."""
    if stale_days <= 0:
        return 0
    cutoff = _reference_now() - timedelta(days=stale_days)
    result = db.execute(
        update(Crisis)
        .where(
            Crisis.status == CrisisStatus.active,
            Crisis.last_event_at.is_not(None),
            Crisis.last_event_at < cutoff,
        )
        .values(status=CrisisStatus.frozen)
    )
    return result.rowcount or 0


def _sweep_stale_conflicts(db: Session, stale_days: int) -> int:
    """Demote active conflicts whose last_event_at predates the cutoff."""
    if stale_days <= 0:
        return 0
    cutoff = _reference_now() - timedelta(days=stale_days)
    result = db.execute(
        update(Conflict)
        .where(
            Conflict.status == ConflictStatus.active,
            Conflict.last_event_at.is_not(None),
            Conflict.last_event_at < cutoff,
        )
        .values(status=ConflictStatus.frozen)
    )
    return result.rowcount or 0


def _promote_emerging_conflicts(db: Session, threshold: int) -> int:
    """Flip emerging → active for conflicts whose 4w event count crosses
    the threshold. Auto-discovered registry rows (registry_source='wiki-auto')
    surface as active to the public API once activity is observed."""
    if threshold <= 0:
        return 0
    result = db.execute(
        update(Conflict)
        .where(
            Conflict.status == ConflictStatus.emerging,
            Conflict.intensity_4w_events >= threshold,
        )
        .values(status=ConflictStatus.active)
    )
    return result.rowcount or 0


def _start_ingest_run(trigger: str) -> int | None:
    """Open an ingest_runs row on its own session.

    Deliberately separate from the ingest session: if that one is poisoned by
    a failed source, the record of the failure still has to land.
    """
    try:
        with SessionLocal() as rec_db:
            run = IngestRun(trigger=trigger)
            rec_db.add(run)
            rec_db.commit()
            return run.id
    except Exception:
        logger.exception("could not open ingest_runs row")
        return None


def _finish_ingest_run(run_id: int | None, ok: bool, result: dict, error: str | None) -> None:
    if run_id is None:
        return
    try:
        with SessionLocal() as rec_db:
            rec_db.execute(
                update(IngestRun)
                .where(IngestRun.id == run_id)
                .values(
                    finished_at=datetime.now(UTC),
                    ok=ok,
                    result=result,
                    error=error,
                )
            )
            rec_db.commit()
    except Exception:
        logger.exception("could not close ingest_runs row %s", run_id)


def run_all_sources(db: Session | None = None, trigger: str = "cron") -> dict:
    close_after = db is None
    db = db or SessionLocal()
    result: dict = {"sources": [], "total_inserted": 0, "total_updated": 0}
    run_id = _start_ingest_run(trigger)
    error: str | None = None
    try:
        # Build the routing index once so attach-only sources can set
        # conflict_id at insert time (events stay routed even if this run
        # dies before the backfill pass below).
        from app.scripts.backfill_routing import _load_routing_index

        routing_idx = _load_routing_index(db)

        for source in SOURCES:
            # Each source is isolated: an unattended run must degrade, not
            # abort. Everything below the loop — dot rollups, routing, the
            # staleness sweeps — is what keeps the globe current, and it
            # stays useful even when one upstream feed is down.
            try:
                if getattr(source, "attach_only", False):
                    counts = source.attach_events(db, routing_idx)
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
                present_keys: set[tuple[str, str]] = set()
                for rec in records:
                    crisis, created = _upsert_crisis(db, source.name, rec)
                    if rec.country_iso3 and rec.admin1_norm:
                        present_keys.add((rec.country_iso3, rec.admin1_norm))

                    if source.owns_sources:
                        source_rows = _replace_sources(db, crisis, rec.sources, source.name)
                    else:
                        source_rows = []
                    if source.owns_actors:
                        _replace_actor_links(db, crisis, rec.actors, source_rows, source.name)
                    if source.owns_events:
                        _replace_events(db, crisis, rec.events, source_rows, source.name)
                    if rec.intensity_rows:
                        _replace_intensity_rows(db, crisis.id, rec.intensity_rows)

                    if created:
                        inserted += 1
                    else:
                        updated += 1

                # Source-specific post-pass hooks.
                seed_aliases = getattr(source, "post_upsert_alias_seed", None)
                if seed_aliases is not None:
                    seed_aliases(db, records)
                entry: dict = {
                    "source": source.name,
                    "inserted": inserted,
                    "updated": updated,
                }
                # sweep_dropped DELETES crises absent from this run. A source
                # that only partly fetched still emits records, so gate the
                # sweep on the source vouching for its own fetch — otherwise
                # three failed region downloads silently delete half the globe.
                sweep_dropped = getattr(source, "sweep_dropped", None)
                if sweep_dropped is not None and present_keys:
                    if getattr(source, "fetch_complete", True):
                        sweep_count = sweep_dropped(db, present_keys)
                        if sweep_count:
                            entry["dropped"] = sweep_count
                    else:
                        logger.warning("%s: incomplete fetch — skipping drop sweep", source.name)
                        entry["sweep_skipped"] = "incomplete fetch"
                db.commit()
                result["sources"].append(entry)
                result["total_inserted"] += inserted
                result["total_updated"] += updated
            except Exception as exc:
                db.rollback()
                logger.exception("source %s failed", source.name)
                result["sources"].append({"source": source.name, "error": str(exc)})
                continue

        # Refresh the globe's dot layer from the freshly-ingested aggregates
        # before anything else in the tail — this is what the map reads.
        result["dot_rollups"] = _refresh_crisis_activity_rollups(db)
        result["violence_classes"] = _classify_violence(db)

        # Route + roll up FIRST — this is the load-bearing tail step, so it
        # runs before anything slow or network-bound can kill the run.
        # backfill() re-routes any events route-on-attach missed and refreshes
        # per-conflict rollups (centroid / last_event_at / intensity_4w_*).
        # It opens its own session and commits internally, so it's safe to
        # call inside the outer session.
        from app.scripts.backfill_routing import backfill as _route_events

        route_report = _route_events(commit=True, flip_legacy=False)
        result["routing"] = {
            "routed": route_report.get("routed_events"),
            "orphans": route_report.get("orphan_events"),
        }

        promoted = _promote_emerging_conflicts(db, settings.conflict_auto_promotion_events_4w)
        if promoted:
            db.commit()
        result["conflicts_promoted"] = promoted

        conflicts_frozen = _sweep_stale_conflicts(db, settings.conflict_stale_days)
        if conflicts_frozen:
            db.commit()
        result["conflicts_frozen"] = conflicts_frozen

        demoted = _sweep_stale_active(db, settings.status_stale_days)
        if demoted:
            db.commit()
        result["status_demoted"] = demoted

        # ReliefWeb situation reports — the dossier's current-narrative
        # section. Network-bound and non-critical, so it must not fail ingest.
        try:
            result["field_reports"] = _attach_field_reports(db)
        except Exception as exc:
            db.rollback()
            result["field_reports"] = {"error": str(exc)}

        # Wikipedia auto-discovery runs REPORT-ONLY: it surfaces candidate
        # conflicts in the ingest result for an admin to curate into
        # registry.yaml, but never inserts rows itself — an earlier auto-
        # insert pass flooded the registry with junk/duplicate storylines.
        try:
            from app.ingestion.wikipedia_discovery import discover as _wiki_discover

            wiki_report = _wiki_discover(commit=False)
            result["wiki_discovery"] = {
                "inspected": wiki_report.get("inspected"),
                "candidates": wiki_report.get("inserted"),
                "skipped_existing": wiki_report.get("skipped_existing"),
            }
        except Exception as exc:  # network errors etc. — don't fail ingest
            result["wiki_discovery"] = {"error": str(exc)}

        # NER runs LAST and capped per run — the spaCy pass over a large
        # backlog takes minutes and used to starve routing when it sat
        # earlier in the tail. A big backlog drains over a few runs.
        ner_counts = ner_process_pending(db, max_events=NER_MAX_EVENTS_PER_RUN)
        result["ner"] = ner_counts
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        # A run is only "ok" if the tail completed AND every source did.
        # A recorded run that half-worked must not read as healthy.
        source_failed = any("error" in s for s in result["sources"])
        _finish_ingest_run(
            run_id, ok=error is None and not source_failed, result=result, error=error
        )
        if close_after:
            db.close()
    return result


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    print(run_all_sources())

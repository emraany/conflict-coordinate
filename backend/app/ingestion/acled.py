"""ACLED lagged-event source — attaches detailed events to existing dots.

ACLED Researcher tier API exposes only a rolling ~12 months of event-level
data. By the time we read it, every record is at least a year old. So the
lagged source no longer creates dots — it attaches event detail (incident
prose, actors, fatalities, geolocation) to dots whose identity was
established by the real-time aggregated source.

Lookup key: each ACLED event publishes `country` + `admin1`. We resolve via
the `admin1_aliases` table to a canonical `(country_iso3, admin1_norm)` and
attach to the matching `Crisis`. Events whose admin1 doesn't resolve are
logged and dropped.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from statistics import mean

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.conflicts.routing import route_event
from app.ingestion import wikipedia
from app.ingestion.acled_auth import get_fresh_token, get_token
from app.ingestion.base import IngestionSource
from app.ingestion.countries import country_iso3 as _country_iso3
from app.models import (
    Actor,
    ActorRole,
    ActorType,
    Conflict,
    Crisis,
    CrisisActor,
    Source,
    SourceType,
)
from app.models.admin1 import Admin1Alias
from app.models.event import CrisisEvent

logger = logging.getLogger(__name__)

NOTES_MAX_CHARS = 2000
ACLED_READ_URL = "https://acleddata.com/api/acled/read"

# Display centroid is updated when the running mean drifts past this many
# degrees (~5 km at the equator). Keeps dot positions visually responsive
# without thrashing on every event.
CENTROID_DRIFT_THRESHOLD_DEG = 0.05


def _normalize_admin1(value: str | None) -> str:
    if not value:
        return ""
    import unicodedata

    s = unicodedata.normalize("NFKD", value)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^the\s+", "", s)
    s = re.sub(
        r"\s+("
        r"governorate|province|state|region|prefecture|district|wilayat|"
        r"muhafazah|oblast|raion|voivodeship|canton|department|county|"
        r"municipality|federal subject|federal district|territory"
        r")$",
        "",
        s,
    )
    return s


def _parse_coord(val: object) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _latest_available_event_date(client: httpx.Client, access_token: str):
    """ACLED access tiers embargo recent data (~12 months for this account).
    Scan back in 30-day windows to find the freshest one that returns rows,
    so the lookback anchors to *available* data — anchoring to wall-clock
    today would fetch nothing."""
    today = datetime.now(UTC).date()
    headers = {"Authorization": f"Bearer {access_token}"}
    for back in range(24):
        end = today - timedelta(days=30 * back)
        start = end - timedelta(days=30)
        resp = client.get(
            ACLED_READ_URL,
            params={
                "event_date": f"{start.isoformat()}|{end.isoformat()}",
                "event_date_where": "BETWEEN",
                "limit": 1,
                "page": 1,
            },
            headers=headers,
            timeout=60.0,
        )
        resp.raise_for_status()
        payload = resp.json()
        batch = payload.get("data", []) if isinstance(payload, dict) else payload
        if batch:
            return end
    return None


def _fetch_events(client: httpx.Client, access_token: str) -> list[dict]:
    lookback_days = settings.acled_lookback_days
    if settings.acled_reference_date:
        from datetime import date as _date

        end = _date.fromisoformat(settings.acled_reference_date)
    else:
        end = _latest_available_event_date(client, access_token)
        if end is None:
            logger.warning("acled-lagged: no available event data found; skipping")
            return []
    start = end - timedelta(days=lookback_days)
    headers = {"Authorization": f"Bearer {access_token}"}
    out: list[dict] = []
    page = 1
    while True:
        resp = client.get(
            ACLED_READ_URL,
            params={
                "event_date": f"{start.isoformat()}|{end.isoformat()}",
                "event_date_where": "BETWEEN",
                "limit": 5000,
                "page": page,
            },
            headers=headers,
            timeout=60.0,
        )
        resp.raise_for_status()
        payload = resp.json()
        batch = payload.get("data", []) if isinstance(payload, dict) else payload
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 5000:
            break
        page += 1
        if page > 40:
            break
    return out


def _load_alias_map(db: Session) -> dict[tuple[str, str], str]:
    """Bulk-load the entire (iso3, alias_norm) → canonical_norm map.
    Replaces ~200k per-event SQL lookups with one query."""
    rows = db.execute(
        select(
            Admin1Alias.country_iso3,
            Admin1Alias.alias_norm,
            Admin1Alias.canonical_admin1_norm,
        )
    ).all()
    return {(iso3, alias): canon for iso3, alias, canon in rows}


def _load_crisis_index(db: Session) -> dict[tuple[str, str], int]:
    """Bulk-load (iso3, admin1_norm) → crisis_id mapping for current dots."""
    rows = db.execute(
        select(Crisis.country_iso3, Crisis.admin1_norm, Crisis.id).where(
            Crisis.country_iso3.is_not(None), Crisis.admin1_norm.is_not(None)
        )
    ).all()
    return {(iso3, admin1): cid for iso3, admin1, cid in rows}


def _resolve_admin1_norm(
    alias_map: dict[tuple[str, str], str], country_iso3: str, admin1: str
) -> str | None:
    """In-memory lookup against the prebuilt alias map; falls back to direct
    normalization for new aliases not yet in the table."""
    norm = _normalize_admin1(admin1)
    if not norm:
        return None
    return alias_map.get((country_iso3, norm), norm)


def _ensure_acled_source(db: Session, crisis: Crisis) -> Source:
    """Make sure the crisis has an ACLED canonical citation (origin='acled')
    and return it. Idempotent — one row per crisis."""
    existing = db.scalar(
        select(Source).where(Source.crisis_id == crisis.id, Source.origin == "acled")
    )
    if existing is not None:
        return existing
    src = Source(
        crisis_id=crisis.id,
        title="ACLED — Armed Conflict Location & Event Data",
        url="https://acleddata.com/",
        publisher="ACLED",
        retrieved_at=datetime.now(UTC),
        source_type=SourceType("primary"),
        origin="acled",
    )
    db.add(src)
    db.flush()
    return src


def _existing_event_ids(db: Session, crisis_id: int) -> set[str]:
    rows = db.scalars(
        select(CrisisEvent.external_id).where(CrisisEvent.crisis_id == crisis_id)
    ).all()
    return {r for r in rows if r}


def _existing_actors(db: Session, crisis_id: int) -> set[int]:
    """Actor IDs already linked to this crisis (any origin, curated or not)."""
    rows = db.scalars(
        select(CrisisActor.actor_id).where(CrisisActor.crisis_id == crisis_id)
    ).all()
    return set(rows)


def _event_actor_strings(ev: dict) -> list[str]:
    """Raw actor names on an ACLED event, for conflict routing."""
    out: list[str] = []
    for key in ("actor1", "actor2"):
        raw = (ev.get(key) or "").strip()
        if raw:
            out.append(raw)
    for key in ("assoc_actor_1", "assoc_actor_2"):
        raw = (ev.get(key) or "").strip()
        for piece in raw.split(";"):
            piece = piece.strip()
            if piece:
                out.append(piece)
    return out


def _attach_events_for_group(
    db: Session,
    crisis: Crisis,
    events: list[dict],
    wiki_client: httpx.Client | None,
    actor_cache: dict[str, tuple[str | None, str | None]],
    routing_idx=None,
    conflict_latest: dict[int, datetime] | None = None,
) -> tuple[int, int]:
    """Attach this group of ACLED events to one crisis. Returns
    (events_attached, actors_attached)."""
    src = _ensure_acled_source(db, crisis)
    seen = _existing_event_ids(db, crisis.id)

    inserted_events = 0
    centroid_lats: list[float] = []
    centroid_lngs: list[float] = []
    for ev in events:
        event_id = (ev.get("event_id_cnty") or "").strip()
        if not event_id:
            continue
        external_id = f"acled:{event_id}"
        if external_id in seen:
            continue
        date_str = (ev.get("event_date") or "").strip()
        if not date_str:
            continue
        try:
            occurred = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
        except ValueError:
            continue

        notes = (ev.get("notes") or "").strip() or None
        if notes and len(notes) > NOTES_MAX_CHARS:
            notes = notes[: NOTES_MAX_CHARS - 1].rstrip() + "…"

        sub_type = (ev.get("sub_event_type") or "").strip()
        main_type = (ev.get("event_type") or "").strip()
        event_type = sub_type or main_type or None
        location_name = (
            (ev.get("location") or "").strip()
            or (ev.get("admin3") or "").strip()
            or (ev.get("admin2") or "").strip()
            or None
        )
        lat = _parse_coord(ev.get("latitude"))
        lng = _parse_coord(ev.get("longitude"))
        if lat is not None and lng is not None:
            centroid_lats.append(lat)
            centroid_lngs.append(lng)

        conflict_id = None
        if routing_idx is not None:
            conflict_id = route_event(
                _event_actor_strings(ev),
                crisis.country_iso3,
                crisis.admin1_norm,
                routing_idx,
            )

        db.add(
            CrisisEvent(
                crisis_id=crisis.id,
                occurred_at=occurred,
                event_type=event_type,
                description=notes,
                fatalities=int(ev.get("fatalities") or 0),
                location_name=location_name,
                lat=lat,
                lng=lng,
                external_id=external_id,
                source_id=src.id,
                conflict_id=conflict_id,
            )
        )
        inserted_events += 1
        seen.add(external_id)

        latest = crisis.last_event_at
        if latest is None or occurred > latest:
            crisis.last_event_at = occurred
        if conflict_id is not None and conflict_latest is not None:
            prev = conflict_latest.get(conflict_id)
            if prev is None or occurred > prev:
                conflict_latest[conflict_id] = occurred

    # Lazy display-centroid update: shift only if drift is meaningful.
    if centroid_lats and centroid_lngs:
        new_lat = float(mean(centroid_lats))
        new_lng = float(mean(centroid_lngs))
        if (
            abs(new_lat - crisis.lat) > CENTROID_DRIFT_THRESHOLD_DEG
            or abs(new_lng - crisis.lng) > CENTROID_DRIFT_THRESHOLD_DEG
        ):
            crisis.lat = new_lat
            crisis.lng = new_lng
            crisis.geom = f"SRID=4326;POINT({new_lng} {new_lat})"

    actor_count = _attach_actors_for_group(
        db, crisis, events, src, wiki_client, actor_cache
    )
    db.flush()
    return inserted_events, actor_count


def _attach_actors_for_group(
    db: Session,
    crisis: Crisis,
    events: list[dict],
    src: Source,
    wiki_client: httpx.Client | None,
    actor_cache: dict[str, tuple[str | None, str | None]],
) -> int:
    """Derive actors from event actor1/actor2 fields, dedupe, link.

    Filters by document frequency (actor must appear in ≥ threshold of
    events) so transient noise doesn't pollute the actor list. Always keeps
    at least the top 3 most-mentioned actors so tiny groups still get content.
    """
    n = len(events)
    if n == 0:
        return 0
    doc_freq: dict[str, int] = {}
    display_for: dict[str, str] = {}
    for ev in events:
        seen_in_ev: set[str] = set()
        for key in ("actor1", "actor2", "assoc_actor_1", "assoc_actor_2"):
            raw = (ev.get(key) or "").strip()
            if not raw:
                continue
            for piece in raw.split(";"):
                piece = piece.strip()
                if not piece:
                    continue
                norm = piece.lower()
                if norm in seen_in_ev:
                    continue
                seen_in_ev.add(norm)
                doc_freq[norm] = doc_freq.get(norm, 0) + 1
                display_for.setdefault(norm, piece)

    if not doc_freq:
        return 0
    threshold = max(1, int(settings.acled_topic_actor_freq_threshold * n))
    ranked = sorted(doc_freq.items(), key=lambda kv: kv[1], reverse=True)
    keep: list[tuple[str, str, int]] = []
    for norm, freq in ranked:
        if freq >= threshold or len(keep) < 3:
            keep.append((norm, display_for[norm], freq))
        if len(keep) >= 30:
            break

    existing_actor_ids = _existing_actors(db, crisis.id)
    inserted = 0
    enriched = 0
    for _norm, display, _freq in keep:
        actor = db.scalar(select(Actor).where(Actor.name == display))
        description: str | None = None
        wiki_url: str | None = None
        if wiki_client is not None and enriched < 5:
            try:
                description, wiki_url = wikipedia.fetch_actor_summary(
                    display, actor_cache, client=wiki_client
                )
                if description:
                    enriched += 1
            except Exception:  # pragma: no cover — best-effort enrichment
                logger.debug("wikipedia lookup failed for %s", display, exc_info=True)
        if actor is None:
            actor = Actor(
                name=display,
                type=ActorType("other"),
                description=description,
                wikipedia_url=wiki_url,
            )
            db.add(actor)
            db.flush()
        else:
            if not actor.description and description:
                actor.description = description
            if not actor.wikipedia_url and wiki_url:
                actor.wikipedia_url = wiki_url
        if actor.id in existing_actor_ids:
            continue
        db.add(
            CrisisActor(
                crisis_id=crisis.id,
                actor_id=actor.id,
                role=ActorRole("party"),
                source_id=src.id,
                admin_curated=False,
            )
        )
        existing_actor_ids.add(actor.id)
        inserted += 1
    return inserted


def _bump_conflicts_last_event(
    db: Session, conflict_latest: dict[int, datetime]
) -> None:
    """Advance Conflict.last_event_at for conflicts that received newer
    routed events this run. Shared by the attach-only sources."""
    if not conflict_latest:
        return
    conflicts = db.scalars(
        select(Conflict).where(Conflict.id.in_(conflict_latest.keys()))
    ).all()
    for c in conflicts:
        new_last = conflict_latest[c.id]
        if c.last_event_at is None or new_last > c.last_event_at:
            c.last_event_at = new_last
    db.flush()


def _purge_legacy_acled_clusters(db: Session) -> int:
    """One-shot cleanup of the old DBSCAN-clustered ACLED crises (source_name
    = 'acled' with no admin1_norm). They've been superseded by aggregated-
    source dots; their slugs roll into `crisis_slug_aliases` first to keep
    bookmarks alive."""
    from app.models import CrisisSlugAlias

    legacy = db.scalars(
        select(Crisis).where(
            Crisis.source_name == "acled",
            Crisis.admin1_norm.is_(None),
        )
    ).all()
    if not legacy:
        return 0
    deleted = 0
    for crisis in legacy:
        # Best-effort: try to map old slug → matching new (iso3, admin1) crisis.
        # Without a derived admin1, we have nothing to map to. Fall back to
        # country-level mapping via the country name.
        target_iso3 = _country_iso3(crisis.country)
        if target_iso3:
            target = db.scalar(
                select(Crisis)
                .where(
                    Crisis.country_iso3 == target_iso3,
                    Crisis.admin1_norm.is_not(None),
                )
                .order_by(Crisis.last_event_at.desc().nullslast())
                .limit(1)
            )
            if target is not None and crisis.slug != target.slug:
                exists = db.scalar(
                    select(CrisisSlugAlias).where(
                        CrisisSlugAlias.old_slug == crisis.slug
                    )
                )
                if exists is None:
                    db.add(
                        CrisisSlugAlias(old_slug=crisis.slug, crisis_id=target.id)
                    )
        db.delete(crisis)
        deleted += 1
    db.flush()
    return deleted


class ACLEDLaggedEventSource(IngestionSource):
    name = "acled-lagged"
    attach_only = True
    owns_actors = True
    owns_events = True
    owns_sources = True

    def fetch(self) -> list:  # attach-only — runner calls attach_events instead
        return []

    def before_run(self, db: Session) -> None:
        if not settings.acled_enabled:
            return
        purged = _purge_legacy_acled_clusters(db)
        if purged:
            logger.info("acled-lagged: purged %d legacy DBSCAN crises", purged)

    def attach_events(self, db: Session, routing_idx=None) -> dict:
        if not settings.acled_enabled:
            return {"attached": 0, "skipped": 0}
        if not settings.acled_username or not settings.acled_password:
            return {"attached": 0, "skipped": 0}

        with httpx.Client(timeout=60.0) as client:
            tok = get_token(client)
            try:
                events = _fetch_events(client, tok.access_token)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 401:
                    raise
                # Dead cached token chain — force one password grant and retry.
                tok = get_fresh_token(client)
                events = _fetch_events(client, tok.access_token)

        # Bulk-load lookup maps once — per-event SQL would be prohibitive
        # with ~100k events.
        alias_map = _load_alias_map(db)
        crisis_index = _load_crisis_index(db)

        # Group events by (iso3, admin1_norm).
        grouped: dict[tuple[str, str], list[dict]] = {}
        skipped_unmappable = 0
        for ev in events:
            country = (ev.get("country") or "").strip()
            admin1 = (ev.get("admin1") or "").strip()
            iso3 = _country_iso3(country)
            if not iso3 or not admin1:
                skipped_unmappable += 1
                continue
            admin1_norm = _resolve_admin1_norm(alias_map, iso3, admin1)
            if not admin1_norm:
                skipped_unmappable += 1
                continue
            grouped.setdefault((iso3, admin1_norm), []).append(ev)

        # Wikipedia enrichment only when explicitly enabled — its 14k+ HTTP
        # round-trips dominate the run otherwise. Re-enable per-actor by
        # backfilling later.
        wiki_client: httpx.Client | None = None
        if settings.acled_lagged_wiki_enrich:
            wiki_client = httpx.Client(
                timeout=httpx.Timeout(10.0, connect=5.0),
                headers={
                    "User-Agent": (
                        "ConflictCoordinate/0.1 "
                        "(https://github.com/emraany/conflict-coordinate)"
                    ),
                    "Accept": "application/json",
                },
            )
        actor_cache: dict[str, tuple[str | None, str | None]] = {}
        conflict_latest: dict[int, datetime] = {}
        attached_events = 0
        attached_actors = 0
        skipped_no_crisis = 0
        groups_done = 0
        try:
            for (iso3, admin1_norm), group in grouped.items():
                crisis_id = crisis_index.get((iso3, admin1_norm))
                if crisis_id is None:
                    skipped_no_crisis += len(group)
                    continue
                # Lazy-load Crisis ORM row for the group only.
                crisis = db.get(Crisis, crisis_id)
                if crisis is None:
                    skipped_no_crisis += len(group)
                    continue
                ev_count, actor_count = _attach_events_for_group(
                    db, crisis, group, wiki_client, actor_cache,
                    routing_idx, conflict_latest,
                )
                attached_events += ev_count
                attached_actors += actor_count
                groups_done += 1
                # Periodic commit so progress is durable + memory bounded.
                if groups_done % 100 == 0:
                    db.commit()
                    logger.info(
                        "acled-lagged: progress %d/%d groups, %d events attached",
                        groups_done,
                        len(grouped),
                        attached_events,
                    )
        finally:
            if wiki_client is not None:
                wiki_client.close()

        _bump_conflicts_last_event(db, conflict_latest)
        db.commit()
        logger.info(
            "acled-lagged: attached=%d (events) actors=%d skipped_no_crisis=%d "
            "skipped_unmappable=%d groups=%d",
            attached_events,
            attached_actors,
            skipped_no_crisis,
            skipped_unmappable,
            len(grouped),
        )
        return {
            "attached": attached_events,
            "skipped": skipped_no_crisis + skipped_unmappable,
            "actors_attached": attached_actors,
        }

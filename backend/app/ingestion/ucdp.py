"""UCDP GED ingestion source — attach-only, admin1-keyed.

Fetches georeferenced events from the Uppsala Conflict Data Program (UCDP)
Georeferenced Event Dataset (GED) and attaches each to the matching crisis
by `(country_iso3, admin1_norm)` lookup. UCDP carries `country` + `adm_1`
fields; we resolve via the `admin1_aliases` table, which the aggregated
source self-populates with the canonical ACLED vocabulary.

If the alias resolution misses, we fall back to point-in-polygon against
the `admin1_polygons` layer (Natural Earth). Events with `where_prec > 5`
(country/region centroids only) are dropped — too coarse to attach with
any confidence.

UCDP GED v25.1 covers 1989–2024. Authentication: static API token via
`x-ucdp-access-token` header.

Neutrality: event headlines copied verbatim from `source_headline`. Actor
rows are NOT created from UCDP — the actor graph stays single-rooted in
ACLED data.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.conflicts.routing import route_event
from app.ingestion.acled import _bump_conflicts_last_event, _normalize_admin1
from app.ingestion.base import CrisisRecord, IngestionSource
from app.ingestion.countries import country_iso3 as _country_iso3
from app.models import Crisis, Source, SourceType
from app.models.admin1 import Admin1Alias
from app.models.event import CrisisEvent

logger = logging.getLogger(__name__)

_API_BASE = "https://ucdpapi.pcr.uu.se/api"
_HEADLINE_MAX_CHARS = 2000

# where_prec >= 6 means country/region centroid only — drop these.
_MIN_WHERE_PREC_ACCEPTABLE = 5

VIOLENCE_TYPE_MAP = {
    1: "state_conflict",
    2: "non_state_conflict",
    3: "one_sided_violence",
}


def _parse_coord(val: object) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _cutoff_date(lookback_days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=lookback_days)


def _fetch_version(
    client: httpx.Client, headers: dict, version: str, cutoff_str: str
) -> list[dict]:
    events: list[dict] = []
    page = 1
    page_ceil = 200
    while True:
        try:
            resp = client.get(
                f"{_API_BASE}/gedevents/{version}",
                params={
                    "pagesize": 1000,
                    "page": page,
                    "StartDate": cutoff_str,
                },
                headers=headers,
                timeout=60.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("ucdp fetch error version=%s page=%s: %s", version, page, exc)
            break
        payload = resp.json()
        batch: list[dict] = payload.get("Result") or []
        if not batch:
            break
        events.extend(batch)
        if len(batch) < 1000:
            break
        page += 1
        if page > page_ceil:
            logger.warning("ucdp: hit page ceiling (%s) for %s, stopping", page_ceil, version)
            break
    return events


def _probe_next_candidates(
    client: httpx.Client, headers: dict, versions: list[str], max_probe: int = 6
) -> list[str]:
    """Auto-discover monthly candidate releases newer than the configured
    ones (e.g. configured …,26.0.5 → probe 26.0.6, 26.0.7, …). Each probe is
    a 1-row request; unknown versions 404 and stop the scan. Removes the
    manual monthly bump of UCDP_CANDIDATE_VERSIONS."""
    candidates = [v for v in versions if v.count(".") == 2]
    if not candidates:
        return []
    try:
        base = max(candidates, key=lambda v: tuple(int(p) for p in v.split(".")))
        a, b, c = (int(p) for p in base.split("."))
    except ValueError:
        return []
    found: list[str] = []
    for i in range(1, max_probe + 1):
        version = f"{a}.{b}.{c + i}"
        try:
            resp = client.get(
                f"{_API_BASE}/gedevents/{version}",
                params={"pagesize": 1, "page": 1},
                headers=headers,
                timeout=30.0,
            )
        except httpx.HTTPError:
            break
        if resp.status_code != 200:
            break
        found.append(version)
    if found:
        logger.info("ucdp: auto-discovered candidate versions %s", found)
    return found


def _fetch_events(client: httpx.Client) -> list[dict]:
    """Fetch the curated GED version plus any configured monthly candidate
    releases. Candidates carry event-level recency past the curated cutoff
    (e.g. 26.1 ends 2025-12; candidates 26.0.x cover 2026 months). Cross-
    version duplicates collapse downstream via the ucdp:{id} external_id."""
    headers = {"x-ucdp-access-token": settings.ucdp_token}
    cutoff = _cutoff_date(settings.ucdp_lookback_days)
    cutoff_str = cutoff.date().isoformat()

    versions = [settings.ucdp_ged_version] + [
        v.strip() for v in settings.ucdp_candidate_versions.split(",") if v.strip()
    ]
    versions += _probe_next_candidates(client, headers, versions)
    all_events: list[dict] = []
    for version in versions:
        batch = _fetch_version(client, headers, version, cutoff_str)
        logger.info("ucdp: version %s → %d events", version, len(batch))
        all_events.extend(batch)
    return all_events


def _load_alias_map(db: Session) -> dict[tuple[str, str], str]:
    rows = db.execute(
        select(
            Admin1Alias.country_iso3,
            Admin1Alias.alias_norm,
            Admin1Alias.canonical_admin1_norm,
        )
    ).all()
    return {(iso3, alias): canon for iso3, alias, canon in rows}


def _load_crisis_index(db: Session) -> dict[tuple[str, str], int]:
    rows = db.execute(
        select(Crisis.country_iso3, Crisis.admin1_norm, Crisis.id).where(
            Crisis.country_iso3.is_not(None), Crisis.admin1_norm.is_not(None)
        )
    ).all()
    return {(iso3, admin1): cid for iso3, admin1, cid in rows}


def _resolve_admin1_via_pip(
    db: Session, country_iso3: str, lat: float, lng: float
) -> str | None:
    """Last-ditch admin1 lookup via PostGIS point-in-polygon. Used when the
    alias table doesn't recognize the admin1 string (rare for real admin
    units; common when UCDP records "Unknown" or admin0-only)."""
    stmt = text(
        """
        SELECT admin1_norm
        FROM admin1_polygons
        WHERE country_iso3 = :iso3
          AND ST_Contains(geom, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326))
        LIMIT 1
        """
    )
    row = db.execute(stmt, {"iso3": country_iso3, "lat": lat, "lng": lng}).first()
    return str(row[0]) if row else None


def _upsert_source(
    db: Session, crisis_id: int, url: str, headline: str | None
) -> Source:
    existing = db.scalar(
        select(Source).where(
            Source.crisis_id == crisis_id,
            Source.url == url,
            Source.origin == "ucdp",
        )
    )
    if existing is not None:
        return existing
    title = (headline or "UCDP source article")[:460]
    src = Source(
        crisis_id=crisis_id,
        title=title,
        url=url[:1000],
        publisher=None,
        retrieved_at=datetime.now(UTC),
        source_type=SourceType.news,
        origin="ucdp",
    )
    db.add(src)
    db.flush()
    return src


def _purge_legacy_ucdp_crises(db: Session) -> int:
    """One-shot cleanup for the attach-only migration. Cascades via FKs."""
    result = db.execute(text("DELETE FROM crises WHERE source_name = 'ucdp'"))
    n = result.rowcount or 0
    if n:
        logger.info("ucdp: purged %d legacy standalone crises", n)
    return n


class UCDPSource(IngestionSource):
    name = "ucdp"
    attach_only = True

    def fetch(self) -> list[CrisisRecord]:
        return []

    def attach_events(self, db: Session, routing_idx=None) -> dict:  # noqa: C901
        if not settings.ucdp_enabled:
            return {"attached": 0, "skipped": 0}
        if not settings.ucdp_token:
            logger.warning("ucdp: UCDP_TOKEN not set, skipping")
            return {"attached": 0, "skipped": 0}

        _purge_legacy_ucdp_crises(db)
        db.flush()

        with httpx.Client() as client:
            events = _fetch_events(client)
        logger.info("ucdp: fetched %d events", len(events))

        alias_map = _load_alias_map(db)
        crisis_index = _load_crisis_index(db)

        attached = 0
        skipped = 0
        skipped_no_admin1 = 0
        skipped_no_crisis = 0
        skipped_pip_used = 0  # admin1 came from PIP fallback (informational)
        seen_ids: set[str] = set()
        latest_per_crisis: dict[int, datetime] = {}
        conflict_latest: dict[int, datetime] = {}

        for ev in events:
            event_id = str(ev.get("id") or "").strip()
            if not event_id or event_id in seen_ids:
                continue
            seen_ids.add(event_id)
            ext_id = f"ucdp:{event_id}"

            already = db.scalar(
                select(CrisisEvent.id).where(CrisisEvent.external_id == ext_id)
            )
            if already is not None:
                skipped += 1
                continue

            prec = ev.get("where_prec")
            if prec is not None:
                try:
                    if int(prec) > _MIN_WHERE_PREC_ACCEPTABLE:
                        skipped += 1
                        continue
                except (TypeError, ValueError):
                    pass

            lat = _parse_coord(ev.get("latitude"))
            lng = _parse_coord(ev.get("longitude"))
            if lat is None or lng is None:
                skipped += 1
                continue
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
                skipped += 1
                continue

            country = (ev.get("country") or "").strip()
            iso3 = _country_iso3(country)
            if not iso3:
                skipped += 1
                continue

            adm_1 = (ev.get("adm_1") or "").strip()
            admin1_norm: str | None = None
            if adm_1:
                norm = _normalize_admin1(adm_1)
                admin1_norm = alias_map.get((iso3, norm), norm) if norm else None

            if admin1_norm is None or (iso3, admin1_norm) not in crisis_index:
                # Try PIP fallback.
                admin1_norm = _resolve_admin1_via_pip(db, iso3, lat, lng)
                if admin1_norm is None:
                    skipped_no_admin1 += 1
                    skipped += 1
                    continue
                skipped_pip_used += 1

            crisis_id = crisis_index.get((iso3, admin1_norm))
            if crisis_id is None:
                skipped_no_crisis += 1
                skipped += 1
                continue

            date_str = (ev.get("date_start") or "").strip()
            try:
                occurred = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
            except ValueError:
                skipped += 1
                continue

            headline = (ev.get("source_headline") or "").strip() or None
            if headline and len(headline) > _HEADLINE_MAX_CHARS:
                headline = headline[: _HEADLINE_MAX_CHARS - 1].rstrip() + "…"

            source_url = (ev.get("source_article") or "").strip()
            source_row = None
            if source_url:
                source_row = _upsert_source(db, crisis_id, source_url, headline)

            conflict_id = None
            if routing_idx is not None:
                conflict_id = route_event(
                    [(ev.get("side_a") or "").strip(), (ev.get("side_b") or "").strip()],
                    iso3,
                    admin1_norm,
                    routing_idx,
                )

            db.add(
                CrisisEvent(
                    crisis_id=crisis_id,
                    occurred_at=occurred,
                    event_type=VIOLENCE_TYPE_MAP.get(
                        ev.get("type_of_violence"), "armed_conflict"
                    ),
                    description=headline,
                    fatalities=int(ev.get("best") or 0),
                    location_name=(ev.get("where_description") or "").strip()[:200]
                    or None,
                    lat=lat,
                    lng=lng,
                    external_id=ext_id,
                    source_id=source_row.id if source_row else None,
                    conflict_id=conflict_id,
                )
            )
            attached += 1

            prev = latest_per_crisis.get(crisis_id)
            if prev is None or occurred > prev:
                latest_per_crisis[crisis_id] = occurred
            if conflict_id is not None:
                prev_c = conflict_latest.get(conflict_id)
                if prev_c is None or occurred > prev_c:
                    conflict_latest[conflict_id] = occurred

        if latest_per_crisis:
            crises = (
                db.execute(
                    select(Crisis).where(Crisis.id.in_(latest_per_crisis.keys()))
                )
                .scalars()
                .all()
            )
            for c in crises:
                new_last = latest_per_crisis[c.id]
                if c.last_event_at is None or new_last > c.last_event_at:
                    c.last_event_at = new_last

        _bump_conflicts_last_event(db, conflict_latest)
        db.flush()
        logger.info(
            "ucdp: attached=%d skipped=%d (no_admin1=%d no_crisis=%d) pip_used=%d",
            attached,
            skipped,
            skipped_no_admin1,
            skipped_no_crisis,
            skipped_pip_used,
        )
        return {"attached": attached, "skipped": skipped}

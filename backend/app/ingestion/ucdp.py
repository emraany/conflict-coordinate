"""UCDP GED ingestion source — attach-only.

Fetches georeferenced events from the Uppsala Conflict Data Program (UCDP)
Georeferenced Event Dataset (GED) and attaches each to the nearest existing
crisis within `UCDP_ATTACH_RADIUS_KM` via PostGIS ST_DWithin. Never creates
standalone crises — UCDP overlaps heavily with ACLED, and emitting both
would duplicate dots on the globe.

UCDP GED v25.1 covers 1989–2024. Authentication: static API token via
`x-ucdp-access-token` header.

Neutrality: event headlines copied verbatim from `source_headline`. Actor
rows are NOT created from UCDP — the actor graph stays single-rooted in
the primary source (ACLED).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion.base import CrisisRecord, IngestionSource
from app.models import Crisis, Source, SourceType
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
    return datetime.now(timezone.utc) - timedelta(days=lookback_days)


def _fetch_events(client: httpx.Client) -> list[dict]:
    token = settings.ucdp_token
    version = settings.ucdp_ged_version
    headers = {"x-ucdp-access-token": token}
    cutoff = _cutoff_date(settings.ucdp_lookback_days)
    cutoff_str = cutoff.date().isoformat()

    all_events: list[dict] = []
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
            logger.warning("ucdp fetch error page=%s: %s", page, exc)
            break
        payload = resp.json()
        batch: list[dict] = payload.get("Result") or []
        if not batch:
            break
        all_events.extend(batch)
        if len(batch) < 1000:
            break
        page += 1
        if page > page_ceil:
            logger.warning("ucdp: hit page ceiling (%s), stopping", page_ceil)
            break
    return all_events


def _find_nearest_crisis(
    db: Session, lat: float, lng: float, radius_km: int
) -> int | None:
    stmt = text(
        """
        SELECT id
        FROM crises
        WHERE geom IS NOT NULL
          AND source_name <> 'ucdp'
          AND ST_DWithin(
            geom::geography,
            ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
            :radius_m
          )
        ORDER BY geom::geography <-> ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
        LIMIT 1
        """
    )
    row = db.execute(
        stmt, {"lat": lat, "lng": lng, "radius_m": radius_km * 1000}
    ).first()
    return row[0] if row else None


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
        retrieved_at=datetime.now(timezone.utc),
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

    def attach_events(self, db: Session) -> dict:
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

        attached = 0
        skipped = 0
        seen_ids: set[str] = set()
        latest_per_crisis: dict[int, datetime] = {}

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

            crisis_id = _find_nearest_crisis(
                db, lat, lng, settings.ucdp_attach_radius_km
            )
            if crisis_id is None:
                skipped += 1
                continue

            date_str = (ev.get("date_start") or "").strip()
            try:
                occurred = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
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
                )
            )
            attached += 1

            prev = latest_per_crisis.get(crisis_id)
            if prev is None or occurred > prev:
                latest_per_crisis[crisis_id] = occurred

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

        db.flush()
        return {"attached": attached, "skipped": skipped}

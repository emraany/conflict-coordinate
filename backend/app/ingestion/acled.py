"""ACLED ingestion source.

Fetches recent armed-conflict events from ACLED, clusters them geographically
with DBSCAN (haversine metric), and emits one `CrisisRecord` per cluster for
the runner to upsert. This replaces the earlier country-year grouping, which
produced one dot per country at its centroid — misrepresenting scattered
conflicts (e.g. Somaliland vs. Mogadishu) as a single event.

Each cluster's centroid becomes the dot location; its dominant ACLED `admin1`
(state/province) field supplies the human-readable name. Noise points —
events with no dense neighborhood — are dropped.

Credentials come from `ACLED_USERNAME` + `ACLED_PASSWORD`. The adapter
caches OAuth tokens to `backend/.cache/acled_token.json` to respect the
24-hour access / 14-day refresh lifetimes.

Neutrality: summaries are templated and count-based. Actors are copied
verbatim from `actor1/actor2` fields; role is always `party` since ACLED
does not distinguish mediators/observers and we refuse to label them.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

import httpx
import numpy as np
import pycountry
from sklearn.cluster import DBSCAN
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion import reliefweb, wikipedia
from app.ingestion.base import (
    ActorRef,
    CrisisRecord,
    EventRef,
    IngestionSource,
    SourceRef,
)
from app.models import Crisis

# Defensive upper bound on ACLED `notes` copied into `CrisisEvent.description`.
# The column is `Text` (no hard limit) but very long notes occasionally appear
# and we don't need novel-length prose in the timeline.
NOTES_MAX_CHARS = 2000

EARTH_RADIUS_KM = 6371.0

ACLED_READ_URL = "https://acleddata.com/api/acled/read"
ACLED_OAUTH_URL = "https://acleddata.com/oauth/token"
ACLED_CLIENT_ID = "acled"

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"
TOKEN_CACHE_PATH = CACHE_DIR / "acled_token.json"

# Map ACLED event_type values to our coarse conflict_type taxonomy.
# Kept descriptive, not interpretive.
EVENT_TYPE_MAP = {
    "Battles": "armed_clashes",
    "Violence against civilians": "one_sided_violence",
    "Explosions/Remote violence": "explosions_remote_violence",
    "Riots": "civil_unrest",
    "Protests": "civil_unrest",
    "Strategic developments": "strategic_developments",
}


@dataclass
class _CachedToken:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime

    def access_valid(self, now: datetime) -> bool:
        return now < self.access_expires_at - timedelta(seconds=60)

    def refresh_valid(self, now: datetime) -> bool:
        return now < self.refresh_expires_at - timedelta(seconds=60)


def _load_cached_token() -> _CachedToken | None:
    if not TOKEN_CACHE_PATH.exists():
        return None
    try:
        data = json.loads(TOKEN_CACHE_PATH.read_text())
        return _CachedToken(
            access_token=data["access_token"],
            access_expires_at=datetime.fromisoformat(data["access_expires_at"]),
            refresh_token=data["refresh_token"],
            refresh_expires_at=datetime.fromisoformat(data["refresh_expires_at"]),
        )
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def _save_cached_token(tok: _CachedToken) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE_PATH.write_text(
        json.dumps(
            {
                "access_token": tok.access_token,
                "access_expires_at": tok.access_expires_at.isoformat(),
                "refresh_token": tok.refresh_token,
                "refresh_expires_at": tok.refresh_expires_at.isoformat(),
            }
        )
    )


def _token_from_response(payload: dict, now: datetime) -> _CachedToken:
    # ACLED returns `expires_in` (access, seconds) and `refresh_expires_in` (optional).
    access_secs = int(payload.get("expires_in", 24 * 3600))
    refresh_secs = int(payload.get("refresh_expires_in", 14 * 24 * 3600))
    return _CachedToken(
        access_token=payload["access_token"],
        access_expires_at=now + timedelta(seconds=access_secs),
        refresh_token=payload.get("refresh_token", ""),
        refresh_expires_at=now + timedelta(seconds=refresh_secs),
    )


def _oauth_password_grant(client: httpx.Client, now: datetime) -> _CachedToken:
    resp = client.post(
        ACLED_OAUTH_URL,
        data={
            "username": settings.acled_username,
            "password": settings.acled_password,
            "grant_type": "password",
            "client_id": ACLED_CLIENT_ID,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return _token_from_response(resp.json(), now)


def _oauth_refresh_grant(
    client: httpx.Client, refresh_token: str, now: datetime
) -> _CachedToken:
    resp = client.post(
        ACLED_OAUTH_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": ACLED_CLIENT_ID,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return _token_from_response(resp.json(), now)


def _get_token(client: httpx.Client) -> _CachedToken:
    now = datetime.now(timezone.utc)
    cached = _load_cached_token()
    if cached and cached.access_valid(now):
        return cached
    if cached and cached.refresh_valid(now):
        tok = _oauth_refresh_grant(client, cached.refresh_token, now)
        _save_cached_token(tok)
        return tok
    tok = _oauth_password_grant(client, now)
    _save_cached_token(tok)
    return tok


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:120] or "unknown"


def _country_iso3(name: str | None) -> str | None:
    if not name:
        return None
    try:
        c = pycountry.countries.lookup(name)
    except LookupError:
        return None
    return getattr(c, "alpha_3", None)


def _fetch_events(client: httpx.Client, access_token: str) -> list[dict]:
    lookback_days = settings.acled_lookback_days
    if settings.acled_reference_date:
        from datetime import date as _date
        end = _date.fromisoformat(settings.acled_reference_date)
    else:
        end = datetime.now(timezone.utc).date()
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
        if page > 40:  # 20k event ceiling per run, protect against runaway
            break
    return out


def _parse_coord(val: object) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _cluster_events(events: list[dict]) -> list[list[dict]]:
    """Group events into geographic clusters via DBSCAN on haversine distance.

    Returns a list of buckets (each a list of events). Noise points — events
    without a dense neighborhood of `min_samples` within `eps_km` — are
    dropped, since a lone incident does not constitute a conflict cluster.
    """
    valid: list[dict] = []
    coords: list[tuple[float, float]] = []
    for ev in events:
        lat = _parse_coord(ev.get("latitude"))
        lng = _parse_coord(ev.get("longitude"))
        if lat is None or lng is None:
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            continue
        valid.append(ev)
        coords.append((lat, lng))

    if not valid:
        return []

    coords_rad = np.radians(np.asarray(coords, dtype=np.float64))
    eps_rad = settings.acled_cluster_eps_km / EARTH_RADIUS_KM
    labels = DBSCAN(
        eps=eps_rad,
        min_samples=settings.acled_cluster_min_samples,
        metric="haversine",
    ).fit_predict(coords_rad)

    buckets: dict[int, list[dict]] = {}
    for idx, label in enumerate(labels):
        lbl = int(label)
        if lbl == -1:
            continue
        buckets.setdefault(lbl, []).append(valid[idx])
    return list(buckets.values())


def _first_sentence(text: str, min_len: int = 30, max_len: int = 240) -> str | None:
    """Return the first non-trivial sentence of `text`, trimmed for display.

    Used for the representative-incident lede in cluster summaries. If no
    sentence meets `min_len`, falls back to a hard truncation so we still
    surface verbatim ACLED prose rather than silently dropping context.
    """
    if not text:
        return None
    cleaned = text.strip()
    if not cleaned:
        return None
    for candidate in cleaned.split(". "):
        piece = candidate.strip()
        if len(piece) < min_len:
            continue
        if not piece.endswith((".", "!", "?")):
            piece += "."
        if len(piece) > max_len:
            piece = piece[: max_len - 1].rstrip() + "…"
        return piece
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1].rstrip() + "…"
    return cleaned


def _pick_representative(bucket: list[dict]) -> dict | None:
    """Select the event that best anchors the cluster summary — highest
    fatalities first, then most recent. Events lacking a `notes` field are
    skipped because we have nothing quotable from them."""
    candidates = [ev for ev in bucket if (ev.get("notes") or "").strip()]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda ev: (int(ev.get("fatalities") or 0), ev.get("event_date") or ""),
    )


def _build_events(bucket: list[dict]) -> list[EventRef]:
    refs: list[EventRef] = []
    seen: set[str] = set()
    for ev in bucket:
        event_id = (ev.get("event_id_cnty") or "").strip()
        if not event_id or event_id in seen:
            continue
        date_str = (ev.get("event_date") or "").strip()
        if not date_str:
            continue
        try:
            occurred = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        seen.add(event_id)

        notes = (ev.get("notes") or "").strip() or None
        if notes and len(notes) > NOTES_MAX_CHARS:
            notes = notes[: NOTES_MAX_CHARS - 1].rstrip() + "…"

        sub_type = (ev.get("sub_event_type") or "").strip()
        main_type = (ev.get("event_type") or "").strip()
        event_type = sub_type or main_type or None

        # Prefer the most specific admin level available for the incident
        # location label; fall back through admin3 → admin2 → location.
        location_name = (
            (ev.get("location") or "").strip()
            or (ev.get("admin3") or "").strip()
            or (ev.get("admin2") or "").strip()
            or None
        )

        refs.append(
            EventRef(
                external_id=f"acled:{event_id}",
                occurred_at=occurred,
                event_type=event_type,
                description=notes,
                fatalities=int(ev.get("fatalities") or 0),
                location_name=location_name,
                lat=_parse_coord(ev.get("latitude")),
                lng=_parse_coord(ev.get("longitude")),
                source_index=0,  # ACLED citation is always sources[0]
            )
        )
    return refs


@dataclass
class _EnrichmentContext:
    """Per-run caches + shared HTTP client for Wikipedia/ReliefWeb lookups.

    Caches are keyed to avoid duplicate network calls across the ~500
    clusters in one ingest run (same actor names and countries recur).
    """

    wiki_client: httpx.Client
    actor_cache: dict[str, tuple[str | None, str | None]]
    background_cache: dict[str, tuple[str | None, str | None]]
    reliefweb_client: httpx.Client
    reliefweb_cache: dict[str, list[SourceRef]]


def _aggregate_events_to_records(
    events: list[dict], enrich: _EnrichmentContext | None = None
) -> list[CrisisRecord]:
    buckets = _cluster_events(events)
    records: list[CrisisRecord] = []

    for bucket in buckets:
        lats = [_parse_coord(ev.get("latitude")) for ev in bucket]
        lngs = [_parse_coord(ev.get("longitude")) for ev in bucket]
        lats = [v for v in lats if v is not None]
        lngs = [v for v in lngs if v is not None]
        if not lats or not lngs:
            continue
        centroid_lat = mean(lats)
        centroid_lng = mean(lngs)

        country_counts = Counter(
            (ev.get("country") or "").strip()
            for ev in bucket
            if (ev.get("country") or "").strip()
        )
        top_country = country_counts.most_common(1)[0][0] if country_counts else "Unknown"

        admin1_counts = Counter(
            (ev.get("admin1") or "").strip()
            for ev in bucket
            if (ev.get("admin1") or "").strip()
        )
        top_admin1 = admin1_counts.most_common(1)[0][0] if admin1_counts else None

        dates = sorted(ev["event_date"] for ev in bucket if ev.get("event_date"))
        if not dates:
            continue
        started = datetime.fromisoformat(dates[0]).replace(tzinfo=timezone.utc)
        last = datetime.fromisoformat(dates[-1]).replace(tzinfo=timezone.utc)

        type_counts = Counter(
            ev.get("event_type") for ev in bucket if ev.get("event_type")
        )
        top_label = type_counts.most_common(1)[0][0] if type_counts else "Armed conflict"
        fatalities = sum(int(ev.get("fatalities") or 0) for ev in bucket)

        pair_counts: Counter[tuple[str, str]] = Counter()
        for ev in bucket:
            a1 = (ev.get("actor1") or "").strip()
            a2 = (ev.get("actor2") or "").strip()
            if a1 and a2:
                pair_counts[(a1, a2)] += 1
        top_pair = pair_counts.most_common(1)[0][0] if pair_counts else None

        rep = _pick_representative(bucket)
        rep_lede = _first_sentence(rep.get("notes") if rep else "")
        rep_date = (rep.get("event_date") if rep else "") or ""

        region = (bucket[0].get("region") or "").strip() or None
        location_label = f"{top_admin1}, {top_country}" if top_admin1 else top_country
        name = f"{location_label} — {top_label}"

        # Lead with the real incident, not the count. The representative ACLED
        # note carries the actual news; the counts are context that follows.
        summary_parts: list[str] = []
        if rep_lede and rep_date:
            summary_parts.append(f'"{rep_lede}" — {location_label}, {rep_date}.')
        else:
            summary_parts.append(
                f"{len(bucket)} incidents reported around {location_label} "
                f"between {dates[0]} and {dates[-1]}."
            )
        if top_pair:
            summary_parts.append(
                f"Principal parties: {top_pair[0]} and {top_pair[1]}."
            )
        if rep_lede and rep_date:
            summary_parts.append(
                f"{len(bucket)} documented incidents, {dates[0]}–{dates[-1]};"
                f" {fatalities} reported fatalities."
                if fatalities > 0
                else f"{len(bucket)} documented incidents, {dates[0]}–{dates[-1]}."
            )
        elif fatalities > 0:
            summary_parts.append(f"{fatalities} reported fatalities.")
        summary = " ".join(summary_parts)

        # Stable external_id via quantized centroid (0.5° grid, ~55 km).
        # Two DBSCAN-distinct clusters are typically ≥ eps_km apart, so they
        # land in different cells; a cluster's centroid is unlikely to drift
        # across a cell boundary between runs on similar data.
        qlat = round(centroid_lat * 2) / 2
        qlng = round(centroid_lng * 2) / 2
        country_slug = _slugify(top_country)
        admin1_slug = _slugify(top_admin1) if top_admin1 else "area"
        external_id = f"acled:{country_slug}:{admin1_slug}:{qlat}:{qlng}"
        slug = _slugify(f"{top_country}-{top_admin1 or 'area'}-{qlat}-{qlng}")

        sources = _build_sources(bucket)
        actors = _build_actors(bucket, sources, enrich)
        event_refs = _build_events(bucket)

        # Append ReliefWeb situation reports (country-level) and the Wikipedia
        # conflict background. Both are cached across the run so the same
        # country isn't fetched 100 times.
        if enrich is not None:
            iso3 = _country_iso3(top_country)
            if iso3:
                sitreps = reliefweb.fetch_situation_reports(
                    iso3, enrich.reliefweb_cache, client=enrich.reliefweb_client
                )
                sources.extend(sitreps)
            bg_actors = [top_pair[0], top_pair[1]] if top_pair else []
            bg_extract, bg_url = wikipedia.fetch_conflict_background(
                top_country,
                bg_actors,
                enrich.background_cache,
                client=enrich.wiki_client,
            )
            if bg_extract and bg_url:
                sources.append(
                    SourceRef(
                        title=f"Background: {top_country}",
                        url=bg_url,
                        publisher="Wikipedia",
                        source_type="reference",
                        body_text=bg_extract,
                    )
                )

        records.append(
            CrisisRecord(
                external_id=external_id,
                slug=slug,
                name=name,
                country=top_country,
                region=region,
                lat=centroid_lat,
                lng=centroid_lng,
                summary=summary,
                status="active",
                conflict_type=EVENT_TYPE_MAP.get(top_label, "armed_conflict"),
                started_at=started,
                last_event_at=last,
                actors=actors,
                sources=sources,
                events=event_refs,
            )
        )
    return records


def _build_sources(bucket: list[dict]) -> list[SourceRef]:
    """Synthesize a sources list for one country-year bucket.

    First source is the ACLED dataset citation (always present). Following
    that, one entry per unique publisher/source string. Source URLs from
    individual events are not always present or reliable, so we link to
    the ACLED site and name the publisher in the title.
    """
    refs: list[SourceRef] = [
        SourceRef(
            title="ACLED — Armed Conflict Location & Event Data",
            url="https://acleddata.com/",
            publisher="ACLED",
            source_type="primary",
        )
    ]
    seen: set[str] = set()
    for ev in bucket:
        name = (ev.get("source") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        refs.append(
            SourceRef(
                title=f"{name[:460]} — cited by ACLED",
                url="https://acleddata.com/",
                publisher=name[:200],
                source_type="news",
            )
        )
        if len(refs) >= 20:
            break
    return refs


def _build_actors(
    bucket: list[dict],
    sources: list[SourceRef],
    enrich: _EnrichmentContext | None = None,
) -> list[ActorRef]:
    # Rank actors by frequency so the most central parties appear first and
    # receive Wikipedia enrichment first (enrichment is capped per cluster).
    name_counts: Counter[str] = Counter()
    for ev in bucket:
        for key in ("actor1", "actor2"):
            n = (ev.get(key) or "").strip()
            if n:
                name_counts[n] += 1
    ordered = [n for n, _ in name_counts.most_common()]

    actors: list[ActorRef] = []
    enriched_count = 0
    for n in ordered:
        description: str | None = None
        wiki_url: str | None = None
        # Enrich the top 5 actors per cluster. Beyond that, descriptions add
        # marginal value and the Wikipedia fetch budget matters for a 500-
        # cluster run. The shared cache still helps for common actors.
        if enrich is not None and enriched_count < 5:
            description, wiki_url = wikipedia.fetch_actor_summary(
                n, enrich.actor_cache, client=enrich.wiki_client
            )
            if description:
                enriched_count += 1
        actors.append(
            ActorRef(
                name=n,
                type="other",
                role="party",
                description=description,
                wikipedia_url=wiki_url,
                attributing_source_index=0,
            )
        )
        if len(actors) >= 30:
            break
    return actors


class ACLEDSource(IngestionSource):
    name = "acled"

    def before_run(self, db: Session) -> None:
        # Clusters are recomputed from scratch each run, so prior ACLED-sourced
        # crises would otherwise linger as orphans. Delete them; relationships
        # cascade to sources, actor links, and attached events.
        if not settings.acled_enabled:
            return
        db.execute(delete(Crisis).where(Crisis.source_name == self.name))
        db.flush()

    def fetch(self) -> list[CrisisRecord]:
        if not settings.acled_enabled:
            return []
        if not settings.acled_username or not settings.acled_password:
            return []
        with httpx.Client() as client:
            tok = _get_token(client)
            events = _fetch_events(client, tok.access_token)

        # Shared clients + per-run caches so Wikipedia and ReliefWeb aren't
        # hit redundantly across the ~500 clusters produced by DBSCAN.
        wiki_client = httpx.Client(
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers={
                "User-Agent": "ConflictCoordinate/0.1 (https://github.com/emraany/conflict-coordinate)",
                "Accept": "application/json",
            },
        )
        reliefweb_client = httpx.Client(
            timeout=httpx.Timeout(15.0, connect=5.0),
            headers={
                "User-Agent": "ConflictCoordinate/0.1 (https://github.com/emraany/conflict-coordinate)",
                "Accept": "application/json",
            },
        )
        enrich = _EnrichmentContext(
            wiki_client=wiki_client,
            actor_cache={},
            background_cache={},
            reliefweb_client=reliefweb_client,
            reliefweb_cache={},
        )
        try:
            return _aggregate_events_to_records(events, enrich)
        finally:
            wiki_client.close()
            reliefweb_client.close()

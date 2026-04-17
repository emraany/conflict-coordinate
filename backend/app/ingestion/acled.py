"""ACLED ingestion source.

Fetches recent armed-conflict events from ACLED, groups them into
per-country-per-year crises, and emits `CrisisRecord` objects for the runner
to upsert. Events themselves are not persisted to `crisis_events` here —
that would require a second write pass; for v2 we surface the aggregate
as the crisis-level record and rely on ACLED's own URLs as sources.

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
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

import httpx

from app.config import settings
from app.ingestion.base import ActorRef, CrisisRecord, IngestionSource, SourceRef

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


def _aggregate_events_to_records(events: list[dict]) -> list[CrisisRecord]:
    threshold = settings.acled_crisis_event_threshold
    by_country: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for ev in events:
        country = (ev.get("country") or "").strip()
        if not country:
            continue
        try:
            year = int((ev.get("event_date") or "")[:4])
        except ValueError:
            continue
        by_country[(country, year)].append(ev)

    records: list[CrisisRecord] = []
    for (country, year), bucket in by_country.items():
        if len(bucket) < threshold:
            continue
        lats = [float(ev["latitude"]) for ev in bucket if ev.get("latitude")]
        lngs = [float(ev["longitude"]) for ev in bucket if ev.get("longitude")]
        if not lats or not lngs:
            continue
        dates = [ev["event_date"] for ev in bucket if ev.get("event_date")]
        dates.sort()
        started = datetime.fromisoformat(dates[0]).replace(tzinfo=timezone.utc)
        last = datetime.fromisoformat(dates[-1]).replace(tzinfo=timezone.utc)
        top_type = Counter(
            ev.get("event_type") for ev in bucket if ev.get("event_type")
        ).most_common(1)
        top_label = top_type[0][0] if top_type else "Armed conflict"
        fatalities = sum(int(ev.get("fatalities") or 0) for ev in bucket)

        region = (bucket[0].get("region") or "").strip() or None
        name = f"{country} — Armed conflict events ({year})"
        summary = (
            f"{len(bucket)} ACLED-reported events in {country} "
            f"between {dates[0]} and {dates[-1]}. "
            f"Most frequent event type: {top_label}. "
            f"Reported fatalities across these events: {fatalities}."
        )

        sources = _build_sources(bucket)
        actors = _build_actors(bucket, sources)

        records.append(
            CrisisRecord(
                external_id=f"acled:{_slugify(country)}:{year}",
                slug=_slugify(f"{country}-acled-{year}"),
                name=name,
                country=country,
                region=region,
                lat=mean(lats),
                lng=mean(lngs),
                summary=summary,
                status="active",
                conflict_type=EVENT_TYPE_MAP.get(top_label, "armed_conflict"),
                started_at=started,
                last_event_at=last,
                actors=actors,
                sources=sources,
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
    bucket: list[dict], sources: list[SourceRef]
) -> list[ActorRef]:
    names: dict[str, int] = {}
    for ev in bucket:
        for key in ("actor1", "actor2"):
            n = (ev.get(key) or "").strip()
            if n and n not in names:
                names[n] = 0
    actors: list[ActorRef] = []
    for n in names:
        actors.append(
            ActorRef(
                name=n,
                type="other",
                role="party",
                attributing_source_index=0,  # attribute to the ACLED citation
            )
        )
        if len(actors) >= 30:
            break
    return actors


class ACLEDSource(IngestionSource):
    name = "acled"

    def fetch(self) -> list[CrisisRecord]:
        if not settings.acled_enabled:
            return []
        if not settings.acled_username or not settings.acled_password:
            return []
        with httpx.Client() as client:
            tok = _get_token(client)
            events = _fetch_events(client, tok.access_token)
        return _aggregate_events_to_records(events)

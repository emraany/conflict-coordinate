"""ReliefWeb situation reports — UN/NGO narrative updates per country.

ReliefWeb's public API (https://api.reliefweb.int/v1/reports) is free and
keyless; we identify ourselves with `appname` per their etiquette guide.

We fetch the 2 most recent Situation Reports per ISO3 country, extract
a plain-text excerpt from the HTML body, and emit `SourceRef` rows with
`source_type="situation_report"`. The frontend surfaces these in a
dedicated FIELD REPORTS section of the dossier.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from html import unescape

import httpx

from app.config import settings
from app.ingestion.base import SourceRef

logger = logging.getLogger(__name__)

_API_URL = "https://api.reliefweb.int/v2/reports"
_BODY_CAP = 1200
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
_HEADERS = {
    "User-Agent": "ConflictCoordinate/0.1 (https://github.com/emraany/conflict-coordinate)",
    "Accept": "application/json",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    text = unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _truncate(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    cut = text[:cap].rsplit(" ", 1)[0]
    return cut + "…"


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # ReliefWeb returns ISO-8601 with 'Z'; fromisoformat needs '+00:00' on <3.11
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_situation_reports(
    country_iso3: str,
    cache: dict[str, list[SourceRef]],
    limit: int = 2,
    client: httpx.Client | None = None,
) -> list[SourceRef]:
    """Return up to `limit` recent situation reports as SourceRefs. Cached
    per ISO3 across a single ingest run (each country fetched once).

    Requires a pre-approved ReliefWeb appname (set `RELIEFWEB_APPNAME`).
    Returns an empty list if the appname isn't configured — SITREP
    enrichment is optional, not load-bearing.
    """
    key = country_iso3.upper()
    if key in cache:
        return cache[key]
    appname = settings.reliefweb_appname.strip()
    if not appname:
        cache[key] = []
        return []

    close_after = client is None
    client = client or httpx.Client(timeout=_TIMEOUT, headers=_HEADERS)
    payload = {
        "filter": {
            "operator": "AND",
            "conditions": [
                {"field": "primary_country.iso3", "value": key.lower()},
                {"field": "format.name", "value": "Situation Report"},
            ],
        },
        "sort": ["date.created:desc"],
        "limit": limit,
        "fields": {
            "include": ["title", "date", "source", "url", "body-html", "url_alias"],
        },
    }
    refs: list[SourceRef] = []
    try:
        r = client.post(_API_URL, params={"appname": appname}, json=payload)
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as e:
        logger.info("reliefweb fetch failed for %s: %s", key, e)
        cache[key] = refs
        if close_after:
            client.close()
        return refs

    for item in data.get("data", []):
        f = item.get("fields", {})
        title = f.get("title") or "Situation report"
        body_html = f.get("body-html") or ""
        body = _truncate(_strip_html(body_html), _BODY_CAP) if body_html else None
        url = f.get("url_alias") or f.get("url") or ""
        sources = f.get("source") or []
        publisher = sources[0].get("name") if sources else None
        date_obj = f.get("date") or {}
        published_at = _parse_date(date_obj.get("created") or date_obj.get("original"))

        if not url:
            continue
        refs.append(
            SourceRef(
                title=title[:500],
                url=url[:1000],
                publisher=publisher,
                published_at=published_at,
                source_type="situation_report",
                body_text=body,
            )
        )

    if close_after:
        client.close()
    cache[key] = refs
    return refs

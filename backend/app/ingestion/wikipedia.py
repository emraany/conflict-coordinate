"""Wikipedia enrichment for ACLED clusters.

Two lookups, both anonymous (no API key needed):

- `fetch_actor_summary(name)` — REST summary endpoint with a search-API fallback.
  Returns a capped extract + canonical article URL, or (None, None).
- `fetch_conflict_background(country, actors)` — searches for a conflict article
  matching the cluster's country + lead actor, returns (extract, url).

All returned prose is verbatim Wikipedia content, which satisfies the
project's neutrality rule (no LLM-generated summaries).
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

_REST_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_SEARCH_API = "https://en.wikipedia.org/w/api.php"
_HEADERS = {
    "User-Agent": "ConflictCoordinate/0.1 (https://github.com/emraany/conflict-coordinate)",
    "Accept": "application/json",
}
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# Actor descriptions: short enough to render in an actor card without
# taking over the dossier. Background blurbs have a larger budget since
# they anchor the whole situation.
_ACTOR_CAP = 400
_BACKGROUND_CAP = 600

# Generic titles that shouldn't be looked up on Wikipedia — avoid noise.
_SKIP_ACTOR_NAMES = {
    "civilians",
    "unidentified armed group",
    "unidentified communal militia",
    "unidentified gang",
    "protesters",
    "rioters",
    "police forces",
    "military forces",
    "rebels",
}


def _is_meaningful_name(name: str) -> bool:
    n = name.strip().lower()
    if len(n) < 4:
        return False
    return n not in _SKIP_ACTOR_NAMES


def _truncate(text: str, cap: int) -> str:
    text = text.strip()
    if len(text) <= cap:
        return text
    cut = text[:cap].rsplit(" ", 1)[0]
    return cut + "…"


def _clean(text: str) -> str:
    # Wikipedia extracts sometimes include stray newline runs from templates.
    return re.sub(r"\s+", " ", text).strip()


def _rest_summary(client: httpx.Client, title: str) -> tuple[str | None, str | None]:
    try:
        r = client.get(_REST_SUMMARY.format(title=quote(title.replace(" ", "_"))))
    except httpx.HTTPError as e:
        logger.debug("wikipedia REST summary failed for %s: %s", title, e)
        return None, None
    if r.status_code != 200:
        return None, None
    data = r.json()
    # Disambiguation pages have type='disambiguation'; skip them.
    if data.get("type") == "disambiguation":
        return None, None
    extract = data.get("extract")
    url = data.get("content_urls", {}).get("desktop", {}).get("page")
    if not extract:
        return None, None
    return _clean(extract), url


def _search_top_title(client: httpx.Client, query: str) -> str | None:
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 1,
        "format": "json",
    }
    try:
        r = client.get(_SEARCH_API, params=params)
    except httpx.HTTPError as e:
        logger.debug("wikipedia search failed for %r: %s", query, e)
        return None
    if r.status_code != 200:
        return None
    hits = r.json().get("query", {}).get("search", [])
    if not hits:
        return None
    return hits[0].get("title")


def fetch_actor_summary(
    name: str,
    cache: dict[str, tuple[str | None, str | None]],
    client: httpx.Client | None = None,
) -> tuple[str | None, str | None]:
    """Return (description, wikipedia_url) for an actor name, or (None, None)."""
    key = name.strip().lower()
    if key in cache:
        return cache[key]
    if not _is_meaningful_name(name):
        cache[key] = (None, None)
        return None, None

    close_after = client is None
    client = client or httpx.Client(timeout=_TIMEOUT, headers=_HEADERS)
    try:
        extract, url = _rest_summary(client, name)
        if not extract:
            title = _search_top_title(client, name)
            if title:
                extract, url = _rest_summary(client, title)
        if extract:
            result = (_truncate(extract, _ACTOR_CAP), url)
        else:
            result = (None, None)
    finally:
        if close_after:
            client.close()
    cache[key] = result
    return result


def fetch_conflict_background(
    country: str | None,
    actors: list[str],
    cache: dict[str, tuple[str | None, str | None]],
    client: httpx.Client | None = None,
) -> tuple[str | None, str | None]:
    """Return (extract, wikipedia_url) for a conflict article relevant to the
    cluster, or (None, None). Uses country + lead actor to form the query.
    """
    if not country:
        return None, None
    lead = next((a for a in actors if _is_meaningful_name(a)), None)
    key = f"{country.lower()}|{(lead or '').lower()}"
    if key in cache:
        return cache[key]

    close_after = client is None
    client = client or httpx.Client(timeout=_TIMEOUT, headers=_HEADERS)
    try:
        queries = []
        if lead:
            queries.append(f"{lead} {country} conflict")
        queries.append(f"{country} conflict")
        queries.append(f"{country} civil war")

        extract, url = None, None
        for q in queries:
            title = _search_top_title(client, q)
            if not title:
                continue
            extract, url = _rest_summary(client, title)
            if extract:
                break
        result = (_truncate(extract, _BACKGROUND_CAP), url) if extract else (None, None)
    finally:
        if close_after:
            client.close()
    cache[key] = result
    return result

"""Auto-discover emerging conflicts from Wikipedia.

For each member of Wikipedia's "Category:Ongoing_armed_conflicts" that
is NOT already in our registry (matched by canonical wikipedia_url),
insert an `emerging` Conflict row with `registry_source="wiki-auto"`
and `admin_curated=False`. When the Wikipedia REST summary lets us
infer a single country, and no existing conflict claims that ISO3, we
also seed a `country_patterns` routing rule so events start flowing
in immediately.

The admin curates from there (Phase 5 admin UI). Auto-promotion to
`active` happens in the ingest runner once intensity_4w_events crosses
`conflict_auto_promotion_events_4w`.

No LLM-generated prose is written anywhere; the verbatim Wikipedia
description is copied (subject to the same cap as actor enrichment) and
admins are expected to replace it with a curated paragraph.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote, unquote

import httpx
import pycountry
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings  # noqa: F401  -- referenced via downstream
from app.db import SessionLocal
from app.models import (
    Conflict,
    ConflictRoutingRule,
    ConflictStatus,
)

logger = logging.getLogger(__name__)

_SOURCE_PAGE = "List_of_ongoing_armed_conflicts"
_API = "https://en.wikipedia.org/w/api.php"
_REST_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_HEADERS = {
    "User-Agent": "ConflictCoordinate/0.1 (https://github.com/emraany/conflict-coordinate)",
    "Accept": "application/json",
}
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# Wikitext link extractor: matches [[Article]] or [[Article|Display]].
_WIKILINK_RE = re.compile(r"\[\[([^\[\]|#]+?)(?:\|[^\[\]]+?)?\]\]")

# Article-title keyword filter — we only want conflict articles, not country
# pages, region pages, factions, or political-party links.
_CONFLICT_TOKENS = re.compile(
    r"(war|conflict|insurgency|crisis|strikes|invasion|civil[ -]?war|"
    r"uprising|battle|campaign|offensive|standoff)",
    re.IGNORECASE,
)

# Titles that are list/meta/region/year articles — skip even if they match
# the conflict tokens.
_SKIP_PATTERNS = re.compile(
    r"^("
    r"list of |timeline of |outline of |history of |index of |"
    r"\d{4} in |"
    r"list of wars|"
    r"category:|"
    r"file:|"
    r"image:|"
    r"template:"
    r")",
    re.IGNORECASE,
)

# Sub-article patterns — these are phase / spillover / incident-level
# children of broader conflicts. Skipping them avoids stamping a separate
# dot for every nested article.
_SUBARTICLE_PATTERNS = re.compile(
    r"("
    r"\((19|20)\d{2}[-–]present\)|"   # "(2022–present)"
    r"\((19|20)\d{2}[-–](19|20)\d{2}\)|"  # "(2022–2024)"
    r" during the | spillover | incidents in | strikes on |"
    r" ceasefire line"
    r")",
    re.IGNORECASE,
)

# Cap on the Wikipedia description / extract we copy in verbatim. Admin is
# expected to overwrite, but a short verbatim seed is better than empty.
_SUMMARY_CAP = 600


def _slugify(title: str) -> str:
    """Stable lowercased kebab-case slug. Used only as the Conflict.slug — not
    for any matching."""
    s = title.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:120] or "untitled"


def _canonical_url(title: str) -> str:
    """Match the form we already store: percent-encoded, underscores for spaces."""
    return f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe=':')}"


def _normalize_url_for_match(url: str | None) -> str:
    """Strip protocol/host, URL-decode the path, lowercase. Lets us match
    "Russo-Ukrainian_War" against "russo-ukrainian war" regardless of how the
    URL was originally encoded."""
    if not url:
        return ""
    path = url.split("/wiki/", 1)[-1]
    return unquote(path).replace("_", " ").lower().strip()


def _fetch_list_article_wikitext(client: httpx.Client) -> str:
    """Return the raw wikitext of `List_of_ongoing_armed_conflicts`."""
    params = {
        "action": "parse",
        "page": _SOURCE_PAGE,
        "format": "json",
        "prop": "wikitext",
    }
    resp = client.get(_API, params=params, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data.get("parse", {}).get("wikitext", {}).get("*", "") or ""


def _extract_conflict_candidates(wikitext: str) -> list[str]:
    """Yield unique article titles linked from inside the first wikitable on
    the page, filtered to those whose title looks like a conflict article."""
    start = wikitext.find('{| class="wikitable')
    if start == -1:
        return []
    # End of the FIRST table is the matching `|}` at column 0. Conservative
    # heuristic: take everything until the next top-level heading or the next
    # top-level `|}` — whichever comes first.
    end = wikitext.find("\n|}", start)
    table = wikitext[start : end if end != -1 else len(wikitext)]

    seen: set[str] = set()
    titles: list[str] = []
    for m in _WIKILINK_RE.finditer(table):
        title = m.group(1).strip()
        if not title or title in seen:
            continue
        if _SKIP_PATTERNS.match(title):
            continue
        if _SUBARTICLE_PATTERNS.search(title):
            continue
        if not _CONFLICT_TOKENS.search(title):
            continue
        seen.add(title)
        titles.append(title)
    return titles


def _fetch_rest_summary(client: httpx.Client, title: str) -> dict | None:
    url = _REST_SUMMARY.format(title=quote(title.replace(" ", "_"), safe=":"))
    try:
        resp = client.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        logger.warning("REST summary failed for %s: %s", title, exc)
        return None


def _guess_iso3_from_title(title: str) -> str | None:
    """Whole-word country-name match against the article title only. Returns
    ISO3 if exactly one country appears. Title-only matching is conservative
    by design — the extract often mentions neighbors that aren't the conflict
    locus and produce wrong guesses."""
    matches: set[str] = set()
    for country in pycountry.countries:
        if len(country.name) < 4:
            continue  # 3-letter pycountry names are typically codes, not names
        if re.search(rf"\b{re.escape(country.name)}\b", title):
            matches.add(country.alpha_3)
    if len(matches) == 1:
        return next(iter(matches))
    return None


def _country_claimed_by_existing(db: Session, iso3: str) -> bool:
    """True iff any existing conflict claims this ISO3 via primary_iso3,
    secondary_iso3s, or an existing country routing rule. Prevents the
    auto-discovered row from competing with a curated entry."""
    iso = iso3.upper()
    by_primary = db.scalar(
        select(Conflict).where(Conflict.primary_iso3 == iso)
    )
    if by_primary is not None:
        return True
    by_secondary = db.scalar(
        select(Conflict).where(Conflict.secondary_iso3s.any(iso))
    )
    if by_secondary is not None:
        return True
    by_rule = db.scalar(
        select(ConflictRoutingRule).where(
            ConflictRoutingRule.rule_type == "country",
            ConflictRoutingRule.pattern == iso,
        )
    )
    return by_rule is not None


def discover(commit: bool = True) -> dict:
    """Run discovery once. Returns a summary dict.

    With `commit=False` returns the would-be inserts without writing anything.
    """
    db: Session = SessionLocal()
    try:
        existing_urls: set[str] = {
            _normalize_url_for_match(u)
            for u in db.scalars(
                select(Conflict.wikipedia_url).where(
                    Conflict.wikipedia_url.is_not(None)
                )
            ).all()
        }

        with httpx.Client() as client:
            wikitext = _fetch_list_article_wikitext(client)
            candidates = _extract_conflict_candidates(wikitext)
            inspected = 0
            inserted: list[dict] = []
            skipped_existing = 0
            no_summary = 0

            for title in candidates:
                inspected += 1
                canonical = _canonical_url(title)
                if _normalize_url_for_match(canonical) in existing_urls:
                    skipped_existing += 1
                    continue

                summary = _fetch_rest_summary(client, title)
                if summary is None:
                    no_summary += 1
                    continue

                description = summary.get("description") or ""
                extract = summary.get("extract") or ""
                iso3 = _guess_iso3_from_title(title)
                set_country_rule = bool(
                    iso3 and not _country_claimed_by_existing(db, iso3)
                )

                inserted.append(
                    {
                        "title": title,
                        "url": canonical,
                        "primary_iso3": iso3,
                        "set_country_rule": set_country_rule,
                    }
                )

                if commit:
                    conflict = Conflict(
                        slug=_slugify(title),
                        name=title,
                        status=ConflictStatus.emerging,
                        primary_iso3=iso3,
                        summary=((extract or description) or None) and
                                (extract or description)[:_SUMMARY_CAP],
                        wikipedia_url=canonical,
                        registry_source="wiki-auto",
                        admin_curated=False,
                    )
                    db.add(conflict)
                    db.flush()
                    if set_country_rule:
                        db.add(
                            ConflictRoutingRule(
                                conflict_id=conflict.id,
                                rule_type="country",
                                pattern=iso3.upper(),
                                priority=3,
                            )
                        )
                    existing_urls.add(_normalize_url_for_match(canonical))
            if commit:
                db.commit()

        return {
            "source_page": _SOURCE_PAGE,
            "candidates_total": len(candidates),
            "inspected": inspected,
            "inserted": len(inserted),
            "skipped_existing": skipped_existing,
            "no_summary": no_summary,
            "candidates": inserted,
            "committed": commit,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:  # CLI entry point
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description="Auto-discover Wikipedia conflicts.")
    p.add_argument(
        "--dry-run", action="store_true", help="Inspect without writing to the DB."
    )
    args = p.parse_args()
    out = discover(commit=not args.dry_run)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()

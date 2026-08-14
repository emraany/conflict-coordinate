"""Dossier composition helpers shared by the region and conflict views.

Both dossiers answer the same questions over different scopes — one admin1
region (`crisis_events.crisis_id`) or one named conflict
(`crisis_events.conflict_id`) — so the presentation rules live here once and
take the scoping column as an argument.

Nothing here mutates data: the collapsing done for the timeline is a display
decision, and the underlying rows and totals are left intact.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.models import Source
from app.models.event import CrisisEvent


def dedupe_events_for_display(
    events: list[CrisisEvent], limit: int = 50
) -> list[tuple[CrisisEvent, int]]:
    """Presentation-only dedup of a dossier timeline. Two collapse rules:

      - identical (day, description) rows fold into one, counted
      - same-day rows within ~0.1° from *different* feeds fold into the row
        with the richest description (ACLED prose beats a UCDP headline);
        same-feed rows at the same spot stay separate — they are distinct
        incidents, not double reporting

    Returns (event, report_count) newest-first, capped at `limit`.
    """

    def _day(ev: CrisisEvent):
        return ev.occurred_at.date()

    def _feed(ev: CrisisEvent) -> str:
        return (ev.external_id or "").split(":", 1)[0]

    # Rank richer rows first within each day so a bucket keeps its best row.
    ranked = sorted(
        events, key=lambda e: (_day(e), len(e.description or "")), reverse=True
    )
    kept: list[list] = []  # [event, count]
    by_desc: dict[tuple, int] = {}
    by_loc: dict[tuple, list[int]] = {}
    for ev in ranked:
        desc_key = (_day(ev), (ev.description or "").strip())
        target = by_desc.get(desc_key)
        loc_key = None
        if target is None and ev.lat is not None and ev.lng is not None:
            loc_key = (_day(ev), round(ev.lat, 1), round(ev.lng, 1))
            for idx in by_loc.get(loc_key, []):
                if _feed(kept[idx][0]) != _feed(ev):
                    target = idx
                    break
        if target is not None:
            kept[target][1] += 1
            continue
        kept.append([ev, 1])
        idx = len(kept) - 1
        by_desc[desc_key] = idx
        if ev.lat is not None and ev.lng is not None:
            loc_key = loc_key or (_day(ev), round(ev.lat, 1), round(ev.lng, 1))
            by_loc.setdefault(loc_key, []).append(idx)
    kept.sort(key=lambda t: t[0].occurred_at, reverse=True)
    return [(ev, count) for ev, count in kept[:limit]]


def gdelt_7d_reports(
    db: Session, scope_col: InstrumentedAttribute, scope_id: int
) -> int:
    """Routed GDELT records in the last 7 days — the freshness signal shown
    in GLANCE. GDELT rows carry no prose, so they never enter the timeline.
    """
    cutoff = datetime.now(UTC) - timedelta(days=7)
    return int(
        db.scalar(
            select(func.count()).where(
                scope_col == scope_id,
                CrisisEvent.external_id.like("gdelt:%"),
                CrisisEvent.occurred_at >= cutoff,
            )
        )
        or 0
    )


def sources_for(
    db: Session,
    scope_col: InstrumentedAttribute,
    scope_id: int,
    cited_ids: set[int],
    limit: int = 50,
) -> list[Source]:
    """Sources for the dossier SOURCES section: newest-first by published
    date, deduped by URL, capped — but sources cited by the returned timeline
    are always kept so "cited in src §NN" references resolve.
    """
    source_ids_subq = (
        select(CrisisEvent.source_id)
        .where(scope_col == scope_id, CrisisEvent.source_id.is_not(None))
        .distinct()
        .subquery()
    )
    rows = db.scalars(
        select(Source)
        .where(Source.id.in_(select(source_ids_subq)))
        .order_by(Source.published_at.desc().nullslast(), Source.id.desc())
    ).all()
    out: list[Source] = []
    seen_urls: set[str] = set()
    kept = 0
    for s in rows:
        cited = s.id in cited_ids
        if cited or (s.url not in seen_urls and kept < limit):
            out.append(s)
            seen_urls.add(s.url)
            if not cited:
                kept += 1
    return out


def field_reports_for_country(
    db: Session, country_iso3: str | None, limit: int = 4
) -> list[Source]:
    """Recent ReliefWeb situation reports for a country — the only current
    narrative available, since incident-level prose lags by months."""
    if not country_iso3:
        return []
    return list(
        db.scalars(
            select(Source)
            .where(
                Source.country_iso3 == country_iso3,
                Source.origin == "reliefweb",
            )
            .order_by(Source.published_at.desc().nullslast())
            .limit(limit)
        )
    )

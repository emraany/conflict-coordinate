"""Public read-only endpoints for the conflict registry.

`/api/conflicts`        — list of dots for the globe.
`/api/conflicts/{slug}` — full dossier: parties, recent events, sources,
                          stats, 52-week ACLED intensity sparkline, top
                          admin1 cells by event count.

Write paths (curation, promotion, merge) live in a separate admin router and
will land in Phase 5. For now, registry edits flow through the YAML +
`seed_conflicts.py`.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import (
    Conflict,
    ConflictParty,
    ConflictStatus,
    Crisis,
    Source,
)
from app.models.event import CrisisEvent
from app.schemas import (
    ConflictDetail,
    ConflictListItem,
    ConflictPartyOut,
    ConflictStats,
    IntensityWeek,
    TopAdmin1,
)
from app.schemas.event import CrisisEventOut
from app.schemas.source import SourceOut

router = APIRouter(prefix="/api/conflicts", tags=["conflicts"])


# --- helpers ----------------------------------------------------------------


def _event_counts_by_conflict(
    db: Session,
) -> dict[int, tuple[int, int]]:
    """Total events + total fatalities, grouped by conflict_id.

    Returns {conflict_id: (event_count, total_fatalities)}.
    """
    rows = db.execute(
        select(
            CrisisEvent.conflict_id,
            func.count().label("n"),
            func.coalesce(func.sum(CrisisEvent.fatalities), 0).label("f"),
        )
        .where(CrisisEvent.conflict_id.is_not(None))
        .group_by(CrisisEvent.conflict_id)
    ).all()
    return {int(r.conflict_id): (int(r.n), int(r.f)) for r in rows}


def _conflict_intensity_52w(
    db: Session, conflict_id: int
) -> tuple[list[IntensityWeek], int, int]:
    """52w weekly aggregate for the conflict, computed from CrisisEvent.

    Groups events by (date_trunc('week', occurred_at), event_type) where
    conflict_id matches — works for any routing strategy (footprint,
    country-pattern, actor-pattern). The recent-4w window is anchored on
    the latest week_start present.

    Returns (weeks, recent_4w_events, recent_4w_fatalities).
    """
    week_col = func.date_trunc("week", CrisisEvent.occurred_at)
    rows = db.execute(
        select(
            week_col.label("week_start"),
            CrisisEvent.event_type,
            func.count().label("ec"),
            func.coalesce(func.sum(CrisisEvent.fatalities), 0).label("f"),
        )
        .where(
            CrisisEvent.conflict_id == conflict_id,
            CrisisEvent.occurred_at.is_not(None),
        )
        .group_by(week_col, CrisisEvent.event_type)
        .order_by(week_col.asc())
    ).all()

    if not rows:
        return [], 0, 0

    by_week: dict[date, dict] = defaultdict(
        lambda: {"counts": defaultdict(int), "fatalities": 0}
    )
    for r in rows:
        # date_trunc returns datetime; normalize to date.
        wk = r.week_start.date() if hasattr(r.week_start, "date") else r.week_start
        bucket = by_week[wk]
        bucket["counts"][r.event_type or "unknown"] += int(r.ec or 0)
        bucket["fatalities"] += int(r.f or 0)

    sorted_weeks = sorted(by_week.keys())
    cutoff_idx = max(0, len(sorted_weeks) - 52)
    weeks = [
        IntensityWeek(
            week_start=w,
            event_count_by_type=dict(by_week[w]["counts"]),
            fatalities=by_week[w]["fatalities"],
            population_exposure=None,
        )
        for w in sorted_weeks[cutoff_idx:]
    ]

    latest = sorted_weeks[-1]
    active_cutoff = latest - timedelta(weeks=4)
    recent_events = 0
    recent_fatalities = 0
    for w in sorted_weeks:
        if w < active_cutoff:
            continue
        recent_events += sum(by_week[w]["counts"].values())
        recent_fatalities += by_week[w]["fatalities"]
    return weeks, recent_events, recent_fatalities


def _compute_stats(
    events: list[CrisisEvent],
    recent_4w_events: int,
    recent_4w_fatalities: int,
) -> ConflictStats:
    type_counts: Counter[str] = Counter()
    total_fatalities = 0
    first_at = None
    last_at = None
    for ev in events:
        if ev.event_type:
            type_counts[ev.event_type] += 1
        total_fatalities += ev.fatalities or 0
        if ev.occurred_at:
            if first_at is None or ev.occurred_at < first_at:
                first_at = ev.occurred_at
            if last_at is None or ev.occurred_at > last_at:
                last_at = ev.occurred_at
    return ConflictStats(
        total_events=len(events),
        total_fatalities=total_fatalities,
        event_type_counts=dict(type_counts.most_common()),
        first_event_at=first_at,
        last_event_at=last_at,
        recent_4w_events=recent_4w_events,
        recent_4w_fatalities=recent_4w_fatalities,
    )


def _dedupe_events_for_display(
    events: list[CrisisEvent], limit: int = 50
) -> list[tuple[CrisisEvent, int]]:
    """Presentation-only dedup of the dossier timeline — DB rows are never
    merged and stats still count every record. Two collapse rules:

      - identical (day, description) rows fold into one, counted
      - same-day rows within ~0.1° from *different* feeds fold into the row
        with the richest description (ACLED prose beats a UCDP headline);
        same-feed rows at the same spot stay separate — they are distinct
        incidents, not double reporting

    Returns (event, report_count) newest-first, capped at `limit`."""

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


def _gdelt_7d_reports(db: Session, conflict_id: int) -> int:
    """Routed GDELT records in the last 7 days — the freshness signal shown
    in GLANCE (GDELT rows are excluded from the prose timeline)."""
    from datetime import UTC, datetime, timedelta

    cutoff = datetime.now(UTC) - timedelta(days=7)
    return int(
        db.scalar(
            select(func.count()).where(
                CrisisEvent.conflict_id == conflict_id,
                CrisisEvent.external_id.like("gdelt:%"),
                CrisisEvent.occurred_at >= cutoff,
            )
        )
        or 0
    )


def _top_admin1s_for(db: Session, conflict_id: int, limit: int = 8) -> list[TopAdmin1]:
    """Top admin1 cells in this conflict, ranked by event count.

    Walks events → parent crisis to recover (iso3, admin1) labels, since the
    event row itself only carries lat/lng + parent crisis_id.
    """
    rows = db.execute(
        select(
            Crisis.country_iso3,
            Crisis.admin1,
            func.count(CrisisEvent.id).label("n"),
        )
        .join(Crisis, Crisis.id == CrisisEvent.crisis_id)
        .where(CrisisEvent.conflict_id == conflict_id)
        .group_by(Crisis.country_iso3, Crisis.admin1)
        .order_by(func.count(CrisisEvent.id).desc())
        .limit(limit)
    ).all()
    return [
        TopAdmin1(
            iso3=r.country_iso3 or "",
            admin1=r.admin1 or "(unknown)",
            event_count=int(r.n),
        )
        for r in rows
    ]


def _sources_for(
    db: Session, conflict_id: int, cited_ids: set[int], limit: int = 50
) -> list[Source]:
    """Sources for the dossier SOURCES section: newest-first by published
    date, deduped by URL, capped — but sources cited by the returned
    timeline events are always kept so "cited in src §NN" refs resolve."""
    source_ids_subq = (
        select(CrisisEvent.source_id)
        .where(
            CrisisEvent.conflict_id == conflict_id,
            CrisisEvent.source_id.is_not(None),
        )
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


# --- endpoints --------------------------------------------------------------


@router.get("", response_model=list[ConflictListItem])
def list_conflicts(
    include_resolved: bool = Query(
        default=False, description="Include status=resolved conflicts"
    ),
    include_emerging: bool = Query(
        default=True,
        description="Include status=emerging (auto-discovered but unconfirmed)",
    ),
    db: Session = Depends(get_db),
) -> list[ConflictListItem]:
    stmt = select(Conflict).order_by(Conflict.name)
    statuses: list[ConflictStatus] = [ConflictStatus.active, ConflictStatus.frozen]
    if include_resolved:
        statuses.append(ConflictStatus.resolved)
    if include_emerging:
        statuses.append(ConflictStatus.emerging)
    stmt = stmt.where(Conflict.status.in_(statuses))

    conflicts = list(db.scalars(stmt))
    counts = _event_counts_by_conflict(db)
    return [
        ConflictListItem(
            id=c.id,
            slug=c.slug,
            name=c.name,
            conflict_type=c.conflict_type,
            status=c.status,
            primary_iso3=c.primary_iso3,
            secondary_iso3s=list(c.secondary_iso3s or []),
            lat=c.lat,
            lng=c.lng,
            started_at=c.started_at,
            last_event_at=c.last_event_at,
            intensity_4w_events=c.intensity_4w_events,
            intensity_4w_fatalities=c.intensity_4w_fatalities,
            event_count=counts.get(c.id, (0, 0))[0],
            total_fatalities=counts.get(c.id, (0, 0))[1],
        )
        for c in conflicts
    ]


@router.get("/{slug}", response_model=ConflictDetail)
def get_conflict(slug: str, db: Session = Depends(get_db)) -> ConflictDetail:
    conflict = db.scalars(
        select(Conflict)
        .where(Conflict.slug == slug)
        .options(
            selectinload(Conflict.party_links).selectinload(ConflictParty.actor),
        )
    ).one_or_none()
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")

    # Dossier timeline: recent events WITH prose only (GDELT rows have no
    # description — they feed stats and the 7-day signal instead). Fetch a
    # wider window, then presentation-dedupe down to 50.
    timeline_rows = list(
        db.scalars(
            select(CrisisEvent)
            .where(
                CrisisEvent.conflict_id == conflict.id,
                CrisisEvent.description.is_not(None),
                CrisisEvent.occurred_at.is_not(None),
            )
            .order_by(CrisisEvent.occurred_at.desc())
            .limit(150)
        )
    )
    deduped = _dedupe_events_for_display(timeline_rows)
    recent_events = [ev for ev, _count in deduped]

    # Stats: total counts come from the conflict-scoped query, NOT just the
    # 50-event window we hand the timeline.
    counts = _event_counts_by_conflict(db).get(conflict.id, (0, 0))
    weeks, r4_events, r4_fatalities = _conflict_intensity_52w(db, conflict.id)
    bounds = db.execute(
        select(
            func.min(CrisisEvent.occurred_at).label("first_at"),
            func.max(CrisisEvent.occurred_at).label("last_at"),
        ).where(CrisisEvent.conflict_id == conflict.id)
    ).one()
    stats = _compute_stats(
        recent_events,
        recent_4w_events=r4_events,
        recent_4w_fatalities=r4_fatalities,
    )
    # Override windowed counts with conflict-scoped aggregates.
    stats.total_events = counts[0]
    stats.total_fatalities = counts[1]
    stats.first_event_at = bounds.first_at
    stats.last_event_at = bounds.last_at
    stats.gdelt_7d_reports = _gdelt_7d_reports(db, conflict.id)

    parties = [
        ConflictPartyOut(
            actor=link.actor,
            role=link.role,
            notes=link.notes,
            source_id=link.source_id,
        )
        for link in conflict.party_links
    ]
    cited_ids = {e.source_id for e in recent_events if e.source_id is not None}
    sources = [
        SourceOut.model_validate(s)
        for s in _sources_for(db, conflict.id, cited_ids)
    ]
    events_out = []
    for ev, count in deduped:
        out = CrisisEventOut.model_validate(ev)
        out.report_count = count
        events_out.append(out)

    return ConflictDetail(
        id=conflict.id,
        slug=conflict.slug,
        name=conflict.name,
        conflict_type=conflict.conflict_type,
        status=conflict.status,
        primary_iso3=conflict.primary_iso3,
        secondary_iso3s=list(conflict.secondary_iso3s or []),
        lat=conflict.lat,
        lng=conflict.lng,
        started_at=conflict.started_at,
        resolved_at=conflict.resolved_at,
        last_event_at=conflict.last_event_at,
        summary=conflict.summary,
        wikipedia_url=conflict.wikipedia_url,
        ucdp_conflict_id=conflict.ucdp_conflict_id,
        parties=parties,
        events=events_out,
        sources=sources,
        stats=stats,
        intensity_52w=weeks,
        top_admin1s=_top_admin1s_for(db, conflict.id),
        created_at=conflict.created_at,
        updated_at=conflict.updated_at,
    )

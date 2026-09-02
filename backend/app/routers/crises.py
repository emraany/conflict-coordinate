from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.conflicts.routing import route_event
from app.db import get_db
from app.deps import require_admin_token
from app.dossier import (
    activity_for_crises,
    dedupe_events_for_display,
    field_reports_for_country,
    gdelt_7d_reports,
    sources_for,
)
from app.models import (
    Conflict,
    ConflictParty,
    Crisis,
    CrisisActor,
    CrisisIntensityWeekly,
    CrisisSlugAlias,
    EntityMention,
    Source,
)
from app.models.event import CrisisEvent
from app.ml.graph import build_graph
from app.schemas.crisis import ConflictContext
from app.schemas.event import CrisisEventOut
from app.scripts.backfill_routing import _load_routing_index
from app.schemas import (
    ActorLinkCreate,
    ActorLinkOut,
    CrisisCreate,
    CrisisDetail,
    CrisisEntities,
    CrisisGraph,
    CrisisListItem,
    CrisisStats,
    CrisisUpdate,
    EntityAggregate,
    EntityGroup,
    IntensityWeek,
    SourceCreate,
    SourceOut,
)

router = APIRouter(prefix="/api/crises", tags=["crises"])


def _load_intensity_52w(
    db: Session, crisis_id: int
) -> tuple[list[IntensityWeek], int, int, int | None]:
    """Return (weeks, recent_4w_events, recent_4w_fatalities, recent_pop_exposed).

    Reads up to 52 weeks of weekly aggregate rows for the crisis. Population
    exposure is MAX (not SUM) over the active window because the same admin1
    population is repeated weekly when there's any activity.
    """
    rows = db.execute(
        select(
            CrisisIntensityWeekly.week_start,
            CrisisIntensityWeekly.event_type,
            CrisisIntensityWeekly.event_count,
            CrisisIntensityWeekly.fatalities,
            CrisisIntensityWeekly.population_exposure,
        )
        .where(CrisisIntensityWeekly.crisis_id == crisis_id)
        .order_by(CrisisIntensityWeekly.week_start.asc())
    ).all()
    if not rows:
        return [], 0, 0, None

    by_week: dict[date, dict] = defaultdict(
        lambda: {"counts": defaultdict(int), "fatalities": 0, "exposure": None}
    )
    for r in rows:
        bucket = by_week[r.week_start]
        bucket["counts"][r.event_type] += int(r.event_count or 0)
        bucket["fatalities"] += int(r.fatalities or 0)
        if r.population_exposure is not None:
            bucket["exposure"] = max(
                bucket["exposure"] or 0, int(r.population_exposure)
            )

    sorted_weeks = sorted(by_week.keys())
    cutoff_idx = max(0, len(sorted_weeks) - 52)
    weeks = [
        IntensityWeek(
            week_start=w,
            event_count_by_type=dict(by_week[w]["counts"]),
            fatalities=by_week[w]["fatalities"],
            population_exposure=by_week[w]["exposure"],
        )
        for w in sorted_weeks[cutoff_idx:]
    ]

    # 4-week window anchored on the most recent week present.
    latest = sorted_weeks[-1]
    active_cutoff = latest - timedelta(weeks=4)
    recent_events = 0
    recent_fatalities = 0
    recent_exposure: int | None = None
    for w in sorted_weeks:
        if w < active_cutoff:
            continue
        bucket = by_week[w]
        recent_events += sum(bucket["counts"].values())
        recent_fatalities += bucket["fatalities"]
        if bucket["exposure"] is not None:
            recent_exposure = max(recent_exposure or 0, bucket["exposure"])
    return weeks, recent_events, recent_fatalities, recent_exposure


def _compute_stats(
    events,
    recent_4w_events: int = 0,
    recent_4w_fatalities: int = 0,
    recent_population_exposed: int | None = None,
) -> CrisisStats:  # type: ignore[no-untyped-def]
    from collections import Counter
    type_counts: Counter = Counter()
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
    return CrisisStats(
        total_events=len(events),
        total_fatalities=total_fatalities,
        event_type_counts=dict(type_counts.most_common()),
        first_event_at=first_at,
        last_event_at=last_at,
        recent_4w_events=recent_4w_events,
        recent_4w_fatalities=recent_4w_fatalities,
        recent_population_exposed=recent_population_exposed,
    )


def _conflict_context(db: Session, crisis: Crisis) -> ConflictContext | None:
    """Resolve the named conflict claiming this region, using the same
    `route_event` the ingest pipeline uses, so a region's label can never
    disagree with where its events were routed."""
    idx = _load_routing_index(db)
    actor_names = [link.actor.name for link in crisis.actor_links]
    conflict_id = route_event(
        actor_names, crisis.country_iso3, crisis.admin1_norm, idx
    )
    if conflict_id is None:
        return None
    conflict = db.scalars(
        select(Conflict)
        .where(Conflict.id == conflict_id)
        .options(selectinload(Conflict.party_links).selectinload(ConflictParty.actor))
    ).one_or_none()
    if conflict is None:
        return None
    return ConflictContext(
        slug=conflict.slug,
        name=conflict.name,
        summary=conflict.summary,
        conflict_type=conflict.conflict_type,
        parties=[
            ActorLinkOut(
                actor=link.actor,
                role=link.role,
                notes=link.notes,
                source_id=link.source_id,
            )
            for link in conflict.party_links
        ],
    )


def _load_crisis_detail(db: Session, crisis: Crisis) -> CrisisDetail:
    actor_links = [
        ActorLinkOut(
            actor=link.actor,
            role=link.role,
            notes=link.notes,
            source_id=link.source_id,
        )
        for link in crisis.actor_links
    ]
    weeks, r4_events, r4_fatalities, r4_exposed = _load_intensity_52w(db, crisis.id)

    # Timeline: incidents WITH prose only. GDELT rows carry no description —
    # they feed the 7-day signal instead of padding the archive with blanks.
    timeline_rows = [
        e
        for e in crisis.events
        if e.description and e.occurred_at is not None
    ]
    timeline_rows.sort(key=lambda e: e.occurred_at, reverse=True)
    deduped = dedupe_events_for_display(timeline_rows[:150])
    events_out = []
    for ev, count in deduped:
        out = CrisisEventOut.model_validate(ev)
        out.report_count = count
        events_out.append(out)

    cited_ids = {ev.source_id for ev, _ in deduped if ev.source_id is not None}
    sources = sources_for(db, CrisisEvent.crisis_id, crisis.id, cited_ids)

    stats = _compute_stats(
        crisis.events,
        recent_4w_events=r4_events,
        recent_4w_fatalities=r4_fatalities,
        recent_population_exposed=r4_exposed,
    )
    stats.gdelt_7d_reports = gdelt_7d_reports(db, CrisisEvent.crisis_id, crisis.id)

    return CrisisDetail.model_validate(
        {
            **{
                k: getattr(crisis, k)
                for k in CrisisDetail.model_fields
                if k
                not in {
                    "actors",
                    "sources",
                    "events",
                    "stats",
                    "intensity_52w",
                    "field_reports",
                    "conflict_context",
                    "activity",
                }
            },
            "activity": activity_for_crises(db, [crisis.id]).get(crisis.id, []),
            "actors": actor_links,
            "sources": sources,
            "events": events_out,
            "stats": stats,
            "intensity_52w": weeks,
            "field_reports": field_reports_for_country(db, crisis.country_iso3),
            "conflict_context": _conflict_context(db, crisis),
        }
    )


def _resolve_slug(db: Session, slug: str) -> str | None:
    """Map an old slug to its current crisis slug via crisis_slug_aliases.
    Returns None if no alias exists."""
    alias = db.scalar(
        select(Crisis.slug)
        .join(CrisisSlugAlias, CrisisSlugAlias.crisis_id == Crisis.id)
        .where(CrisisSlugAlias.old_slug == slug)
    )
    return alias


@router.get("", response_model=list[CrisisListItem])
def list_crises(
    include_dropped: bool = False,
    include_legacy: bool = False,
    db: Session = Depends(get_db),
) -> list[CrisisListItem]:
    """List crisis rows. By default hides legacy admin1-keyed rows that are
    superseded by the conflict registry — pass include_legacy=true from the
    admin UI to surface them for triage."""
    stmt = select(Crisis).order_by(Crisis.name)
    if not include_dropped:
        # Today our enum is {active, frozen, resolved}; admin can later add
        # dropped if needed. For now this is a no-op surface.
        pass
    if not include_legacy:
        stmt = stmt.where(Crisis.legacy.is_(False))
    crises = list(db.scalars(stmt))
    counts_q = select(
        CrisisEvent.crisis_id,
        func.count().label("n"),
        func.coalesce(func.sum(CrisisEvent.fatalities), 0).label("f"),
    ).group_by(CrisisEvent.crisis_id)
    counts = {row.crisis_id: (int(row.n), int(row.f)) for row in db.execute(counts_q)}
    return [
        CrisisListItem(
            id=c.id,
            slug=c.slug,
            name=c.name,
            country=c.country,
            country_iso3=c.country_iso3,
            admin1=c.admin1,
            region=c.region,
            lat=c.lat,
            lng=c.lng,
            status=c.status,
            conflict_type=c.conflict_type,
            started_at=c.started_at,
            last_event_at=c.last_event_at,
            event_count=counts.get(c.id, (0, 0))[0],
            total_fatalities=counts.get(c.id, (0, 0))[1],
        )
        for c in crises
    ]


@router.get("/{slug}/entities", response_model=CrisisEntities)
def get_crisis_entities(
    slug: str,
    per_label: int = 12,
    db: Session = Depends(get_db),
) -> CrisisEntities:
    crisis = db.scalar(select(Crisis.id).where(Crisis.slug == slug))
    if crisis is None:
        raise HTTPException(status_code=404, detail="Crisis not found")

    from sqlalchemy.dialects.postgresql import array_agg

    rows = db.execute(
        select(
            EntityMention.label,
            EntityMention.text_norm,
            func.count().label("n"),
            func.min(EntityMention.text).label("text"),
            array_agg(EntityMention.event_id.distinct()).label("event_ids"),
        )
        .join(CrisisEvent, CrisisEvent.id == EntityMention.event_id)
        .where(CrisisEvent.crisis_id == crisis)
        .group_by(EntityMention.label, EntityMention.text_norm)
        .order_by(EntityMention.label, func.count().desc())
    ).all()

    by_label: dict[str, list[EntityAggregate]] = {}
    total = 0
    for r in rows:
        total += int(r.n)
        bucket = by_label.setdefault(r.label, [])
        if len(bucket) >= per_label:
            continue
        bucket.append(
            EntityAggregate(
                label=r.label,
                text=r.text,
                count=int(r.n),
                event_ids=[int(x) for x in (r.event_ids or [])],
            )
        )

    label_order = ["GPE", "ORG", "PERSON", "NORP", "LOC", "FAC", "EVENT"]
    groups = [
        EntityGroup(label=lbl, entities=by_label[lbl])
        for lbl in label_order
        if lbl in by_label
    ]
    for lbl, ents in by_label.items():
        if lbl not in label_order:
            groups.append(EntityGroup(label=lbl, entities=ents))

    return CrisisEntities(crisis_id=crisis, total_mentions=total, groups=groups)


@router.get("/{slug}/graph", response_model=CrisisGraph)
def get_crisis_graph(slug: str, db: Session = Depends(get_db)) -> CrisisGraph:
    crisis_id = db.scalar(select(Crisis.id).where(Crisis.slug == slug))
    if crisis_id is None:
        raise HTTPException(status_code=404, detail="Crisis not found")
    payload = build_graph(db, crisis_id)
    return CrisisGraph(crisis_id=crisis_id, **payload)


@router.get("/by-slug-alias/{old_slug}")
def resolve_slug_alias(old_slug: str, db: Session = Depends(get_db)):
    """301-redirect old DBSCAN-cluster slugs to their admin1-keyed successor."""
    new_slug = _resolve_slug(db, old_slug)
    if new_slug is None:
        raise HTTPException(status_code=404, detail="No alias for this slug")
    return RedirectResponse(url=f"/api/crises/{new_slug}", status_code=301)


@router.get("/{slug}", response_model=CrisisDetail)
def get_crisis(slug: str, db: Session = Depends(get_db)):
    stmt = (
        select(Crisis)
        .where(Crisis.slug == slug)
        .options(
            selectinload(Crisis.actor_links).selectinload(CrisisActor.actor),
            selectinload(Crisis.actor_links).selectinload(CrisisActor.source),
            selectinload(Crisis.sources),
            selectinload(Crisis.events),
        )
    )
    crisis = db.scalars(stmt).one_or_none()
    if crisis is None:
        new_slug = _resolve_slug(db, slug)
        if new_slug is not None:
            return RedirectResponse(
                url=f"/api/crises/{new_slug}", status_code=301
            )
        raise HTTPException(status_code=404, detail="Crisis not found")
    return _load_crisis_detail(db, crisis)


@router.post(
    "",
    response_model=CrisisDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_token)],
)
def create_crisis(payload: CrisisCreate, db: Session = Depends(get_db)) -> CrisisDetail:
    existing = db.scalar(select(Crisis).where(Crisis.slug == payload.slug))
    if existing is not None:
        raise HTTPException(status_code=409, detail="slug already exists")
    crisis = Crisis(**payload.model_dump())
    crisis.geom = f"SRID=4326;POINT({payload.lng} {payload.lat})"
    db.add(crisis)
    db.commit()
    db.refresh(crisis)
    return _load_crisis_detail(db, crisis)


@router.patch(
    "/{slug}",
    response_model=CrisisDetail,
    dependencies=[Depends(require_admin_token)],
)
def update_crisis(
    slug: str, payload: CrisisUpdate, db: Session = Depends(get_db)
) -> CrisisDetail:
    crisis = db.scalar(select(Crisis).where(Crisis.slug == slug))
    if crisis is None:
        raise HTTPException(status_code=404, detail="Crisis not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(crisis, k, v)
    if "lat" in data or "lng" in data:
        crisis.geom = f"SRID=4326;POINT({crisis.lng} {crisis.lat})"
    db.commit()
    db.refresh(crisis)
    return _load_crisis_detail(db, crisis)


@router.delete(
    "/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_token)],
)
def delete_crisis(slug: str, db: Session = Depends(get_db)) -> None:
    crisis = db.scalar(select(Crisis).where(Crisis.slug == slug))
    if crisis is None:
        raise HTTPException(status_code=404, detail="Crisis not found")
    db.delete(crisis)
    db.commit()


@router.post(
    "/{slug}/actors",
    response_model=ActorLinkOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_token)],
)
def link_actor(
    slug: str, payload: ActorLinkCreate, db: Session = Depends(get_db)
) -> ActorLinkOut:
    crisis = db.scalar(select(Crisis).where(Crisis.slug == slug))
    if crisis is None:
        raise HTTPException(status_code=404, detail="Crisis not found")
    existing = db.get(CrisisActor, (crisis.id, payload.actor_id))
    if existing is not None:
        raise HTTPException(status_code=409, detail="actor already linked")
    link = CrisisActor(
        crisis_id=crisis.id,
        actor_id=payload.actor_id,
        role=payload.role,
        notes=payload.notes,
        source_id=payload.source_id,
        admin_curated=True,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return ActorLinkOut(
        actor=link.actor,
        role=link.role,
        notes=link.notes,
        source_id=link.source_id,
    )


@router.delete(
    "/{slug}/actors/{actor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_token)],
)
def unlink_actor(slug: str, actor_id: int, db: Session = Depends(get_db)) -> None:
    crisis = db.scalar(select(Crisis).where(Crisis.slug == slug))
    if crisis is None:
        raise HTTPException(status_code=404, detail="Crisis not found")
    link = db.get(CrisisActor, (crisis.id, actor_id))
    if link is None:
        raise HTTPException(status_code=404, detail="link not found")
    db.delete(link)
    db.commit()


@router.post(
    "/{slug}/sources",
    response_model=SourceOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_token)],
)
def add_source(
    slug: str, payload: SourceCreate, db: Session = Depends(get_db)
) -> Source:
    crisis = db.scalar(select(Crisis).where(Crisis.slug == slug))
    if crisis is None:
        raise HTTPException(status_code=404, detail="Crisis not found")
    data = payload.model_dump(exclude={"crisis_id"})
    src = Source(crisis_id=crisis.id, **data)
    db.add(src)
    db.commit()
    db.refresh(src)
    return src

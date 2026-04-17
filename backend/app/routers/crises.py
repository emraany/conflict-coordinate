from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import require_admin_token
from app.models import Crisis, CrisisActor, Source
from app.schemas import (
    ActorLinkCreate,
    ActorLinkOut,
    CrisisCreate,
    CrisisDetail,
    CrisisListItem,
    CrisisStats,
    CrisisUpdate,
    SourceCreate,
    SourceOut,
)

router = APIRouter(prefix="/api/crises", tags=["crises"])


def _compute_stats(events) -> CrisisStats:  # type: ignore[no-untyped-def]
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
    return CrisisDetail.model_validate(
        {
            **{k: getattr(crisis, k) for k in CrisisDetail.model_fields if k not in {"actors", "sources", "events", "stats"}},
            "actors": actor_links,
            "sources": crisis.sources,
            "events": sorted(crisis.events, key=lambda e: e.occurred_at, reverse=True)[:50],
            "stats": _compute_stats(crisis.events),
        }
    )


@router.get("", response_model=list[CrisisListItem])
def list_crises(db: Session = Depends(get_db)) -> list[Crisis]:
    return list(db.scalars(select(Crisis).order_by(Crisis.name)))


@router.get("/{slug}", response_model=CrisisDetail)
def get_crisis(slug: str, db: Session = Depends(get_db)) -> CrisisDetail:
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

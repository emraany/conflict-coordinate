"""Admin endpoints for conflict-registry curation.

Companion to the public `/api/conflicts` router. All routes require the
`X-Admin-Token` header. Surfaces the triage queue (emerging + admin
metadata) and the basic edit operations needed to promote an
auto-discovered conflict into an `active` dot:

  GET    /api/admin/conflicts                          — list all (admin shape)
  PATCH  /api/admin/conflicts/{slug}                   — edit identity fields
  DELETE /api/admin/conflicts/{slug}                   — drop entirely
  POST   /api/admin/conflicts/{slug}/routing-rules     — add routing rule
  DELETE /api/admin/conflicts/{slug}/routing-rules/{id} — drop routing rule
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.conflicts.loader import normalize_admin1
from app.db import get_db
from app.deps import require_admin_token
from app.models import (
    Actor,
    ActorRole,
    Conflict,
    ConflictFootprint,
    ConflictParty,
    ConflictRoutingRule,
    ConflictStatus,
)
from app.models.event import CrisisEvent

router = APIRouter(
    prefix="/api/admin/conflicts",
    tags=["admin:conflicts"],
    dependencies=[Depends(require_admin_token)],
)


# ---------------------------------------------------------------------------
# Schemas — kept small and focused on what the triage UI needs. They diverge
# from `ConflictListItem` because admin needs the routing-rule list and
# pending event counts that the public router hides.
# ---------------------------------------------------------------------------


class RoutingRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_type: str
    pattern: str
    priority: int


class FootprintCellOut(BaseModel):
    country_iso3: str
    admin1_norm: str
    confidence: float


class FootprintCellCreate(BaseModel):
    iso3: str = Field(min_length=3, max_length=3)
    admin1: str = Field(min_length=1, max_length=120)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class PartyActorOut(BaseModel):
    """Trimmed actor card for the admin curate panel."""

    id: int
    name: str
    type: str


class PartyOut(BaseModel):
    actor: PartyActorOut
    role: ActorRole
    notes: str | None


class PartyCreate(BaseModel):
    actor_id: int
    role: ActorRole = ActorRole.party
    notes: str | None = None


class AdminConflictListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    conflict_type: str | None
    status: ConflictStatus
    primary_iso3: str | None
    secondary_iso3s: list[str]
    summary: str | None
    wikipedia_url: str | None
    registry_source: str
    admin_curated: bool
    event_count: int
    intensity_4w_events: int
    routing_rule_count: int
    last_event_at: str | None


class AdminConflictDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    conflict_type: str | None
    status: ConflictStatus
    primary_iso3: str | None
    secondary_iso3s: list[str]
    summary: str | None
    wikipedia_url: str | None
    registry_source: str
    admin_curated: bool
    event_count: int
    intensity_4w_events: int
    routing_rules: list[RoutingRuleOut]
    footprints: list[FootprintCellOut]
    parties: list[PartyOut]
    last_event_at: str | None


class ConflictPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    conflict_type: str | None = None
    status: ConflictStatus | None = None
    primary_iso3: str | None = Field(default=None, min_length=3, max_length=3)
    secondary_iso3s: list[str] | None = None
    summary: str | None = None
    wikipedia_url: str | None = None


class RoutingRuleCreate(BaseModel):
    rule_type: Literal["actor", "admin1", "country"]
    pattern: str = Field(min_length=1, max_length=400)
    priority: int = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event_counts_by_conflict(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(CrisisEvent.conflict_id, func.count().label("n"))
        .where(CrisisEvent.conflict_id.is_not(None))
        .group_by(CrisisEvent.conflict_id)
    ).all()
    return {int(r.conflict_id): int(r.n) for r in rows}


def _routing_rule_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(ConflictRoutingRule.conflict_id, func.count())
        .group_by(ConflictRoutingRule.conflict_id)
    ).all()
    return {int(c): int(n) for c, n in rows}


def _serialize_detail(db: Session, conflict: Conflict) -> AdminConflictDetail:
    rules = db.scalars(
        select(ConflictRoutingRule)
        .where(ConflictRoutingRule.conflict_id == conflict.id)
        .order_by(ConflictRoutingRule.priority, ConflictRoutingRule.id)
    ).all()
    footprints = db.scalars(
        select(ConflictFootprint)
        .where(ConflictFootprint.conflict_id == conflict.id)
        .order_by(ConflictFootprint.country_iso3, ConflictFootprint.admin1_norm)
    ).all()
    party_rows = db.execute(
        select(ConflictParty, Actor)
        .join(Actor, Actor.id == ConflictParty.actor_id)
        .where(ConflictParty.conflict_id == conflict.id)
        .order_by(Actor.name)
    ).all()
    ev_count = db.scalar(
        select(func.count())
        .select_from(CrisisEvent)
        .where(CrisisEvent.conflict_id == conflict.id)
    ) or 0
    return AdminConflictDetail(
        id=conflict.id,
        slug=conflict.slug,
        name=conflict.name,
        conflict_type=conflict.conflict_type,
        status=conflict.status,
        primary_iso3=conflict.primary_iso3,
        secondary_iso3s=list(conflict.secondary_iso3s or []),
        summary=conflict.summary,
        wikipedia_url=conflict.wikipedia_url,
        registry_source=conflict.registry_source,
        admin_curated=conflict.admin_curated,
        event_count=int(ev_count),
        intensity_4w_events=conflict.intensity_4w_events,
        routing_rules=[RoutingRuleOut.model_validate(r) for r in rules],
        footprints=[
            FootprintCellOut(
                country_iso3=f.country_iso3,
                admin1_norm=f.admin1_norm,
                confidence=f.confidence,
            )
            for f in footprints
        ],
        parties=[
            PartyOut(
                actor=PartyActorOut(
                    id=actor.id, name=actor.name, type=actor.type.value
                ),
                role=link.role,
                notes=link.notes,
            )
            for link, actor in party_rows
        ],
        last_event_at=(
            conflict.last_event_at.isoformat() if conflict.last_event_at else None
        ),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[AdminConflictListItem])
def list_admin_conflicts(db: Session = Depends(get_db)) -> list[AdminConflictListItem]:
    conflicts = list(db.scalars(select(Conflict).order_by(Conflict.status, Conflict.name)))
    ev_counts = _event_counts_by_conflict(db)
    rule_counts = _routing_rule_counts(db)
    return [
        AdminConflictListItem(
            id=c.id,
            slug=c.slug,
            name=c.name,
            conflict_type=c.conflict_type,
            status=c.status,
            primary_iso3=c.primary_iso3,
            secondary_iso3s=list(c.secondary_iso3s or []),
            summary=c.summary,
            wikipedia_url=c.wikipedia_url,
            registry_source=c.registry_source,
            admin_curated=c.admin_curated,
            event_count=ev_counts.get(c.id, 0),
            intensity_4w_events=c.intensity_4w_events,
            routing_rule_count=rule_counts.get(c.id, 0),
            last_event_at=c.last_event_at.isoformat() if c.last_event_at else None,
        )
        for c in conflicts
    ]


@router.get("/{slug}", response_model=AdminConflictDetail)
def get_admin_conflict(slug: str, db: Session = Depends(get_db)) -> AdminConflictDetail:
    conflict = db.scalar(select(Conflict).where(Conflict.slug == slug))
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    return _serialize_detail(db, conflict)


@router.patch("/{slug}", response_model=AdminConflictDetail)
def update_conflict(
    slug: str, payload: ConflictPatch, db: Session = Depends(get_db)
) -> AdminConflictDetail:
    conflict = db.scalar(select(Conflict).where(Conflict.slug == slug))
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    data = payload.model_dump(exclude_unset=True)
    if "primary_iso3" in data and data["primary_iso3"]:
        data["primary_iso3"] = data["primary_iso3"].upper()
    if "secondary_iso3s" in data and data["secondary_iso3s"] is not None:
        data["secondary_iso3s"] = [s.upper() for s in data["secondary_iso3s"]]
    for k, v in data.items():
        setattr(conflict, k, v)
    # Any admin edit marks the row as curated — wiki re-discovery should
    # never overwrite it.
    conflict.admin_curated = True
    db.commit()
    db.refresh(conflict)
    return _serialize_detail(db, conflict)


@router.delete(
    "/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conflict(slug: str, db: Session = Depends(get_db)) -> None:
    conflict = db.scalar(select(Conflict).where(Conflict.slug == slug))
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    # Detach events from this conflict so the routing index can re-route
    # them on the next backfill. Cascade handles footprints / parties /
    # routing rules via FK ondelete.
    db.execute(
        CrisisEvent.__table__.update()
        .where(CrisisEvent.conflict_id == conflict.id)
        .values(conflict_id=None)
    )
    db.delete(conflict)
    db.commit()


@router.post(
    "/{slug}/routing-rules",
    response_model=RoutingRuleOut,
    status_code=status.HTTP_201_CREATED,
)
def add_routing_rule(
    slug: str, payload: RoutingRuleCreate, db: Session = Depends(get_db)
) -> RoutingRuleOut:
    conflict = db.scalar(select(Conflict).where(Conflict.slug == slug))
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")

    # Normalize pattern by rule type. Match the conventions in loader.py so
    # admin-curated rules stack correctly with YAML-loaded ones.
    pattern = payload.pattern
    if payload.rule_type == "country":
        pattern = pattern.upper().strip()
        if len(pattern) != 3:
            raise HTTPException(
                status_code=400, detail="country pattern must be ISO-3 alpha"
            )
    elif payload.rule_type == "admin1":
        if ":" not in pattern:
            raise HTTPException(
                status_code=400, detail="admin1 pattern must be '<ISO3>:<admin1_norm>'"
            )

    # Reject exact duplicates against this conflict — typo protection.
    existing = db.scalar(
        select(ConflictRoutingRule).where(
            ConflictRoutingRule.conflict_id == conflict.id,
            ConflictRoutingRule.rule_type == payload.rule_type,
            ConflictRoutingRule.pattern == pattern,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="rule already exists")

    rule = ConflictRoutingRule(
        conflict_id=conflict.id,
        rule_type=payload.rule_type,
        pattern=pattern,
        priority=payload.priority,
    )
    db.add(rule)
    conflict.admin_curated = True
    db.commit()
    db.refresh(rule)
    return RoutingRuleOut.model_validate(rule)


@router.delete(
    "/{slug}/routing-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_routing_rule(
    slug: str, rule_id: int, db: Session = Depends(get_db)
) -> None:
    conflict = db.scalar(select(Conflict).where(Conflict.slug == slug))
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    rule = db.scalar(
        select(ConflictRoutingRule).where(
            ConflictRoutingRule.id == rule_id,
            ConflictRoutingRule.conflict_id == conflict.id,
        )
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found on this conflict")
    db.delete(rule)
    conflict.admin_curated = True
    db.commit()


# ---------------------------------------------------------------------------
# Footprint cells
# ---------------------------------------------------------------------------


@router.post(
    "/{slug}/footprint",
    response_model=FootprintCellOut,
    status_code=status.HTTP_201_CREATED,
)
def add_footprint_cell(
    slug: str, payload: FootprintCellCreate, db: Session = Depends(get_db)
) -> FootprintCellOut:
    conflict = db.scalar(select(Conflict).where(Conflict.slug == slug))
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")

    iso3 = payload.iso3.upper()
    admin1_norm = normalize_admin1(payload.admin1)
    if not admin1_norm:
        raise HTTPException(status_code=400, detail="admin1 normalizes to empty")

    existing = db.get(ConflictFootprint, (conflict.id, iso3, admin1_norm))
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="footprint cell already exists on this conflict"
        )

    cell = ConflictFootprint(
        conflict_id=conflict.id,
        country_iso3=iso3,
        admin1_norm=admin1_norm,
        confidence=payload.confidence,
    )
    db.add(cell)

    # Footprint cells also imply a priority-2 admin1 routing rule. The router
    # only reads the conflict_routing_rules table, so we insert a matching
    # rule here unless one already exists.
    rule_pattern = f"{iso3}:{admin1_norm}"
    existing_rule = db.scalar(
        select(ConflictRoutingRule).where(
            ConflictRoutingRule.conflict_id == conflict.id,
            ConflictRoutingRule.rule_type == "admin1",
            ConflictRoutingRule.pattern == rule_pattern,
        )
    )
    if existing_rule is None:
        db.add(
            ConflictRoutingRule(
                conflict_id=conflict.id,
                rule_type="admin1",
                pattern=rule_pattern,
                priority=2,
            )
        )

    conflict.admin_curated = True
    db.commit()
    return FootprintCellOut(
        country_iso3=iso3, admin1_norm=admin1_norm, confidence=payload.confidence
    )


@router.delete(
    "/{slug}/footprint/{iso3}/{admin1_norm}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_footprint_cell(
    slug: str,
    iso3: str,
    admin1_norm: str,
    db: Session = Depends(get_db),
) -> None:
    conflict = db.scalar(select(Conflict).where(Conflict.slug == slug))
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    iso = iso3.upper()
    norm = admin1_norm.lower().strip()
    cell = db.get(ConflictFootprint, (conflict.id, iso, norm))
    if cell is None:
        raise HTTPException(status_code=404, detail="footprint cell not found")
    db.delete(cell)
    # Drop the implied admin1 routing rule too — keep them in lockstep.
    db.execute(
        ConflictRoutingRule.__table__.delete().where(
            ConflictRoutingRule.conflict_id == conflict.id,
            ConflictRoutingRule.rule_type == "admin1",
            ConflictRoutingRule.pattern == f"{iso}:{norm}",
        )
    )
    conflict.admin_curated = True
    db.commit()


# ---------------------------------------------------------------------------
# Parties
# ---------------------------------------------------------------------------


@router.post(
    "/{slug}/parties",
    response_model=PartyOut,
    status_code=status.HTTP_201_CREATED,
)
def add_party(
    slug: str, payload: PartyCreate, db: Session = Depends(get_db)
) -> PartyOut:
    conflict = db.scalar(select(Conflict).where(Conflict.slug == slug))
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    actor = db.get(Actor, payload.actor_id)
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")
    existing = db.get(ConflictParty, (conflict.id, actor.id))
    if existing is not None:
        raise HTTPException(status_code=409, detail="actor already linked")

    link = ConflictParty(
        conflict_id=conflict.id,
        actor_id=actor.id,
        role=payload.role,
        notes=payload.notes,
        admin_curated=True,
    )
    db.add(link)
    conflict.admin_curated = True
    db.commit()
    return PartyOut(
        actor=PartyActorOut(id=actor.id, name=actor.name, type=actor.type.value),
        role=link.role,
        notes=link.notes,
    )


@router.delete(
    "/{slug}/parties/{actor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_party(slug: str, actor_id: int, db: Session = Depends(get_db)) -> None:
    conflict = db.scalar(select(Conflict).where(Conflict.slug == slug))
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    link = db.get(ConflictParty, (conflict.id, actor_id))
    if link is None:
        raise HTTPException(status_code=404, detail="party link not found")
    db.delete(link)
    conflict.admin_curated = True
    db.commit()

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.conflict import Conflict, ConflictStatus
from app.models.event import CrisisEvent

router = APIRouter(prefix="/api/activity", tags=["activity"])


class ActivityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    event_type: str | None
    description: str | None
    fatalities: int | None
    location_name: str | None
    conflict_slug: str
    conflict_name: str
    conflict_primary_iso3: str | None
    conflict_status: ConflictStatus
    conflict_type: str | None


@router.get("", response_model=list[ActivityItem])
def get_activity(
    since: datetime | None = Query(default=None),
    days: int | None = Query(default=None, ge=1, le=3650),
    limit: int = Query(default=500, le=1000),
    db: Session = Depends(get_db),
) -> list[ActivityItem]:
    # `days` windows back from the newest event on record, not from now.
    # Individual incident records are an archive — ACLED embargoes them ~12
    # months — so a wall-clock window returns an empty page and reads as
    # "nothing is happening" rather than "these records aren't published yet".
    if days is not None:
        newest = db.scalar(
            select(func.max(CrisisEvent.occurred_at)).where(
                CrisisEvent.conflict_id.is_not(None)
            )
        )
        if newest is not None:
            since = newest - timedelta(days=days)
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(days=7)

    stmt = (
        select(CrisisEvent, Conflict)
        .join(Conflict, CrisisEvent.conflict_id == Conflict.id)
        .where(
            CrisisEvent.occurred_at >= since,
            CrisisEvent.conflict_id.is_not(None),
        )
        .order_by(CrisisEvent.occurred_at.desc())
        .limit(limit)
    )

    items = []
    for event, conflict in db.execute(stmt):
        items.append(
            ActivityItem(
                id=event.id,
                occurred_at=event.occurred_at,
                event_type=event.event_type,
                description=event.description,
                fatalities=event.fatalities,
                location_name=event.location_name,
                conflict_slug=conflict.slug,
                conflict_name=conflict.name,
                conflict_primary_iso3=conflict.primary_iso3,
                conflict_status=conflict.status,
                conflict_type=conflict.conflict_type,
            )
        )
    return items

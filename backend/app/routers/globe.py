"""The globe's dot layer.

A dot is an admin1 region with current violent activity, per ACLED's weekly
aggregates (the part of ACLED's feed that carries no embargo). Dots are
derived from data, not curated: nothing needs to be hand-listed for a newly
violent region to appear.

Where the conflict registry claims a region, the dot carries that conflict's
name — resolved with the same `route_event` the ingest pipeline uses to
assign events, so labels and routing can never disagree.

Counts come from `crises.violence_4w_*`, refreshed once per ingest by
`app.ingestion.runner._refresh_crisis_activity_rollups` (computing them per
request costs ~1.5s).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.conflicts.routing import route_event
from app.db import get_db
from app.ingestion.runner import (
    DOT_MIN_EVENTS,
    DOT_MIN_FATALITIES,
    DOT_WINDOW_WEEKS,
    VIOLENT_EVENT_TYPES,
)
from app.models import Conflict, Crisis
from app.schemas.globe import ActivityType, ConflictLabel, GlobeDot
from app.scripts.backfill_routing import _load_routing_index

router = APIRouter(prefix="/api/globe", tags=["globe"])


def _activity_by_crisis(
    db: Session, crisis_ids: list[int]
) -> dict[int, list[ActivityType]]:
    """What kind of violence each region saw in the window, most frequent
    first. Lets a dot state what is happening rather than only where it is."""
    if not crisis_ids:
        return {}
    types_sql = ", ".join(f"'{t}'" for t in VIOLENT_EVENT_TYPES)
    rows = db.execute(
        text(
            f"""
            WITH latest AS (
                SELECT max(week_start) AS w FROM crisis_intensity_weekly
            )
            SELECT w.crisis_id, w.event_type,
                   sum(w.event_count) AS ev, sum(w.fatalities) AS fat
            FROM crisis_intensity_weekly w, latest
            WHERE w.crisis_id = ANY(:ids)
              AND w.week_start > latest.w - make_interval(weeks => :weeks)
              AND w.event_type IN ({types_sql})
            GROUP BY w.crisis_id, w.event_type
            ORDER BY w.crisis_id, sum(w.event_count) DESC
            """
        ),
        {"ids": crisis_ids, "weeks": DOT_WINDOW_WEEKS},
    ).all()
    out: dict[int, list[ActivityType]] = {}
    for r in rows:
        out.setdefault(r.crisis_id, []).append(
            ActivityType(
                type=r.event_type, events=int(r.ev or 0), fatalities=int(r.fat or 0)
            )
        )
    return out


@router.get("", response_model=list[GlobeDot])
def list_globe_dots(
    min_events: int = Query(default=DOT_MIN_EVENTS, ge=0),
    min_fatalities: int = Query(default=DOT_MIN_FATALITIES, ge=0),
    db: Session = Depends(get_db),
) -> list[GlobeDot]:
    rows = db.scalars(
        select(Crisis)
        .where(
            Crisis.lat.is_not(None),
            Crisis.lng.is_not(None),
            (Crisis.violence_4w_events >= min_events)
            | (Crisis.violence_4w_fatalities >= min_fatalities),
        )
        .order_by(Crisis.violence_4w_events.desc())
    ).all()

    activity = _activity_by_crisis(db, [c.id for c in rows])
    idx = _load_routing_index(db)
    conflict_names = {
        row.id: (row.slug, row.name)
        for row in db.execute(select(Conflict.id, Conflict.slug, Conflict.name)).all()
    }

    dots: list[GlobeDot] = []
    for c in rows:
        label: ConflictLabel | None = None
        conflict_id = route_event([], c.country_iso3, c.admin1_norm, idx)
        if conflict_id is not None and conflict_id in conflict_names:
            slug, name = conflict_names[conflict_id]
            label = ConflictLabel(slug=slug, name=name)
        dots.append(
            GlobeDot(
                slug=c.slug,
                name=c.name,
                country=c.country,
                country_iso3=c.country_iso3,
                admin1=c.admin1,
                lat=c.lat,
                lng=c.lng,
                events_4w=c.violence_4w_events,
                fatalities_4w=c.violence_4w_fatalities,
                population_exposure=c.violence_4w_pop_exposure,
                latest_week=c.latest_agg_week,
                conflict=label,
                activity=activity.get(c.id, []),
            )
        )
    return dots

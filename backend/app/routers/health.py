"""Health and data-currency.

Doubles as the uptime probe and as the source of the freshness stamp the UI
shows. Both need the same answer to the same question, and it isn't "is the
web server up" — the pipeline can stall for weeks while every request keeps
returning 200 and the globe keeps rendering last month's aggregates.

So `status` here describes the *data*, not the process:
  ok        — a successful ingest within STALE_AFTER_DAYS
  stale     — no successful ingest in that window (or none on record)
  degraded  — the most recent run finished with a failure
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.ingestion.runner import DOT_MIN_EVENTS, DOT_MIN_FATALITIES
from app.models import Crisis, IngestRun

router = APIRouter(prefix="/api", tags=["health"])

# ACLED's weekly aggregates publish weekly and land 1–2 weeks behind, so a
# weekly schedule that has missed two cycles is genuinely broken, not late.
STALE_AFTER_DAYS = 14


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    # Read the aggregate week off crises, not crisis_intensity_weekly: it's
    # the same value by construction (the rollup writes it from
    # max(week_start)) over ~2.8k rows instead of ~840k unindexed ones.
    latest_week = db.scalar(select(func.max(Crisis.latest_agg_week)))
    dots = db.scalar(
        select(func.count())
        .select_from(Crisis)
        .where(
            (Crisis.violence_4w_events >= DOT_MIN_EVENTS)
            | (Crisis.violence_4w_fatalities >= DOT_MIN_FATALITIES)
        )
    )

    last_run = db.scalars(
        select(IngestRun)
        .where(IngestRun.finished_at.is_not(None))
        .order_by(IngestRun.finished_at.desc())
        .limit(1)
    ).first()
    last_ok = db.scalars(
        select(IngestRun)
        .where(IngestRun.ok.is_(True), IngestRun.finished_at.is_not(None))
        .order_by(IngestRun.finished_at.desc())
        .limit(1)
    ).first()

    days_since_ok: int | None = None
    if last_ok is not None:
        days_since_ok = (datetime.now(UTC) - last_ok.finished_at).days

    if days_since_ok is None or days_since_ok > STALE_AFTER_DAYS:
        status = "stale"
    elif last_run is not None and not last_run.ok:
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "latest_aggregate_week": latest_week.isoformat() if latest_week else None,
        "dots": int(dots or 0),
        "last_ingest_at": last_run.finished_at.isoformat() if last_run else None,
        "last_ingest_ok": last_run.ok if last_run else None,
        "last_successful_ingest_at": (
            last_ok.finished_at.isoformat() if last_ok else None
        ),
        "days_since_successful_ingest": days_since_ok,
        "stale_after_days": STALE_AFTER_DAYS,
    }

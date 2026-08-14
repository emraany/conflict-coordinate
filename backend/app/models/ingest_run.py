from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class IngestRun(Base):
    """One row per ingest attempt, written whether it succeeds or dies.

    The in-memory status dict in `app.routers.ingest` only exists inside the
    API process, so a run started by the cron worker left no trace at all.
    This table is what `/api/health` reads to answer "is the pipeline still
    alive", which is the only way an unattended weekly schedule is knowable.
    """

    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # "cron" for the standalone worker, "api" for POST /api/ingest/run.
    trigger: Mapped[str] = mapped_column(String(16), nullable=False, default="cron")
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_ingest_runs_finished_at", "finished_at"),)

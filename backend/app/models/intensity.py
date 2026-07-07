from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CrisisIntensityWeekly(Base):
    """Weekly ACLED-aggregated activity for one crisis × event_type.

    Sourced from ACLED's regional aggregated xlsx files. Replaces stale
    event-derived sparklines with a real-time intensity signal.
    """

    __tablename__ = "crisis_intensity_weekly"

    id: Mapped[int] = mapped_column(primary_key=True)
    crisis_id: Mapped[int] = mapped_column(
        ForeignKey("crises.id", ondelete="CASCADE"), nullable=False
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fatalities: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    population_exposure: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_intensity_crisis_week_type",
            "crisis_id",
            "week_start",
            "event_type",
            unique=True,
        ),
        Index("ix_intensity_crisis_week", "crisis_id", "week_start"),
    )

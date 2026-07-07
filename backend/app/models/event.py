from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.crisis import Crisis
    from app.models.source import Source


class CrisisEvent(Base):
    __tablename__ = "crisis_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    crisis_id: Mapped[int] = mapped_column(
        ForeignKey("crises.id", ondelete="CASCADE"), index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    event_type: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    fatalities: Mapped[int | None] = mapped_column(Integer)
    location_name: Mapped[str | None] = mapped_column(String(200))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    external_id: Mapped[str | None] = mapped_column(String(200), index=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
    # Routing target — populated during conflict-registry rebuild. NULL means
    # the event hasn't been routed yet, or no routing rule matched (orphan).
    conflict_id: Mapped[int | None] = mapped_column(
        ForeignKey("conflicts.id", ondelete="SET NULL"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    crisis: Mapped[Crisis] = relationship(back_populates="events")
    source: Mapped[Source | None] = relationship()

    __table_args__ = (
        Index("ix_events_crisis_occurred", "crisis_id", "occurred_at"),
    )

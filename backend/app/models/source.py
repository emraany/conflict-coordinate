from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.crisis import Crisis


class SourceType(str, enum.Enum):
    news = "news"
    report = "report"
    academic = "academic"
    official = "official"
    primary = "primary"
    situation_report = "situation_report"
    reference = "reference"


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    crisis_id: Mapped[int | None] = mapped_column(
        ForeignKey("crises.id", ondelete="CASCADE"), index=True
    )
    # Conflict-scoped sources (e.g. ReliefWeb situation reports) hang off the
    # conflict directly instead of an event's parent crisis.
    conflict_id: Mapped[int | None] = mapped_column(
        ForeignKey("conflicts.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(1000))
    publisher: Mapped[str | None] = mapped_column(String(200))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type"), default=SourceType.news
    )
    origin: Mapped[str | None] = mapped_column(String(40), index=True)
    body_text: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    crisis: Mapped[Crisis | None] = relationship(back_populates="sources")

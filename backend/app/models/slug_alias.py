from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CrisisSlugAlias(Base):
    """Old slug → current crisis_id, for 301-redirecting bookmarks after the
    DBSCAN-cluster → admin1 identity migration."""

    __tablename__ = "crisis_slug_aliases"

    old_slug: Mapped[str] = mapped_column(String(120), primary_key=True)
    crisis_id: Mapped[int] = mapped_column(
        ForeignKey("crises.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_crisis_slug_aliases_crisis_id", "crisis_id"),
    )

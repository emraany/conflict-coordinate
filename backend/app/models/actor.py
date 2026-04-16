from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.crisis import CrisisActor


class ActorType(str, enum.Enum):
    state = "state"
    non_state = "non_state"
    coalition = "coalition"
    other = "other"


class Actor(Base):
    __tablename__ = "actors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    type: Mapped[ActorType] = mapped_column(
        Enum(ActorType, name="actor_type"), default=ActorType.other
    )
    description: Mapped[str | None] = mapped_column(Text)
    wikipedia_url: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    crisis_links: Mapped[list[CrisisActor]] = relationship(
        back_populates="actor", cascade="all, delete-orphan"
    )

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.source import SourceType


class SourceBase(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=1000)
    publisher: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    source_type: SourceType = SourceType.news
    origin: str | None = None
    body_text: str | None = None


class SourceCreate(SourceBase):
    crisis_id: int | None = None


class SourceOut(SourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    crisis_id: int | None
    created_at: datetime

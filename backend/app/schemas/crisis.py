from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.crisis import ActorRole, CrisisStatus
from app.schemas.actor import ActorOut
from app.schemas.event import CrisisEventOut
from app.schemas.source import SourceOut


class CrisisStats(BaseModel):
    total_events: int
    total_fatalities: int
    event_type_counts: dict[str, int]
    first_event_at: datetime | None
    last_event_at: datetime | None


class CrisisBase(BaseModel):
    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=200)
    country: str | None = None
    region: str | None = None
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    summary: str | None = None
    status: CrisisStatus = CrisisStatus.active
    conflict_type: str | None = None
    started_at: datetime | None = None
    last_event_at: datetime | None = None


class CrisisCreate(CrisisBase):
    external_id: str | None = None
    source_name: str | None = None


class CrisisUpdate(BaseModel):
    name: str | None = None
    country: str | None = None
    region: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    summary: str | None = None
    status: CrisisStatus | None = None
    conflict_type: str | None = None
    started_at: datetime | None = None
    last_event_at: datetime | None = None


class CrisisListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    country: str | None
    lat: float
    lng: float
    status: CrisisStatus
    conflict_type: str | None


class ActorLinkCreate(BaseModel):
    actor_id: int
    role: ActorRole = ActorRole.party
    notes: str | None = None
    source_id: int | None = None


class ActorLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    actor: ActorOut
    role: ActorRole
    notes: str | None
    source_id: int | None


class CrisisDetail(CrisisBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str | None
    source_name: str | None
    created_at: datetime
    updated_at: datetime
    actors: list[ActorLinkOut]
    sources: list[SourceOut]
    events: list[CrisisEventOut]
    stats: CrisisStats

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.conflict import ConflictStatus
from app.models.crisis import ActorRole
from app.schemas.actor import ActorOut
from app.schemas.crisis import IntensityWeek
from app.schemas.event import CrisisEventOut
from app.schemas.source import SourceOut


class ConflictPartyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    actor: ActorOut
    role: ActorRole
    notes: str | None
    source_id: int | None


class ConflictStats(BaseModel):
    total_events: int
    total_fatalities: int
    event_type_counts: dict[str, int]
    first_event_at: datetime | None
    last_event_at: datetime | None
    recent_4w_events: int = 0
    recent_4w_fatalities: int = 0
    # Machine-coded GDELT reports routed here in the last 7 days — a
    # freshness signal, not incident records (GDELT rows carry no prose).
    gdelt_7d_reports: int = 0


class TopAdmin1(BaseModel):
    iso3: str
    admin1: str
    event_count: int


class ConflictListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    conflict_type: str | None
    status: ConflictStatus
    primary_iso3: str | None
    secondary_iso3s: list[str]
    lat: float | None
    lng: float | None
    started_at: datetime | None
    last_event_at: datetime | None
    intensity_4w_events: int
    intensity_4w_fatalities: int
    event_count: int
    total_fatalities: int


class ConflictDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    conflict_type: str | None
    status: ConflictStatus
    primary_iso3: str | None
    secondary_iso3s: list[str]
    lat: float | None
    lng: float | None
    started_at: datetime | None
    resolved_at: datetime | None
    last_event_at: datetime | None
    summary: str | None
    wikipedia_url: str | None
    ucdp_conflict_id: str | None
    parties: list[ConflictPartyOut]
    events: list[CrisisEventOut]
    sources: list[SourceOut]
    stats: ConflictStats
    intensity_52w: list[IntensityWeek]
    top_admin1s: list[TopAdmin1]
    created_at: datetime
    updated_at: datetime

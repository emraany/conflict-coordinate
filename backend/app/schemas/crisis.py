from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.crisis import ActorRole, CrisisStatus
from app.schemas.activity import ActivityType
from app.schemas.actor import ActorOut
from app.schemas.event import CrisisEventOut
from app.schemas.source import SourceOut


class CrisisStats(BaseModel):
    total_events: int
    total_fatalities: int
    event_type_counts: dict[str, int]
    first_event_at: datetime | None
    last_event_at: datetime | None
    # Recent-window aggregates from ACLED's weekly intensity table.
    recent_4w_events: int = 0
    recent_4w_fatalities: int = 0
    # Population exposure is admin1-population for any week with ≥1 event,
    # so MAX (not SUM) over weeks is the correct fold.
    recent_population_exposed: int | None = None
    # Machine-coded GDELT reports routed here in the last 7 days — a
    # freshness signal, not incident records (GDELT rows carry no prose).
    gdelt_7d_reports: int = 0


class IntensityWeek(BaseModel):
    week_start: date
    event_count_by_type: dict[str, int]
    fatalities: int
    population_exposure: int | None = None


class EntityAggregate(BaseModel):
    label: str
    text: str
    count: int
    event_ids: list[int]


class EntityGroup(BaseModel):
    label: str
    entities: list[EntityAggregate]


class CrisisEntities(BaseModel):
    crisis_id: int
    total_mentions: int
    groups: list[EntityGroup]


class GraphNode(BaseModel):
    id: str
    label: str
    mentions: int
    community: int
    centrality: float


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: int


class CrisisGraph(BaseModel):
    crisis_id: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    communities: list[list[str]]


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
    country_iso3: str | None = None
    admin1: str | None = None
    region: str | None
    lat: float
    lng: float
    status: CrisisStatus
    conflict_type: str | None
    started_at: datetime | None
    last_event_at: datetime | None
    event_count: int
    total_fatalities: int


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


class ConflictContext(BaseModel):
    """The named conflict this region belongs to, when the registry claims
    it. Absent for regions nobody has named — most criminal violence."""

    slug: str
    name: str
    summary: str | None
    conflict_type: str | None
    parties: list[ActorLinkOut]


class CrisisDetail(CrisisBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str | None
    source_name: str | None
    country_iso3: str | None = None
    admin1: str | None = None
    created_at: datetime
    updated_at: datetime
    actors: list[ActorLinkOut]
    sources: list[SourceOut]
    events: list[CrisisEventOut]
    stats: CrisisStats
    intensity_52w: list[IntensityWeek] = Field(default_factory=list)
    # Current activity rollup — the same figures that size and colour the dot.
    violence_4w_events: int = 0
    violence_4w_fatalities: int = 0
    violence_4w_pop_exposure: int | None = None
    latest_agg_week: date | None = None
    # What kind of violence was recorded, most frequent first.
    activity: list[ActivityType] = Field(default_factory=list)
    # Current narrative (ReliefWeb) and named-conflict context.
    field_reports: list[SourceOut] = Field(default_factory=list)
    conflict_context: ConflictContext | None = None

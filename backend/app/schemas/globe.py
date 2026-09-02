from datetime import date

from pydantic import BaseModel

from app.schemas.activity import ActivityType

__all__ = ["ActivityType", "ConflictLabel", "GlobeDot"]


class ConflictLabel(BaseModel):
    """The named conflict a region belongs to, when the registry claims it."""

    slug: str
    name: str


class GlobeDot(BaseModel):
    """One admin1 region with current violent activity.

    Counts are the trailing-4-week rollup of ACLED weekly aggregates ending
    at `latest_week` — real-time data, typically 1-2 weeks behind publication.
    """

    slug: str
    name: str
    country: str | None
    country_iso3: str | None
    admin1: str | None
    lat: float
    lng: float
    events_4w: int
    fatalities_4w: int
    population_exposure: int | None
    latest_week: date | None
    conflict: ConflictLabel | None
    # What kind of violence, and the derived evidence for that call.
    violence_class: str | None
    violence_class_basis: str | None
    # What kind of violence was recorded, most frequent first.
    activity: list[ActivityType]

from datetime import date

from pydantic import BaseModel


class ConflictLabel(BaseModel):
    """The named conflict a region belongs to, when the registry claims it."""

    slug: str
    name: str


class ActivityType(BaseModel):
    """One ACLED event category recorded in the region during the window.

    Categories are ACLED's own labels, used verbatim — the dot says what the
    source recorded, never a characterisation of our own.
    """

    type: str
    events: int
    fatalities: int


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
    # What kind of violence was recorded, most frequent first.
    activity: list[ActivityType]

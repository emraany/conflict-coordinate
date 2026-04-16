from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CrisisEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    crisis_id: int
    occurred_at: datetime
    event_type: str | None
    description: str | None
    fatalities: int | None
    location_name: str | None
    lat: float | None
    lng: float | None
    source_id: int | None
    created_at: datetime

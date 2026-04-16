from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.actor import ActorType


class ActorBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: ActorType = ActorType.other
    description: str | None = None
    wikipedia_url: str | None = None


class ActorCreate(ActorBase):
    pass


class ActorUpdate(BaseModel):
    name: str | None = None
    type: ActorType | None = None
    description: str | None = None
    wikipedia_url: str | None = None


class ActorOut(ActorBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    activity,
    actors,
    admin_conflicts,
    conflicts,
    crises,
    globe,
    health,
    ingest,
    sources,
)

app = FastAPI(
    title="The Conflict Coordinate API",
    version="0.1.0",
    description=(
        "Neutral, source-traceable index of active global conflicts. "
        "All claims visible to users are attributed to cited sources."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

app.include_router(crises.router)
app.include_router(conflicts.router)
app.include_router(globe.router)
app.include_router(admin_conflicts.router)
app.include_router(actors.router)
app.include_router(sources.router)
app.include_router(ingest.router)
app.include_router(activity.router)
app.include_router(health.router)


@app.on_event("startup")
def _start_scheduler() -> None:
    ingest.start_scheduler()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.rate_limit import limiter
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

# Applies DEFAULT_LIMIT to every route, admin ones included, rather than
# decorating endpoints one at a time — a new router should not be able to
# ship unthrottled by omission.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS is added *after* the limiter, which in Starlette means it wraps it.
# Keep that order: a 429 that skips CORS reaches the browser as an opaque
# network error, so the app would look broken rather than throttled.
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

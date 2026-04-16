from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import actors, crises, ingest, sources

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
app.include_router(actors.router)
app.include_router(sources.router)
app.include_router(ingest.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}

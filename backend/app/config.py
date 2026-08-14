from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+psycopg://conflict:conflict@localhost:5432/conflict"
    )
    admin_token: str = Field(default="change-me")
    cors_origins: str = Field(default="http://localhost:5173")
    acled_username: str = Field(default="")
    acled_password: str = Field(default="")
    acled_enabled: bool = Field(default=False)
    acled_lookback_days: int = Field(default=90)
    acled_crisis_event_threshold: int = Field(default=10)
    # Document-frequency threshold for keeping an actor on a crisis. 0.10 =
    # actor must appear in ≥ 10% of attached events for that admin1.
    acled_topic_actor_freq_threshold: float = Field(default=0.10)
    # Optional ISO date (YYYY-MM-DD) to use as "today" for ACLED queries.
    # Set this if the system clock doesn't match real-world date.
    acled_reference_date: str = Field(default="")
    # Wikipedia enrichment for actor descriptions during lagged-event attach.
    # Each unique actor triggers an anonymous Wikipedia API call; with ~5
    # actors per admin1 dot × 2800 dots = ~14k cold-cache lookups. Off by
    # default; flip on once for a backfill pass, then off.
    acled_lagged_wiki_enrich: bool = Field(default=False)
    gdelt_enabled: bool = Field(default=False)
    gdelt_lookback_minutes: int = Field(default=180)
    # ReliefWeb requires a pre-approved appname since Nov 2025 — request one
    # at https://apidoc.reliefweb.int/parameters#appname. If empty, SITREP
    # enrichment is skipped (Wikipedia background + actor descriptions still
    # run, so dossiers are still richer than the old count-only template).
    reliefweb_appname: str = Field(default="")
    ucdp_enabled: bool = Field(default=False)
    ucdp_token: str = Field(default="")
    ucdp_lookback_days: int = Field(default=730)
    ucdp_ged_version: str = Field(default="26.1")
    # Monthly GED candidate releases carrying events past the curated cutoff
    # (comma-separated version strings, e.g. "26.0.1,26.0.2"). Confirm each
    # exists via /gedevents/{v} before adding — unknown versions 404.
    ucdp_candidate_versions: str = Field(default="")
    # Active crises whose last_event_at is older than this many days are
    # demoted to `frozen` after each ingest run. 0 disables the sweep.
    status_stale_days: int = Field(default=90)
    # Emerging conflicts auto-promote to `active` after each ingest run if
    # their last-4-weeks event count reaches this threshold. 0 disables.
    conflict_auto_promotion_events_4w: int = Field(default=10)
    # Active conflicts with no event in this many days are demoted to
    # `frozen`. Tighter than crisis stale (admin1 cells can lull but the
    # parent conflict shouldn't). 0 disables.
    conflict_stale_days: int = Field(default=60)
    # In-server daily scheduler — HH:MM in 24h UTC. Disabled by default:
    # scheduled ingestion should run as a standalone worker
    # (`uv run python -m app.ingestion.runner` via cron/launchd) so long
    # runs survive server restarts/reloads. Manual /api/ingest/run remains.
    ingest_schedule_time: str = Field(default="")
    # Set true on any deployed environment. Turns the permissive local
    # defaults below into startup errors rather than silent security holes.
    production: bool = Field(default=False)

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def _normalize_db_driver(cls, v: str) -> str:
        # Hosted Postgres (Railway, Heroku, Render) injects a bare
        # `postgresql://` URL. SQLAlchemy resolves that to psycopg2, which
        # isn't a dependency — the app would die at import with a driver
        # error that reads like a network problem.
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+psycopg://", 1)
        return v

    @model_validator(mode="after")
    def _check_production_safety(self) -> Settings:
        if self.production and self.admin_token == "change-me":
            raise ValueError(
                "ADMIN_TOKEN is still the default while PRODUCTION=true. "
                "It guards every write endpoint; set it to a random secret."
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

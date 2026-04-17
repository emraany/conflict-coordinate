from functools import lru_cache
from pathlib import Path

from pydantic import Field
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
    # DBSCAN geographic clustering radius (kilometers). Events within this
    # distance of each other are treated as one conflict cluster.
    acled_cluster_eps_km: float = Field(default=100.0)
    # Minimum events for a cluster core point (DBSCAN min_samples).
    acled_cluster_min_samples: int = Field(default=3)
    # Optional ISO date (YYYY-MM-DD) to use as "today" for ACLED queries.
    # Set this if the system clock doesn't match real-world date.
    acled_reference_date: str = Field(default="")
    gdelt_enabled: bool = Field(default=False)
    gdelt_attach_radius_km: int = Field(default=300)
    gdelt_lookback_minutes: int = Field(default=180)
    # ReliefWeb requires a pre-approved appname since Nov 2025 — request one
    # at https://apidoc.reliefweb.int/parameters#appname. If empty, SITREP
    # enrichment is skipped (Wikipedia background + actor descriptions still
    # run, so dossiers are still richer than the old count-only template).
    reliefweb_appname: str = Field(default="")

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

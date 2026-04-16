"""ACLED ingestion source — STUB.

Not enabled in v1. Requires ACLED OAuth credentials (see .env).
The shape of `fetch()` matches `IngestionSource`; wiring this up later is a
self-contained change: implement the OAuth token exchange, call
`GET https://acleddata.com/api/acled/read`, and map event rows onto
`CrisisRecord` (aggregating events into a per-location or per-actor-pair
record, depending on how we want the globe markers to granularly reflect
ACLED's event-level data).
"""

from __future__ import annotations

from app.config import settings
from app.ingestion.base import CrisisRecord, IngestionSource

ACLED_READ_URL = "https://acleddata.com/api/acled/read"
ACLED_OAUTH_URL = "https://acleddata.com/oauth/token"


class ACLEDSource(IngestionSource):
    name = "acled"

    def fetch(self) -> list[CrisisRecord]:
        if not settings.acled_username or not settings.acled_password:
            # Credentials not provided — stub returns empty so runner skips silently.
            return []
        # TODO: implement OAuth token fetch (POST to ACLED_OAUTH_URL with
        # username, password, client_id="acled") and ACLED read with filters
        # (event_date_range, limit, etc.). Map events -> CrisisRecord.
        raise NotImplementedError("ACLED ingestion not yet implemented")

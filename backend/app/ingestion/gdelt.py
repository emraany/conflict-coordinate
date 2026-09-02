"""GDELT 2.0 supplementary event stream — attach via admin1 PIP.

Fetches the most recent GDELT Events exports (15-min cadence), filters to
violent conflict categories (CAMEO EventRootCode 18, 19, 20), and attaches
each event to the crisis whose admin1 polygon contains the event's lat/lng.
Never creates crises — GDELT extraction is too noisy.

We do NOT create Actor rows from GDELT data. Persisted rows:
  - `CrisisEvent` (external_id = `gdelt:{GLOBALEVENTID}`)
  - `Source` (one per SOURCEURL, origin='gdelt')

Admin1 attach precondition: `admin1_polygons` must be populated. Run
`app.scripts.load_admin1_polygons` once before enabling GDELT in production.
If the table is empty, GDELT logs a warning and skips all events.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from datetime import UTC, datetime

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.conflicts.routing import route_event
from app.ingestion.acled import _bump_conflicts_last_event
from app.ingestion.base import CrisisRecord, IngestionSource
from app.models import Crisis, Source, SourceType
from app.models.event import CrisisEvent

logger = logging.getLogger(__name__)

GDELT_LASTUPDATE_URL = "https://data.gdeltproject.org/gdeltv2/lastupdate.txt"

GDELT_COLUMNS = [
    "GLOBALEVENTID",
    "SQLDATE",
    "MonthYear",
    "Year",
    "FractionDate",
    "Actor1Code",
    "Actor1Name",
    "Actor1CountryCode",
    "Actor1KnownGroupCode",
    "Actor1EthnicCode",
    "Actor1Religion1Code",
    "Actor1Religion2Code",
    "Actor1Type1Code",
    "Actor1Type2Code",
    "Actor1Type3Code",
    "Actor2Code",
    "Actor2Name",
    "Actor2CountryCode",
    "Actor2KnownGroupCode",
    "Actor2EthnicCode",
    "Actor2Religion1Code",
    "Actor2Religion2Code",
    "Actor2Type1Code",
    "Actor2Type2Code",
    "Actor2Type3Code",
    "IsRootEvent",
    "EventCode",
    "EventBaseCode",
    "EventRootCode",
    "QuadClass",
    "GoldsteinScale",
    "NumMentions",
    "NumSources",
    "NumArticles",
    "AvgTone",
    "Actor1Geo_Type",
    "Actor1Geo_Fullname",
    "Actor1Geo_CountryCode",
    "Actor1Geo_ADM1Code",
    "Actor1Geo_ADM2Code",
    "Actor1Geo_Lat",
    "Actor1Geo_Long",
    "Actor1Geo_FeatureID",
    "Actor2Geo_Type",
    "Actor2Geo_Fullname",
    "Actor2Geo_CountryCode",
    "Actor2Geo_ADM1Code",
    "Actor2Geo_ADM2Code",
    "Actor2Geo_Lat",
    "Actor2Geo_Long",
    "Actor2Geo_FeatureID",
    "ActionGeo_Type",
    "ActionGeo_Fullname",
    "ActionGeo_CountryCode",
    "ActionGeo_ADM1Code",
    "ActionGeo_ADM2Code",
    "ActionGeo_Lat",
    "ActionGeo_Long",
    "ActionGeo_FeatureID",
    "DATEADDED",
    "SOURCEURL",
]

VIOLENT_ROOT_CODES = {"18", "19", "20"}

EVENT_ROOT_LABEL = {
    "18": "assault",
    "19": "fight",
    "20": "use_of_unconventional_mass_violence",
}

# Refuse to attach a violent GDELT event to a topically-incompatible crisis.
_INCOMPATIBLE: frozenset[tuple[str, str]] = frozenset(
    {
        ("19", "civil_unrest"),
        ("20", "civil_unrest"),
        ("18", "strategic_developments"),
        ("19", "strategic_developments"),
        ("20", "strategic_developments"),
    }
)


def _latest_export_urls() -> list[str]:
    """Return up to N most-recent export CSV.zip URLs (15-min cadence each)."""
    n = max(1, settings.gdelt_lookback_minutes // 15)
    resp = httpx.get(GDELT_LASTUPDATE_URL, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    line = resp.text.strip().splitlines()[0]
    url = line.split()[-1]
    urls = [url]
    m = re.search(r"(\d{14})\.export\.CSV\.zip", url)
    if not m:
        return urls
    from datetime import datetime as _dt

    stamp = _dt.strptime(m.group(1), "%Y%m%d%H%M%S")
    for i in range(1, n):
        t = stamp.timestamp() - i * 15 * 60
        prev = _dt.utcfromtimestamp(t)
        minute = (prev.minute // 15) * 15
        prev = prev.replace(minute=minute, second=0, microsecond=0)
        urls.append(
            "https://data.gdeltproject.org/gdeltv2/"
            + prev.strftime("%Y%m%d%H%M%S")
            + ".export.CSV.zip"
        )
    return urls


def _fetch_events_csv(url: str) -> list[dict]:
    try:
        resp = httpx.get(url, timeout=60.0, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError:
        return []
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            name = zf.namelist()[0]
            raw = zf.read(name).decode("utf-8", errors="replace")
    except zipfile.BadZipFile:
        return []
    reader = csv.reader(io.StringIO(raw), delimiter="\t")
    out: list[dict] = []
    for row in reader:
        if len(row) < len(GDELT_COLUMNS):
            continue
        d = dict(zip(GDELT_COLUMNS, row))
        if d.get("EventRootCode") not in VIOLENT_ROOT_CODES:
            continue
        if not d.get("ActionGeo_Lat") or not d.get("ActionGeo_Long"):
            continue
        out.append(d)
    return out


_ISO2_TO_ISO3_CACHE: dict[str, str] = {}


def _iso2_to_iso3(iso2: str) -> str | None:
    if not iso2:
        return None
    if iso2 in _ISO2_TO_ISO3_CACHE:
        return _ISO2_TO_ISO3_CACHE[iso2]
    import pycountry

    try:
        c = pycountry.countries.get(alpha_2=iso2)
    except LookupError:
        c = None
    iso3 = getattr(c, "alpha_3", None) if c else None
    if iso3:
        _ISO2_TO_ISO3_CACHE[iso2] = iso3
    return iso3


def _polygon_count(db: Session) -> int:
    return int(db.execute(text("SELECT count(*) FROM admin1_polygons")).scalar() or 0)


def _resolve_via_pip(
    db: Session, country_iso3: str, lat: float, lng: float
) -> str | None:
    stmt = text(
        """
        SELECT admin1_norm
        FROM admin1_polygons
        WHERE country_iso3 = :iso3
          AND ST_Contains(geom, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326))
        LIMIT 1
        """
    )
    row = db.execute(stmt, {"iso3": country_iso3, "lat": lat, "lng": lng}).first()
    return str(row[0]) if row else None


def _title_from_url(url: str) -> str:
    """Readable title from the article URL slug — GDELT exports carry no
    headline, so the slug is the best human-readable label available."""
    from urllib.parse import urlparse

    path = urlparse(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1]
    slug = re.sub(r"\.(html?|php|aspx?)$", "", slug, flags=re.IGNORECASE)
    words = re.sub(r"[-_+]+", " ", slug).strip()
    # Drop pure-id slugs (numbers/hex) — fall back to the domain.
    if len(re.sub(r"[0-9\s]", "", words)) < 8:
        return _domain_of(url) or "GDELT-cited article"
    return words[:460]


def _domain_of(url: str) -> str | None:
    from urllib.parse import urlparse

    netloc = urlparse(url).netloc
    return netloc.removeprefix("www.") or None


def _upsert_source(
    db: Session, crisis_id: int, url: str, published_at: datetime | None
) -> Source:
    existing = db.scalar(
        select(Source).where(
            Source.crisis_id == crisis_id,
            Source.url == url,
            Source.origin == "gdelt",
        )
    )
    if existing is not None:
        if existing.published_at is None and published_at is not None:
            existing.published_at = published_at
        return existing
    src = Source(
        crisis_id=crisis_id,
        title=_title_from_url(url),
        url=url,
        publisher=_domain_of(url),
        published_at=published_at,
        retrieved_at=datetime.now(UTC),
        source_type=SourceType.news,
        origin="gdelt",
    )
    db.add(src)
    db.flush()
    return src


class GDELTSource(IngestionSource):
    name = "gdelt"
    attach_only = True

    def fetch(self) -> list[CrisisRecord]:
        return []

    def attach_events(self, db: Session, routing_idx=None) -> dict:  # noqa: C901
        if not settings.gdelt_enabled:
            return {"attached": 0, "skipped": 0}

        if _polygon_count(db) == 0:
            logger.warning(
                "gdelt: admin1_polygons empty — run "
                "`uv run python -m app.scripts.load_admin1_polygons` "
                "before enabling GDELT. Skipping."
            )
            return {"attached": 0, "skipped": 0}

        # Bulk-load (iso3, admin1_norm) → crisis_id mapping.
        crisis_index = {
            (iso3, admin1): cid
            for iso3, admin1, cid in db.execute(
                select(Crisis.country_iso3, Crisis.admin1_norm, Crisis.id).where(
                    Crisis.country_iso3.is_not(None),
                    Crisis.admin1_norm.is_not(None),
                )
            ).all()
        }

        attached = 0
        skipped = 0
        skipped_no_pip = 0
        skipped_no_crisis = 0
        skipped_incompatible = 0
        seen_ids: set[str] = set()
        conflict_latest: dict[int, datetime] = {}

        for url in _latest_export_urls():
            for ev in _fetch_events_csv(url):
                gid = ev["GLOBALEVENTID"]
                if gid in seen_ids:
                    continue
                seen_ids.add(gid)
                ext_id = f"gdelt:{gid}"

                already = db.scalar(
                    select(CrisisEvent.id).where(CrisisEvent.external_id == ext_id)
                )
                if already is not None:
                    skipped += 1
                    continue

                try:
                    lat = float(ev["ActionGeo_Lat"])
                    lng = float(ev["ActionGeo_Long"])
                except ValueError:
                    skipped += 1
                    continue

                country_iso2 = (ev.get("ActionGeo_CountryCode") or "").strip().upper()
                iso3 = _iso2_to_iso3(country_iso2)
                if not iso3:
                    skipped += 1
                    continue

                admin1_norm = _resolve_via_pip(db, iso3, lat, lng)
                if not admin1_norm:
                    skipped_no_pip += 1
                    skipped += 1
                    continue
                crisis_id = crisis_index.get((iso3, admin1_norm))
                if crisis_id is None:
                    skipped_no_crisis += 1
                    skipped += 1
                    continue

                crisis = db.get(Crisis, crisis_id)
                if crisis is None:
                    skipped += 1
                    continue
                ctype = crisis.conflict_type or ""
                if (ev["EventRootCode"], ctype) in _INCOMPATIBLE:
                    skipped_incompatible += 1
                    skipped += 1
                    continue

                try:
                    occurred = datetime.strptime(
                        ev["SQLDATE"], "%Y%m%d"
                    ).replace(tzinfo=UTC)
                except ValueError:
                    occurred = datetime.now(UTC)

                source_url = (ev.get("SOURCEURL") or "").strip()
                source_row = None
                if source_url:
                    source_row = _upsert_source(
                        db, crisis_id, source_url, published_at=occurred
                    )

                conflict_id = None
                if routing_idx is not None:
                    conflict_id = route_event(
                        [
                            (ev.get("Actor1Name") or "").strip(),
                            (ev.get("Actor2Name") or "").strip(),
                        ],
                        iso3,
                        admin1_norm,
                        routing_idx,
                    )

                db.add(
                    CrisisEvent(
                        crisis_id=crisis_id,
                        occurred_at=occurred,
                        event_type=EVENT_ROOT_LABEL.get(
                            ev["EventRootCode"], "violence"
                        ),
                        description=None,
                        location_name=ev.get("ActionGeo_Fullname") or None,
                        lat=lat,
                        lng=lng,
                        external_id=ext_id,
                        source_id=source_row.id if source_row else None,
                        conflict_id=conflict_id,
                    )
                )
                attached += 1
                if conflict_id is not None:
                    prev_c = conflict_latest.get(conflict_id)
                    if prev_c is None or occurred > prev_c:
                        conflict_latest[conflict_id] = occurred

        _bump_conflicts_last_event(db, conflict_latest)
        db.flush()
        logger.info(
            "gdelt: attached=%d skipped=%d (no_pip=%d no_crisis=%d "
            "incompatible=%d)",
            attached,
            skipped,
            skipped_no_pip,
            skipped_no_crisis,
            skipped_incompatible,
        )
        return {"attached": attached, "skipped": skipped}

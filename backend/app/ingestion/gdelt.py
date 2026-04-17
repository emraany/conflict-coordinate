"""GDELT 2.0 supplementary event stream.

Fetches the most recent GDELT Events exports (15-min cadence), filters to
violent conflict categories (CAMEO EventRootCode 18, 19, 20), and attaches
each event to the nearest existing crisis within a configurable radius via
PostGIS ST_DWithin. Never creates standalone crises — GDELT's automated
news extraction is too noisy to be trusted as a primary source of record.

We do NOT create Actor rows from GDELT data. The actor-extraction layer in
GDELT produces frequent misclassifications, and letting them into the
actor graph would poison our neutrality rules. We only persist:
  - `CrisisEvent` rows (external_id = `gdelt:{GLOBALEVENTID}`)
  - `Source` rows (one per SOURCEURL, origin='gdelt')
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion.base import CrisisRecord, IngestionSource
from app.models import Source, SourceType
from app.models.event import CrisisEvent

GDELT_LASTUPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"

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


def _latest_export_urls() -> list[str]:
    """Return up to N most-recent export CSV.zip URLs (15-min cadence each)."""
    n = max(1, settings.gdelt_lookback_minutes // 15)
    resp = httpx.get(GDELT_LASTUPDATE_URL, timeout=30.0)
    resp.raise_for_status()
    # lastupdate.txt has three lines; the first is the 15-min export CSV.
    line = resp.text.strip().splitlines()[0]
    # Line format: "<size> <md5> <url>"
    url = line.split()[-1]
    urls = [url]
    # Walk back: URLs are timestamped; easier to just rely on lastupdate.txt
    # and fetch older files by name derived from the latest timestamp.
    m = re.search(r"(\d{14})\.export\.CSV\.zip", url)
    if not m:
        return urls
    from datetime import datetime as _dt

    stamp = _dt.strptime(m.group(1), "%Y%m%d%H%M%S")
    for i in range(1, n):
        t = stamp.timestamp() - i * 15 * 60
        prev = _dt.utcfromtimestamp(t)
        # Round to 15-min boundary.
        minute = (prev.minute // 15) * 15
        prev = prev.replace(minute=minute, second=0, microsecond=0)
        urls.append(
            "http://data.gdeltproject.org/gdeltv2/"
            + prev.strftime("%Y%m%d%H%M%S")
            + ".export.CSV.zip"
        )
    return urls


def _fetch_events_csv(url: str) -> list[dict]:
    try:
        resp = httpx.get(url, timeout=60.0)
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


def _find_nearest_crisis(
    db: Session, lat: float, lng: float, radius_km: int
) -> int | None:
    stmt = text(
        """
        SELECT id
        FROM crises
        WHERE geom IS NOT NULL
          AND ST_DWithin(
            geom::geography,
            ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
            :radius_m
          )
        ORDER BY geom::geography <-> ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
        LIMIT 1
        """
    )
    row = db.execute(
        stmt, {"lat": lat, "lng": lng, "radius_m": radius_km * 1000}
    ).first()
    return row[0] if row else None


def _upsert_source(db: Session, crisis_id: int, url: str) -> Source:
    existing = db.scalar(
        select(Source).where(
            Source.crisis_id == crisis_id,
            Source.url == url,
            Source.origin == "gdelt",
        )
    )
    if existing is not None:
        return existing
    src = Source(
        crisis_id=crisis_id,
        title=f"GDELT-cited article: {url[:120]}",
        url=url,
        publisher="GDELT",
        retrieved_at=datetime.now(timezone.utc),
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
        # attach_only source — never creates crises.
        return []

    def attach_events(self, db: Session) -> dict:
        if not settings.gdelt_enabled:
            return {"attached": 0, "skipped": 0}

        attached = 0
        skipped = 0
        seen_ids: set[str] = set()

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

                crisis_id = _find_nearest_crisis(
                    db, lat, lng, settings.gdelt_attach_radius_km
                )
                if crisis_id is None:
                    skipped += 1
                    continue

                source_url = (ev.get("SOURCEURL") or "").strip()
                source_row = None
                if source_url:
                    source_row = _upsert_source(db, crisis_id, source_url)

                try:
                    occurred = datetime.strptime(
                        ev["SQLDATE"], "%Y%m%d"
                    ).replace(tzinfo=timezone.utc)
                except ValueError:
                    occurred = datetime.now(timezone.utc)

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
                    )
                )
                attached += 1

        db.flush()
        return {"attached": attached, "skipped": skipped}

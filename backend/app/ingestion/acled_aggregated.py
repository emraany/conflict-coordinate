"""ACLED aggregated source — real-time backbone for crisis identity.

ACLED Researcher tier publishes weekly aggregated xlsx files per region
(country × admin1 × event_type × week). This source scrapes the regional
landing pages, downloads the latest xlsx with the shared OAuth bearer token,
and emits one `CrisisRecord` per (country_iso3, admin1_norm) cell with
recent activity.

Identity is `(country_iso3, admin1_norm)` — stable across runs, immune to
DBSCAN cluster drift. Display location is the ACLED-published admin1
centroid (the lagged event source updates it later from real event points).

This source does NOT own actors / events / sources — those come from the
ACLED lagged event API, UCDP, and GDELT. It owns identity + weekly
intensity, period.

URL pattern (latest, scraped each run):
  https://acleddata.com/aggregated/aggregated-data-{region-slug}
   → contains a link to
  https://acleddata.com/system/files/YYYY-MM/{Region}_aggregated_data_up_to_week_of-YYYY-MM-DD.xlsx

Schema columns (validated each run; drift falls back to last-good cache):
  WEEK, REGION, COUNTRY, ADMIN1, EVENT_TYPE, SUB_EVENT_TYPE, EVENTS,
  FATALITIES, POPULATION_EXPOSURE, DISORDER_TYPE, ID, CENTROID_LATITUDE,
  CENTROID_LONGITUDE
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import mean

import httpx
import openpyxl
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion.acled_auth import CACHE_DIR, get_token
from app.ingestion.base import (
    CrisisRecord,
    IngestionSource,
    IntensityRow,
    SourceRef,
)
from app.ingestion.countries import country_iso3 as _country_iso3
from app.models import Admin1Alias, Crisis

logger = logging.getLogger(__name__)


REGIONS: tuple[str, ...] = (
    "africa",
    "asia-pacific",
    "europe-and-central-asia",
    "latin-america-caribbean",
    "middle-east",
    "united-states-canada",
)

LANDING_BASE = "https://acleddata.com/aggregated/aggregated-data-"
EXPECTED_COLUMNS: tuple[str, ...] = (
    "WEEK",
    "REGION",
    "COUNTRY",
    "ADMIN1",
    "EVENT_TYPE",
    "SUB_EVENT_TYPE",
    "EVENTS",
    "FATALITIES",
    "POPULATION_EXPOSURE",
    "DISORDER_TYPE",
    "ID",
    "CENTROID_LATITUDE",
    "CENTROID_LONGITUDE",
)

# Active = at least one event in any of these weeks (relative to reference week).
ACTIVE_WINDOW_WEEKS = 4
# Crises with no activity in this many weeks are dropped from the globe.
RETAIN_WINDOW_WEEKS = 52

# ACLED's landing pages 403 anything that looks like a bot UA, but the xlsx
# files are gated by bearer token regardless of UA. Use a generic browser UA
# for the scrape.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


@dataclass
class _RegionFile:
    region: str
    url: str
    xlsx_path: Path
    etag: str | None
    last_modified: str | None


def _agg_cache_dir() -> Path:
    p = CACHE_DIR / "acled_aggregated"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_meta_path(region: str) -> Path:
    return _agg_cache_dir() / f"{region}.meta.json"


def _cache_xlsx_path(region: str) -> Path:
    return _agg_cache_dir() / f"{region}.xlsx"


def _load_meta(region: str) -> dict:
    p = _cache_meta_path(region)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (ValueError, OSError):
        return {}


def _save_meta(region: str, meta: dict) -> None:
    _cache_meta_path(region).write_text(json.dumps(meta))


def _normalize_admin1(value: str) -> str:
    """ASCII-fold + lowercase + strip common admin1 suffixes for stable
    cross-source matching."""
    s = unicodedata.normalize("NFKD", value or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^the\s+", "", s)
    s = re.sub(
        r"\s+("
        r"governorate|province|state|region|prefecture|district|wilayat|"
        r"muhafazah|oblast|raion|voivodeship|canton|department|county|"
        r"municipality|federal subject|federal district|territory"
        r")$",
        "",
        s,
    )
    return s


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:120] or "unknown"


def _discover_region_xlsx_url(
    client: httpx.Client, region: str, bearer: str
) -> str | None:
    """Scrape the regional landing page for the latest xlsx URL.

    The landing pages are gated behind a myACLED login — anonymous requests
    get a 403 page even though the URL looks public. Send the bearer token.
    """
    url = LANDING_BASE + region
    headers = {"Authorization": f"Bearer {bearer}"}
    resp = client.get(url, headers=headers, timeout=30.0, follow_redirects=True)
    if resp.status_code != 200:
        logger.warning("acled-agg: landing %s returned %d", region, resp.status_code)
        return None
    # Match the system/files/<YYYY-MM>/<Region>_aggregated_data_..._YYYY-MM-DD.xlsx pattern.
    m = re.search(
        r'https://acleddata\.com/system/files/\d{4}-\d{2}/[^"\s]+_aggregated_data_up_to_week_of-\d{4}-\d{2}-\d{2}\.xlsx',
        resp.text,
    )
    return m.group(0) if m else None


def _download_with_etag(
    client: httpx.Client, url: str, region: str, bearer: str
) -> _RegionFile | None:
    """Download the region xlsx if changed; otherwise reuse cached copy."""
    meta = _load_meta(region)
    headers = {
        "Authorization": f"Bearer {bearer}",
        "User-Agent": USER_AGENT,
    }
    if meta.get("etag"):
        headers["If-None-Match"] = meta["etag"]
    if meta.get("last_modified"):
        headers["If-Modified-Since"] = meta["last_modified"]
    xlsx_path = _cache_xlsx_path(region)

    # If URL changed since last run, force a fresh fetch.
    url_changed = meta.get("url") != url

    if not url_changed and xlsx_path.exists() and (meta.get("etag") or meta.get("last_modified")):
        # Conditional GET — saves ~6 MB per region per run when nothing changed.
        resp = client.get(url, headers=headers, timeout=120.0, follow_redirects=True)
        if resp.status_code == 304:
            return _RegionFile(
                region=region,
                url=url,
                xlsx_path=xlsx_path,
                etag=meta.get("etag"),
                last_modified=meta.get("last_modified"),
            )
        if resp.status_code != 200:
            logger.warning("acled-agg: %s GET returned %d", region, resp.status_code)
            return None
        new_bytes = resp.content
    else:
        resp = client.get(url, headers=headers, timeout=120.0, follow_redirects=True)
        if resp.status_code != 200:
            logger.warning("acled-agg: %s GET returned %d", region, resp.status_code)
            return None
        new_bytes = resp.content

    # Persist xlsx + meta.
    xlsx_path.write_bytes(new_bytes)
    new_meta = {
        "url": url,
        "etag": resp.headers.get("ETag"),
        "last_modified": resp.headers.get("Last-Modified"),
        "sha256": hashlib.sha256(new_bytes).hexdigest(),
        "downloaded_at": datetime.now(UTC).isoformat(),
    }
    _save_meta(region, new_meta)
    return _RegionFile(
        region=region,
        url=url,
        xlsx_path=xlsx_path,
        etag=new_meta["etag"],
        last_modified=new_meta["last_modified"],
    )


def _iter_xlsx_rows(path: Path) -> tuple[list[str], list[tuple]]:
    """Read the xlsx and return (header, rows). Tolerates the broken
    `dimension` metadata ACLED's exporter emits by calling reset_dimensions."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    ws.reset_dimensions()
    header: list[str] = []
    rows: list[tuple] = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            header = [str(v) if v is not None else "" for v in row]
            continue
        rows.append(row)
    wb.close()
    return header, rows


def _validate_schema(header: list[str], region: str) -> bool:
    if header[: len(EXPECTED_COLUMNS)] != list(EXPECTED_COLUMNS):
        logger.error(
            "acled-agg: %s schema drift; expected %s, got %s",
            region,
            EXPECTED_COLUMNS,
            tuple(header),
        )
        return False
    return True


def _parse_int(v: object) -> int:
    if v is None or v == "":
        return 0
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _parse_float(v: object) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _to_date(v: object) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v[:10]).date()
        except ValueError:
            return None
    return None


def _reference_today() -> date:
    """The 'today' anchor for activity windows. Honors ACLED_REFERENCE_DATE
    so backtests work; otherwise UTC now."""
    if settings.acled_reference_date:
        try:
            return date.fromisoformat(settings.acled_reference_date)
        except ValueError:
            pass
    return datetime.now(UTC).date()


@dataclass
class _AdminCell:
    """Accumulator for one (country_iso3, admin1_norm) admin1 across weeks."""

    country: str
    country_iso3: str
    region: str
    admin1: str
    admin1_norm: str
    centroid_lats: list[float]
    centroid_lngs: list[float]
    intensity: dict[tuple[date, str], IntensityRow]
    last_week: date | None
    earliest_week: date | None


def _aggregate_rows(
    header: list[str], rows: list[tuple]
) -> dict[tuple[str, str], _AdminCell]:
    """Roll xlsx rows into per-(iso3, admin1_norm) cells."""
    idx = {col: i for i, col in enumerate(header)}
    cells: dict[tuple[str, str], _AdminCell] = {}
    for row in rows:
        try:
            week = _to_date(row[idx["WEEK"]])
            country = (row[idx["COUNTRY"]] or "").strip()
            admin1 = (row[idx["ADMIN1"]] or "").strip()
            event_type = (row[idx["EVENT_TYPE"]] or "").strip()
        except (IndexError, KeyError):
            continue
        if not (week and country and admin1 and event_type):
            continue
        iso3 = _country_iso3(country)
        if not iso3:
            continue
        admin1_norm = _normalize_admin1(admin1)
        key = (iso3, admin1_norm)
        cell = cells.get(key)
        if cell is None:
            cell = _AdminCell(
                country=country,
                country_iso3=iso3,
                region=(row[idx["REGION"]] or "").strip() or "",
                admin1=admin1,
                admin1_norm=admin1_norm,
                centroid_lats=[],
                centroid_lngs=[],
                intensity={},
                last_week=week,
                earliest_week=week,
            )
            cells[key] = cell
        cell.last_week = max(cell.last_week or week, week)
        cell.earliest_week = min(cell.earliest_week or week, week)

        lat = _parse_float(row[idx["CENTROID_LATITUDE"]])
        lng = _parse_float(row[idx["CENTROID_LONGITUDE"]])
        if lat is not None and lng is not None:
            cell.centroid_lats.append(lat)
            cell.centroid_lngs.append(lng)

        events = _parse_int(row[idx["EVENTS"]])
        fatalities = _parse_int(row[idx["FATALITIES"]])
        exposure_raw = row[idx["POPULATION_EXPOSURE"]]
        exposure = _parse_int(exposure_raw) if exposure_raw not in (None, "") else None

        agg_key = (week, event_type)
        existing = cell.intensity.get(agg_key)
        if existing is None:
            cell.intensity[agg_key] = IntensityRow(
                week_start=week,
                event_type=event_type,
                event_count=events,
                fatalities=fatalities,
                # Population exposure is admin1-population for any week with
                # ≥1 event — same value within a week regardless of event_type
                # split, so MAX (== value) is the right fold.
                population_exposure=exposure,
            )
        else:
            existing.event_count += events
            existing.fatalities += fatalities
            if exposure is not None:
                existing.population_exposure = max(
                    existing.population_exposure or 0, exposure
                )
    return cells


def _build_record(cell: _AdminCell, ref_today: date) -> CrisisRecord | None:
    if not cell.intensity:
        return None
    intensity_rows = sorted(
        cell.intensity.values(), key=lambda r: (r.week_start, r.event_type)
    )
    weeks_with_events = sorted({r.week_start for r in intensity_rows if r.event_count > 0})
    if not weeks_with_events:
        return None
    latest = max(weeks_with_events)
    # Drop entirely if no activity in the retain window.
    drop_cutoff = ref_today - timedelta(weeks=RETAIN_WINDOW_WEEKS)
    if latest < drop_cutoff:
        return None
    active_cutoff = ref_today - timedelta(weeks=ACTIVE_WINDOW_WEEKS)
    status = "active" if latest >= active_cutoff else "frozen"

    # Display centroid: mean of all observed admin1 centroids in the file.
    if cell.centroid_lats and cell.centroid_lngs:
        lat = float(mean(cell.centroid_lats))
        lng = float(mean(cell.centroid_lngs))
    else:
        return None

    # Dominant event_type across the active window for the conflict_type.
    by_type_recent: dict[str, int] = defaultdict(int)
    for r in intensity_rows:
        if r.week_start >= active_cutoff:
            by_type_recent[r.event_type] += r.event_count
    if not by_type_recent:
        # No active-window activity — use full-window dominance.
        for r in intensity_rows:
            by_type_recent[r.event_type] += r.event_count
    dominant_type = max(by_type_recent.items(), key=lambda kv: kv[1])[0]
    conflict_type = _CONFLICT_TYPE_FROM_EVENT.get(dominant_type, "armed_conflict")

    name = f"{cell.admin1}, {cell.country}"
    slug = _slugify(f"{cell.country}-{cell.admin1}")
    external_id = f"acled-agg:{cell.country_iso3}:{cell.admin1_norm}"

    started = datetime.combine(
        cell.earliest_week or weeks_with_events[0], datetime.min.time(), tzinfo=UTC
    )
    last_event_at = datetime.combine(latest, datetime.min.time(), tzinfo=UTC)

    summary = (
        f"{cell.admin1}, {cell.country} — admin1-level activity per ACLED weekly "
        f"aggregates. Latest recorded week: {latest.isoformat()}."
    )

    sources = [
        SourceRef(
            title="ACLED — Armed Conflict Location & Event Data (aggregated)",
            url="https://acleddata.com/conflict-data/download-data-files/aggregated-data",
            publisher="ACLED",
            source_type="primary",
        )
    ]

    return CrisisRecord(
        external_id=external_id,
        slug=slug,
        name=name,
        country=cell.country,
        region=cell.region or None,
        lat=lat,
        lng=lng,
        summary=summary,
        status=status,
        conflict_type=conflict_type,
        country_iso3=cell.country_iso3,
        admin1=cell.admin1,
        admin1_norm=cell.admin1_norm,
        started_at=started,
        last_event_at=last_event_at,
        intensity_last_week_at=last_event_at,
        actors=[],
        sources=sources,
        events=[],
        intensity_rows=intensity_rows,
    )


_CONFLICT_TYPE_FROM_EVENT = {
    "Battles": "armed_clashes",
    "Violence against civilians": "one_sided_violence",
    "Explosions/Remote violence": "explosions_remote_violence",
    "Riots": "civil_unrest",
    "Protests": "civil_unrest",
    "Strategic developments": "strategic_developments",
}


def _ensure_alias(db: Session, country_iso3: str, admin1: str, admin1_norm: str) -> None:
    """Self-populate admin1_aliases with each canonical admin1 we see, so that
    UCDP/GDELT sources can resolve their spelling variants against the same
    target. Idempotent."""
    existing = db.scalar(
        select(Admin1Alias).where(
            Admin1Alias.country_iso3 == country_iso3,
            Admin1Alias.alias_norm == admin1_norm,
        )
    )
    if existing is not None:
        return
    db.add(
        Admin1Alias(
            country_iso3=country_iso3,
            alias_norm=admin1_norm,
            canonical_admin1_norm=admin1_norm,
            canonical_admin1=admin1,
        )
    )


class ACLEDAggregatedSource(IngestionSource):
    name = "acled-agg"
    attach_only = False
    # Identity-only: aggregated source decides which dots exist, but never
    # owns actor/event/source content. Lagged events + UCDP + GDELT do.
    owns_actors = False
    owns_events = False
    # We emit a single canonical ACLED citation; it'd be nice to scope sources
    # by origin. Today the runner replaces ALL sources when owns_sources=True,
    # which would wipe lagged-source citations. Set False; the lagged source
    # (re)inserts the ACLED citation as part of its event sourcing.
    owns_sources = False

    def before_run(self, db: Session) -> None:
        # No wholesale wipe — we want stable identity. Records that age out of
        # the retain window simply aren't emitted; the runner deletes ones
        # that don't reappear in this run via the post-pass.
        return None

    def fetch(self) -> list[CrisisRecord]:  # noqa: C901 — orchestration
        if not settings.acled_enabled:
            return []
        if not settings.acled_username or not settings.acled_password:
            logger.warning("acled-agg: credentials missing; skipping")
            return []

        records: list[CrisisRecord] = []
        ref_today = _reference_today()

        with httpx.Client(timeout=120.0, headers={"User-Agent": USER_AGENT}) as client:
            tok = get_token(client)
            for region in REGIONS:
                url = _discover_region_xlsx_url(client, region, tok.access_token)
                if not url:
                    logger.warning("acled-agg: %s — no xlsx URL discovered", region)
                    continue
                rf = _download_with_etag(client, url, region, tok.access_token)
                if rf is None:
                    continue
                try:
                    header, rows = _iter_xlsx_rows(rf.xlsx_path)
                except Exception:
                    logger.exception("acled-agg: %s parse failed", region)
                    continue
                if not _validate_schema(header, region):
                    continue
                cells = _aggregate_rows(header, rows)
                for cell in cells.values():
                    rec = _build_record(cell, ref_today)
                    if rec is not None:
                        records.append(rec)
                logger.info(
                    "acled-agg: %s → %d crises emitted from %d rows",
                    region,
                    sum(1 for c in cells.values() if _build_record(c, ref_today) is not None),
                    len(rows),
                )

        return records

    def post_upsert_alias_seed(self, db: Session, records: list[CrisisRecord]) -> None:
        """Self-populate the admin1_aliases table from canonical names we
        emitted. The runner calls this after upserting records so the table
        reflects current vocabulary; UCDP/GDELT use it on subsequent runs."""
        for rec in records:
            if rec.country_iso3 and rec.admin1 and rec.admin1_norm:
                _ensure_alias(db, rec.country_iso3, rec.admin1, rec.admin1_norm)

    def sweep_dropped(self, db: Session, present_keys: set[tuple[str, str]]) -> int:
        """Delete crises whose (iso3, admin1_norm) wasn't emitted this run AND
        have no admin-curated content (i.e. truly aged out of the 52-week
        window). Crises with admin_curated actor links are spared."""
        keep_iso3 = {k[0] for k in present_keys}
        keep_admin1 = {k[1] for k in present_keys}
        # Pick candidates: agg-sourced crises that aren't in present_keys.
        from app.models import CrisisActor

        candidates = db.scalars(
            select(Crisis).where(
                Crisis.source_name == self.name,
                Crisis.admin1_norm.is_not(None),
            )
        ).all()
        deleted = 0
        for crisis in candidates:
            if (crisis.country_iso3, crisis.admin1_norm) in present_keys:
                continue
            curated = db.scalar(
                select(CrisisActor)
                .where(
                    CrisisActor.crisis_id == crisis.id,
                    CrisisActor.admin_curated.is_(True),
                )
                .limit(1)
            )
            if curated is not None:
                continue
            db.execute(delete(Crisis).where(Crisis.id == crisis.id))
            deleted += 1
        return deleted

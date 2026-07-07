"""Load Natural Earth 10m admin1 polygons into the `admin1_polygons` table.

Natural Earth distributes admin1 boundaries as a public-domain shapefile.
We pull the GeoJSON mirror (smaller, no shapefile reader needed), iterate
features, and upsert one row per (iso3, admin1_norm).

Polygons are used by GDELT and (as fallback) UCDP for point-in-polygon
attach when the source's published `adm_1` string doesn't resolve via the
alias table. They're also used to seed `admin1_aliases` from `name` and
`name_alt` so UCDP/GDELT can find ACLED's spelling on first run.

Run once after migrations and after the aggregated source has populated
`admin1_aliases` with ACLED's canonical vocabulary; rerun whenever Natural
Earth ships a new release.

Usage:
    uv run python -m app.scripts.load_admin1_polygons
"""

from __future__ import annotations

import gzip
import json
import logging
import sys
from pathlib import Path

import httpx
from sqlalchemy import select, text

from app.db import SessionLocal
from app.ingestion.acled import _normalize_admin1
from app.models import Admin1Alias, Admin1Polygon

logger = logging.getLogger(__name__)

# GitHub-hosted public-domain Natural Earth 10m admin-1 GeoJSON.
# nvkelso/natural-earth-vector is the canonical mirror; the file is ~5MB.
NE_GEOJSON_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_10m_admin_1_states_provinces.geojson"
)

CACHE_PATH = Path(__file__).resolve().parents[2] / ".cache" / "ne_admin1.geojson.gz"


def _download(force: bool = False) -> bytes:
    if not force and CACHE_PATH.exists():
        return gzip.decompress(CACHE_PATH.read_bytes())
    logger.info("Downloading Natural Earth admin1 GeoJSON (~5MB)…")
    resp = httpx.get(NE_GEOJSON_URL, timeout=120.0, follow_redirects=True)
    resp.raise_for_status()
    raw = resp.content
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_bytes(gzip.compress(raw))
    return raw


def _coerce_multipolygon(geom: dict) -> dict:
    """Wrap a Polygon as a MultiPolygon so the column type is uniform."""
    if geom.get("type") == "Polygon":
        return {"type": "MultiPolygon", "coordinates": [geom["coordinates"]]}
    return geom


def _ring_centroid(coords: list) -> tuple[float, float] | None:
    """Cheap centroid of a polygon's outer ring (mean of vertices). Good
    enough for a label point — not the true geometric centroid."""
    if not coords or not coords[0]:
        return None
    outer = coords[0][0] if isinstance(coords[0][0], list) and isinstance(
        coords[0][0][0], list
    ) else coords[0]
    if not outer:
        return None
    lat_sum = 0.0
    lng_sum = 0.0
    n = 0
    for pt in outer:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            continue
        lng_sum += float(pt[0])
        lat_sum += float(pt[1])
        n += 1
    if n == 0:
        return None
    return lat_sum / n, lng_sum / n


def _multipolygon_centroid(geom: dict) -> tuple[float, float] | None:
    if geom.get("type") == "Polygon":
        return _ring_centroid(geom["coordinates"])
    if geom.get("type") == "MultiPolygon":
        # Largest sub-polygon centroid by vertex count.
        best = None
        best_n = 0
        for poly in geom["coordinates"]:
            if not poly or not poly[0]:
                continue
            n = len(poly[0])
            if n > best_n:
                best_n = n
                best = _ring_centroid(poly)
        return best
    return None


def main() -> int:
    raw = _download()
    fc = json.loads(raw)
    features = fc.get("features", [])
    logger.info("Loaded %d Natural Earth admin1 features", len(features))

    db = SessionLocal()
    inserted = 0
    updated = 0
    aliases_added = 0
    skipped_no_iso3 = 0
    try:
        # Preload existing aliases to avoid N+1 lookups + dedupe within run.
        existing_aliases = {
            (iso3, alias)
            for iso3, alias in db.execute(
                select(Admin1Alias.country_iso3, Admin1Alias.alias_norm)
            ).all()
        }
        for feat in features:
            props = feat.get("properties") or {}
            iso3 = (props.get("adm0_a3") or "").strip().upper()
            name = (props.get("name") or props.get("name_en") or "").strip()
            if not iso3 or len(iso3) != 3 or not name:
                skipped_no_iso3 += 1
                continue
            admin1_norm = _normalize_admin1(name)
            if not admin1_norm:
                continue
            geom_json = _coerce_multipolygon(feat.get("geometry") or {})
            centroid = _multipolygon_centroid(feat.get("geometry") or {})

            existing = db.scalar(
                select(Admin1Polygon).where(
                    Admin1Polygon.country_iso3 == iso3,
                    Admin1Polygon.admin1_norm == admin1_norm,
                )
            )
            geom_text = json.dumps(geom_json)
            if existing is None:
                db.execute(
                    text(
                        """
                        INSERT INTO admin1_polygons
                        (country_iso3, admin1, admin1_norm, centroid_lat,
                         centroid_lng, geom)
                        VALUES (:iso3, :a1, :a1n, :clat, :clng,
                          ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326)))
                        """
                    ),
                    {
                        "iso3": iso3,
                        "a1": name[:120],
                        "a1n": admin1_norm[:120],
                        "clat": centroid[0] if centroid else None,
                        "clng": centroid[1] if centroid else None,
                        "geom": geom_text,
                    },
                )
                inserted += 1
            else:
                db.execute(
                    text(
                        """
                        UPDATE admin1_polygons
                        SET admin1 = :a1,
                            centroid_lat = :clat,
                            centroid_lng = :clng,
                            geom = ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326))
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": existing.id,
                        "a1": name[:120],
                        "clat": centroid[0] if centroid else None,
                        "clng": centroid[1] if centroid else None,
                        "geom": geom_text,
                    },
                )
                updated += 1

            # Seed aliases from `name` and `name_alt`.
            alt_names_field = props.get("name_alt") or ""
            alt_names = [n.strip() for n in str(alt_names_field).split("|") if n.strip()]
            for alt in [name] + alt_names:
                alt_norm = _normalize_admin1(alt)
                if not alt_norm:
                    continue
                key = (iso3, alt_norm)
                if key in existing_aliases:
                    continue
                existing_aliases.add(key)
                db.add(
                    Admin1Alias(
                        country_iso3=iso3,
                        alias_norm=alt_norm,
                        canonical_admin1_norm=admin1_norm,
                        canonical_admin1=name,
                    )
                )
                aliases_added += 1
        db.commit()
    finally:
        db.close()

    logger.info(
        "admin1_polygons: inserted=%d updated=%d skipped_no_iso3=%d aliases_added=%d",
        inserted,
        updated,
        skipped_no_iso3,
        aliases_added,
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sys.exit(main())

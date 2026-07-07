"""One-shot triage script for the 43 emerging conflicts.

Promotes 8 real parent conflicts and deletes 35 duplicates/noise/sub-conflicts.
After running, run `uv run python -m app.scripts.backfill_routing` to compute
lat/lng centroids from routed events.

Usage:
    cd backend
    uv run python triage_emerging.py --dry-run    # preview
    uv run python triage_emerging.py              # execute
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load .env from repo root
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

API_BASE = "http://localhost:8000"
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")
if not ADMIN_TOKEN:
    sys.exit("ADMIN_TOKEN missing from environment")

HEADERS = {"X-Admin-Token": ADMIN_TOKEN, "Content-Type": "application/json"}

# (slug, primary_iso3, secondary_iso3s, conflict_type, country_routing_rule_iso3)
PROMOTE = [
    ("kivu-conflict", "COD", ["RWA", "UGA"], "insurgency", "COD"),
    ("ituri-conflict", "COD", [], "insurgency", "COD"),
    ("allied-democratic-forces-insurgency", "COD", ["UGA"], "insurgency", "COD"),
    ("2026-lebanon-war", "LBN", ["ISR"], "asymmetric", "LBN"),
    ("2026-iran-war", "IRN", ["ISR", "IRQ", "JOR", "SYR"], "interstate", "IRN"),
    ("red-sea-crisis", "YEM", [], "maritime_incident", "YEM"),
    ("hezbollah-israel-conflict", "LBN", ["ISR"], "asymmetric", "LBN"),
    ("jnim-isgs-war", "BFA", ["MLI", "NER"], "insurgency", "BFA"),
]

DELETE = [
    # Duplicates of existing active conflicts
    "myanmar-conflict",
    "somali-civil-war",
    "sudanese-civil-war",
    "islamist-insurgency-in-burkina-faso",
    "islamist-insurgency-in-niger",
    # Noise / non-conflicts
    "armed-conflict-location-and-event-data-project",
    "congolese-civil-war-disambiguation",
    "arab-israeli-conflict",
    "israeli-palestinian-conflict",
    # Sub-conflicts (Gaza/Israel)
    "gaza-israel-conflict",
    "gaza-war",
    "anti-hamas-insurgency-in-gaza",
    "salafi-jihadist-insurgency-in-the-gaza-strip",
    "fatah-hamas-conflict",
    "palestinian-authority-west-bank-militias-conflict",
    "israeli-lebanese-conflict",
    "israeli-syrian-conflict",
    "iran-israel-conflict",
    "iran-israel-proxy-conflict",
    # Sub-conflicts (Myanmar)
    "kachin-conflict",
    "karen-conflict",
    "rohingya-conflict",
    "involvement-of-northeast-indian-insurgents-in-the-myanmar-conflict",
    # Sub-conflicts (other)
    "druze-insurgency-in-southern-syria",
    "katanga-insurgency",
    "islamic-state-insurgency-in-puntland",
    "jubaland-crisis",
    "constitutional-crisis-in-somalia",
    "2026-strait-of-hormuz-campaign",
    "syria-in-the-2026-iran-war",
    "2026-kurdish-iranian-crisis",
    "fulani-mossi-conflict",
    # Historical / dormant
    "lord-s-resistance-army-insurgency",
    "sudanese-nomadic-conflicts",
    "war-in-the-sahel",
]


def promote(client: httpx.Client, slug: str, iso3: str, secondary: list[str],
            ctype: str, routing_iso3: str, dry: bool) -> None:
    patch = {
        "status": "active",
        "primary_iso3": iso3,
        "secondary_iso3s": secondary,
        "conflict_type": ctype,
    }
    rule = {"rule_type": "country", "pattern": routing_iso3, "priority": 3}
    if dry:
        print(f"  [DRY] PATCH /api/admin/conflicts/{slug} {patch}")
        print(f"  [DRY] POST /api/admin/conflicts/{slug}/routing-rules {rule}")
        return
    r = client.patch(f"/api/admin/conflicts/{slug}", json=patch)
    if r.status_code != 200:
        print(f"  ! PATCH {slug} failed: {r.status_code} {r.text}")
        return
    r = client.post(f"/api/admin/conflicts/{slug}/routing-rules", json=rule)
    if r.status_code == 409:
        print(f"  - routing rule already exists for {slug}")
    elif r.status_code not in (200, 201):
        print(f"  ! routing rule POST {slug} failed: {r.status_code} {r.text}")
    else:
        print(f"  ok promoted {slug}")


def delete(client: httpx.Client, slug: str, dry: bool) -> None:
    if dry:
        print(f"  [DRY] DELETE /api/admin/conflicts/{slug}")
        return
    r = client.delete(f"/api/admin/conflicts/{slug}")
    if r.status_code == 204:
        print(f"  ok deleted {slug}")
    elif r.status_code == 404:
        print(f"  - already gone: {slug}")
    else:
        print(f"  ! DELETE {slug} failed: {r.status_code} {r.text}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print(f"=== Triage plan: promote {len(PROMOTE)}, delete {len(DELETE)} ===")
    if args.dry_run:
        print("(dry-run — no changes will be made)\n")

    with httpx.Client(base_url=API_BASE, headers=HEADERS, timeout=15.0) as client:
        print("\n--- PROMOTE ---")
        for slug, iso3, sec, ctype, route in PROMOTE:
            promote(client, slug, iso3, sec, ctype, route, args.dry_run)
        print("\n--- DELETE ---")
        for slug in DELETE:
            delete(client, slug, args.dry_run)

    print("\nDone.")
    if not args.dry_run:
        print("\nNext: run backfill to compute lat/lng + route any matching events:")
        print("  cd backend && uv run python -m app.scripts.backfill_routing")


if __name__ == "__main__":
    main()

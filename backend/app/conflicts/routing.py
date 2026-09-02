"""Route an incoming event to a `conflict_id`.

The routing function is intentionally pure: it takes a `RoutingIndex` (built
once from `conflict_routing_rules`) plus the event's identifying fields, and
returns a `conflict_id` (or `None` for orphans).

Priority order (lowest priority number wins):
  1. Actor match  — any of the event's actor strings matches a LIKE pattern,
     provided the event's country is one the conflict actually spans. Armed
     groups appear far outside their own war (Hezbollah in Syria, Ukrainian
     forces in Kazakhstan), and without that bound a single actor string
     drags a whole region under the wrong conflict's name.
  2. Admin1 match — (iso3, admin1_norm) is in a conflict footprint.
  3. Country fallback — iso3 has exactly one conflict claiming it. If two or
     more conflicts list the same iso3 in `country_patterns`, the fallback
     does NOT fire (ambiguous → orphan), forcing the curator to add more
     specific routing.

This module has no SQLAlchemy dependency so the routing logic is testable in
isolation and reusable from both the backfill script and the per-event ingest
runner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class RoutingIndex:
    # (compiled_regex, conflict_id), priority=1 — ordered as inserted; first
    # match wins. Conflicts are independent, so ordering between conflicts is
    # not meaningful unless two patterns overlap (rare; routing then picks
    # whichever was loaded first, deterministically by row id).
    actor_rules: list[tuple[re.Pattern[str], int]] = field(default_factory=list)

    # (iso3, admin1_norm) -> conflict_id, priority=2
    admin1_rules: dict[tuple[str, str], int] = field(default_factory=dict)

    # iso3 -> list of conflict_ids claiming this country. Fallback fires only
    # when the list has exactly one entry (unambiguous).
    country_rules: dict[str, list[int]] = field(default_factory=dict)

    # conflict_id -> the ISO3s that conflict spans. Bounds tier 1: an actor
    # match only counts inside the conflict's own geography. A conflict absent
    # from this map is unrestricted, so an index built without it behaves
    # exactly as before.
    actor_scope: dict[int, set[str]] = field(default_factory=dict)


def _compile_like(pattern: str) -> re.Pattern[str]:
    """Translate a SQL-LIKE pattern to a case-insensitive regex.

    `%` → `.*`, `_` → `.`, everything else escaped. Anchored at both ends so
    that "Hamas" does NOT match "Hamas Sympathizer" unless the pattern was
    "Hamas%".
    """
    parts: list[str] = []
    for ch in pattern:
        if ch == "%":
            parts.append(".*")
        elif ch == "_":
            parts.append(".")
        else:
            parts.append(re.escape(ch))
    regex = "^" + "".join(parts) + "$"
    return re.compile(regex, re.IGNORECASE)


def build_routing_index(
    rules: Iterable[tuple[int, str, str, int]],
    conflict_iso3s: dict[int, set[str]] | None = None,
) -> RoutingIndex:
    """Build the in-memory routing index.

    `rules` is an iterable of (conflict_id, rule_type, pattern, priority)
    tuples — the natural shape of a `SELECT conflict_id, rule_type, pattern,
    priority FROM conflict_routing_rules ORDER BY priority` query.

    `conflict_iso3s` maps conflict_id to the countries that conflict spans
    (primary + secondary). Conflicts it omits keep unbounded actor matching.
    """
    idx = RoutingIndex(actor_scope=dict(conflict_iso3s or {}))

    # Sort by priority so the actor rules end up ahead of admin1/country in
    # the actor_rules list. Within a priority, preserve insertion order.
    ordered = sorted(rules, key=lambda r: (r[3], r[0]))

    for conflict_id, rule_type, pattern, _priority in ordered:
        if rule_type == "actor":
            idx.actor_rules.append((_compile_like(pattern), conflict_id))
        elif rule_type == "admin1":
            # pattern format: "<iso3>:<admin1_norm>"
            if ":" not in pattern:
                continue
            iso3, admin1_norm = pattern.split(":", 1)
            iso3 = iso3.upper()
            admin1_norm = admin1_norm.lower().strip()
            # If two conflicts claim the same cell, last-write-wins.
            # Curators are expected to keep footprints disjoint.
            idx.admin1_rules[(iso3, admin1_norm)] = conflict_id
        elif rule_type == "country":
            iso3 = pattern.upper().strip()
            idx.country_rules.setdefault(iso3, []).append(conflict_id)

    return idx


def route_event(
    actors: Iterable[str | None],
    iso3: str | None,
    admin1_norm: str | None,
    idx: RoutingIndex,
) -> int | None:
    """Return the conflict_id for an event, or None if no rule matches.

    Args:
        actors: any number of raw actor strings (actor1, actor2,
            assoc_actor_1, assoc_actor_2, …). Empty / None entries skipped.
        iso3: ISO-3166-1 alpha-3 country code, uppercase. Also bounds the
            actor tier — see `RoutingIndex.actor_scope`.
        admin1_norm: normalized admin1 name (lowercase, ASCII-fold).
        idx: a RoutingIndex built from `conflict_routing_rules`.
    """
    # 1. Actor match (highest priority), bounded by the conflict's geography.
    scoped_iso3 = iso3.upper() if iso3 else None
    for actor in actors:
        if not actor:
            continue
        for regex, conflict_id in idx.actor_rules:
            if not regex.match(actor):
                continue
            spans = idx.actor_scope.get(conflict_id)
            if spans is not None and scoped_iso3 not in spans:
                continue
            return conflict_id

    # 2. Admin1 match.
    if iso3 and admin1_norm:
        hit = idx.admin1_rules.get((iso3.upper(), admin1_norm.lower().strip()))
        if hit is not None:
            return hit

    # 3. Country fallback — only when exactly one conflict claims this iso3.
    if iso3:
        candidates = idx.country_rules.get(iso3.upper(), [])
        if len(candidates) == 1:
            return candidates[0]

    return None

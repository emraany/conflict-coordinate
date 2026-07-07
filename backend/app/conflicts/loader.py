"""Parse + validate the conflict registry YAML and the canonical actor catalog.

Two inputs:
  - `registry.yaml`      — one entry per conflict (the dots that show up on
                           the globe).
  - `actors_canon.yaml`  — canonical actor catalog with ACLED/UCDP/GDELT
                           alias patterns. Every party referenced from a
                           conflict resolves to one of these.

The loader is intentionally pure: it validates the YAML and produces dataclass
instances. Database upsert lives in the seed script that calls into this.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

REGISTRY_PATH = Path(__file__).resolve().parent / "registry.yaml"
ACTORS_CANON_PATH = Path(__file__).resolve().parent / "actors_canon.yaml"


# ---------------------------------------------------------------------------
# Pydantic schemas — validate the YAML on load. Failures are loud so a bad
# registry edit can't silently corrupt routing.
# ---------------------------------------------------------------------------


class _ActorCanonEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=200)
    type: Literal["state", "non_state", "coalition", "other"] = "other"
    description: str | None = None
    wikipedia_url: str | None = None
    aliases: list[str] = Field(default_factory=list)


class _ActorsCanonFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actors: list[_ActorCanonEntry]


class _PartyRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str  # canon slug
    role: Literal["party", "mediator", "observer", "affected"] = "party"
    notes: str | None = None


class _FootprintCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iso3: str = Field(min_length=3, max_length=3)
    admin1: str = Field(min_length=1, max_length=120)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class _RoutingBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_patterns: list[str] = Field(default_factory=list)
    admin1_patterns: list[str] = Field(default_factory=list)
    country_patterns: list[str] = Field(default_factory=list)


class _ConflictEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=200)
    conflict_type: str | None = None
    status: Literal["active", "frozen", "resolved", "emerging"] = "active"
    primary_iso3: str | None = Field(default=None, min_length=3, max_length=3)
    secondary_iso3s: list[str] = Field(default_factory=list)
    started_at: date | None = None
    resolved_at: date | None = None
    summary: str | None = None
    wikipedia_url: str | None = None
    ucdp_conflict_id: str | None = None
    parties: list[_PartyRef] = Field(default_factory=list)
    footprint: list[_FootprintCell] = Field(default_factory=list)
    routing: _RoutingBlock = Field(default_factory=_RoutingBlock)

    @field_validator("secondary_iso3s")
    @classmethod
    def _validate_iso3_list(cls, v: list[str]) -> list[str]:
        for code in v:
            if len(code) != 3 or not code.isalpha():
                raise ValueError(f"invalid iso3 code in secondary_iso3s: {code!r}")
        return [code.upper() for code in v]


class _RegistryFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conflicts: list[_ConflictEntry]


# ---------------------------------------------------------------------------
# Public dataclasses returned by the loader. Decoupled from the YAML schema so
# callers don't have to reach for Pydantic models.
# ---------------------------------------------------------------------------


@dataclass
class ActorCanon:
    slug: str
    name: str
    type: str
    description: str | None
    wikipedia_url: str | None
    aliases: list[str]


@dataclass
class FootprintCell:
    iso3: str
    admin1: str        # original display form
    admin1_norm: str   # normalized for matching
    confidence: float


@dataclass
class PartyLink:
    actor_slug: str
    role: str
    notes: str | None


@dataclass
class RoutingRule:
    rule_type: Literal["actor", "admin1", "country"]
    pattern: str
    priority: int


@dataclass
class ConflictEntry:
    slug: str
    name: str
    conflict_type: str | None
    status: str
    primary_iso3: str | None
    secondary_iso3s: list[str]
    started_at: datetime | None
    resolved_at: datetime | None
    summary: str | None
    wikipedia_url: str | None
    ucdp_conflict_id: str | None
    parties: list[PartyLink]
    footprint: list[FootprintCell]
    routing_rules: list[RoutingRule] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Normalization — must match the rule used by ACLED-aggregated so footprints
# line up with admin1_norm values already in the DB.
# ---------------------------------------------------------------------------


def normalize_admin1(value: str) -> str:
    """ASCII-fold + lowercase + strip common admin1 suffixes. Must match
    `app.ingestion.acled_aggregated._normalize_admin1` byte-for-byte."""
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


# ---------------------------------------------------------------------------
# Public loader API
# ---------------------------------------------------------------------------


def load_actors_canon(path: Path = ACTORS_CANON_PATH) -> dict[str, ActorCanon]:
    """Return canon by slug. Raises if YAML is invalid or slugs collide."""
    with path.open() as f:
        raw = yaml.safe_load(f) or {}
    try:
        model = _ActorsCanonFile.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(
            f"actors_canon.yaml failed validation: {exc}"
        ) from exc
    out: dict[str, ActorCanon] = {}
    for entry in model.actors:
        if entry.slug in out:
            raise ValueError(f"duplicate actor canon slug: {entry.slug!r}")
        out[entry.slug] = ActorCanon(
            slug=entry.slug,
            name=entry.name,
            type=entry.type,
            description=entry.description,
            wikipedia_url=entry.wikipedia_url,
            aliases=list(entry.aliases),
        )
    return out


def load_registry(
    registry_path: Path = REGISTRY_PATH,
    actors_canon: dict[str, ActorCanon] | None = None,
) -> list[ConflictEntry]:
    """Parse the conflict registry into ConflictEntry records.

    Raises ValueError when:
      - YAML structure violates the pydantic schema
      - a party references an unknown actor canon slug
      - the same conflict slug appears twice
    """
    canon = actors_canon or load_actors_canon()

    with registry_path.open() as f:
        raw = yaml.safe_load(f) or {}
    try:
        model = _RegistryFile.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"registry.yaml failed validation: {exc}") from exc

    seen: set[str] = set()
    out: list[ConflictEntry] = []
    for c in model.conflicts:
        if c.slug in seen:
            raise ValueError(f"duplicate conflict slug: {c.slug!r}")
        seen.add(c.slug)

        # Resolve party references against the actor canon up front.
        parties: list[PartyLink] = []
        for p in c.parties:
            if p.actor not in canon:
                raise ValueError(
                    f"conflict {c.slug!r} references unknown actor canon "
                    f"{p.actor!r}; add it to actors_canon.yaml"
                )
            parties.append(
                PartyLink(actor_slug=p.actor, role=p.role, notes=p.notes)
            )

        # Footprint cells get pre-normalized so DB upsert is one-step.
        footprint: list[FootprintCell] = []
        for cell in c.footprint:
            footprint.append(
                FootprintCell(
                    iso3=cell.iso3.upper(),
                    admin1=cell.admin1,
                    admin1_norm=normalize_admin1(cell.admin1),
                    confidence=cell.confidence,
                )
            )

        # Routing rules are produced as a single flat list with priorities so
        # the runtime router can sort once. Actor rules win first (priority=1),
        # admin1 next (2), country fallback last (3). The implicit admin1
        # rules derived from the footprint pre-populate the rule set so a
        # conflict's footprint also routes events arriving from UCDP/GDELT
        # without an actor match.
        routing: list[RoutingRule] = []
        for pat in c.routing.actor_patterns:
            routing.append(RoutingRule("actor", pat, priority=1))
        # Explicit admin1 overrides (rare).
        for pat in c.routing.admin1_patterns:
            routing.append(RoutingRule("admin1", pat, priority=2))
        # Implicit admin1 rules from footprint cells.
        for cell in footprint:
            routing.append(
                RoutingRule(
                    "admin1",
                    f"{cell.iso3}:{cell.admin1_norm}",
                    priority=2,
                )
            )
        for pat in c.routing.country_patterns:
            routing.append(RoutingRule("country", pat.upper(), priority=3))

        # Dedupe routing rules (footprint + explicit admin1 may overlap).
        seen_rules: set[tuple[str, str]] = set()
        deduped: list[RoutingRule] = []
        for r in routing:
            key = (r.rule_type, r.pattern.lower())
            if key in seen_rules:
                continue
            seen_rules.add(key)
            deduped.append(r)

        def _to_dt(d: date | None) -> datetime | None:
            if d is None:
                return None
            return datetime(d.year, d.month, d.day)

        out.append(
            ConflictEntry(
                slug=c.slug,
                name=c.name,
                conflict_type=c.conflict_type,
                status=c.status,
                primary_iso3=c.primary_iso3.upper() if c.primary_iso3 else None,
                secondary_iso3s=c.secondary_iso3s,
                started_at=_to_dt(c.started_at),
                resolved_at=_to_dt(c.resolved_at),
                summary=c.summary,
                wikipedia_url=c.wikipedia_url,
                ucdp_conflict_id=c.ucdp_conflict_id,
                parties=parties,
                footprint=footprint,
                routing_rules=deduped,
            )
        )
    return out

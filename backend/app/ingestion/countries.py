"""Country-name → ISO3 resolution shared by all ingestion sources.

`pycountry.countries.lookup()` misses many names that ACLED and UCDP actually
emit — including "Russia", "Turkey", "Ivory Coast", "Democratic Republic of
Congo", "Palestine", and UCDP's parenthesized historical forms like
"DR Congo (Zaire)". Before this module each source had its own bare lookup
and silently dropped every event in those countries.

Resolution order:
  1. override table (casefolded exact match)
  2. pycountry.lookup on the raw name
  3. strip a trailing " (...)" qualifier, retry 1 then 2

Unresolvable names are logged once per process so future gaps are visible
instead of silent.
"""

from __future__ import annotations

import logging
import re

import pycountry

logger = logging.getLogger(__name__)

# Names pycountry.lookup() cannot resolve, as emitted by ACLED / UCDP.
_OVERRIDES: dict[str, str] = {
    "democratic republic of congo": "COD",
    "democratic republic of the congo": "COD",
    "dr congo": "COD",
    "republic of congo": "COG",
    "ivory coast": "CIV",
    "turkey": "TUR",
    "kosovo": "XKX",
    "palestine": "PSE",
    "russia": "RUS",
    "swaziland": "SWZ",
    "east timor": "TLS",
    "cape verde": "CPV",
    "macedonia": "MKD",
    "brunei": "BRN",
    "micronesia": "FSM",
    "saint martin": "MAF",
}

_warned_names: set[str] = set()


def _lookup(name: str) -> str | None:
    key = name.casefold()
    if key in _OVERRIDES:
        return _OVERRIDES[key]
    try:
        c = pycountry.countries.lookup(name)
    except LookupError:
        return None
    return getattr(c, "alpha_3", None)


def country_iso3(name: str | None) -> str | None:
    if not name:
        return None
    name = re.sub(r"\s+", " ", name).strip()
    iso3 = _lookup(name)
    if iso3 is None:
        # UCDP appends historical qualifiers: "Myanmar (Burma)", "DR Congo (Zaire)".
        base = re.sub(r"\s*\([^)]*\)\s*$", "", name)
        if base and base != name:
            iso3 = _lookup(base)
    if iso3 is None and name not in _warned_names:
        _warned_names.add(name)
        logger.warning("unmapped country name: %r — events dropped", name)
    return iso3

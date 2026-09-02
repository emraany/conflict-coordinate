"""What kind of violence a region is currently seeing.

A dot answers "where" and "how much"; this answers "what". Rio and Donetsk
render identically without it, and ACLED's event types cannot tell them
apart — a gang-versus-police shootout in Rio is coded `Battles / Armed
clash`, exactly like a frontline engagement in Donetsk. The discriminator is
in the actor names, where ACLED's conventions are regular enough to key on:

    Unidentified Gang (Brazil), CV: Red Command, B-18: Barrio-18
    Military Forces of Russia (2000-), Al Shabaab, Fulani Ethnic Militia
    Protesters (Kenya), Labor Group (Iraq), Students (Bangladesh)

Two conventions that trip up the obvious patterns, both confirmed in the
data: state police are named `Military Forces of Brazil (2023-) Military
Police`, so `^Military Forces of` alone makes Rio a war; and `Unidentified
Armed Group (X)` is ACLED's filler for an unknown perpetrator, not evidence
that an armed group is present.

The two inputs age differently, and the returned basis always names both so
a reader can see it: the event mix is the current four-week window, while the
actor list is derived from the incident archive, which ACLED embargoes ~12
months on the Research tier. A region whose war ended last year still carries
its combatants.

Pure — no SQLAlchemy — so it is testable in isolation, like `routing.py`.
"""

from __future__ import annotations

import re

ARMED_CONFLICT = "armed_conflict"
CRIMINAL_VIOLENCE = "criminal_violence"
UNREST = "unrest"
UNCLEAR = "unclear"

# The four ACLED event types a dot is built from (mirrors
# `runner.VIOLENT_EVENT_TYPES`; kept as literals to keep this module pure).
_VIOLENT = (
    "Battles",
    "Violence against civilians",
    "Explosions/Remote violence",
    "Riots",
)

# ACLED's placeholders. `Civilians (X)` marks who was hit, not who fought;
# `Unidentified Armed Group (X)` means the perpetrator is unknown. Neither is
# evidence of anything, so both are excluded from every count below.
_GENERIC = re.compile(
    r"^(civilians|unidentified armed group|unidentified group|"
    r"unidentified military|unidentified communal)",
    re.I,
)

# State police, however named. ACLED files them under `Military Forces of X`
# as often as `Police Forces of X`, and police are present at riots, gang
# shootouts and wars alike — so they never decide a class.
_POLICE = re.compile(r"police|gendarmerie|national guard", re.I)

# Organised crime. Named syndicates plus ACLED's generic `Unidentified Gang`.
# Deliberately absent: `Vigilante Group (X)`, which is a neighbourhood
# response to crime and shows up in riot-dominant regions like Nairobi.
_CRIMINAL = re.compile(
    r"\bgangs?\b|cartel|mafia|\bnarco|traffick|^cv:|^pcc|^b-18|^ms-13|"
    r"barrio|comando vermelho|red command|gulf clan|clan del golfo|"
    r"tren de aragua|choneros|\blobos\b",
    re.I,
)

# Non-state armed groups: insurgencies, rebel movements, ethnic militias,
# mercenaries. Presence of one is the strongest single signal there is.
_NON_STATE_ARMED = re.compile(
    r"islamic state|al shabaab|\bjnim\b|boko haram|rapid support forces|"
    r"wagner|africa corps|hezbollah|\bhamas\b|houthi|taliban|al qaeda|"
    r"ethnic militia|communal militia|political militia|\brebels?\b|"
    r"separatist|insurgen|\bbrigades?\b|\bfront\b|\barmy\b|liberation",
    re.I,
)

# National armed forces. Distinguished from police above.
_STATE_MILITARY = re.compile(r"^military forces of|^government of .*forces", re.I)

# Protest constituencies, anchored at the start because ACLED names them as
# `Protesters (Kenya)`, `Labor Group (Iraq)`, `Students (Bangladesh)`.
_UNREST = re.compile(
    r"^(protesters|rioters|students|teachers|labor group|women|farmers|"
    r"health workers|taxi|bus drivers|lawyers|journalists|traders|"
    r"pensioners|doctors|nurses|refugees/idps)",
    re.I,
)

# A region whose violence is mostly riots, with nothing armed or criminal on
# record, is unrest.
_RIOT_SHARE = 0.5
# With no actors at all to go on, these mixes still read as organised armed
# violence: sustained shelling and drone strikes, or battle-dominant weeks.
_EXPLOSION_SHARE = 0.3
_BATTLE_SHARE = 0.6


def classify_region(actor_names: list[str], mix: dict[str, int]) -> tuple[str, str]:
    """Classify one region's current violence.

    `actor_names` are the raw ACLED actor strings linked to the region;
    `mix` maps ACLED event type to event count over the current window (pass
    the whole mix — `Protests` included — the shares below use the violent
    subset).

    Returns `(class, basis)`. The basis is assembled from the counts, never
    authored: it is what the dossier shows to justify the label.
    """
    named = [n for n in actor_names if n and not _GENERIC.match(n)]
    criminal = [n for n in named if _CRIMINAL.search(n)]
    non_state = [
        n
        for n in named
        if _NON_STATE_ARMED.search(n) and not _POLICE.search(n) and not _CRIMINAL.search(n)
    ]
    state_mil = [n for n in named if _STATE_MILITARY.search(n) and not _POLICE.search(n)]
    protest = [n for n in named if _UNREST.match(n)]

    total = sum(mix.get(t, 0) for t in _VIOLENT)
    riots = mix.get("Riots", 0) / total if total else 0.0
    battles = mix.get("Battles", 0) / total if total else 0.0
    explosions = mix.get("Explosions/Remote violence", 0) / total if total else 0.0
    shape = f"{battles:.0%} battles, {explosions:.0%} explosions, {riots:.0%} riots"

    # Criminal first: armies are deployed against cartels, so state forces
    # alongside a named syndicate do not make Sinaloa a war.
    if criminal and not non_state:
        return CRIMINAL_VIOLENCE, f"{_names(criminal)} on record; {shape}"
    if non_state:
        return ARMED_CONFLICT, f"{_names(non_state)} on record; {shape}"
    if state_mil:
        return ARMED_CONFLICT, f"{_names(state_mil)} on record; {shape}"
    if riots >= _RIOT_SHARE:
        who = f"{_names(protest)} on record; " if protest else ""
        return UNREST, f"{who}{shape}"
    if explosions >= _EXPLOSION_SHARE or battles >= _BATTLE_SHARE:
        return ARMED_CONFLICT, f"no armed group on record; {shape}"
    return UNCLEAR, f"no distinguishing actors on record; {shape}"


def _names(actors: list[str], limit: int = 2) -> str:
    """The first couple of actor names, so the basis cites its evidence."""
    head = ", ".join(sorted(actors)[:limit])
    extra = len(actors) - limit
    return f"{head} (+{extra} more)" if extra > 0 else head

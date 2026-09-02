"""Region violence classification, pinned to real actor bags.

Every actor list below is copied verbatim from the live database, because
the rules key on ACLED's naming conventions and the conventions are the
part that breaks: state police filed as `Military Forces of ... Military
Police`, and `Unidentified Armed Group (X)` used as a filler for "we don't
know who did this".
"""

from app.conflicts.violence_class import (
    ARMED_CONFLICT,
    CRIMINAL_VIOLENCE,
    UNCLEAR,
    UNREST,
    classify_region,
)

RIO = [
    "Civilians (Brazil)",
    "CV: Red Command",
    "Military Forces of Brazil (2023-) Military Police",
    "Unidentified Armed Group (Brazil)",
    "Unidentified Gang and/or Police Militia",
]
DONETSK = [
    "Military Forces of Russia (2000-)",
    "Military Forces of Russia (2000-) Air Force",
    "Military Forces of Ukraine (2019-)",
]
SINALOA = [
    "Civilians (Mexico)",
    "Military Forces of Mexico (2018-)",
    "Police Forces of Mexico (2018-) National Guard",
    "Protesters (Mexico)",
    "Unidentified Armed Group (Mexico)",
    "Unidentified Gang (Mexico)",
]
NAIROBI = [
    "Civilians (Kenya)",
    "Government of Kenya (2022-)",
    "Labor Group (Kenya)",
    "Police Forces of Kenya (2022-)",
    "Protesters (Kenya)",
    "Rioters (Kenya)",
    "Vigilante Group (Kenya)",
]

GANG_MIX = {"Battles": 110, "Violence against civilians": 21, "Riots": 4}
FRONTLINE_MIX = {"Battles": 1124, "Explosions/Remote violence": 666}
RIOT_MIX = {"Riots": 9, "Violence against civilians": 1, "Protests": 40}


def test_military_police_do_not_make_rio_a_war():
    """Rio's only `Military Forces of` entry is Brazil's military police, and
    ACLED codes gang-versus-police shootouts as Battles — so both signals
    point the wrong way until police are excluded."""
    cls, basis = classify_region(RIO, GANG_MIX)
    assert cls == CRIMINAL_VIOLENCE
    assert "Red Command" in basis


def test_frontline_regions_read_as_armed_conflict():
    cls, _ = classify_region(DONETSK, FRONTLINE_MIX)
    assert cls == ARMED_CONFLICT


def test_an_army_deployed_against_cartels_is_still_criminal_violence():
    """Sinaloa carries Mexico's army alongside the cartels. Armies are sent
    against organised crime; that does not make the state a belligerent in a
    war, so criminal actors are weighed before state forces."""
    cls, _ = classify_region(SINALOA, GANG_MIX)
    assert cls == CRIMINAL_VIOLENCE


def test_riot_dominant_region_with_no_armed_or_criminal_actors_is_unrest():
    """Nairobi's `Vigilante Group (Kenya)` is a response to crime, not a
    syndicate — the criminal lexicon deliberately omits it."""
    cls, basis = classify_region(NAIROBI, RIOT_MIX)
    assert cls == UNREST
    assert "90% riots" in basis


def test_heavy_weapons_mix_carries_a_region_with_no_actors_on_record():
    cls, basis = classify_region([], {"Explosions/Remote violence": 40, "Battles": 10})
    assert cls == ARMED_CONFLICT
    assert "no armed group on record" in basis


def test_nothing_to_go_on_stays_unclear():
    """Four dots have no actor rows at all, and a scattered mix. The globe
    says so rather than guessing."""
    cls, _ = classify_region(
        ["Civilians (Iraq)", "Unidentified Armed Group (Iraq)"],
        {"Battles": 3, "Violence against civilians": 3, "Riots": 1},
    )
    assert cls == UNCLEAR

"""Tier-1 actor routing is bounded by each conflict's own geography.

Armed groups are recorded far outside their war — Ukrainian forces in
Kazakhstan, Hezbollah in Syria — so an unbounded actor match drags whole
regions under the wrong conflict's name. These cases pin the boundary.
"""

from app.conflicts.routing import build_routing_index, route_event

# (conflict_id, rule_type, pattern, priority)
RULES = [
    (1, "actor", "Military Forces of Ukraine%", 1),
    (1, "admin1", "UKR:donetsk", 2),
    (104, "actor", "Hezbollah%", 1),
    (104, "admin1", "LBN:south", 2),
    (8, "country", "SYR", 3),
]
# russo-ukrainian-war spans UKR+RUS; israel-hezbollah spans LBN+ISR.
SCOPE = {1: {"UKR", "RUS"}, 104: {"LBN", "ISR"}}

UA_FORCES = "Military Forces of Ukraine (2019-)"


def _idx(scope=SCOPE):
    return build_routing_index(RULES, scope)


def test_actor_match_wins_inside_the_conflicts_geography():
    """Belgorod: Russian oblast, no footprint cell, no country rule — named
    only because RUS is a country the Russo-Ukrainian War spans."""
    assert route_event([UA_FORCES], "RUS", "belgorod", _idx()) == 1


def test_actor_match_is_refused_outside_it():
    """Homs has Hezbollah in its actor list but is Syrian, so tier 1 declines
    and the country fallback names it for Syria instead."""
    assert route_event(["Hezbollah"], "SYR", "homs", _idx()) == 8


def test_refused_actor_match_does_not_shadow_a_later_one():
    """A blocked match must keep scanning, not abandon the tier."""
    idx = _idx()
    assert route_event(["Hezbollah", UA_FORCES], "RUS", "belgorod", idx) == 1


def test_unscoped_conflict_keeps_unbounded_actor_matching():
    """An index built without a scope routes exactly as it did before."""
    assert route_event(["Hezbollah"], "SYR", "homs", build_routing_index(RULES)) == 104


def test_tier_precedence_is_unchanged():
    idx = _idx()
    # Actor beats footprint: Donetsk would match UKR:donetsk either way.
    assert route_event([UA_FORCES], "UKR", "donetsk", idx) == 1
    # Footprint beats country when no actor matches.
    assert route_event(["Civilians (Lebanon)"], "LBN", "south", idx) == 104
    # Country fallback is last.
    assert route_event([], "SYR", "aleppo", idx) == 8
    # No rule at any tier.
    assert route_event(["Rioters (Brazil)"], "BRA", "rio de janeiro", idx) is None

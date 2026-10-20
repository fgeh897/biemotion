"""Pure interpretation, state, and behavior scoring for witnessed betrayal.

The module deliberately contains no Sims 4 imports.  It models three different
questions separately:

1. Who does the observer blame for this event?
2. How much does the observer -> partner state change?
3. What does the observer feel inclined to do next?

Actual interactions are intentionally outside this module.  The result is a
decision opportunity, not an order to break up, forgive, or confront someone.
"""

import random

from fgeh_cheatingharder_utility_model import (
    RELATIONSHIP_UTILITY_MODELS,
    UtilityCandidateDefinition,
    UtilityFactor,
    UtilityGate,
)


class AttributionTarget:
    PARTNER = "partner"
    RIVAL = "rival"
    SELF = "self"
    CIRCUMSTANCE = "circumstance"

    ALL = (PARTNER, RIVAL, SELF, CIRCUMSTANCE)


class BetrayalIntent:
    FORGIVE_PARTNER = "forgive_partner"
    SEEK_REASSURANCE = "seek_reassurance"
    CLING_TO_PARTNER = "cling_to_partner"
    CONFRONT_PARTNER = "confront_partner"
    CONFRONT_RIVAL = "confront_rival"
    BREAK_UP = "break_up"
    ENDURE_SILENTLY = "endure_silently"

    ALL = (
        FORGIVE_PARTNER,
        SEEK_REASSURANCE,
        CLING_TO_PARTNER,
        CONFRONT_PARTNER,
        CONFRONT_RIVAL,
        BREAK_UP,
        ENDURE_SILENTLY,
    )


class BetrayalProfileKey:
    BALANCED = "balanced"
    RELATIONSHIP_FIRST = "relationship_first_forgiving"
    BOUNDARY_FIRST = "boundary_self_respect"
    RIVAL_BLAMING = "possessive_rival_blame"

    TEST_PROFILES = (
        RELATIONSHIP_FIRST,
        BOUNDARY_FIRST,
        RIVAL_BLAMING,
    )


def _clamp(value, minimum, maximum):
    return max(float(minimum), min(float(maximum), float(value)))


def _state_value(state, dimension, default=0.0):
    try:
        return _clamp(state.get(dimension, default), 0.0, 100.0)
    except Exception:
        return _clamp(default, 0.0, 100.0)


def _normalized_percentages(raw_values):
    values = {
        key: max(0.0, float(raw_values.get(key, 0.0)))
        for key in AttributionTarget.ALL
    }
    total = sum(values.values())
    if total <= 0.0:
        return {
            AttributionTarget.PARTNER: 25.0,
            AttributionTarget.RIVAL: 25.0,
            AttributionTarget.SELF: 25.0,
            AttributionTarget.CIRCUMSTANCE: 25.0,
        }
    return {
        key: values[key] * 100.0 / total
        for key in AttributionTarget.ALL
    }


class TraitInfluence:
    """Registered parameters for one personality bottom.

    These are not five new relationship dimensions.  They modify how one
    event is interpreted, how that event changes the five dimensions, and how
    resulting behavior utilities are scored.
    """

    def __init__(
        self,
        key,
        attribution_multipliers=None,
        state_multipliers=None,
        behavior_modifiers=None,
        description="",
    ):
        self.key = str(key)
        self.attribution_multipliers = {
            target: _clamp(
                dict(attribution_multipliers or {}).get(target, 1.0),
                0.05,
                4.0,
            )
            for target in AttributionTarget.ALL
        }
        self.state_multipliers = {
            str(dimension): _clamp(value, 0.25, 2.50)
            for dimension, value in dict(state_multipliers or {}).items()
        }
        self.behavior_modifiers = {
            str(intent): _clamp(value, -40.0, 40.0)
            for intent, value in dict(behavior_modifiers or {}).items()
        }
        self.description = str(description)

    def state_multiplier(self, dimension):
        return _clamp(
            self.state_multipliers.get(str(dimension), 1.0),
            0.25,
            2.50,
        )

    def behavior_modifier(self, intent):
        return _clamp(
            self.behavior_modifiers.get(str(intent), 0.0),
            -40.0,
            40.0,
        )


class TraitInfluenceRegistry:

    def __init__(self):
        self._profiles = {}

    def register(self, profile):
        if not isinstance(profile, TraitInfluence):
            raise TypeError("profile must be TraitInfluence")
        if profile.key in self._profiles:
            raise ValueError(
                "Betrayal profile already registered: {}".format(profile.key)
            )
        self._profiles[profile.key] = profile
        return profile

    def get(self, key, default=None):
        return self._profiles.get(str(key), default)

    def require(self, key):
        profile = self.get(key)
        if profile is None:
            raise KeyError("Unknown betrayal profile: {}".format(key))
        return profile

    def keys(self):
        return tuple(sorted(self._profiles))


class BetrayalBehaviorCandidate:

    def __init__(
        self,
        intent,
        score,
        terms=None,
        eligible=True,
        blockers=None,
    ):
        self.intent = str(intent)
        self.score = max(0.0, float(score))
        self.terms = tuple(terms or ())
        self.eligible = bool(eligible)
        self.blockers = tuple(str(value) for value in (blockers or ()))

    def as_dict(self):
        return {
            "intent": self.intent,
            "score": self.score,
            "terms": tuple(self.terms),
            "eligible": self.eligible,
            "blockers": tuple(self.blockers),
        }


class BetrayalReactionEvaluation:

    def __init__(
        self,
        profile_key,
        attribution,
        state_before,
        state_deltas,
        state_after,
        candidates,
        roll,
        selected_intent,
    ):
        self.profile_key = str(profile_key)
        self.attribution = dict(attribution)
        self.state_before = dict(state_before)
        self.state_deltas = dict(state_deltas)
        self.state_after = dict(state_after)
        self.candidates = tuple(candidates)
        self.roll = float(roll)
        self.selected_intent = str(selected_intent)

    def as_dict(self):
        return {
            "profile_key": self.profile_key,
            "attribution": dict(self.attribution),
            "state_before": dict(self.state_before),
            "state_deltas": dict(self.state_deltas),
            "state_after": dict(self.state_after),
            "candidates": tuple(
                candidate.as_dict() for candidate in self.candidates
            ),
            "roll": self.roll,
            "selected_intent": self.selected_intent,
        }


BETRAYAL_PROFILES = TraitInfluenceRegistry()


for _profile in (
    TraitInfluence(
        BetrayalProfileKey.BALANCED,
        description="Neutral fallback when no personality profile is known.",
    ),
    TraitInfluence(
        BetrayalProfileKey.RELATIONSHIP_FIRST,
        attribution_multipliers={
            AttributionTarget.PARTNER: 0.35,
            AttributionTarget.RIVAL: 1.50,
            AttributionTarget.SELF: 0.70,
            AttributionTarget.CIRCUMSTANCE: 1.30,
        },
        state_multipliers={
            "attachment": 0.25,
            "trust": 0.45,
            "exclusivity": 0.70,
            "commitment": 0.25,
            "boundary": 0.35,
        },
        behavior_modifiers={
            BetrayalIntent.FORGIVE_PARTNER: 30,
            BetrayalIntent.SEEK_REASSURANCE: 20,
            BetrayalIntent.CLING_TO_PARTNER: 18,
            BetrayalIntent.CONFRONT_RIVAL: 25,
            BetrayalIntent.CONFRONT_PARTNER: -15,
            BetrayalIntent.BREAK_UP: -35,
            BetrayalIntent.ENDURE_SILENTLY: 18,
        },
        description="Protects the relationship, minimizes partner blame.",
    ),
    TraitInfluence(
        BetrayalProfileKey.BOUNDARY_FIRST,
        attribution_multipliers={
            AttributionTarget.PARTNER: 1.40,
            AttributionTarget.RIVAL: 0.80,
            AttributionTarget.SELF: 0.35,
            AttributionTarget.CIRCUMSTANCE: 0.30,
        },
        state_multipliers={
            "attachment": 1.10,
            "trust": 1.30,
            "exclusivity": 1.10,
            "commitment": 1.10,
            "boundary": 1.40,
        },
        behavior_modifiers={
            BetrayalIntent.FORGIVE_PARTNER: -30,
            BetrayalIntent.SEEK_REASSURANCE: -8,
            BetrayalIntent.CLING_TO_PARTNER: -20,
            BetrayalIntent.CONFRONT_PARTNER: 30,
            BetrayalIntent.CONFRONT_RIVAL: 4,
            BetrayalIntent.BREAK_UP: 25,
            BetrayalIntent.ENDURE_SILENTLY: -25,
        },
        description="Holds the partner responsible and protects boundaries.",
    ),
    TraitInfluence(
        BetrayalProfileKey.RIVAL_BLAMING,
        attribution_multipliers={
            AttributionTarget.PARTNER: 0.45,
            AttributionTarget.RIVAL: 1.90,
            AttributionTarget.SELF: 0.35,
            AttributionTarget.CIRCUMSTANCE: 0.45,
        },
        state_multipliers={
            "attachment": 0.50,
            "trust": 0.70,
            "exclusivity": 1.40,
            "commitment": 0.60,
            "boundary": 1.15,
        },
        behavior_modifiers={
            BetrayalIntent.FORGIVE_PARTNER: 8,
            BetrayalIntent.SEEK_REASSURANCE: 15,
            BetrayalIntent.CLING_TO_PARTNER: 20,
            BetrayalIntent.CONFRONT_PARTNER: -10,
            BetrayalIntent.CONFRONT_RIVAL: 35,
            BetrayalIntent.BREAK_UP: -22,
            BetrayalIntent.ENDURE_SILENTLY: 4,
        },
        description="Defends the bond and directs hostility toward the rival.",
    ),
):
    BETRAYAL_PROFILES.register(_profile)


BASE_ATTRIBUTION = {
    AttributionTarget.PARTNER: 50.0,
    AttributionTarget.RIVAL: 30.0,
    AttributionTarget.SELF: 5.0,
    AttributionTarget.CIRCUMSTANCE: 15.0,
}

BASE_STATE_DELTAS = {
    "attachment": -10.0,
    "trust": -40.0,
    "exclusivity": 12.0,
    "commitment": -20.0,
    "boundary": 20.0,
}

BREAKUP_UTILITY_MODEL_KEY = "core.relationship.break_up.after_betrayal.v1"
BREAKUP_UTILITY_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        BREAKUP_UTILITY_MODEL_KEY,
        base=4.0,
        factors=(
            UtilityFactor(
                "partner_blame",
                "interpretation.partner_blame",
                0.28,
            ),
            UtilityFactor("boundary", "state.boundary", 0.30),
            UtilityFactor(
                "distrust",
                "state.trust",
                0.22,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "exclusivity_violation",
                "state.exclusivity",
                0.10,
            ),
            UtilityFactor(
                "known_betrayals",
                "history.known_betrayal_count",
                2.0,
                maximum=3.0,
            ),
            UtilityFactor(
                "broken_promises",
                "history.known_broken_promise_count",
                10.0,
                maximum=3.0,
            ),
            UtilityFactor(
                "low_attachment",
                "state.attachment",
                0.16,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "low_commitment",
                "state.commitment",
                0.18,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "severe_safety_event",
                "context.severe_safety_event",
                40.0,
            ),
            UtilityFactor(
                "permanent_devotion",
                "context.permanently_devoted",
                -35.0,
            ),
        ),
        gates=(
            UtilityGate(
                "permanent_devotion_protective_separation_gate",
                "context.breakup_allowed",
            ),
        ),
    )
)


def build_attribution(profile):
    return _normalized_percentages({
        target: BASE_ATTRIBUTION[target]
        * profile.attribution_multipliers[target]
        for target in AttributionTarget.ALL
    })


def build_state_deltas(profile, attribution, severity=100.0):
    severity_factor = _clamp(severity, 0.0, 100.0) / 100.0
    partner_factor = attribution[AttributionTarget.PARTNER] / 100.0
    deltas = {}
    for dimension, base_delta in BASE_STATE_DELTAS.items():
        responsibility_factor = (
            partner_factor
            if base_delta < 0.0
            else 1.0
        )
        deltas[dimension] = (
            base_delta
            * severity_factor
            * responsibility_factor
            * profile.state_multiplier(dimension)
        )
    return deltas


def apply_state_deltas(state, deltas):
    return {
        dimension: _clamp(
            _state_value(state, dimension) + deltas.get(dimension, 0.0),
            0.0,
            100.0,
        )
        for dimension in BASE_STATE_DELTAS
    }


def _candidate(
    profile,
    intent,
    terms,
    eligible=True,
    blockers=None,
):
    all_terms = tuple(terms) + (
        ("personality_modifier", profile.behavior_modifier(intent)),
    )
    return BetrayalBehaviorCandidate(
        intent,
        sum(value for _, value in all_terms),
        terms=all_terms,
        eligible=eligible,
        blockers=blockers,
    )


def _context_number(context, key, default=0.0):
    try:
        return max(0.0, float(dict(context or {}).get(key, default)))
    except (TypeError, ValueError):
        return max(0.0, float(default))


def _breakup_candidate(
    profile,
    attribution,
    state_after,
    behavior_context,
):
    attachment = _state_value(state_after, "attachment")
    trust = _state_value(state_after, "trust")
    exclusivity = _state_value(state_after, "exclusivity")
    commitment = _state_value(state_after, "commitment")
    boundary = _state_value(state_after, "boundary")
    partner_blame = attribution[AttributionTarget.PARTNER]
    known_betrayals = _context_number(
        behavior_context,
        "known_betrayal_count",
    )
    broken_promises = _context_number(
        behavior_context,
        "known_broken_promise_count",
    )
    repeat_betrayals = max(0.0, known_betrayals - 1.0)
    bounded_repeats = min(3.0, repeat_betrayals)
    permanently_devoted = bool(
        dict(behavior_context or {}).get("permanently_devoted", False)
    )
    severe_safety_event = bool(
        dict(behavior_context or {}).get("severe_safety_event", False)
    )
    protective_separation = (
        severe_safety_event
        or (
            trust <= 20.0
            and boundary >= 80.0
            and partner_blame >= 60.0
            and (known_betrayals >= 2.0 or broken_promises >= 2.0)
        )
    )
    result = BREAKUP_UTILITY_MODEL.evaluate(
        {
            "state": {
                "attachment": attachment,
                "trust": trust,
                "exclusivity": exclusivity,
                "commitment": commitment,
                "boundary": boundary,
            },
            "history": {
                "known_betrayal_count": known_betrayals,
                "known_broken_promise_count": broken_promises,
            },
            "interpretation": {
                "partner_blame": partner_blame,
            },
            "context": {
                "permanently_devoted": permanently_devoted,
                "severe_safety_event": severe_safety_event,
                "protective_separation": protective_separation,
                "breakup_allowed": (
                    not permanently_devoted or protective_separation
                ),
            },
        },
        extra_terms=(
            # Repeated betrayal is pressure, not a universal auto-breakup.
            # The same second incident therefore pushes a high-boundary Sim
            # much harder than a low-boundary, highly attached Sim.
            (
                "repeat_boundary_escalation",
                bounded_repeats * (boundary / 100.0) * 18.0,
            ),
            (
                "repeat_distrust_escalation",
                bounded_repeats * ((100.0 - trust) / 100.0) * 8.0,
            ),
            (
                "repeat_attachment_resistance",
                bounded_repeats * (attachment / 100.0) * -10.0,
            ),
            (
                "repeat_commitment_resistance",
                bounded_repeats * (commitment / 100.0) * -8.0,
            ),
            (
                "personality_modifier",
                profile.behavior_modifier(BetrayalIntent.BREAK_UP),
            ),
        ),
    )
    return BetrayalBehaviorCandidate(
        BetrayalIntent.BREAK_UP,
        result.score,
        terms=result.terms,
        eligible=result.eligible,
        blockers=result.blockers,
    )


def score_behaviors(
    profile,
    attribution,
    state_after,
    behavior_context=None,
):
    attachment = _state_value(state_after, "attachment")
    trust = _state_value(state_after, "trust")
    exclusivity = _state_value(state_after, "exclusivity")
    commitment = _state_value(state_after, "commitment")
    boundary = _state_value(state_after, "boundary")
    partner_blame = attribution[AttributionTarget.PARTNER]
    rival_blame = attribution[AttributionTarget.RIVAL]
    return (
        _candidate(profile, BetrayalIntent.FORGIVE_PARTNER, (
            ("base", 12.0),
            ("attachment", attachment * 0.30),
            ("commitment", commitment * 0.24),
            ("remaining_trust", trust * 0.10),
            ("low_partner_blame", (100.0 - partner_blame) * 0.18),
        )),
        _candidate(profile, BetrayalIntent.SEEK_REASSURANCE, (
            ("base", 10.0),
            ("attachment", attachment * 0.22),
            ("exclusivity", exclusivity * 0.18),
            ("distrust", (100.0 - trust) * 0.14),
        )),
        _candidate(profile, BetrayalIntent.CLING_TO_PARTNER, (
            ("base", 6.0),
            ("attachment", attachment * 0.30),
            ("commitment", commitment * 0.18),
            ("low_boundary", (100.0 - boundary) * 0.12),
        )),
        _candidate(profile, BetrayalIntent.CONFRONT_PARTNER, (
            ("base", 8.0),
            ("partner_blame", partner_blame * 0.52),
            ("boundary", boundary * 0.22),
            ("distrust", (100.0 - trust) * 0.14),
        )),
        _candidate(profile, BetrayalIntent.CONFRONT_RIVAL, (
            ("base", 8.0),
            ("rival_blame", rival_blame * 0.62),
            ("exclusivity", exclusivity * 0.20),
        )),
        _breakup_candidate(
            profile,
            attribution,
            state_after,
            behavior_context,
        ),
        _candidate(profile, BetrayalIntent.ENDURE_SILENTLY, (
            ("base", 10.0),
            ("attachment", attachment * 0.17),
            ("commitment", commitment * 0.16),
            ("low_boundary", (100.0 - boundary) * 0.15),
        )),
    )


def select_candidate(candidates, roll=None):
    available = tuple(
        candidate
        for candidate in candidates
        if candidate.eligible and candidate.score > 0.0
    )
    if not available:
        return (None, 0.0)
    total = sum(candidate.score for candidate in available)
    normalized_roll = (
        random.random()
        if roll is None
        else _clamp(roll, 0.0, 0.999999)
    )
    cursor = normalized_roll * total
    selected = available[-1]
    running = 0.0
    for candidate in available:
        running += candidate.score
        if cursor < running:
            selected = candidate
            break
    return (selected, normalized_roll)


def evaluate_caught_betrayal(
    state,
    profile_key=BetrayalProfileKey.BALANCED,
    severity=100.0,
    roll=None,
    behavior_context=None,
):
    profile = BETRAYAL_PROFILES.require(profile_key)
    state_before = {
        dimension: _state_value(state, dimension)
        for dimension in BASE_STATE_DELTAS
    }
    attribution = build_attribution(profile)
    deltas = build_state_deltas(profile, attribution, severity=severity)
    state_after = apply_state_deltas(state_before, deltas)
    candidates = score_behaviors(
        profile,
        attribution,
        state_after,
        behavior_context=behavior_context,
    )
    selected, normalized_roll = select_candidate(candidates, roll=roll)
    return BetrayalReactionEvaluation(
        profile.key,
        attribution,
        state_before,
        deltas,
        state_after,
        candidates,
        normalized_roll,
        selected.intent if selected is not None else BetrayalIntent.ENDURE_SILENTLY,
    )

"""Read-only migration shadow for the caught-betrayal influence model.

The established betrayal evaluator remains authoritative while this module
re-expresses the same event and personality parameters through the reusable
tag-driven influence model.  It must never mutate relationship state or choose
the action that is sent to the game.
"""

from fgeh_cheatingharder_betrayal_reactions import (
    BASE_ATTRIBUTION,
    BASE_STATE_DELTAS,
    BetrayalIntent,
    BetrayalProfileKey,
    BetrayalReactionEvaluation,
    evaluate_caught_betrayal,
    score_behaviors,
    select_candidate,
)
from fgeh_cheatingharder_influence_model import (
    AttributionTarget,
    EventImpactDefinition,
    InfluenceRegistry,
    RelationshipDimension,
    RelationshipEventStimulus,
    RelationshipEventTag,
    TraitInfluenceDefinition,
    evaluate_event_impact,
    resolve_attribution,
    resolve_behavior_modifier,
)


CAUGHT_BETRAYAL_IMPACT_KEY = "core.caught_betrayal.v1"
SHADOW_VERSION = 1
_EVENT_TAGS = (
    RelationshipEventTag.BETRAYAL,
    RelationshipEventTag.BOUNDARY_BREAK,
    RelationshipEventTag.ROMANCE,
)
_COMPARISON_TOLERANCE = 0.000001


BETRAYAL_INFLUENCE_REGISTRY = InfluenceRegistry()
BETRAYAL_INFLUENCE_REGISTRY.register_event(EventImpactDefinition(
    CAUGHT_BETRAYAL_IMPACT_KEY,
    tags=_EVENT_TAGS,
    base_state_deltas=BASE_STATE_DELTAS,
    responsibility_sensitive_dimensions=(
        RelationshipDimension.ATTACHMENT,
        RelationshipDimension.TRUST,
        RelationshipDimension.COMMITMENT,
    ),
    description=(
        "A known romantic betrayal interpreted by the affected observer."
    ),
))


def _tagged(values):
    return {RelationshipEventTag.BETRAYAL: dict(values)}


for _influence in (
    TraitInfluenceDefinition(
        BetrayalProfileKey.BALANCED,
        description="Neutral betrayal interpretation and response.",
    ),
    TraitInfluenceDefinition(
        BetrayalProfileKey.RELATIONSHIP_FIRST,
        attribution_tag_multipliers=_tagged({
            AttributionTarget.PARTNER: 0.35,
            AttributionTarget.RIVAL: 1.50,
            AttributionTarget.SELF: 0.70,
            AttributionTarget.CIRCUMSTANCE: 1.30,
        }),
        state_tag_multipliers=_tagged({
            RelationshipDimension.ATTACHMENT: 0.25,
            RelationshipDimension.TRUST: 0.45,
            RelationshipDimension.EXCLUSIVITY: 0.70,
            RelationshipDimension.COMMITMENT: 0.25,
            RelationshipDimension.BOUNDARY: 0.35,
        }),
        behavior_tag_modifiers=_tagged({
            BetrayalIntent.FORGIVE_PARTNER: 30,
            BetrayalIntent.SEEK_REASSURANCE: 20,
            BetrayalIntent.CLING_TO_PARTNER: 18,
            BetrayalIntent.CONFRONT_RIVAL: 25,
            BetrayalIntent.CONFRONT_PARTNER: -15,
            BetrayalIntent.BREAK_UP: -35,
            BetrayalIntent.ENDURE_SILENTLY: 18,
        }),
        description="Protects the relationship and minimizes partner blame.",
    ),
    TraitInfluenceDefinition(
        BetrayalProfileKey.BOUNDARY_FIRST,
        attribution_tag_multipliers=_tagged({
            AttributionTarget.PARTNER: 1.40,
            AttributionTarget.RIVAL: 0.80,
            AttributionTarget.SELF: 0.35,
            AttributionTarget.CIRCUMSTANCE: 0.30,
        }),
        state_tag_multipliers=_tagged({
            RelationshipDimension.ATTACHMENT: 1.10,
            RelationshipDimension.TRUST: 1.30,
            RelationshipDimension.EXCLUSIVITY: 1.10,
            RelationshipDimension.COMMITMENT: 1.10,
            RelationshipDimension.BOUNDARY: 1.40,
        }),
        behavior_tag_modifiers=_tagged({
            BetrayalIntent.FORGIVE_PARTNER: -30,
            BetrayalIntent.SEEK_REASSURANCE: -8,
            BetrayalIntent.CLING_TO_PARTNER: -20,
            BetrayalIntent.CONFRONT_PARTNER: 30,
            BetrayalIntent.CONFRONT_RIVAL: 4,
            BetrayalIntent.BREAK_UP: 25,
            BetrayalIntent.ENDURE_SILENTLY: -25,
        }),
        description="Holds the partner responsible and protects boundaries.",
    ),
    TraitInfluenceDefinition(
        BetrayalProfileKey.RIVAL_BLAMING,
        attribution_tag_multipliers=_tagged({
            AttributionTarget.PARTNER: 0.45,
            AttributionTarget.RIVAL: 1.90,
            AttributionTarget.SELF: 0.35,
            AttributionTarget.CIRCUMSTANCE: 0.45,
        }),
        state_tag_multipliers=_tagged({
            RelationshipDimension.ATTACHMENT: 0.50,
            RelationshipDimension.TRUST: 0.70,
            RelationshipDimension.EXCLUSIVITY: 1.40,
            RelationshipDimension.COMMITMENT: 0.60,
            RelationshipDimension.BOUNDARY: 1.15,
        }),
        behavior_tag_modifiers=_tagged({
            BetrayalIntent.FORGIVE_PARTNER: 8,
            BetrayalIntent.SEEK_REASSURANCE: 15,
            BetrayalIntent.CLING_TO_PARTNER: 20,
            BetrayalIntent.CONFRONT_PARTNER: -10,
            BetrayalIntent.CONFRONT_RIVAL: 35,
            BetrayalIntent.BREAK_UP: -22,
            BetrayalIntent.ENDURE_SILENTLY: 4,
        }),
        description="Defends the bond and directs blame toward the rival.",
    ),
):
    BETRAYAL_INFLUENCE_REGISTRY.register_trait(_influence)


class _GenericBehaviorInfluenceAdapter:
    """Temporary adapter for the established base behavior formula."""

    def __init__(self, influence, event_tags):
        self._influence = influence
        self._event_tags = tuple(event_tags)

    def behavior_modifier(self, intent):
        score, _trace = resolve_behavior_modifier(
            (str(intent),),
            self._event_tags,
            (self._influence,),
        )
        return score


def _candidate_scores(candidates):
    return {
        str(candidate.intent): float(candidate.score)
        for candidate in tuple(candidates or ())
    }


def _maximum_numeric_delta(first, second):
    keys = set(dict(first or {})).union(dict(second or {}))
    if not keys:
        return 0.0
    return max(
        abs(
            float(dict(first or {}).get(key, 0.0))
            - float(dict(second or {}).get(key, 0.0))
        )
        for key in keys
    )


def evaluate_caught_betrayal_influence(
    state,
    profile_key,
    severity=100.0,
    roll=None,
    behavior_context=None,
):
    """Evaluate betrayal through the registered tag-driven influence model."""
    influence = BETRAYAL_INFLUENCE_REGISTRY.trait(profile_key)
    if influence is None:
        influence = BETRAYAL_INFLUENCE_REGISTRY.trait(
            BetrayalProfileKey.BALANCED
        )
    event_definition = BETRAYAL_INFLUENCE_REGISTRY.event(
        CAUGHT_BETRAYAL_IMPACT_KEY
    )
    attribution = resolve_attribution(
        BASE_ATTRIBUTION,
        _EVENT_TAGS,
        (influence,),
    )
    stimulus = RelationshipEventStimulus(
        "caught_cheating",
        tags=_EVENT_TAGS,
        severity=severity,
        confidence=100.0,
        partner_responsibility=attribution[AttributionTarget.PARTNER],
    )
    impact = evaluate_event_impact(
        event_definition,
        stimulus,
        state,
        influences=(influence,),
    )
    behavior_profile = _GenericBehaviorInfluenceAdapter(
        influence,
        impact.event_tags,
    )
    candidates = score_behaviors(
        behavior_profile,
        attribution,
        impact.state_after,
        behavior_context=behavior_context,
    )
    selected, normalized_roll = select_candidate(
        candidates,
        roll=roll,
    )
    selected_intent = (
        selected.intent
        if selected is not None
        else BetrayalIntent.ENDURE_SILENTLY
    )
    return BetrayalReactionEvaluation(
        influence.key,
        attribution,
        impact.state_before,
        impact.state_deltas,
        impact.state_after,
        candidates,
        normalized_roll,
        selected_intent,
    )


def evaluate_betrayal_influence_shadow(
    legacy_evaluation,
    state,
    profile_key,
    severity=100.0,
    behavior_context=None,
):
    """Compare the legacy baseline with the authoritative generic model."""
    influence_evaluation = evaluate_caught_betrayal_influence(
        state,
        profile_key=profile_key,
        severity=severity,
        roll=legacy_evaluation.roll,
        behavior_context=behavior_context,
    )
    legacy_candidate_scores = _candidate_scores(
        legacy_evaluation.candidates
    )
    attribution_delta = _maximum_numeric_delta(
        legacy_evaluation.attribution,
        influence_evaluation.attribution,
    )
    state_delta = _maximum_numeric_delta(
        legacy_evaluation.state_deltas,
        influence_evaluation.state_deltas,
    )
    candidate_delta = _maximum_numeric_delta(
        legacy_candidate_scores,
        _candidate_scores(influence_evaluation.candidates),
    )
    selected_matches = (
        str(legacy_evaluation.selected_intent)
        == str(influence_evaluation.selected_intent)
    )
    matches = (
        attribution_delta <= _COMPARISON_TOLERANCE
        and state_delta <= _COMPARISON_TOLERANCE
        and candidate_delta <= _COMPARISON_TOLERANCE
        and selected_matches
    )
    return {
        "shadow_version": SHADOW_VERSION,
        "mode": "read_only",
        "authoritative_model": "tag_driven_influence",
        "comparison_baseline": "legacy_betrayal",
        "profile_key": influence_evaluation.profile_key,
        "status": "match" if matches else "mismatch",
        "matches": matches,
        "attribution": dict(influence_evaluation.attribution),
        "state_deltas": dict(influence_evaluation.state_deltas),
        "state_after": dict(influence_evaluation.state_after),
        "behavior_candidates": tuple(
            candidate.as_dict()
            for candidate in influence_evaluation.candidates
        ),
        "roll": influence_evaluation.roll,
        "selected_intent": str(
            influence_evaluation.selected_intent
        ),
        "comparison": {
            "attribution_max_abs_delta": attribution_delta,
            "state_delta_max_abs_delta": state_delta,
            "candidate_score_max_abs_delta": candidate_delta,
            "selected_matches": selected_matches,
            "legacy_selected_intent": str(
                legacy_evaluation.selected_intent
            ),
            "shadow_selected_intent": str(
                influence_evaluation.selected_intent
            ),
        },
    }


def evaluate_betrayal_shadow_matrix(
    active_legacy_evaluation,
    state,
    active_profile_key,
    severity=100.0,
    behavior_context=None,
):
    """Compare every registered profile without executing counterfactuals.

    Only compact comparison evidence is returned so a real event does not
    persist four copies of the full candidate trace in the romantic ledger.
    """
    profile_keys = (
        BetrayalProfileKey.BALANCED,
    ) + BetrayalProfileKey.TEST_PROFILES
    results = {}
    active_profile_key = str(active_profile_key)
    for profile_key in profile_keys:
        legacy_evaluation = (
            active_legacy_evaluation
            if str(profile_key) == active_profile_key
            else evaluate_caught_betrayal(
                state,
                profile_key=profile_key,
                severity=severity,
                roll=active_legacy_evaluation.roll,
                behavior_context=behavior_context,
            )
        )
        shadow = evaluate_betrayal_influence_shadow(
            legacy_evaluation,
            state,
            profile_key=profile_key,
            severity=severity,
            behavior_context=behavior_context,
        )
        results[str(profile_key)] = {
            "profile_key": str(profile_key),
            "active_profile": str(profile_key) == active_profile_key,
            "status": shadow["status"],
            "matches": shadow["matches"],
            "comparison": dict(shadow["comparison"]),
        }
    return results

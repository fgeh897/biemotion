"""Pure utility scoring and weighted choice for relationship behaviors."""

import random

from fgeh_cheatingharder_domain import (
    BehaviorCandidate,
    BehaviorIntent,
    DecisionRecord,
    IntentType,
    OpportunityType,
)
from fgeh_cheatingharder_utility_model import (
    RELATIONSHIP_UTILITY_MODELS,
    UtilityCandidateDefinition,
    UtilityFactor,
    UtilityGate,
)


REPAIR_RELATIONSHIP_MODEL_KEY = "core.relationship.repair.periodic.v1"
REPAIR_RELATIONSHIP_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        REPAIR_RELATIONSHIP_MODEL_KEY,
        base=-15.0,
        factors=(
            UtilityFactor("attachment", "state.attachment", 0.25),
            UtilityFactor("commitment", "state.commitment", 0.18),
            UtilityFactor(
                "distrust_needs_reassurance",
                "state.trust",
                0.25,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "soft_boundary",
                "state.boundary",
                0.05,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
        ),
    )
)

AUTONOMOUS_BREAKUP_MODEL_KEY = "core.relationship.break_up.periodic.v1"
AUTONOMOUS_BREAKUP_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        AUTONOMOUS_BREAKUP_MODEL_KEY,
        base=-25.0,
        factors=(
            UtilityFactor(
                "low_commitment",
                "state.commitment",
                0.45,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "low_attachment",
                "state.attachment",
                0.30,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor("firm_boundary", "state.boundary", 0.25),
            UtilityFactor(
                "distrust",
                "state.trust",
                0.18,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
        ),
        gates=(
            UtilityGate(
                "permanent_devotion_prohibits_initiation",
                "context.permanently_devoted",
                requirement=UtilityGate.REQUIRE_FALSE,
            ),
            UtilityGate(
                "autonomous_breakup_cooldown",
                "context.autonomous_breakup_cooldown",
                requirement=UtilityGate.REQUIRE_FALSE,
            ),
            UtilityGate(
                "pair_not_together_on_active_zone",
                "context.pair_together_on_active_zone",
            ),
            UtilityGate(
                "official_relationship_already_ended",
                "context.can_consider_breakup",
            ),
        ),
    )
)

CRISIS_SEEK_REASSURANCE_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        "core.relationship.crisis.seek_reassurance.v1",
        base=-12.0,
        factors=(
            UtilityFactor("attachment", "state.attachment", 0.34),
            UtilityFactor("commitment", "state.commitment", 0.20),
            UtilityFactor(
                "distrust_needs_confirmation",
                "state.trust",
                0.18,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "soft_boundary",
                "state.boundary",
                0.10,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor("crisis_severity", "context.crisis.severity", 0.15),
        ),
        gates=(
            UtilityGate("relationship_crisis_missing", "context.crisis.active"),
            UtilityGate("official_relationship_ended", "context.official"),
            UtilityGate("pair_not_together", "context.pair_together"),
        ),
    )
)

CRISIS_GIVE_SPACE_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        "core.relationship.crisis.give_space.v1",
        base=6.0,
        factors=(
            UtilityFactor("firm_boundary", "state.boundary", 0.27),
            UtilityFactor("trust_allows_distance", "state.trust", 0.10),
            UtilityFactor(
                "low_attachment",
                "state.attachment",
                0.10,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor("crisis_severity", "context.crisis.severity", 0.08),
        ),
        gates=(
            UtilityGate("relationship_crisis_missing", "context.crisis.active"),
            UtilityGate("official_relationship_ended", "context.official"),
        ),
    )
)

CRISIS_REPEAT_BREAKUP_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        "core.relationship.crisis.repeat_breakup.v1",
        base=-28.0,
        factors=(
            UtilityFactor(
                "low_commitment",
                "state.commitment",
                0.42,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "low_attachment",
                "state.attachment",
                0.28,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor("firm_boundary", "state.boundary", 0.28),
            UtilityFactor(
                "distrust",
                "state.trust",
                0.18,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor("crisis_severity", "context.crisis.severity", 0.14),
            UtilityFactor(
                "repeated_proposal_pressure",
                "context.crisis.proposal_count",
                6.0,
                maximum=5.0,
            ),
        ),
        gates=(
            UtilityGate("relationship_crisis_missing", "context.crisis.active"),
            UtilityGate("not_original_proposer", "context.is_proposer"),
            UtilityGate("official_relationship_ended", "context.official"),
            UtilityGate("pair_not_together", "context.pair_together"),
            UtilityGate(
                "permanent_devotion_prohibits_initiation",
                "context.permanently_devoted",
                requirement=UtilityGate.REQUIRE_FALSE,
            ),
        ),
    )
)


def build_wait_candidate(state, opportunity, context):
    if opportunity.opportunity_type != OpportunityType.RELATIONSHIP_RESPONSE:
        return BehaviorCandidate(
            IntentType.WAIT,
            0,
            eligible=False,
            blockers=("wrong_opportunity_type",),
        )
    terms = (
        ("base", 28.0),
        ("trust", state.get("trust") * 0.25),
        ("low_attachment", (100.0 - state.get("attachment")) * 0.10),
        ("low_exclusivity", (100.0 - state.get("exclusivity")) * 0.06),
    )
    return BehaviorCandidate(
        IntentType.WAIT,
        sum(value for _, value in terms),
        terms=terms,
        eligible=True,
    )


def build_repair_relationship_candidate(state, opportunity, context):
    """Score choosing the relationship over leaving it."""
    if opportunity.opportunity_type != OpportunityType.RELATIONSHIP_RESPONSE:
        return BehaviorCandidate(
            IntentType.REPAIR_RELATIONSHIP,
            0,
            eligible=False,
            blockers=("wrong_opportunity_type",),
        )
    if dict(context.get("relationship_crisis", {}) or {}).get("active"):
        return BehaviorCandidate(
            IntentType.REPAIR_RELATIONSHIP,
            0,
            eligible=False,
            blockers=("relationship_crisis_uses_visible_reassurance",),
        )
    result = REPAIR_RELATIONSHIP_MODEL.evaluate(
        {"state": state.as_dict()},
        extra_terms=((
            "event_repair_pressure",
            float(opportunity.context.get("repair_pressure", 0.0)),
        ),),
    )
    blockers = (
        result.blockers
        if result.score >= 5.0
        else result.blockers + ("repair_pressure_below_threshold",)
    )
    return BehaviorCandidate(
        IntentType.REPAIR_RELATIONSHIP,
        result.score if not blockers else 0.0,
        terms=result.terms,
        eligible=not blockers,
        blockers=blockers,
    )


def build_break_up_candidate(state, opportunity, context):
    """Score an autonomous breakup proposal from one directed relationship."""
    if opportunity.opportunity_type != OpportunityType.RELATIONSHIP_RESPONSE:
        return BehaviorCandidate(
            IntentType.BREAK_UP,
            0,
            eligible=False,
            blockers=("wrong_opportunity_type",),
        )
    if dict(context.get("relationship_crisis", {}) or {}).get("active"):
        return BehaviorCandidate(
            IntentType.BREAK_UP,
            0,
            eligible=False,
            blockers=("relationship_crisis_uses_repeat_breakup",),
        )

    known_affair_count = max(0.0, float(context.get("known_affair_count", 0.0)))
    exclusivity_violation = min(1.0, known_affair_count)
    transient_pressure = float(opportunity.context.get("exit_pressure", 0.0))
    result = AUTONOMOUS_BREAKUP_MODEL.evaluate(
        {
            "state": state.as_dict(),
            "context": {
                "permanently_devoted": context.get("is_only_beloved", False),
                "autonomous_breakup_cooldown": context.get(
                    "autonomous_breakup_cooldown",
                    False,
                ) and not bool(opportunity.context.get(
                    "debug_ignore_breakup_cooldown",
                    False,
                )),
                "pair_together_on_active_zone": (
                    context.get("observer_on_active_zone", False)
                    and context.get("partner_on_active_zone", False)
                ),
                "can_consider_breakup": (
                    bool(context.get("are_official_partners", False))
                    and opportunity.reason != "breakup_completed"
                ),
            },
        },
        extra_terms=(
            (
                "known_exclusivity_violation",
                state.get("exclusivity") * 0.20 * exclusivity_violation,
            ),
            ("transient_exit_pressure", transient_pressure),
        ),
    )
    blockers = result.blockers
    if result.score < 25.0:
        blockers = blockers + ("exit_pressure_below_threshold",)
    return BehaviorCandidate(
        IntentType.BREAK_UP,
        result.score if not blockers else 0.0,
        terms=result.terms,
        eligible=not blockers,
        blockers=blockers,
    )


def _crisis_model_values(state, context):
    crisis = dict(context.get("relationship_crisis", {}) or {})
    return {
        "state": state.as_dict(),
        "context": {
            "crisis": crisis,
            "official": bool(context.get("are_official_partners", False)),
            "pair_together": bool(
                context.get("observer_on_active_zone", False)
                and context.get("partner_on_active_zone", False)
            ),
            "is_proposer": crisis.get("role") == "proposer",
            "permanently_devoted": bool(context.get("is_only_beloved", False)),
        },
    }


def build_crisis_seek_reassurance_candidate(state, opportunity, context):
    if opportunity.opportunity_type != OpportunityType.RELATIONSHIP_RESPONSE:
        return BehaviorCandidate(
            IntentType.CRISIS_SEEK_REASSURANCE,
            0,
            eligible=False,
            blockers=("wrong_opportunity_type",),
        )
    crisis = dict(context.get("relationship_crisis", {}) or {})
    result = CRISIS_SEEK_REASSURANCE_MODEL.evaluate(
        _crisis_model_values(state, context),
        extra_terms=((
            "recipient_response_pressure",
            18.0 if crisis.get("role") == "recipient" else 4.0,
        ),),
    )
    return BehaviorCandidate(
        IntentType.CRISIS_SEEK_REASSURANCE,
        result.score,
        terms=result.terms,
        eligible=result.eligible,
        blockers=result.blockers,
    )


def build_crisis_give_space_candidate(state, opportunity, context):
    if opportunity.opportunity_type != OpportunityType.RELATIONSHIP_RESPONSE:
        return BehaviorCandidate(
            IntentType.CRISIS_GIVE_SPACE,
            0,
            eligible=False,
            blockers=("wrong_opportunity_type",),
        )
    crisis = dict(context.get("relationship_crisis", {}) or {})
    result = CRISIS_GIVE_SPACE_MODEL.evaluate(
        _crisis_model_values(state, context),
        extra_terms=((
            "proposer_space_preference",
            10.0 if crisis.get("role") == "proposer" else 0.0,
        ),),
    )
    return BehaviorCandidate(
        IntentType.CRISIS_GIVE_SPACE,
        result.score,
        terms=result.terms,
        eligible=result.eligible,
        blockers=result.blockers,
    )


def build_crisis_repeat_breakup_candidate(state, opportunity, context):
    if opportunity.opportunity_type != OpportunityType.RELATIONSHIP_RESPONSE:
        return BehaviorCandidate(
            IntentType.CRISIS_REPEAT_BREAKUP,
            0,
            eligible=False,
            blockers=("wrong_opportunity_type",),
        )
    result = CRISIS_REPEAT_BREAKUP_MODEL.evaluate(
        _crisis_model_values(state, context),
    )
    blockers = result.blockers
    if result.score < 25.0:
        blockers = blockers + ("repeat_breakup_pressure_below_threshold",)
    return BehaviorCandidate(
        IntentType.CRISIS_REPEAT_BREAKUP,
        result.score if not blockers else 0.0,
        terms=result.terms,
        eligible=not blockers,
        blockers=blockers,
    )


def build_visit_candidate(state, opportunity, context):
    blockers = []
    if opportunity.opportunity_type != OpportunityType.RELATIONSHIP_RESPONSE:
        blockers.append("wrong_opportunity_type")
    if not context.get("has_claim", False):
        blockers.append("claim_missing")
    if context.get("cooldown", False):
        blockers.append("cooldown_active")
    if context.get("active_route", False):
        blockers.append("route_already_active")
    if not context.get("partner_on_active_zone", False):
        blockers.append("partner_not_on_active_zone")
    if context.get("observer_on_active_zone", False):
        blockers.append("observer_already_on_active_zone")

    terms = (
        ("base", 18.0),
        ("attachment", state.get("attachment") * 0.18),
        ("exclusivity", state.get("exclusivity") * 0.16),
        ("distrust", (100.0 - state.get("trust")) * 0.28),
        ("commitment", state.get("commitment") * 0.08),
        ("boundary_sensitivity", state.get("boundary") * 0.05),
        ("event_urgency", opportunity.urgency),
        ("known_original_affair", context.get("known_affair_count", 0) * 20.0),
    )
    return BehaviorCandidate(
        IntentType.VISIT_UNANNOUNCED,
        0.0 if blockers else sum(value for _, value in terms),
        terms=terms,
        eligible=not blockers,
        blockers=blockers,
    )


def build_longing_wait_candidate(state, opportunity, context):
    blockers = []
    if opportunity.opportunity_type != OpportunityType.DEVOTION_LONGING:
        blockers.append("wrong_opportunity_type")
    intensity = float(context.get("longing_intensity", 0.0))
    terms = (
        ("base", 8.0),
        ("not_yet_overwhelming", (100.0 - intensity) * 0.12),
    )
    return BehaviorCandidate(
        IntentType.LONGING_WAIT,
        0.0 if blockers else sum(value for _, value in terms),
        terms=terms,
        eligible=not blockers,
        blockers=blockers,
    )


def build_seek_beloved_candidate(state, opportunity, context):
    blockers = []
    if opportunity.opportunity_type != OpportunityType.DEVOTION_LONGING:
        blockers.append("wrong_opportunity_type")
    if not context.get("is_only_beloved", False):
        blockers.append("devotion_bond_missing")
    if not context.get("both_on_active_zone", False):
        blockers.append("not_together_on_active_zone")
    if context.get("seek_cooldown", False):
        blockers.append("seek_cooldown_active")
    if not context.get("owner_can_autonomously_seek", False):
        blockers.append("owner_unavailable")

    intensity = float(context.get("longing_intensity", 0.0))
    terms = (
        ("base", 16.0),
        ("attachment", state.get("attachment") * 0.30),
        ("longing_intensity", intensity * 0.70),
        ("commitment", state.get("commitment") * 0.10),
    )
    return BehaviorCandidate(
        IntentType.SEEK_BELOVED,
        0.0 if blockers else sum(value for _, value in terms),
        terms=terms,
        eligible=not blockers,
        blockers=blockers,
    )


def apply_score_terms(candidate, additional_terms):
    terms = tuple(candidate.terms) + tuple(additional_terms or ())
    score = 0.0 if not candidate.eligible else sum(value for _, value in terms)
    return BehaviorCandidate(
        candidate.intent_type,
        score,
        terms=terms,
        eligible=candidate.eligible,
        blockers=candidate.blockers,
    )


def select_behavior(opportunity, state, candidates, roll=None):
    """Select exactly one positive candidate using a normalized utility roll."""
    candidates = tuple(candidate for candidate in candidates if candidate.score > 0.0)
    if not candidates:
        return (None, None)
    total = sum(candidate.score for candidate in candidates)
    normalized_roll = random.random() if roll is None else max(0.0, min(0.999999, float(roll)))
    cursor = normalized_roll * total
    selected = candidates[-1]
    running = 0.0
    for candidate in candidates:
        running += candidate.score
        if cursor < running:
            selected = candidate
            break
    record = DecisionRecord(
        opportunity.observer_id,
        opportunity.partner_id,
        opportunity.reason,
        state.as_dict(),
        candidates,
        normalized_roll,
        total,
        selected.intent_type,
    )
    intent = BehaviorIntent(
        selected.intent_type,
        opportunity.observer_id,
        opportunity.partner_id,
        opportunity.reason,
        context={
            "decision": record.as_dict(),
            "opportunity_context": dict(opportunity.context),
        },
    )
    return (intent, record)

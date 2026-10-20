"""Ledger, knowledge, state, and summary rules for repair actions."""

from fgeh_cheatingharder_domain import EventType
from fgeh_cheatingharder_journal_catalog import (
    get_journal_event_definition,
)
from fgeh_cheatingharder_memory_models import (
    AcquisitionMode,
    BeliefDraft,
    BeliefStatus,
    ClaimDraft,
    ClaimTruthStatus,
    DirectedStateDelta,
    InterpretationDraft,
    ParticipantRole,
    StateChangeMode,
    SummaryMutation,
)
from fgeh_cheatingharder_memory_registry import RomanticMemoryRegistry
from fgeh_cheatingharder_repair import get_repair_action


CLAIM_REPAIR_ACTION_RESOLVED = "relationship_repair_action_resolved"
INTERPRETATION_REPAIR_ACCEPTED = "repair_effort_was_accepted"
INTERPRETATION_REPAIR_REJECTED = "repair_effort_was_rejected"


def _single_participant(event, role):
    values = event.participants_for(role)
    return values[0] if values else None


def _actor_target(event):
    return (
        _single_participant(event, ParticipantRole.ACTOR),
        _single_participant(event, ParticipantRole.TARGET),
    )


def _repair_claims(context):
    actor_id, target_id = _actor_target(context.event)
    action_type = context.event.payload.get("repair_action_type")
    if (
        actor_id is None
        or target_id is None
        or get_repair_action(action_type) is None
    ):
        return ()
    return (
        ClaimDraft(
            CLAIM_REPAIR_ACTION_RESOLVED,
            subject_ids=(actor_id,),
            object_ids=(target_id,),
            value={
                "repair_action_type": action_type,
                "accepted": bool(
                    context.event.payload.get("accepted", False)
                ),
            },
            truth_status=ClaimTruthStatus.SUPPORTED,
            supporting_event_ids=(context.event.event_id,),
            provenance="direct_repair_participation",
            stable_key="{}:repair-resolution".format(
                context.event.event_id
            ),
        ),
    )


def _repair_knowledge(context):
    actor_id, target_id = _actor_target(context.event)
    if actor_id is None or target_id is None:
        return ()
    beliefs = []
    for claim in context.claims:
        if claim.claim_type != CLAIM_REPAIR_ACTION_RESOLVED:
            continue
        for knower_id in (actor_id, target_id):
            beliefs.append(
                BeliefDraft(
                    knower_id,
                    claim.claim_id,
                    AcquisitionMode.PARTICIPANT,
                    status=BeliefStatus.CONFIRMED,
                    credibility=100,
                    confidence=100,
                    acquisition_event_id=context.event.event_id,
                    acquired_at=context.event.occurred_at,
                    stable_key="{}:participant:{}".format(
                        claim.claim_id,
                        knower_id,
                    ),
                )
            )
    return tuple(beliefs)


def _repair_interpretations(context):
    accepted = bool(context.event.payload.get("accepted", False))
    interpretation_type = (
        INTERPRETATION_REPAIR_ACCEPTED
        if accepted
        else INTERPRETATION_REPAIR_REJECTED
    )
    return tuple(
        InterpretationDraft(
            belief.knower_id,
            belief.claim_id,
            interpretation_type,
            confidence=belief.confidence,
            rule_id="core.relationship_repair.meaning.v1",
            source_belief_id=belief.belief_id,
            created_at=context.event.occurred_at,
            details={
                "repair_action_type": context.event.payload.get(
                    "repair_action_type"
                ),
                "accepted": accepted,
            },
            stable_key="{}:repair-meaning".format(belief.belief_id),
        )
        for belief in context.beliefs
    )


def _repair_state(context):
    actor_id, target_id = _actor_target(context.event)
    definition = get_repair_action(
        context.event.payload.get("repair_action_type")
    )
    if actor_id is None or target_id is None or definition is None:
        return ()
    actor_effects, recipient_effects = definition.effects(
        context.event.payload.get("accepted", False)
    )
    effects_by_edge = {
        (actor_id, target_id): actor_effects,
        (target_id, actor_id): recipient_effects,
    }
    beliefs_by_knower = {
        belief.knower_id: belief
        for belief in context.beliefs
    }
    interpretations_by_knower = {
        interpretation.knower_id: interpretation
        for interpretation in context.interpretations
    }
    deltas = []
    for observer_id, partner_id in context.directed_edges():
        belief = beliefs_by_knower.get(observer_id)
        interpretation = interpretations_by_knower.get(observer_id)
        if belief is None or interpretation is None:
            continue
        for dimension, value in effects_by_edge.get(
            (observer_id, partner_id),
            (),
        ):
            deltas.append(
                DirectedStateDelta(
                    observer_id,
                    partner_id,
                    dimension,
                    value,
                    "repair_action:{}:{}".format(
                        definition.action_type,
                        "accepted"
                        if context.event.payload.get("accepted", False)
                        else "rejected",
                    ),
                    mode=StateChangeMode.ADD,
                    event_id=context.event.event_id,
                    claim_id=belief.claim_id,
                    belief_id=belief.belief_id,
                    interpretation_id=interpretation.interpretation_id,
                )
            )
    return tuple(deltas)


def _repair_summary(context):
    actor_id, target_id = _actor_target(context.event)
    if actor_id is None or target_id is None:
        return ()
    accepted = bool(context.event.payload.get("accepted", False))
    action_type = str(
        context.event.payload.get("repair_action_type", "unknown")
    )
    mutations = []
    for first_id, second_id in (
        (actor_id, target_id),
        (target_id, actor_id),
    ):
        mutations.extend((
            SummaryMutation(
                first_id,
                second_id,
                SummaryMutation.INCREMENT,
                "repair_actions_observed",
                1,
            ),
            SummaryMutation(
                first_id,
                second_id,
                SummaryMutation.INCREMENT,
                (
                    "accepted_repair_actions"
                    if accepted
                    else "rejected_repair_actions"
                ),
                1,
            ),
            SummaryMutation(
                first_id,
                second_id,
                SummaryMutation.SET_TIMESTAMP,
                "last_repair_action_at",
                context.event.occurred_at,
            ),
            SummaryMutation(
                first_id,
                second_id,
                SummaryMutation.SET_FLAG,
                "last_repair_action_type:{}".format(action_type),
                True,
            ),
        ))
    return tuple(mutations)


def register_repair_memory_rules(registry):
    event_types = (EventType.REPAIR_ACTION_RESOLVED,)
    registry.register_event_definition(
        get_journal_event_definition(EventType.REPAIR_ACTION_RESOLVED)
    )
    registry.register_rule(
        RomanticMemoryRegistry.CLAIM_STAGE,
        "core.repair.claim",
        _repair_claims,
        event_types=event_types,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.KNOWLEDGE_STAGE,
        "core.repair.knowledge",
        _repair_knowledge,
        event_types=event_types,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.INTERPRETATION_STAGE,
        "core.repair.interpretation",
        _repair_interpretations,
        event_types=event_types,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.STATE_STAGE,
        "core.repair.state",
        _repair_state,
        event_types=event_types,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.SUMMARY_STAGE,
        "core.repair.summary",
        _repair_summary,
        event_types=event_types,
        priority=100,
    )
    return registry

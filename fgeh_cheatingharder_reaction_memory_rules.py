"""Memory rules for model-selected visible relationship reactions.

The resolved relationship action and the chosen emotional expression are
different facts.  The former may be known by both participants; the latter is
private cognition owned by the Sim who receives the Buff.  Keeping them as
linked events prevents a UI expression from being mistaken for objective
relationship truth.
"""

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
    InterpretationDraft,
    ParticipantRole,
    SummaryMutation,
)
from fgeh_cheatingharder_memory_registry import RomanticMemoryRegistry


CLAIM_REACTION_EXPRESSION_SELECTED = "relationship_reaction_expression_selected"


def _single_participant(event, role):
    values = event.participants_for(role)
    return values[0] if values else None


def _reaction_claims(context):
    observer_id = _single_participant(
        context.event,
        ParticipantRole.OBSERVER,
    )
    partner_id = _single_participant(
        context.event,
        ParticipantRole.PARTNER,
    )
    expression_type = context.event.payload.get("expression_type")
    if observer_id is None or partner_id is None or expression_type is None:
        return ()
    return (
        ClaimDraft(
            CLAIM_REACTION_EXPRESSION_SELECTED,
            subject_ids=(observer_id,),
            object_ids=(partner_id,),
            value={
                "phase": context.event.payload.get("phase"),
                "expression_type": expression_type,
                "applied": bool(context.event.payload.get("applied", False)),
                "duration_minutes": context.event.payload.get(
                    "duration_minutes",
                    0,
                ),
                "repair_action_type": context.event.payload.get(
                    "repair_action_type"
                ),
                "accepted": context.event.payload.get("accepted"),
                "cause_id": context.event.cause_id,
            },
            truth_status=ClaimTruthStatus.SUPPORTED,
            supporting_event_ids=(context.event.event_id,),
            provenance="relationship_reaction_runtime",
            stable_key="{}:reaction-expression".format(
                context.event.event_id
            ),
        ),
    )


def _reaction_knowledge(context):
    observer_id = _single_participant(
        context.event,
        ParticipantRole.OBSERVER,
    )
    if observer_id is None:
        return ()
    return tuple(
        BeliefDraft(
            observer_id,
            claim.claim_id,
            AcquisitionMode.PARTICIPANT,
            status=BeliefStatus.CONFIRMED,
            credibility=100,
            confidence=100,
            acquisition_event_id=context.event.event_id,
            acquired_at=context.event.occurred_at,
            stable_key="{}:private-reaction-owner".format(claim.claim_id),
        )
        for claim in context.claims
        if claim.claim_type == CLAIM_REACTION_EXPRESSION_SELECTED
    )


def _reaction_interpretations(context):
    expression_type = str(
        context.event.payload.get("expression_type", "none")
    )
    return tuple(
        InterpretationDraft(
            belief.knower_id,
            belief.claim_id,
            "felt:{}".format(expression_type),
            confidence=belief.confidence,
            rule_id="core.relationship_reaction.expression.v1",
            source_belief_id=belief.belief_id,
            created_at=context.event.occurred_at,
            details={
                "phase": context.event.payload.get("phase"),
                "expression_type": expression_type,
                "applied": bool(context.event.payload.get("applied", False)),
                "duration_minutes": context.event.payload.get(
                    "duration_minutes",
                    0,
                ),
                "repair_action_type": context.event.payload.get(
                    "repair_action_type"
                ),
                "accepted": context.event.payload.get("accepted"),
                "cause_id": context.event.cause_id,
            },
            stable_key="{}:felt-expression".format(belief.belief_id),
        )
        for belief in context.beliefs
    )


def _reaction_summary(context):
    observer_id = _single_participant(
        context.event,
        ParticipantRole.OBSERVER,
    )
    partner_id = _single_participant(
        context.event,
        ParticipantRole.PARTNER,
    )
    if observer_id is None or partner_id is None:
        return ()
    expression_type = str(
        context.event.payload.get("expression_type", "none")
    )
    return (
        SummaryMutation(
            observer_id,
            partner_id,
            SummaryMutation.INCREMENT,
            "relationship_reactions_selected",
            1,
        ),
        SummaryMutation(
            observer_id,
            partner_id,
            SummaryMutation.SET_TIMESTAMP,
            "last_relationship_reaction_at",
            context.event.occurred_at,
        ),
        SummaryMutation(
            observer_id,
            partner_id,
            SummaryMutation.SET_FLAG,
            "last_reaction_expression:{}".format(expression_type),
            True,
        ),
    )


def register_reaction_memory_rules(registry):
    event_types = (EventType.REACTION_EXPRESSION_SELECTED,)
    registry.register_event_definition(
        get_journal_event_definition(
            EventType.REACTION_EXPRESSION_SELECTED
        )
    )
    registry.register_rule(
        RomanticMemoryRegistry.CLAIM_STAGE,
        "core.reaction.claim",
        _reaction_claims,
        event_types=event_types,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.KNOWLEDGE_STAGE,
        "core.reaction.private_knowledge",
        _reaction_knowledge,
        event_types=event_types,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.INTERPRETATION_STAGE,
        "core.reaction.interpretation",
        _reaction_interpretations,
        event_types=event_types,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.SUMMARY_STAGE,
        "core.reaction.summary",
        _reaction_summary,
        event_types=event_types,
        priority=100,
    )
    return registry

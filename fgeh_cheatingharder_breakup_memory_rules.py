"""Ledger and cognition rules for directed breakup negotiation events."""

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


CLAIM_BREAKUP_PROPOSED = "breakup_was_proposed"
CLAIM_BREAKUP_RESPONSE_GIVEN = "breakup_response_was_given"
CLAIM_BREAKUP_NEGOTIATION_RESOLVED = "breakup_negotiation_was_resolved"

INTERPRETATION_BREAKUP_PROPOSAL = "breakup_proposal_meaning"
INTERPRETATION_BREAKUP_RESPONSE = "breakup_response_meaning"
INTERPRETATION_BREAKUP_RESOLUTION = "breakup_resolution_meaning"

NEGOTIATION_EVENT_TYPES = (
    EventType.BREAKUP_PROPOSED,
    EventType.BREAKUP_RESPONSE,
    EventType.BREAKUP_NEGOTIATION_RESOLVED,
)


def _single_participant(event, role):
    values = event.participants_for(role)
    return values[0] if values else None


def _actor_target(event):
    return (
        _single_participant(event, ParticipantRole.ACTOR),
        _single_participant(event, ParticipantRole.TARGET),
    )


def _claim_spec(event):
    if event.event_type == EventType.BREAKUP_PROPOSED:
        return (
            CLAIM_BREAKUP_PROPOSED,
            {
                "transaction_id": event.payload.get("transaction_id"),
                "motive": event.payload.get("motive"),
            },
        )
    if event.event_type == EventType.BREAKUP_RESPONSE:
        return (
            CLAIM_BREAKUP_RESPONSE_GIVEN,
            {
                "transaction_id": event.payload.get("transaction_id"),
                "response": event.payload.get("response"),
            },
        )
    if event.event_type == EventType.BREAKUP_NEGOTIATION_RESOLVED:
        return (
            CLAIM_BREAKUP_NEGOTIATION_RESOLVED,
            {
                "transaction_id": event.payload.get("transaction_id"),
                "proposer_decision": event.payload.get(
                    "proposer_decision"
                ),
                "outcome": event.payload.get("outcome"),
                "official_breakup_authorized": event.payload.get(
                    "official_breakup_authorized",
                    False,
                ),
            },
        )
    return None


def _negotiation_claims(context):
    actor_id, target_id = _actor_target(context.event)
    spec = _claim_spec(context.event)
    if actor_id is None or target_id is None or spec is None:
        return ()
    claim_type, value = spec
    return (
        ClaimDraft(
            claim_type,
            subject_ids=(actor_id,),
            object_ids=(target_id,),
            value=value,
            truth_status=ClaimTruthStatus.SUPPORTED,
            supporting_event_ids=(context.event.event_id,),
            provenance="direct_breakup_participation",
            stable_key="{}:{}".format(
                context.event.event_id,
                claim_type,
            ),
        ),
    )


def _negotiation_knowledge(context):
    actor_id, target_id = _actor_target(context.event)
    if actor_id is None or target_id is None:
        return ()
    beliefs = []
    for claim in context.claims:
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


def _interpretation_type(event_type):
    if event_type == EventType.BREAKUP_PROPOSED:
        return INTERPRETATION_BREAKUP_PROPOSAL
    if event_type == EventType.BREAKUP_RESPONSE:
        return INTERPRETATION_BREAKUP_RESPONSE
    return INTERPRETATION_BREAKUP_RESOLUTION


def _relationship_intent(event, knower_id, actor_id, target_id):
    payload = event.payload
    if event.event_type == EventType.BREAKUP_PROPOSED:
        return "leave" if knower_id == actor_id else "respond_to_breakup"
    if event.event_type == EventType.BREAKUP_RESPONSE:
        response = payload.get("response")
        if knower_id == actor_id:
            if response == "accept_breakup":
                return "accept_end"
            if response == "refuse_breakup":
                return "reject_end"
            return "repair"
        return "consider_partner_response"
    if knower_id == actor_id:
        return payload.get("proposer_intent", "uncertain")
    if knower_id == target_id:
        return payload.get("recipient_intent", "uncertain")
    return "uncertain"


def _negotiation_interpretations(context):
    event = context.event
    actor_id, target_id = _actor_target(event)
    if actor_id is None or target_id is None:
        return ()
    results = []
    for belief in context.beliefs:
        results.append(
            InterpretationDraft(
                belief.knower_id,
                belief.claim_id,
                _interpretation_type(event.event_type),
                confidence=belief.confidence,
                rule_id="core.breakup_negotiation.meaning.v1",
                source_belief_id=belief.belief_id,
                created_at=event.occurred_at,
                details={
                    "transaction_id": event.payload.get(
                        "transaction_id"
                    ),
                    "proposer_id": event.payload.get("proposer_id"),
                    "recipient_id": event.payload.get("recipient_id"),
                    "relationship_intent": _relationship_intent(
                        event,
                        belief.knower_id,
                        actor_id,
                        target_id,
                    ),
                    "response": event.payload.get("response"),
                    "proposer_decision": event.payload.get(
                        "proposer_decision"
                    ),
                    "outcome": event.payload.get("outcome"),
                    "official_breakup_authorized": event.payload.get(
                        "official_breakup_authorized",
                        False,
                    ),
                },
                stable_key="{}:meaning".format(belief.belief_id),
            )
        )
    return tuple(results)


def _summary_flag(mutations, observer_id, partner_id, key, value):
    mutations.append(
        SummaryMutation(
            observer_id,
            partner_id,
            SummaryMutation.SET_FLAG,
            key,
            value,
        )
    )


def _negotiation_summary(context):
    event = context.event
    actor_id, target_id = _actor_target(event)
    if actor_id is None or target_id is None:
        return ()
    mutations = []
    if event.event_type == EventType.BREAKUP_PROPOSED:
        mutations.extend((
            SummaryMutation(
                actor_id,
                target_id,
                SummaryMutation.INCREMENT,
                "breakup_proposals_made",
                1,
            ),
            SummaryMutation(
                target_id,
                actor_id,
                SummaryMutation.INCREMENT,
                "breakup_proposals_received",
                1,
            ),
            SummaryMutation(
                actor_id,
                target_id,
                SummaryMutation.SET_TIMESTAMP,
                "last_breakup_proposal_at",
                event.occurred_at,
            ),
            SummaryMutation(
                target_id,
                actor_id,
                SummaryMutation.SET_TIMESTAMP,
                "last_breakup_proposal_at",
                event.occurred_at,
            ),
        ))
    elif event.event_type == EventType.BREAKUP_RESPONSE:
        response = event.payload.get("response")
        if response == "plead_to_stay":
            counter = "breakup_pleas_made"
        elif response == "refuse_breakup":
            counter = "breakup_refusals_made"
        else:
            counter = "breakup_acceptances_made"
        mutations.append(
            SummaryMutation(
                actor_id,
                target_id,
                SummaryMutation.INCREMENT,
                counter,
                1,
            )
        )
    elif event.event_type == EventType.BREAKUP_NEGOTIATION_RESOLVED:
        outcome = str(event.payload.get("outcome", "unknown"))
        for observer_id, partner_id in (
            (actor_id, target_id),
            (target_id, actor_id),
        ):
            for known_outcome in (
                "official_breakup_authorized",
                "relationship_retained",
                "relationship_delayed",
            ):
                _summary_flag(
                    mutations,
                    observer_id,
                    partner_id,
                    "last_breakup_outcome_{}".format(known_outcome),
                    outcome == known_outcome,
                )
        _summary_flag(
            mutations,
            target_id,
            actor_id,
            "subjectively_denies_latest_breakup",
            event.payload.get("recipient_intent") == "deny_breakup",
        )
    return tuple(mutations)


def register_breakup_negotiation_memory_rules(registry):
    for event_type in NEGOTIATION_EVENT_TYPES:
        registry.register_event_definition(
            get_journal_event_definition(event_type)
        )
    registry.register_rule(
        RomanticMemoryRegistry.CLAIM_STAGE,
        "core.breakup_negotiation.claim",
        _negotiation_claims,
        event_types=NEGOTIATION_EVENT_TYPES,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.KNOWLEDGE_STAGE,
        "core.breakup_negotiation.knowledge",
        _negotiation_knowledge,
        event_types=NEGOTIATION_EVENT_TYPES,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.INTERPRETATION_STAGE,
        "core.breakup_negotiation.interpretation",
        _negotiation_interpretations,
        event_types=NEGOTIATION_EVENT_TYPES,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.SUMMARY_STAGE,
        "core.breakup_negotiation.summary",
        _negotiation_summary,
        event_types=NEGOTIATION_EVENT_TYPES,
        priority=100,
    )
    return registry

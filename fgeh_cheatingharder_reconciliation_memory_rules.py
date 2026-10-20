"""Ledger and cognition rules for reconciliation negotiations."""

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


CLAIM_RECONCILIATION_PROPOSED = "reconciliation_was_proposed"
CLAIM_RECONCILIATION_RESPONSE = "reconciliation_response_was_given"
CLAIM_RECONCILIATION_RESOLVED = "reconciliation_was_resolved"

INTERPRETATION_RECONCILIATION_PROPOSAL = (
    "reconciliation_proposal_meaning"
)
INTERPRETATION_RECONCILIATION_RESPONSE = (
    "reconciliation_response_meaning"
)
INTERPRETATION_RECONCILIATION_RESOLUTION = (
    "reconciliation_resolution_meaning"
)

RECONCILIATION_EVENT_TYPES = (
    EventType.RECONCILIATION_PROPOSED,
    EventType.RECONCILIATION_RESPONSE,
    EventType.RECONCILIATION_RESOLVED,
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
    if event.event_type == EventType.RECONCILIATION_PROPOSED:
        return (
            CLAIM_RECONCILIATION_PROPOSED,
            {
                "transaction_id": event.payload.get("transaction_id"),
                "proposal": event.payload.get("proposal"),
            },
        )
    if event.event_type == EventType.RECONCILIATION_RESPONSE:
        return (
            CLAIM_RECONCILIATION_RESPONSE,
            {
                "transaction_id": event.payload.get("transaction_id"),
                "response": event.payload.get("response"),
            },
        )
    if event.event_type == EventType.RECONCILIATION_RESOLVED:
        return (
            CLAIM_RECONCILIATION_RESOLVED,
            {
                "transaction_id": event.payload.get("transaction_id"),
                "outcome": event.payload.get("effective_outcome"),
                "official_partnership_restored": event.payload.get(
                    "official_partnership_restored",
                    False,
                ),
            },
        )
    return None


def _reconciliation_claims(context):
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
            provenance="direct_reconciliation_participation",
            stable_key="{}:{}".format(
                context.event.event_id,
                claim_type,
            ),
        ),
    )


def _reconciliation_knowledge(context):
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
    if event_type == EventType.RECONCILIATION_PROPOSED:
        return INTERPRETATION_RECONCILIATION_PROPOSAL
    if event_type == EventType.RECONCILIATION_RESPONSE:
        return INTERPRETATION_RECONCILIATION_RESPONSE
    return INTERPRETATION_RECONCILIATION_RESOLUTION


def _relationship_intent(event, knower_id, actor_id, target_id):
    if event.event_type == EventType.RECONCILIATION_PROPOSED:
        return (
            "restore_relationship"
            if knower_id == actor_id
            else "consider_reconciliation"
        )
    if event.event_type == EventType.RECONCILIATION_RESPONSE:
        response = event.payload.get("response")
        if knower_id == actor_id:
            if response == "accept_reconciliation":
                return "restore_relationship"
            if response == "request_repair_before_reconciliation":
                return "repair_before_commitment"
            if response == "defer_reconciliation":
                return "need_time_before_reconciliation"
            return "remain_apart"
        return "understand_partner_response"
    if knower_id == actor_id:
        return event.payload.get("proposer_intent", "uncertain")
    if knower_id == target_id:
        return event.payload.get("recipient_intent", "uncertain")
    return "uncertain"


def _reconciliation_interpretations(context):
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
                rule_id="core.reconciliation.meaning.v1",
                source_belief_id=belief.belief_id,
                created_at=event.occurred_at,
                details={
                    "transaction_id": event.payload.get(
                        "transaction_id"
                    ),
                    "relationship_intent": _relationship_intent(
                        event,
                        belief.knower_id,
                        actor_id,
                        target_id,
                    ),
                    "response": event.payload.get("response"),
                    "outcome": event.payload.get("effective_outcome"),
                    "official_partnership_restored": event.payload.get(
                        "official_partnership_restored",
                        False,
                    ),
                },
                stable_key="{}:meaning".format(belief.belief_id),
            )
        )
    return tuple(results)


def _summary_flag(mutations, first_id, second_id, key, value):
    mutations.append(
        SummaryMutation(
            first_id,
            second_id,
            SummaryMutation.SET_FLAG,
            key,
            value,
        )
    )


def _reconciliation_summary(context):
    event = context.event
    actor_id, target_id = _actor_target(event)
    if actor_id is None or target_id is None:
        return ()
    mutations = []
    if event.event_type == EventType.RECONCILIATION_PROPOSED:
        mutations.extend((
            SummaryMutation(
                actor_id,
                target_id,
                SummaryMutation.INCREMENT,
                "reconciliation_proposals_made",
                1,
            ),
            SummaryMutation(
                target_id,
                actor_id,
                SummaryMutation.INCREMENT,
                "reconciliation_proposals_received",
                1,
            ),
        ))
    elif event.event_type == EventType.RECONCILIATION_RESPONSE:
        response = event.payload.get("response")
        if response == "accept_reconciliation":
            made_key = "reconciliation_acceptances_made"
            received_key = "reconciliation_acceptances_received"
        elif response == "request_repair_before_reconciliation":
            made_key = "reconciliation_repair_requests_made"
            received_key = "reconciliation_repair_requests_received"
        elif response == "defer_reconciliation":
            made_key = "reconciliation_deferrals_made"
            received_key = "reconciliation_deferrals_received"
        else:
            made_key = "reconciliation_refusals_made"
            received_key = "reconciliation_refusals_received"
        mutations.extend((
            SummaryMutation(
                actor_id,
                target_id,
                SummaryMutation.INCREMENT,
                made_key,
                1,
            ),
            SummaryMutation(
                target_id,
                actor_id,
                SummaryMutation.INCREMENT,
                received_key,
                1,
            ),
        ))
    elif event.event_type == EventType.RECONCILIATION_RESOLVED:
        restored = bool(
            event.payload.get("official_partnership_restored", False)
        )
        for first_id, second_id in (
            (actor_id, target_id),
            (target_id, actor_id),
        ):
            if restored:
                mutations.append(
                    SummaryMutation(
                        first_id,
                        second_id,
                        SummaryMutation.INCREMENT,
                        "successful_reconciliations",
                        1,
                    )
                )
            mutations.append(
                SummaryMutation(
                    first_id,
                    second_id,
                    SummaryMutation.SET_TIMESTAMP,
                    "last_reconciliation_resolution_at",
                    event.occurred_at,
                )
            )
            _summary_flag(
                mutations,
                first_id,
                second_id,
                "currently_reconciled_by_framework",
                restored,
            )
            _summary_flag(
                mutations,
                first_id,
                second_id,
                "latest_reconciliation_requires_repair",
                event.payload.get("effective_outcome")
                == "repair_required",
            )
    return tuple(mutations)


def register_reconciliation_memory_rules(registry):
    for event_type in RECONCILIATION_EVENT_TYPES:
        registry.register_event_definition(
            get_journal_event_definition(event_type)
        )
    registry.register_rule(
        RomanticMemoryRegistry.CLAIM_STAGE,
        "core.reconciliation.claim",
        _reconciliation_claims,
        event_types=RECONCILIATION_EVENT_TYPES,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.KNOWLEDGE_STAGE,
        "core.reconciliation.knowledge",
        _reconciliation_knowledge,
        event_types=RECONCILIATION_EVENT_TYPES,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.INTERPRETATION_STAGE,
        "core.reconciliation.interpretation",
        _reconciliation_interpretations,
        event_types=RECONCILIATION_EVENT_TYPES,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.SUMMARY_STAGE,
        "core.reconciliation.summary",
        _reconciliation_summary,
        event_types=RECONCILIATION_EVENT_TYPES,
        priority=100,
    )
    return registry

"""First registered vertical slice for the romantic memory framework."""

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
    MemoryOpportunity,
    ParticipantRole,
    StateChangeMode,
    SummaryMutation,
)
from fgeh_cheatingharder_memory_registry import RomanticMemoryRegistry


CLAIM_ROMANTIC_CONTACT_OCCURRED = "romantic_contact_occurred"
INTERPRETATION_POSITIVE_ROMANTIC_CONTACT = "positive_romantic_contact"
OPPORTUNITY_RELATIONSHIP_MAINTENANCE = "relationship_maintenance"
DIRECTED_STATE_DEFAULTS = (
    ("attachment", 68),
    ("trust", 65),
    ("exclusivity", 88),
    ("commitment", 68),
    ("boundary", 50),
)
POSITIVE_CONTACT_CHANGES = (
    ("attachment", 2),
    ("trust", 1),
    ("commitment", 1),
)


def _single_participant(event, role):
    values = event.participants_for(role)
    return values[0] if values else None


def _romance_claims(context):
    event = context.event
    actor_id = _single_participant(event, ParticipantRole.ACTOR)
    target_id = _single_participant(event, ParticipantRole.TARGET)
    if actor_id is None or target_id is None:
        return ()
    return (
        ClaimDraft(
            CLAIM_ROMANTIC_CONTACT_OCCURRED,
            subject_ids=(actor_id,),
            object_ids=(target_id,),
            value={
                "interaction_name": event.payload.get("interaction_name"),
                "affordance_id": event.payload.get("affordance_id"),
            },
            truth_status=ClaimTruthStatus.SUPPORTED,
            supporting_event_ids=(event.event_id,),
            provenance="successful_interaction_outcome",
            stable_key="{}:romantic-contact".format(event.event_id),
        ),
    )


def _romance_knowledge(context):
    event = context.event
    actor_id = _single_participant(event, ParticipantRole.ACTOR)
    target_id = _single_participant(event, ParticipantRole.TARGET)
    witnesses = event.participants_for(ParticipantRole.WITNESS)
    if actor_id is None or target_id is None:
        return ()
    beliefs = []
    for claim in context.claims:
        if claim.claim_type != CLAIM_ROMANTIC_CONTACT_OCCURRED:
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
                    source_sim_id=None,
                    acquisition_event_id=event.event_id,
                    acquired_at=event.occurred_at,
                    stable_key="{}:participant:{}".format(
                        claim.claim_id,
                        knower_id,
                    ),
                )
            )
        for witness_id in witnesses:
            if witness_id in (actor_id, target_id):
                continue
            beliefs.append(
                BeliefDraft(
                    witness_id,
                    claim.claim_id,
                    AcquisitionMode.EYEWITNESS,
                    status=BeliefStatus.CONFIRMED,
                    credibility=100,
                    confidence=100,
                    source_sim_id=None,
                    acquisition_event_id=event.event_id,
                    acquired_at=event.occurred_at,
                    stable_key="{}:eyewitness:{}".format(
                        claim.claim_id,
                        witness_id,
                    ),
                )
            )
    return tuple(beliefs)


def _romance_interpretations(context):
    interpretations = []
    for belief in context.beliefs:
        claim = context.store.get_claim(belief.claim_id)
        if claim is None or claim.claim_type != CLAIM_ROMANTIC_CONTACT_OCCURRED:
            continue
        related_sim_id = None
        if belief.knower_id in claim.subject_ids and claim.object_ids:
            related_sim_id = claim.object_ids[0]
        elif belief.knower_id in claim.object_ids and claim.subject_ids:
            related_sim_id = claim.subject_ids[0]
        interpretations.append(
            InterpretationDraft(
                belief.knower_id,
                claim.claim_id,
                INTERPRETATION_POSITIVE_ROMANTIC_CONTACT,
                confidence=belief.confidence,
                rule_id="core.romantic_contact.participant_meaning.v1",
                source_belief_id=belief.belief_id,
                created_at=context.event.occurred_at,
                details={"related_sim_id": related_sim_id},
                stable_key="{}:positive-contact".format(belief.belief_id),
            )
        )
    return tuple(interpretations)


def _romance_state_reducer(context):
    """Small state effect proving the reducer boundary for the first slice."""
    event = context.event
    actor_id = _single_participant(event, ParticipantRole.ACTOR)
    target_id = _single_participant(event, ParticipantRole.TARGET)
    valid_pair = frozenset((actor_id, target_id))
    interpretation_by_knower = {
        value.knower_id: value
        for value in context.interpretations
        if value.interpretation_type
        == INTERPRETATION_POSITIVE_ROMANTIC_CONTACT
    }
    changes = []
    for observer_id, partner_id in context.directed_edges():
        if frozenset((observer_id, partner_id)) != valid_pair:
            continue
        interpretation = interpretation_by_knower.get(observer_id)
        if interpretation is None:
            continue
        belief = context.store.get_belief(interpretation.source_belief_id)
        if belief is None or belief.knower_id != observer_id:
            continue
        claim_id = belief.claim_id
        for dimension, value in DIRECTED_STATE_DEFAULTS:
            changes.append(DirectedStateDelta(
                observer_id,
                partner_id,
                dimension,
                value,
                "directed_relationship_default",
                mode=StateChangeMode.SET_IF_MISSING,
                event_id=event.event_id,
                claim_id=claim_id,
                belief_id=belief.belief_id,
                interpretation_id=interpretation.interpretation_id,
            ))
        for dimension, value in POSITIVE_CONTACT_CHANGES:
            changes.append(DirectedStateDelta(
                observer_id,
                partner_id,
                dimension,
                value,
                "known_positive_romantic_contact",
                mode=StateChangeMode.ADD,
                event_id=event.event_id,
                claim_id=claim_id,
                belief_id=belief.belief_id,
                interpretation_id=interpretation.interpretation_id,
            ))
    return tuple(changes)


def _romance_summary_projection(context):
    mutations = []
    for belief in context.beliefs:
        claim = context.store.get_claim(belief.claim_id)
        if claim is None or claim.claim_type != CLAIM_ROMANTIC_CONTACT_OCCURRED:
            continue
        partner_id = None
        if belief.knower_id in claim.subject_ids and claim.object_ids:
            partner_id = claim.object_ids[0]
        elif belief.knower_id in claim.object_ids and claim.subject_ids:
            partner_id = claim.subject_ids[0]
        if partner_id is None:
            continue
        mutations.extend((
            SummaryMutation(
                belief.knower_id,
                partner_id,
                SummaryMutation.INCREMENT,
                "known_positive_romantic_contacts",
                1,
            ),
            SummaryMutation(
                belief.knower_id,
                partner_id,
                SummaryMutation.SET_TIMESTAMP,
                "last_positive_romantic_contact_at",
                context.event.occurred_at,
            ),
        ))
    return tuple(mutations)


def _romance_opportunity(context):
    opportunities = []
    actor_id = _single_participant(context.event, ParticipantRole.ACTOR)
    target_id = _single_participant(context.event, ParticipantRole.TARGET)
    if actor_id is None or target_id is None:
        return ()
    valid_pair = frozenset((actor_id, target_id))
    for observer_id, partner_id in context.directed_edges():
        if frozenset((observer_id, partner_id)) != valid_pair:
            continue
        summary = context.store.get_summary(observer_id, partner_id)
        if summary is None:
            continue
        opportunities.append(
            MemoryOpportunity(
                OPPORTUNITY_RELATIONSHIP_MAINTENANCE,
                observer_id,
                partner_id,
                reason=EventType.ROMANCE_COMPLETED,
                urgency=0,
                event_id=context.event.event_id,
                context={
                    "known_positive_romantic_contacts": (
                        summary.counters.get(
                            "known_positive_romantic_contacts",
                            0,
                        )
                    ),
                },
            )
        )
    return tuple(opportunities)


def register_core_memory_rules(registry):
    registry.register_event_definition(
        get_journal_event_definition(EventType.ROMANCE_COMPLETED)
    )
    event_types = (EventType.ROMANCE_COMPLETED,)
    registry.register_rule(
        RomanticMemoryRegistry.CLAIM_STAGE,
        "core.romance.claim",
        _romance_claims,
        event_types=event_types,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.KNOWLEDGE_STAGE,
        "core.romance.knowledge",
        _romance_knowledge,
        event_types=event_types,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.INTERPRETATION_STAGE,
        "core.romance.interpretation",
        _romance_interpretations,
        event_types=event_types,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.STATE_STAGE,
        "core.romance.state",
        _romance_state_reducer,
        event_types=event_types,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.SUMMARY_STAGE,
        "core.romance.summary",
        _romance_summary_projection,
        event_types=event_types,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.OPPORTUNITY_STAGE,
        "core.romance.opportunity",
        _romance_opportunity,
        event_types=event_types,
        priority=100,
    )
    return registry

"""Romantic-memory registrations for permanent one-way devotion."""

from fgeh_cheatingharder_devotion import (
    build_devotion_floor_deltas,
)
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


CLAIM_DEVOTION_BOND_EXISTS = "devotion_bond_exists"
CLAIM_OUTSIDE_ROMANCE_REJECTED = "outside_romance_rejected"
INTERPRETATION_ONLY_BELOVED = "only_beloved"
INTERPRETATION_DEVOTION_REFUSAL = "devotion_refusal"


def _one(event, role):
    values = event.participants_for(role)
    return values[0] if values else None


def _devotion_claims(context):
    event = context.event
    owner_id = _one(event, ParticipantRole.OBSERVER)
    beloved_id = _one(event, ParticipantRole.PARTNER)
    if owner_id is None or beloved_id is None:
        return ()
    return (
        ClaimDraft(
            CLAIM_DEVOTION_BOND_EXISTS,
            subject_ids=(owner_id,),
            object_ids=(beloved_id,),
            value={
                "permanent": True,
                "exclusive": True,
                "source": event.payload.get("devotion_source", event.source),
            },
            truth_status=ClaimTruthStatus.SUPPORTED,
            supporting_event_ids=(event.event_id,),
            provenance="devotion_bond_projection",
            stable_key="devotion-bond:{}:{}".format(owner_id, beloved_id),
        ),
    )


def _rejection_claims(context):
    event = context.event
    actor_id = _one(event, ParticipantRole.ACTOR)
    target_id = _one(event, ParticipantRole.TARGET)
    owner_id = _one(event, ParticipantRole.OBSERVER)
    beloved_id = _one(event, ParticipantRole.PARTNER)
    if None in (actor_id, target_id, owner_id, beloved_id):
        return ()
    return (
        ClaimDraft(
            CLAIM_OUTSIDE_ROMANCE_REJECTED,
            subject_ids=(actor_id,),
            object_ids=(target_id,),
            value={
                "devoted_owner_id": owner_id,
                "beloved_id": beloved_id,
                "interaction_name": event.payload.get("interaction_name"),
                "block_reason": event.payload.get("block_reason"),
            },
            truth_status=ClaimTruthStatus.SUPPORTED,
            supporting_event_ids=(event.event_id,),
            provenance="interaction_queue_guard",
            stable_key="{}:outside-romance-rejected".format(event.event_id),
        ),
    )


def _devotion_knowledge(context):
    owner_id = _one(context.event, ParticipantRole.OBSERVER)
    if owner_id is None:
        return ()
    beliefs = []
    for claim in context.claims:
        if claim.claim_type not in (
            CLAIM_DEVOTION_BOND_EXISTS,
            CLAIM_OUTSIDE_ROMANCE_REJECTED,
        ):
            continue
        beliefs.append(
            BeliefDraft(
                owner_id,
                claim.claim_id,
                AcquisitionMode.PARTICIPANT,
                status=BeliefStatus.CONFIRMED,
                credibility=100,
                confidence=100,
                acquisition_event_id=context.event.event_id,
                acquired_at=context.event.occurred_at,
                stable_key="{}:owner-knows:{}".format(
                    claim.claim_id,
                    owner_id,
                ),
            )
        )
    return tuple(beliefs)


def _devotion_interpretations(context):
    values = []
    for belief in context.beliefs:
        claim = context.store.get_claim(belief.claim_id)
        if claim is None:
            continue
        if claim.claim_type == CLAIM_DEVOTION_BOND_EXISTS:
            interpretation_type = INTERPRETATION_ONLY_BELOVED
        elif claim.claim_type == CLAIM_OUTSIDE_ROMANCE_REJECTED:
            interpretation_type = INTERPRETATION_DEVOTION_REFUSAL
        else:
            continue
        values.append(
            InterpretationDraft(
                belief.knower_id,
                claim.claim_id,
                interpretation_type,
                confidence=100,
                rule_id="devotion.owner_meaning.v1",
                source_belief_id=belief.belief_id,
                created_at=context.event.occurred_at,
                details={
                    "beloved_id": _one(
                        context.event,
                        ParticipantRole.PARTNER,
                    )
                },
                stable_key="{}:{}".format(
                    belief.belief_id,
                    interpretation_type,
                ),
            )
        )
    return tuple(values)


def _devotion_state_floor(context):
    """Reassert love/commitment without freezing trust or boundaries."""
    changes = []
    for owner_id, beloved_id in context.directed_edges():
        changes.extend(
            build_devotion_floor_deltas(
                context.store,
                owner_id,
                beloved_id,
                event_id=context.event.event_id,
            )
        )
    return tuple(changes)


def _devotion_summary(context):
    owner_id = _one(context.event, ParticipantRole.OBSERVER)
    beloved_id = _one(context.event, ParticipantRole.PARTNER)
    if owner_id is None or beloved_id is None:
        return ()
    if context.event.event_type == EventType.DEVOTION_BOND_CREATED:
        return (
            SummaryMutation(
                owner_id,
                beloved_id,
                SummaryMutation.SET_FLAG,
                "is_only_beloved",
                True,
                projection_version=1,
            ),
            SummaryMutation(
                owner_id,
                beloved_id,
                SummaryMutation.SET_TIMESTAMP,
                "devotion_established_at",
                context.event.occurred_at,
                projection_version=1,
            ),
        )
    if context.event.event_type == EventType.OUTSIDE_ROMANCE_REJECTED:
        return (
            SummaryMutation(
                owner_id,
                beloved_id,
                SummaryMutation.INCREMENT,
                "outside_romance_rejections",
                1,
                projection_version=1,
            ),
        )
    if context.event.event_type == EventType.DEVOTION_LONGING_STARTED:
        return (
            SummaryMutation(
                owner_id,
                beloved_id,
                SummaryMutation.SET_FLAG,
                "is_longing_for_only_beloved",
                True,
                projection_version=1,
            ),
            SummaryMutation(
                owner_id,
                beloved_id,
                SummaryMutation.SET_TIMESTAMP,
                "last_devotion_longing_started_at",
                context.event.occurred_at,
                projection_version=1,
            ),
            SummaryMutation(
                owner_id,
                beloved_id,
                SummaryMutation.INCREMENT,
                "devotion_longing_episodes",
                1,
                projection_version=1,
            ),
        )
    if context.event.event_type == EventType.DEVOTION_CONTACT_SOUGHT:
        return (
            SummaryMutation(
                owner_id,
                beloved_id,
                SummaryMutation.SET_TIMESTAMP,
                "last_devotion_seek_at",
                context.event.occurred_at,
                projection_version=1,
            ),
            SummaryMutation(
                owner_id,
                beloved_id,
                SummaryMutation.INCREMENT,
                "devotion_contact_seek_attempts",
                1,
                projection_version=1,
            ),
        )
    if context.event.event_type == EventType.DEVOTION_CONTACT_COMPLETED:
        return (
            SummaryMutation(
                owner_id,
                beloved_id,
                SummaryMutation.SET_FLAG,
                "is_longing_for_only_beloved",
                False,
                projection_version=1,
            ),
            SummaryMutation(
                owner_id,
                beloved_id,
                SummaryMutation.SET_TIMESTAMP,
                "last_meaningful_devotion_contact_at",
                context.event.occurred_at,
                projection_version=1,
            ),
            SummaryMutation(
                owner_id,
                beloved_id,
                SummaryMutation.INCREMENT,
                "meaningful_devotion_contacts",
                1,
                projection_version=1,
            ),
        )
    return ()


def register_devotion_memory_rules(registry):
    for event_type in (
        EventType.DEVOTION_BOND_CREATED,
        EventType.OUTSIDE_ROMANCE_REJECTED,
        EventType.DEVOTION_LONGING_STARTED,
        EventType.DEVOTION_CONTACT_SOUGHT,
        EventType.DEVOTION_CONTACT_COMPLETED,
    ):
        registry.register_event_definition(
            get_journal_event_definition(event_type)
        )

    registry.register_rule(
        RomanticMemoryRegistry.CLAIM_STAGE,
        "devotion.bond.claim",
        _devotion_claims,
        event_types=(EventType.DEVOTION_BOND_CREATED,),
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.CLAIM_STAGE,
        "devotion.rejection.claim",
        _rejection_claims,
        event_types=(EventType.OUTSIDE_ROMANCE_REJECTED,),
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.KNOWLEDGE_STAGE,
        "devotion.owner.knowledge",
        _devotion_knowledge,
        event_types=(
            EventType.DEVOTION_BOND_CREATED,
            EventType.OUTSIDE_ROMANCE_REJECTED,
        ),
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.INTERPRETATION_STAGE,
        "devotion.owner.interpretation",
        _devotion_interpretations,
        event_types=(
            EventType.DEVOTION_BOND_CREATED,
            EventType.OUTSIDE_ROMANCE_REJECTED,
        ),
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.STATE_STAGE,
        "devotion.permanent_love_floor",
        _devotion_state_floor,
        event_types=None,
        # Run after ordinary relationship reducers for the same event.
        priority=-100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.SUMMARY_STAGE,
        "devotion.hot_summary",
        _devotion_summary,
        event_types=(
            EventType.DEVOTION_BOND_CREATED,
            EventType.OUTSIDE_ROMANCE_REJECTED,
            EventType.DEVOTION_LONGING_STARTED,
            EventType.DEVOTION_CONTACT_SOUGHT,
            EventType.DEVOTION_CONTACT_COMPLETED,
        ),
        priority=100,
    )
    return registry

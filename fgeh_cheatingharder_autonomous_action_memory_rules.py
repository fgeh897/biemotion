"""Ledger rules for completed memory-driven autonomous actions."""

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
    DIRECTED_DIMENSIONS,
    DirectedStateDelta,
    InterpretationDraft,
    ParticipantRole,
    StateChangeMode,
    SummaryMutation,
)
from fgeh_cheatingharder_memory_registry import RomanticMemoryRegistry


CLAIM_AUTONOMOUS_RELATIONSHIP_ACTION = (
    "autonomous_relationship_action_resolved"
)
INTERPRETATION_REASSURANCE_RECEIVED = "reassurance_received"
INTERPRETATION_REASSURANCE_UNMET = "reassurance_unmet"
INTERPRETATION_PARTNER_SOUGHT_REASSURANCE = (
    "partner_sought_reassurance"
)
INTERPRETATION_CLUNG_TO_PARTNER = "clung_to_partner"
INTERPRETATION_CLINGING_CONTACT_UNMET = "clinging_contact_unmet"
INTERPRETATION_PARTNER_CLUNG_TO_ME = "partner_clung_to_me"
INTERPRETATION_BETRAYAL_CONFRONTED = "betrayal_confronted"
INTERPRETATION_CONFRONTATION_UNMET = "confrontation_unmet"
INTERPRETATION_PARTNER_WAS_CONFRONTED = "partner_was_confronted"
INTERPRETATION_RIVAL_CONFRONTED = "rival_confronted"
INTERPRETATION_CONFRONTED_AS_RIVAL = "confronted_as_rival"
INTERPRETATION_BETRAYAL_FORGIVEN = "betrayal_forgiven"
INTERPRETATION_BETRAYAL_ENDURED_SILENTLY = (
    "betrayal_endured_silently"
)


def _single_participant(event, role):
    values = event.participants_for(role)
    return values[0] if values else None


def _is_debug_executor_event(context):
    return bool(context.event.payload.get("debug_executor_test", False))


def _action_target_id(event):
    target_id = _single_participant(event, ParticipantRole.TARGET)
    if target_id is not None:
        return target_id
    return _single_participant(event, ParticipantRole.PARTNER)


def _action_claims(context):
    if _is_debug_executor_event(context):
        return ()
    observer_id = _single_participant(
        context.event,
        ParticipantRole.OBSERVER,
    )
    partner_id = _single_participant(context.event, ParticipantRole.PARTNER)
    target_id = _action_target_id(context.event)
    intent = context.event.payload.get("intent")
    if (
        observer_id is None
        or partner_id is None
        or target_id is None
        or not intent
    ):
        return ()
    return (
        ClaimDraft(
            CLAIM_AUTONOMOUS_RELATIONSHIP_ACTION,
            subject_ids=(observer_id,),
            object_ids=(target_id,),
            value={
                "intent": str(intent),
                "target_id": target_id,
                "target_role": context.event.payload.get("target_role"),
                "relationship_partner_id": partner_id,
                "rival_id": context.event.payload.get("rival_id"),
                "success": bool(
                    context.event.payload.get("success", False)
                ),
                "status": context.event.payload.get("status"),
                "opportunity_type": context.event.payload.get(
                    "opportunity_type"
                ),
                "execution_strategy": context.event.payload.get(
                    "execution_strategy"
                ),
                "affordance_profile": context.event.payload.get(
                    "affordance_profile"
                ),
                "affordance_name": context.event.payload.get(
                    "affordance_name"
                ),
                "interaction_id": context.event.payload.get(
                    "interaction_id"
                ),
                "source_event_id": context.event.payload.get(
                    "source_event_id"
                ),
                "decision_source": context.event.payload.get(
                    "decision_source"
                ),
                "counterpart_response": context.event.payload.get(
                    "counterpart_response"
                ),
            },
            truth_status=ClaimTruthStatus.SUPPORTED,
            supporting_event_ids=(context.event.event_id,),
            provenance="autonomous_behavior_runtime",
            stable_key="{}:autonomous-action".format(
                context.event.event_id
            ),
        ),
    )


def _action_knowledge(context):
    if _is_debug_executor_event(context):
        return ()
    observer_id = _single_participant(
        context.event,
        ParticipantRole.OBSERVER,
    )
    target_id = _action_target_id(context.event)
    if observer_id is None or target_id is None:
        return ()
    # A timeout or failed queue attempt is private to the actor.  Once an EA
    # social produced an outcome, both participants know it occurred.
    status = str(context.event.payload.get("status", ""))
    knowers = [observer_id]
    if status in ("interaction_succeeded", "interaction_failed"):
        knowers.append(target_id)
    beliefs = []
    for claim in context.claims:
        if claim.claim_type != CLAIM_AUTONOMOUS_RELATIONSHIP_ACTION:
            continue
        for knower_id in knowers:
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


def _action_interpretations(context):
    if _is_debug_executor_event(context):
        return ()
    observer_id = _single_participant(
        context.event,
        ParticipantRole.OBSERVER,
    )
    success = bool(context.event.payload.get("success", False))
    intent = str(context.event.payload.get("intent", ""))
    target_id = _action_target_id(context.event)
    results = []
    for belief in context.beliefs:
        if intent == "confront_rival":
            if belief.knower_id == observer_id:
                interpretation_type = (
                    INTERPRETATION_RIVAL_CONFRONTED
                    if success
                    else INTERPRETATION_CONFRONTATION_UNMET
                )
            elif belief.knower_id == target_id:
                interpretation_type = INTERPRETATION_CONFRONTED_AS_RIVAL
            else:
                continue
        elif intent == "confront_partner":
            if belief.knower_id == observer_id:
                interpretation_type = (
                    INTERPRETATION_BETRAYAL_CONFRONTED
                    if success
                    else INTERPRETATION_CONFRONTATION_UNMET
                )
            else:
                interpretation_type = (
                    INTERPRETATION_PARTNER_WAS_CONFRONTED
                )
        elif intent == "cling_to_partner":
            if belief.knower_id == observer_id:
                interpretation_type = (
                    INTERPRETATION_CLUNG_TO_PARTNER
                    if success
                    else INTERPRETATION_CLINGING_CONTACT_UNMET
                )
            else:
                interpretation_type = INTERPRETATION_PARTNER_CLUNG_TO_ME
        elif intent == "forgive_partner":
            if belief.knower_id != observer_id:
                continue
            interpretation_type = INTERPRETATION_BETRAYAL_FORGIVEN
        elif intent == "endure_silently":
            if belief.knower_id != observer_id:
                continue
            interpretation_type = (
                INTERPRETATION_BETRAYAL_ENDURED_SILENTLY
            )
        else:
            if belief.knower_id == observer_id:
                interpretation_type = (
                    INTERPRETATION_REASSURANCE_RECEIVED
                    if success
                    else INTERPRETATION_REASSURANCE_UNMET
                )
            else:
                interpretation_type = (
                    INTERPRETATION_PARTNER_SOUGHT_REASSURANCE
                )
        results.append(
            InterpretationDraft(
                belief.knower_id,
                belief.claim_id,
                interpretation_type,
                confidence=belief.confidence,
                rule_id="core.autonomous_action.meaning.v1",
                source_belief_id=belief.belief_id,
                created_at=context.event.occurred_at,
                details={
                    "intent": context.event.payload.get("intent"),
                    "success": success,
                    "status": context.event.payload.get("status"),
                    "source_event_id": context.event.payload.get(
                        "source_event_id"
                    ),
                    "target_id": target_id,
                    "target_role": context.event.payload.get("target_role"),
                    "relationship_partner_id": context.event.payload.get(
                        "relationship_partner_id"
                    ),
                    "rival_id": context.event.payload.get("rival_id"),
                    "decision_source": context.event.payload.get(
                        "decision_source"
                    ),
                    "counterpart_response": context.event.payload.get(
                        "counterpart_response"
                    ),
                },
                stable_key="{}:{}".format(
                    belief.belief_id,
                    interpretation_type,
                ),
            )
        )
    return tuple(results)


def _counterpart_response_state(context, injured_id, responder_id):
    decision = context.event.payload.get(
        "counterpart_response_decision"
    )
    if not isinstance(decision, dict):
        return ()
    response = str(
        decision.get("selected_response")
        or context.event.payload.get("counterpart_response")
        or "unknown"
    )
    results = []
    for (
        state_observer_id,
        state_partner_id,
        delta_key,
        direction,
    ) in (
        (
            injured_id,
            responder_id,
            "injured_state_deltas",
            "injured",
        ),
        (
            responder_id,
            injured_id,
            "responder_state_deltas",
            "responder",
        ),
    ):
        interpretation = next((
            value
            for value in context.interpretations
            if value.knower_id == state_observer_id
        ), None)
        if interpretation is None:
            continue
        belief = context.store.get_belief(
            interpretation.source_belief_id
        )
        if belief is None:
            continue
        for dimension, raw_value in dict(
            decision.get(delta_key, {}) or {}
        ).items():
            if dimension not in DIRECTED_DIMENSIONS:
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if value == 0.0:
                continue
            results.append(DirectedStateDelta(
                state_observer_id,
                state_partner_id,
                dimension,
                value,
                "counterpart_{}_{}_{}".format(
                    response,
                    direction,
                    dimension,
                ),
                mode=StateChangeMode.ADD,
                event_id=context.event.event_id,
                claim_id=belief.claim_id,
                belief_id=belief.belief_id,
                interpretation_id=interpretation.interpretation_id,
            ))
    return tuple(results)


def _action_state(context):
    if _is_debug_executor_event(context):
        return ()
    intent = str(context.event.payload.get("intent", ""))
    if not bool(context.event.payload.get("success", False)):
        return ()
    observer_id = _single_participant(
        context.event,
        ParticipantRole.OBSERVER,
    )
    partner_id = _single_participant(
        context.event,
        ParticipantRole.PARTNER,
    )
    expected_interpretation = {
        "seek_reassurance": INTERPRETATION_REASSURANCE_RECEIVED,
        "cling_to_partner": INTERPRETATION_CLUNG_TO_PARTNER,
        "confront_partner": INTERPRETATION_BETRAYAL_CONFRONTED,
        "confront_rival": INTERPRETATION_RIVAL_CONFRONTED,
    }.get(intent)
    if expected_interpretation is None:
        return ()
    interpretation = next((
        value
        for value in context.interpretations
        if (
            value.knower_id == observer_id
            and value.interpretation_type == expected_interpretation
        )
    ), None)
    if observer_id is None or partner_id is None or interpretation is None:
        return ()
    belief = context.store.get_belief(
        interpretation.source_belief_id
    )
    if belief is None:
        return ()
    # Confronting the rival is a role-directed social consequence. It does
    # not directly rewrite the observer's five romantic dimensions toward
    # their partner; the action and its outcome remain in summaries/history.
    if intent == "confront_rival":
        return ()
    if intent == "confront_partner":
        base_deltas = (
            DirectedStateDelta(
                observer_id,
                partner_id,
                "boundary",
                1,
                "betrayal_confrontation_succeeded",
                mode=StateChangeMode.ADD,
                event_id=context.event.event_id,
                claim_id=belief.claim_id,
                belief_id=belief.belief_id,
                interpretation_id=interpretation.interpretation_id,
            ),
        )
    elif intent == "cling_to_partner":
        base_deltas = (
            DirectedStateDelta(
                observer_id,
                partner_id,
                "attachment",
                1,
                "clinging_contact_succeeded",
                mode=StateChangeMode.ADD,
                event_id=context.event.event_id,
                claim_id=belief.claim_id,
                belief_id=belief.belief_id,
                interpretation_id=interpretation.interpretation_id,
            ),
        )
    else:
        base_deltas = (
            DirectedStateDelta(
                observer_id,
                partner_id,
                "trust",
                2,
                "reassurance_interaction_succeeded",
                mode=StateChangeMode.ADD,
                event_id=context.event.event_id,
                claim_id=belief.claim_id,
                belief_id=belief.belief_id,
                interpretation_id=interpretation.interpretation_id,
            ),
            DirectedStateDelta(
                observer_id,
                partner_id,
                "attachment",
                1,
                "reassurance_interaction_succeeded",
                mode=StateChangeMode.ADD,
                event_id=context.event.event_id,
                claim_id=belief.claim_id,
                belief_id=belief.belief_id,
                interpretation_id=interpretation.interpretation_id,
            ),
        )
    return tuple(base_deltas) + _counterpart_response_state(
        context,
        observer_id,
        partner_id,
    )


def _action_summary(context):
    if _is_debug_executor_event(context):
        return ()
    observer_id = _single_participant(
        context.event,
        ParticipantRole.OBSERVER,
    )
    relationship_partner_id = _single_participant(
        context.event,
        ParticipantRole.PARTNER,
    )
    target_id = _action_target_id(context.event)
    if (
        observer_id is None
        or relationship_partner_id is None
        or target_id is None
    ):
        return ()
    intent = str(context.event.payload.get("intent", "unknown_action"))
    mutations = [
        SummaryMutation(
            observer_id,
            target_id,
            SummaryMutation.INCREMENT,
            "{}_attempts".format(intent),
            1,
        ),
        SummaryMutation(
            observer_id,
            target_id,
            SummaryMutation.SET_TIMESTAMP,
            "last_{}_at".format(intent),
            context.event.occurred_at,
        ),
    ]
    if bool(context.event.payload.get("success", False)):
        mutations.append(
            SummaryMutation(
                observer_id,
                target_id,
                SummaryMutation.INCREMENT,
                "{}_successes".format(intent),
                1,
            )
        )
    else:
        mutations.append(
            SummaryMutation(
                observer_id,
                target_id,
                SummaryMutation.INCREMENT,
                "{}_failures".format(intent),
                1,
            )
        )
    if intent == "confront_rival":
        mutations.extend((
            SummaryMutation(
                observer_id,
                relationship_partner_id,
                SummaryMutation.INCREMENT,
                "rival_confrontation_attempts",
                1,
            ),
            SummaryMutation(
                observer_id,
                relationship_partner_id,
                SummaryMutation.SET_TIMESTAMP,
                "last_rival_confrontation_at",
                context.event.occurred_at,
            ),
            SummaryMutation(
                observer_id,
                relationship_partner_id,
                SummaryMutation.INCREMENT,
                (
                    "rival_confrontation_successes"
                    if bool(context.event.payload.get("success", False))
                    else "rival_confrontation_failures"
                ),
                1,
            ),
        ))
    counterpart_response = context.event.payload.get(
        "counterpart_response"
    )
    if counterpart_response and target_id == relationship_partner_id:
        response_key = "counterpart_response:{}".format(
            counterpart_response
        )
        mutations.extend((
            SummaryMutation(
                observer_id,
                relationship_partner_id,
                SummaryMutation.INCREMENT,
                response_key,
                1,
            ),
            SummaryMutation(
                observer_id,
                relationship_partner_id,
                SummaryMutation.SET_TIMESTAMP,
                "last_counterpart_response_at",
                context.event.occurred_at,
            ),
            SummaryMutation(
                relationship_partner_id,
                observer_id,
                SummaryMutation.INCREMENT,
                "betrayal_crisis_responses",
                1,
            ),
            SummaryMutation(
                relationship_partner_id,
                observer_id,
                SummaryMutation.SET_FLAG,
                response_key,
                True,
            ),
        ))
    return tuple(mutations)


def register_autonomous_action_memory_rules(registry):
    event_types = (EventType.AUTONOMOUS_ACTION_RESOLVED,)
    registry.register_event_definition(
        get_journal_event_definition(
            EventType.AUTONOMOUS_ACTION_RESOLVED
        )
    )
    registry.register_rule(
        RomanticMemoryRegistry.CLAIM_STAGE,
        "core.autonomous_action.claim",
        _action_claims,
        event_types=event_types,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.KNOWLEDGE_STAGE,
        "core.autonomous_action.knowledge",
        _action_knowledge,
        event_types=event_types,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.INTERPRETATION_STAGE,
        "core.autonomous_action.interpretation",
        _action_interpretations,
        event_types=event_types,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.STATE_STAGE,
        "core.autonomous_action.state",
        _action_state,
        event_types=event_types,
        priority=100,
    )
    registry.register_rule(
        RomanticMemoryRegistry.SUMMARY_STAGE,
        "core.autonomous_action.summary",
        _action_summary,
        event_types=event_types,
        priority=100,
    )
    return registry

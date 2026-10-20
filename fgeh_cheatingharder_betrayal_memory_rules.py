"""Registered caught-betrayal vertical slice for romantic memory."""

from fgeh_cheatingharder_betrayal_reactions import (
    BETRAYAL_PROFILES,
    BREAKUP_UTILITY_MODEL_KEY,
    BetrayalIntent,
    BetrayalProfileKey,
    evaluate_caught_betrayal,
)
from fgeh_cheatingharder_betrayal_influence_shadow import (
    evaluate_caught_betrayal_influence,
    evaluate_betrayal_influence_shadow,
    evaluate_betrayal_shadow_matrix,
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
    MemoryOpportunity,
    ParticipantRole,
    StateChangeMode,
    SummaryMutation,
)
from fgeh_cheatingharder_memory_registry import RomanticMemoryRegistry
from fgeh_cheatingharder_role_attitudes import (
    build_betrayal_role_mutations,
)


CLAIM_PARTNER_ROMANCE_WITH_RIVAL = "partner_romance_with_rival"
# Compatibility alias for existing extensions and tests.
CLAIM_WITNESSED_PARTNER_ROMANCE = CLAIM_PARTNER_ROMANCE_WITH_RIVAL
INTERPRETATION_BETRAYAL_ATTRIBUTION = "betrayal_responsibility_attribution"
OPPORTUNITY_BETRAYAL_RESPONSE = "betrayal_response"
REACTION_DEFAULTS = {
    "attachment": 68.0,
    "trust": 65.0,
    "exclusivity": 88.0,
    "commitment": 68.0,
    "boundary": 50.0,
}


def _single_participant(event, role):
    values = event.participants_for(role)
    return values[0] if values else None


def _observer_partner_rival(event):
    return (
        _single_participant(event, ParticipantRole.OBSERVER),
        _single_participant(event, ParticipantRole.PARTNER),
        _single_participant(event, ParticipantRole.RIVAL),
    )


def betrayal_rival_marker_edge(event, beliefs):
    """Return the directed observer -> rival edge after confirmed knowledge.

    The visible Relationship Bit is a projection of one Sim's knowledge, not
    proof that every Sim shares the same interpretation of the objective event.
    """
    if event is None or event.event_type not in (
        EventType.CAUGHT_CHEATING,
        EventType.ROMANTIC_BOUNDARY_DISCOVERED,
    ):
        return None
    observer_id, _partner_id, rival_id = _observer_partner_rival(event)
    if observer_id is None or rival_id is None or observer_id == rival_id:
        return None
    confirmed = any(
        (
            getattr(belief, "knower_id", None) == observer_id
            and getattr(belief, "status", None) == BeliefStatus.CONFIRMED
        )
        for belief in (beliefs or ())
    )
    if not confirmed:
        return None
    return (observer_id, rival_id)


def latest_betrayal_event_for_observer(store, observer_id):
    """Return the newest complete betrayal event known by ``observer_id``.

    Target selection must be derived from participant roles recorded on the
    event.  Falling back to an arbitrary Sim on the active lot would turn a
    relationship reaction into unrelated autonomous hostility.
    """
    observer_id = int(observer_id)
    accepted_types = (
        EventType.CAUGHT_CHEATING,
        EventType.ROMANTIC_BOUNDARY_DISCOVERED,
    )
    events = tuple(store.events_for_participant(observer_id))
    for event in reversed(events):
        if event.event_type not in accepted_types:
            continue
        recorded_observer, partner_id, rival_id = _observer_partner_rival(event)
        if (
            recorded_observer == observer_id
            and partner_id is not None
            and rival_id is not None
        ):
            return event
    return None


def betrayal_target_matches_event(
    event,
    observer_id,
    target_id,
    target_role,
):
    """Validate that a directed reaction targets a role on its source event."""
    if event is None or event.event_type not in (
        EventType.CAUGHT_CHEATING,
        EventType.ROMANTIC_BOUNDARY_DISCOVERED,
    ):
        return False
    if str(target_role) not in (
        ParticipantRole.PARTNER,
        ParticipantRole.RIVAL,
    ):
        return False
    return (
        int(observer_id) in event.participants_for(ParticipantRole.OBSERVER)
        and int(target_id) in event.participants_for(str(target_role))
    )


def betrayal_action_target(selected_intent, partner_id, rival_id):
    """Resolve the selected behavior's target without losing its source pair."""
    if str(selected_intent) == BetrayalIntent.CONFRONT_RIVAL:
        return (rival_id, ParticipantRole.RIVAL)
    return (partner_id, ParticipantRole.PARTNER)


def _acquisition_mode(event):
    requested = event.payload.get("acquisition_mode")
    if requested == AcquisitionMode.EA_CONFIRMED:
        return AcquisitionMode.EA_CONFIRMED
    return AcquisitionMode.EYEWITNESS


def _event_tags(event):
    tags = ["betrayal", "boundary_break", "romance", "discovered"]
    if _acquisition_mode(event) == AcquisitionMode.EYEWITNESS:
        tags.append("witnessed")
    return tuple(tags)


def _profile_key(context):
    requested = (
        context.event.payload.get("reaction_profile_key")
        or context.external_context.get("reaction_profile_key")
        or BetrayalProfileKey.BALANCED
    )
    if BETRAYAL_PROFILES.get(requested) is None:
        return BetrayalProfileKey.BALANCED
    return str(requested)


def _state_for_evaluation(context, observer_id, partner_id):
    record = context.store.get_directed_state(observer_id, partner_id)
    if record is None:
        return dict(REACTION_DEFAULTS)
    values = {}
    for dimension, default in REACTION_DEFAULTS.items():
        if record.initialized.get(dimension, False):
            values[dimension] = record.get(dimension)
        else:
            values[dimension] = default
    return values


def _behavior_context(context, observer_id, partner_id):
    summary = context.store.get_summary(observer_id, partner_id)
    counters = {} if summary is None else dict(summary.counters)
    bond = context.store.get_devotion_bond(observer_id)
    permanently_devoted = (
        bond is not None and bond.beloved_id == partner_id
    )
    return {
        # Include the current confirmed event before summary projection runs.
        "known_betrayal_count": (
            float(counters.get("known_betrayal_count", 0)) + 1.0
        ),
        "known_broken_promise_count": float(
            counters.get("known_broken_promise_count", 0)
        ),
        "permanently_devoted": permanently_devoted,
        "severe_safety_event": bool(
            context.event.payload.get("severe_safety_event", False)
        ),
    }


def _episode_data(context):
    return dict(
        context.external_context.get("betrayal_episode", {}) or {}
    )


def _is_primary_episode_event(context):
    return bool(
        context.external_context.get("betrayal_episode_primary", True)
    )


def _betrayal_claims(context):
    observer_id, partner_id, rival_id = _observer_partner_rival(context.event)
    if observer_id is None or partner_id is None or rival_id is None:
        return ()
    return (
        ClaimDraft(
            CLAIM_PARTNER_ROMANCE_WITH_RIVAL,
            subject_ids=(partner_id,),
            object_ids=(rival_id,),
            value={
                "observer_id": observer_id,
                "interaction_name": context.event.payload.get(
                    "interaction_name"
                ),
                "affordance_id": context.event.payload.get("affordance_id"),
                "event_tags": _event_tags(context.event),
                "acquisition_mode": _acquisition_mode(context.event),
                "source_romance_event_ids": context.event.payload.get(
                    "source_romance_event_ids",
                    (),
                ),
            },
            truth_status=ClaimTruthStatus.SUPPORTED,
            supporting_event_ids=(context.event.event_id,),
            provenance="{}_betrayal".format(
                _acquisition_mode(context.event)
            ),
            stable_key="{}:partner-romance-with-rival".format(
                context.event.event_id
            ),
        ),
    )


def _betrayal_knowledge(context):
    observer_id, _partner_id, _rival_id = _observer_partner_rival(
        context.event
    )
    if observer_id is None:
        return ()
    acquisition_mode = _acquisition_mode(context.event)
    return tuple(
        BeliefDraft(
            observer_id,
            claim.claim_id,
            acquisition_mode,
            status=BeliefStatus.CONFIRMED,
            credibility=100,
            confidence=100,
            acquisition_event_id=context.event.event_id,
            acquired_at=context.event.occurred_at,
            stable_key="{}:{}:{}".format(
                claim.claim_id,
                acquisition_mode,
                observer_id,
            ),
        )
        for claim in context.claims
        if claim.claim_type == CLAIM_PARTNER_ROMANCE_WITH_RIVAL
    )


def _betrayal_interpretations(context):
    observer_id, partner_id, rival_id = _observer_partner_rival(context.event)
    if observer_id is None or partner_id is None or rival_id is None:
        return ()
    severity = context.event.severity or 100.0
    episode = _episode_data(context)
    cached_reaction = dict(
        context.external_context.get("betrayal_episode_reaction", {}) or {}
    )
    if not _is_primary_episode_event(context) and cached_reaction:
        details_template = cached_reaction
        details_template["episode_supplementary"] = True
    else:
        state = _state_for_evaluation(context, observer_id, partner_id)
        behavior_context = _behavior_context(
            context,
            observer_id,
            partner_id,
        )
        legacy_reaction = evaluate_caught_betrayal(
            state,
            profile_key=_profile_key(context),
            severity=severity,
            roll=context.event.payload.get("decision_roll"),
            behavior_context=behavior_context,
        )
        reaction = evaluate_caught_betrayal_influence(
            state,
            profile_key=_profile_key(context),
            severity=severity,
            roll=legacy_reaction.roll,
            behavior_context=behavior_context,
        )
        influence_shadow = evaluate_betrayal_influence_shadow(
            legacy_reaction,
            state,
            profile_key=_profile_key(context),
            severity=severity,
            behavior_context=behavior_context,
        )
        influence_shadow_matrix = evaluate_betrayal_shadow_matrix(
            legacy_reaction,
            state,
            active_profile_key=_profile_key(context),
            severity=severity,
            behavior_context=behavior_context,
        )
        details_template = reaction.as_dict()
        details_template.update({
            "influence_shadow": influence_shadow,
            "influence_shadow_matrix": influence_shadow_matrix,
            "episode_supplementary": False,
        })
    results = []
    for belief in context.beliefs:
        claim = context.store.get_claim(belief.claim_id)
        if (
            claim is None
            or claim.claim_type != CLAIM_PARTNER_ROMANCE_WITH_RIVAL
            or belief.knower_id != observer_id
        ):
            continue
        details = dict(details_template)
        details.update({
            "partner_id": partner_id,
            "rival_id": rival_id,
            "event_tags": _event_tags(context.event),
            "acquisition_mode": _acquisition_mode(context.event),
            "severity": severity,
            "decision_model": "tag_driven_influence_v1",
            "betrayal_episode_id": episode.get("episode_id"),
            "betrayal_episode_primary": _is_primary_episode_event(context),
        })
        results.append(
            InterpretationDraft(
                observer_id,
                claim.claim_id,
                INTERPRETATION_BETRAYAL_ATTRIBUTION,
                confidence=belief.confidence,
                rule_id="core.caught_betrayal.attribution.v1",
                source_belief_id=belief.belief_id,
                created_at=context.event.occurred_at,
                details=details,
                stable_key="{}:betrayal-attribution".format(
                    belief.belief_id
                ),
            )
        )
    return tuple(results)


def _betrayal_state_reducer(context):
    if not _is_primary_episode_event(context):
        return ()
    observer_id, partner_id, _rival_id = _observer_partner_rival(context.event)
    if observer_id is None or partner_id is None:
        return ()
    changes = []
    for interpretation in context.interpretations:
        if (
            interpretation.knower_id != observer_id
            or interpretation.interpretation_type
            != INTERPRETATION_BETRAYAL_ATTRIBUTION
        ):
            continue
        belief = context.store.get_belief(
            interpretation.source_belief_id
        )
        if belief is None:
            continue
        for dimension, default in REACTION_DEFAULTS.items():
            changes.append(DirectedStateDelta(
                observer_id,
                partner_id,
                dimension,
                default,
                "directed_relationship_default",
                mode=StateChangeMode.SET_IF_MISSING,
                event_id=context.event.event_id,
                claim_id=belief.claim_id,
                belief_id=belief.belief_id,
                interpretation_id=interpretation.interpretation_id,
            ))
        for dimension, value in dict(
            interpretation.details.get("state_deltas", {})
        ).items():
            changes.append(DirectedStateDelta(
                observer_id,
                partner_id,
                dimension,
                value,
                "caught_betrayal_personality_reaction",
                mode=StateChangeMode.ADD,
                event_id=context.event.event_id,
                claim_id=belief.claim_id,
                belief_id=belief.belief_id,
                interpretation_id=interpretation.interpretation_id,
            ))
    return tuple(changes)


def _betrayal_summary_projection(context):
    observer_id, partner_id, rival_id = _observer_partner_rival(context.event)
    if observer_id is None or partner_id is None or rival_id is None:
        return ()
    if not _is_primary_episode_event(context):
        return (
            SummaryMutation(
                observer_id,
                partner_id,
                SummaryMutation.SET_TIMESTAMP,
                "last_betrayal_evidence_at",
                context.event.occurred_at,
            ),
        )
    interpretation = next((
        value
        for value in context.interpretations
        if (
            value.knower_id == observer_id
            and value.interpretation_type
            == INTERPRETATION_BETRAYAL_ATTRIBUTION
        )
    ), None)
    if interpretation is None:
        return ()
    belief = context.store.get_belief(
        interpretation.source_belief_id
    )
    if belief is None or belief.knower_id != observer_id:
        return ()
    mutations = [
        SummaryMutation(
            observer_id,
            partner_id,
            SummaryMutation.INCREMENT,
            "known_betrayal_count",
            1,
        ),
        SummaryMutation(
            observer_id,
            partner_id,
            SummaryMutation.SET_TIMESTAMP,
            "last_known_betrayal_at",
            context.event.occurred_at,
        ),
    ]
    if _acquisition_mode(context.event) == AcquisitionMode.EYEWITNESS:
        mutations.extend((
            SummaryMutation(
                observer_id,
                partner_id,
                SummaryMutation.INCREMENT,
                "eyewitness_betrayal_count",
                1,
            ),
            SummaryMutation(
                observer_id,
                partner_id,
                SummaryMutation.SET_TIMESTAMP,
                "last_eyewitness_betrayal_at",
                context.event.occurred_at,
            ),
        ))
    mutations.extend((
        SummaryMutation(
            observer_id,
            partner_id,
            SummaryMutation.SET_FLAG,
            "has_confirmed_betrayal",
            True,
        ),
        SummaryMutation(
            observer_id,
            partner_id,
            SummaryMutation.SET_CONFIDENCE,
            "betrayal_confidence",
            100,
        ),
    ))
    mutations.extend(build_betrayal_role_mutations(
        observer_id,
        partner_id,
        rival_id,
        interpretation.details.get("attribution", {}),
        belief.confidence,
        context.event.occurred_at,
        eyewitness_confirmed=(
            _acquisition_mode(context.event)
            == AcquisitionMode.EYEWITNESS
        ),
    ))
    return tuple(mutations)


def _betrayal_opportunity(context):
    if not _is_primary_episode_event(context):
        return ()
    observer_id, partner_id, rival_id = _observer_partner_rival(context.event)
    if observer_id is None or partner_id is None or rival_id is None:
        return ()
    opportunities = []
    for interpretation in context.interpretations:
        if (
            interpretation.knower_id != observer_id
            or interpretation.interpretation_type
            != INTERPRETATION_BETRAYAL_ATTRIBUTION
        ):
            continue
        details = interpretation.details
        selected_intent = details.get("selected_intent")
        target_id, target_role = betrayal_action_target(
            selected_intent,
            partner_id,
            rival_id,
        )
        if target_id is None:
            continue
        opportunities.append(MemoryOpportunity(
            OPPORTUNITY_BETRAYAL_RESPONSE,
            observer_id,
            target_id,
            reason=context.event.event_type,
            urgency=context.event.severity or 100.0,
            event_id=context.event.event_id,
            context={
                "relationship_partner_id": partner_id,
                "rival_id": rival_id,
                "target_role": target_role,
                "target_id": target_id,
                "source_betrayal_event_id": context.event.event_id,
                "profile_key": details.get("profile_key"),
                "attribution": details.get("attribution", {}),
                "state_before": details.get("state_before", {}),
                "state_deltas": details.get("state_deltas", {}),
                "state_after": details.get("state_after", {}),
                "behavior_candidates": details.get("candidates", ()),
                "utility_model_keys": {
                    "break_up": BREAKUP_UTILITY_MODEL_KEY,
                },
                "decision_roll": details.get("roll"),
                "selected_intent": selected_intent,
                # The runtime admits only explicitly registered actions.
                # Social responses use constrained affordance profiles;
                # break_up is routed to the separate negotiation state
                # machine and never removes relationship bits directly.
                "execution_enabled": True,
                "acquisition_mode": _acquisition_mode(context.event),
                "betrayal_episode_id": _episode_data(context).get(
                    "episode_id"
                ),
            },
        ))
    return tuple(opportunities)


def register_caught_betrayal_rules(registry):
    registry.register_event_definition(
        get_journal_event_definition(EventType.CAUGHT_CHEATING)
    )
    registry.register_event_definition(
        get_journal_event_definition(
            EventType.ROMANTIC_BOUNDARY_DISCOVERED
        )
    )
    event_types = (
        EventType.CAUGHT_CHEATING,
        EventType.ROMANTIC_BOUNDARY_DISCOVERED,
    )
    registry.register_rule(
        RomanticMemoryRegistry.CLAIM_STAGE,
        "core.caught_betrayal.claim",
        _betrayal_claims,
        event_types=event_types,
        priority=110,
    )
    registry.register_rule(
        RomanticMemoryRegistry.KNOWLEDGE_STAGE,
        "core.caught_betrayal.knowledge",
        _betrayal_knowledge,
        event_types=event_types,
        priority=110,
    )
    registry.register_rule(
        RomanticMemoryRegistry.INTERPRETATION_STAGE,
        "core.caught_betrayal.interpretation",
        _betrayal_interpretations,
        event_types=event_types,
        priority=110,
        version=2,
    )
    registry.register_rule(
        RomanticMemoryRegistry.STATE_STAGE,
        "core.caught_betrayal.state",
        _betrayal_state_reducer,
        event_types=event_types,
        priority=110,
    )
    registry.register_rule(
        RomanticMemoryRegistry.SUMMARY_STAGE,
        "core.caught_betrayal.summary",
        _betrayal_summary_projection,
        event_types=event_types,
        priority=110,
        version=2,
    )
    registry.register_rule(
        RomanticMemoryRegistry.OPPORTUNITY_STAGE,
        "core.caught_betrayal.opportunity",
        _betrayal_opportunity,
        event_types=event_types,
        priority=110,
    )
    return registry

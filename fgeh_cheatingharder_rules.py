"""Core state-transition and opportunity rules."""

from fgeh_cheatingharder_domain import (
    BehaviorOpportunity,
    EventType,
    OpportunityType,
    StateChange,
)


def core_state_rules(event, state):
    event_type = event.event_type
    initialized_event_types = (
        EventType.CLAIM_ESTABLISHED,
        EventType.RELATIONSHIP_REEVALUATION,
        EventType.CAUGHT_CHEATING,
        EventType.BREAKUP_COMPLETED,
        EventType.VISIT_FINISHED,
    )
    changes = []
    if event_type in initialized_event_types:
        changes.extend((
            StateChange("attachment", 68, "claim_initial_attachment", StateChange.SET_IF_MISSING),
            StateChange("trust", 65, "claim_initial_trust", StateChange.SET_IF_MISSING),
            StateChange("exclusivity", 88, "claim_initial_exclusivity", StateChange.SET_IF_MISSING),
            StateChange("commitment", 68, "claim_initial_commitment", StateChange.SET_IF_MISSING),
            StateChange("boundary", 50, "claim_initial_boundary", StateChange.SET_IF_MISSING),
        ))
    # ROMANCE_COMPLETED, including initialization of missing dimensions, is
    # reduced entirely by the romantic-memory pipeline.  Keeping it here as
    # well would create two write paths and double-apply the delta.
    # AFFAIR_SECRET_DISCOVERED is an authoritative EA knowledge signal only.
    # The correlated three-person caught/discovered event owns interpretation
    # and state change so the same betrayal is never reduced twice.
    # CAUGHT_CHEATING is reduced exclusively by the romantic-memory pipeline.
    # Its observer-specific interpretation controls the five-dimensional
    # deltas; a second fixed write here would erase personality differences.
    if event_type == EventType.BREAKUP_COMPLETED:
        changes.extend((
            StateChange("exclusivity", -20, "breakup_completed"),
            StateChange("commitment", -25, "breakup_completed"),
            StateChange("boundary", 20, "breakup_completed"),
        ))
    if event_type == EventType.VISIT_FINISHED:
        if event.payload.get("outcome") == "no_finding":
            changes.extend((
                StateChange("trust", 4, "check_in_found_nothing"),
                StateChange("boundary", -2, "check_in_found_nothing"),
            ))
    return tuple(changes)


def core_opportunity_provider(event, state):
    urgency_by_event = {
        EventType.CLAIM_ESTABLISHED: 0,
        EventType.RELATIONSHIP_REEVALUATION: 0,
        EventType.BREAKUP_COMPLETED: 12,
    }
    if event.event_type == EventType.DEVOTION_LONGING_STARTED:
        if event.observer_id is None or event.partner_id is None:
            return ()
        return (
            BehaviorOpportunity(
                event.observer_id,
                event.partner_id,
                reason=event.event_type,
                urgency=float(event.payload.get("longing_intensity", 0)),
                opportunity_type=OpportunityType.DEVOTION_LONGING,
                context={"source_event_id": event.event_id},
            ),
        )
    if event.event_type not in urgency_by_event:
        return ()
    if event.observer_id is None or event.partner_id is None:
        return ()
    return (
        BehaviorOpportunity(
            event.observer_id,
            event.partner_id,
            reason=event.event_type,
            urgency=urgency_by_event[event.event_type],
            context={
                "source_event_id": event.event_id,
                "debug_ignore_breakup_cooldown": bool(
                    event.payload.get(
                        "debug_ignore_breakup_cooldown",
                        False,
                    )
                ),
            },
        ),
    )

"""Sims 4 boundary for the pure reconciliation negotiation engine."""

from collections import deque

import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_domain import EventType
from fgeh_cheatingharder_memory_models import ParticipantRole
from fgeh_cheatingharder_reconciliation import (
    DIRECTED_STATE_DEFAULTS,
    PERMANENT_DEVOTION_INFLUENCE,
    ReconciliationResponse,
    evaluate_reconciliation,
)


class ReconciliationRuntimeRegistry:

    def __init__(self, capacity=64):
        self.capacity = max(1, int(capacity))
        self._results = {}
        self._order = deque()

    def clear(self):
        self._results.clear()
        self._order.clear()

    def get(self, request_key):
        return self._results.get(str(request_key))

    def remember(self, request_key, value):
        request_key = str(request_key)
        existing = self._results.get(request_key)
        if existing is not None:
            return existing, False
        self._results[request_key] = value
        self._order.append(request_key)
        while len(self._order) > self.capacity:
            self._results.pop(self._order.popleft(), None)
        return value, True


_RECONCILIATIONS = ReconciliationRuntimeRegistry()


def reset_reconciliation_runtime():
    _RECONCILIATIONS.clear()
    log("reconciliation runtime reset")


def _sim_now_ticks():
    try:
        import services

        now = services.time_service().sim_now
        absolute_ticks = getattr(now, "absolute_ticks", None)
        return (
            absolute_ticks()
            if callable(absolute_ticks)
            else int(now)
        )
    except Exception:
        return None


def _request_key(proposer_id, recipient_id, source, occurred_ticks):
    return "reconciliation:{}:{}:{}:{}".format(
        proposer_id,
        recipient_id,
        source,
        "unknown" if occurred_ticks is None else occurred_ticks,
    )


def _state_values(observer, partner):
    from fgeh_cheatingharder_state import get_directed_state

    state = get_directed_state(observer, partner)
    if state is None:
        return dict(DIRECTED_STATE_DEFAULTS)
    return {
        dimension: (
            state.get(dimension)
            if state.persisted.get(dimension, False)
            else default
        )
        for dimension, default in DIRECTED_STATE_DEFAULTS.items()
    }


def _history(observer_id, partner_id):
    try:
        from fgeh_cheatingharder_memory_runtime import get_memory_summary

        summary = get_memory_summary(observer_id, partner_id)
        return {} if summary is None else dict(summary.counters)
    except Exception:
        log_exception(
            "reconciliation history lookup failed edge={}->{}".format(
                observer_id,
                partner_id,
            )
        )
        return {}


def _recent_breakup_intent_context(
    proposer_id,
    recipient_id,
    occurred_ticks,
):
    """Expose a bounded, explicit breakup decision to the response model."""
    result = {
        "recipient_recently_confirmed_breakup": False,
        "recent_breakup_proposer_id": None,
        "recent_breakup_age_ticks": None,
    }
    if occurred_ticks is None:
        return result
    try:
        import date_and_time
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        window_ticks = int(
            date_and_time.create_time_span(
                minutes=(
                    settings
                    .RECONCILIATION_CONFIRMED_BREAKUP_COOLDOWN_SIM_MINUTES
                )
            ).in_ticks()
        )
        events = get_memory_service().store.events_for_relationship(
            proposer_id,
            recipient_id,
        )
        for event in sorted(
            tuple(events or ()),
            key=lambda value: value.sequence,
            reverse=True,
        ):
            if (
                event.event_type == EventType.RECONCILIATION_RESOLVED
                and event.payload.get("official_partnership_restored")
            ):
                break
            if event.event_type != EventType.BREAKUP_NEGOTIATION_RESOLVED:
                continue
            if not event.payload.get("official_breakup_authorized"):
                continue
            actors = event.participants_for(ParticipantRole.ACTOR)
            breakup_proposer_id = actors[0] if actors else None
            event_ticks = (
                event.occurred_at
                if event.occurred_at is not None
                else event.payload.get("occurred_at")
            )
            if breakup_proposer_id is None or event_ticks is None:
                return result
            age_ticks = int(occurred_ticks) - int(event_ticks)
            result.update({
                "recipient_recently_confirmed_breakup": bool(
                    int(breakup_proposer_id) == int(recipient_id)
                    and 0 <= age_ticks <= window_ticks
                ),
                "recent_breakup_proposer_id": int(breakup_proposer_id),
                "recent_breakup_age_ticks": age_ticks,
            })
            return result
    except Exception:
        log_exception(
            "reconciliation recent breakup context failed pair={}:{}".format(
                proposer_id,
                recipient_id,
            )
        )
    return result


def _is_permanently_devoted(owner_id, beloved_id):
    try:
        from fgeh_cheatingharder_devotion_runtime import get_devotion_bond

        bond = get_devotion_bond(owner_id)
        return (
            bond is not None
            and bond.beloved_id == int(beloved_id)
        )
    except Exception:
        log_exception(
            "reconciliation devotion lookup failed edge={}->{}".format(
                owner_id,
                beloved_id,
            )
        )
        return False


def _has_project_edge(first, second):
    try:
        from fgeh_cheatingharder_devotion_runtime import get_devotion_bond
        from fgeh_cheatingharder_relationship import has_claim
        from fgeh_cheatingharder_state import has_initialized_relationship_pair

        if has_claim(first, second) or has_claim(second, first):
            return True
        if has_initialized_relationship_pair(first, second):
            return True
        first_bond = get_devotion_bond(first.sim_id)
        second_bond = get_devotion_bond(second.sim_id)
        return (
            first_bond is not None
            and first_bond.beloved_id == second.sim_id
        ) or (
            second_bond is not None
            and second_bond.beloved_id == first.sim_id
        )
    except Exception:
        log_exception(
            "reconciliation project edge lookup failed first={} second={}".format(
                getattr(first, "sim_id", None),
                getattr(second, "sim_id", None),
            )
        )
        return False


def _publish_events(
    result,
    source,
    occurred_ticks,
    official_partnership_restored,
):
    from fgeh_cheatingharder_event_center import publish

    base_payload = {
        "transaction_id": result.transaction_id,
        "proposer_id": result.proposer_id,
        "recipient_id": result.recipient_id,
        "relationship_member_ids": tuple(sorted((
            result.proposer_id,
            result.recipient_id,
        ))),
        "occurred_at": occurred_ticks,
        "source_origin": source,
    }
    proposal_payload = dict(base_payload)
    proposal_payload.update({
        "proposal": result.proposal,
        "proposal_decision": result.proposal_decision.as_dict(),
    })
    publish(
        EventType.RECONCILIATION_PROPOSED,
        source="reconciliation_negotiation",
        event_id="{}:proposed".format(result.transaction_id),
        actor_id=result.proposer_id,
        target_id=result.recipient_id,
        payload=proposal_payload,
    )

    if result.response_decision is not None:
        response_payload = dict(base_payload)
        response_payload.update({
            "response": result.response,
            "response_decision": result.response_decision.as_dict(),
        })
        publish(
            EventType.RECONCILIATION_RESPONSE,
            source="reconciliation_negotiation",
            event_id="{}:response".format(result.transaction_id),
            actor_id=result.recipient_id,
            target_id=result.proposer_id,
            payload=response_payload,
        )

    resolution_payload = dict(base_payload)
    resolution_payload.update(result.as_dict())
    resolution_payload["official_partnership_restored"] = bool(
        official_partnership_restored
    )
    if (
        result.official_reconciliation_authorized
        and not official_partnership_restored
    ):
        resolution_payload["effective_outcome"] = (
            "official_transition_failed"
        )
    else:
        resolution_payload["effective_outcome"] = result.outcome
    publish(
        EventType.RECONCILIATION_RESOLVED,
        source="reconciliation_negotiation",
        event_id="{}:resolved".format(result.transaction_id),
        actor_id=result.proposer_id,
        target_id=result.recipient_id,
        payload=resolution_payload,
    )


def _notify(proposer, recipient, result, restored):
    try:
        from fgeh_cheatingharder_notification import (
            show_reconciliation_notification,
        )

        show_reconciliation_notification(
            proposer,
            recipient,
            result,
            official_partnership_restored=restored,
        )
    except Exception:
        log_exception(
            "reconciliation notification failed transaction={}".format(
                result.transaction_id
            )
        )


def request_reconciliation(
    proposer,
    recipient,
    source="player_interaction",
    force_player_proposal=True,
):
    """Evaluate both directions and commit only mutual acceptance through EA."""
    try:
        if proposer is None or recipient is None:
            return None, False
        if proposer.sim_id == recipient.sim_id:
            return None, False
        if not _has_project_edge(proposer, recipient):
            log(
                "reconciliation rejected unmanaged pair proposer={} recipient={}",
                proposer.sim_id,
                recipient.sim_id,
            )
            return None, False

        from fgeh_cheatingharder_reconciliation_ea import (
            are_official_partners,
            have_former_relationship_marker,
            restore_official_partnership,
        )

        if are_official_partners(proposer, recipient):
            log(
                "reconciliation skipped already official proposer={} recipient={}",
                proposer.sim_id,
                recipient.sim_id,
            )
            return None, True
        if not have_former_relationship_marker(proposer, recipient):
            log(
                "reconciliation rejected without EA former marker proposer={} recipient={}",
                proposer.sim_id,
                recipient.sim_id,
            )
            return None, False

        occurred_ticks = _sim_now_ticks()
        request_key = _request_key(
            proposer.sim_id,
            recipient.sim_id,
            source,
            occurred_ticks,
        )
        existing = _RECONCILIATIONS.get(request_key)
        if existing is not None:
            return existing

        proposer_devoted = _is_permanently_devoted(
            proposer.sim_id,
            recipient.sim_id,
        )
        recipient_devoted = _is_permanently_devoted(
            recipient.sim_id,
            proposer.sim_id,
        )
        from fgeh_cheatingharder_repair_case_runtime import (
            close_completed_cases,
            open_case_for_reconciliation,
            reconciliation_context,
        )

        repair_context = reconciliation_context(
            proposer.sim_id,
            recipient.sim_id,
        )
        repair_context.update(
            _recent_breakup_intent_context(
                proposer.sim_id,
                recipient.sim_id,
                occurred_ticks,
            )
        )
        result = evaluate_reconciliation(
            request_key,
            proposer.sim_id,
            recipient.sim_id,
            proposer_state=_state_values(proposer, recipient),
            recipient_state=_state_values(recipient, proposer),
            proposer_history=_history(
                proposer.sim_id,
                recipient.sim_id,
            ),
            recipient_history=_history(
                recipient.sim_id,
                proposer.sim_id,
            ),
            proposer_influences=(
                (PERMANENT_DEVOTION_INFLUENCE,)
                if proposer_devoted
                else ()
            ),
            recipient_influences=(
                (PERMANENT_DEVOTION_INFLUENCE,)
                if recipient_devoted
                else ()
            ),
            recipient_context=repair_context,
            force_proposal=bool(force_player_proposal),
        )
        restored = False
        if result.official_reconciliation_authorized:
            restored = restore_official_partnership(
                proposer,
                recipient,
            )

        value = (result, restored)
        value, created = _RECONCILIATIONS.remember(request_key, value)
        if created:
            open_case_for_reconciliation(result)
            _publish_events(
                result,
                source,
                occurred_ticks,
                restored,
            )
            _notify(proposer, recipient, result, restored)
            if restored:
                close_completed_cases(
                    proposer.sim_id,
                    recipient.sim_id,
                )
        log(
            "reconciliation resolved transaction={} proposer={} recipient={} proposal={} proposal_scores={} response={} response_scores={} outcome={} authorized={} restored={} proposer_devoted={} recipient_devoted={} repair_context={}",
            result.transaction_id,
            proposer.sim_id,
            recipient.sim_id,
            result.proposal,
            tuple(
                value.as_dict()
                for value in result.proposal_decision.candidates
            ),
            result.response,
            (
                ()
                if result.response_decision is None
                else tuple(
                    value.as_dict()
                    for value in result.response_decision.candidates
                )
            ),
            result.outcome,
            result.official_reconciliation_authorized,
            restored,
            proposer_devoted,
            recipient_devoted,
            repair_context,
        )
        return result, restored
    except Exception:
        log_exception(
            "reconciliation request failed proposer={} recipient={}".format(
                getattr(proposer, "sim_id", None),
                getattr(recipient, "sim_id", None),
            )
        )
        return None, False

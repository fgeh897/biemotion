"""Sims 4 boundary for the pure breakup negotiation engine."""

from collections import deque

from fgeh_cheatingharder_breakup_negotiation import (
    BreakupFinalDecision,
    BreakupMotive,
    BreakupNegotiationOutcome,
    BreakupResponse,
    PERMANENT_DEVOTION_INFLUENCE,
    DIRECTED_STATE_DEFAULTS,
    evaluate_breakup_negotiation,
    force_breakup_final_decision,
)
import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_domain import EventType


class BreakupNegotiationRuntimeRegistry:
    """Deduplicate the several EA callbacks belonging to one request."""

    def __init__(self, capacity=64):
        self.capacity = max(1, int(capacity))
        self._results = {}
        self._order = deque()
        self._pair_sessions = {}
        self._pair_order = deque()

    def clear(self):
        self._results.clear()
        self._order.clear()
        self._pair_sessions.clear()
        self._pair_order.clear()

    def get(self, request_key):
        return self._results.get(str(request_key))

    def remember(self, request_key, result):
        request_key = str(request_key)
        existing = self._results.get(request_key)
        if existing is not None:
            return existing, False
        self._results[request_key] = result
        self._order.append(request_key)
        while len(self._order) > self.capacity:
            expired = self._order.popleft()
            self._results.pop(expired, None)
        return result, True

    @staticmethod
    def _pair_key(first_sim_id, second_sim_id):
        return tuple(sorted((int(first_sim_id), int(second_sim_id))))

    def get_pair_session(
        self,
        first_sim_id,
        second_sim_id,
        occurred_ticks,
        max_age_ticks,
    ):
        """Return the recent final result shared by one relationship pair."""
        if occurred_ticks is None:
            return None
        pair_key = self._pair_key(first_sim_id, second_sim_id)
        session = self._pair_sessions.get(pair_key)
        if session is None:
            return None
        session_ticks, result = session
        age = int(occurred_ticks) - int(session_ticks)
        if age < 0 or age > max(0, int(max_age_ticks)):
            self._pair_sessions.pop(pair_key, None)
            return None
        return result

    def remember_pair_session(
        self,
        first_sim_id,
        second_sim_id,
        occurred_ticks,
        result,
    ):
        """Open one bounded pair-level reaction session if ticks are known."""
        if occurred_ticks is None:
            return result, False
        pair_key = self._pair_key(first_sim_id, second_sim_id)
        existing = self._pair_sessions.get(pair_key)
        if existing is not None:
            return existing[1], False
        session_ticks = int(occurred_ticks)
        self._pair_sessions[pair_key] = (session_ticks, result)
        self._pair_order.append((pair_key, session_ticks))
        while len(self._pair_order) > self.capacity:
            expired_key, expired_ticks = self._pair_order.popleft()
            current = self._pair_sessions.get(expired_key)
            if current is not None and current[0] == expired_ticks:
                self._pair_sessions.pop(expired_key, None)
        return result, True


_NEGOTIATIONS = BreakupNegotiationRuntimeRegistry(
    settings.BREAKUP_NEGOTIATION_CAPACITY
)
_PLAYER_PENDING_NEGOTIATIONS = {}


def reset_breakup_negotiation_runtime():
    _NEGOTIATIONS.clear()
    _PLAYER_PENDING_NEGOTIATIONS.clear()
    log("breakup negotiation runtime reset")


def _reaction_session_window_ticks():
    try:
        import date_and_time

        return int(date_and_time.create_time_span(
            minutes=settings.BREAKUP_REACTION_SESSION_SIM_MINUTES
        ).in_ticks())
    except Exception:
        return int(settings.BREAKUP_REACTION_SESSION_SIM_MINUTES)


def _request_key(proposer_id, recipient_id, evidence, occurred_ticks):
    evidence = dict(evidence or {})
    interaction_id = evidence.get("interaction_id")
    if interaction_id is not None:
        source_key = "interaction:{}".format(interaction_id)
    else:
        source_key = "tick:{}:affordance:{}".format(
            "unknown" if occurred_ticks is None else occurred_ticks,
            evidence.get("affordance_id", "unknown"),
        )
    return "breakup-negotiation:{}:{}:{}:{}".format(
        proposer_id,
        recipient_id,
        evidence.get("origin", "unknown"),
        source_key,
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
            "breakup negotiation history lookup failed edge={}->{}".format(
                observer_id,
                partner_id,
            )
        )
        return {}


def _is_permanently_devoted(owner_id, beloved_id):
    try:
        from fgeh_cheatingharder_devotion_runtime import get_devotion_bond

        bond = get_devotion_bond(owner_id)
        return bond is not None and bond.beloved_id == int(beloved_id)
    except Exception:
        log_exception(
            "breakup negotiation devotion lookup failed edge={}->{}".format(
                owner_id,
                beloved_id,
            )
        )
        return False


def _motive(evidence, policy_details):
    reaction_context = dict(
        dict(policy_details or {}).get("reaction_context", {}) or {}
    )
    event_tags = {
        str(value).strip().lower()
        for value in tuple(reaction_context.get("event_tags", ()) or ())
    }
    if "betrayal" in event_tags:
        return BreakupMotive.BETRAYAL_REACTION
    if dict(evidence or {}).get("intentional") is True:
        return BreakupMotive.FINAL_DECISION
    return BreakupMotive.EXTERNAL_PRESSURE


def _publish_negotiation_events(result, evidence, policy_details, occurred_ticks):
    from fgeh_cheatingharder_event_center import publish

    base_payload = {
        "transaction_id": result.transaction_id,
        "proposer_id": result.proposer_id,
        "recipient_id": result.recipient_id,
        "relationship_member_ids": tuple(sorted((
            result.proposer_id,
            result.recipient_id,
        ))),
        "motive": result.motive,
        "occurred_at": occurred_ticks,
        "source_origin": dict(evidence or {}).get("origin"),
        "source_interaction_id": dict(evidence or {}).get(
            "interaction_id"
        ),
        "source_affordance_id": dict(evidence or {}).get(
            "affordance_id"
        ),
        "upper_layer_decision_reference": dict(
            policy_details or {}
        ).get("decision_reference"),
    }
    publish(
        EventType.BREAKUP_PROPOSED,
        source="breakup_negotiation",
        event_id="{}:proposed".format(result.transaction_id),
        actor_id=result.proposer_id,
        target_id=result.recipient_id,
        payload=dict(base_payload),
    )
    response_payload = dict(base_payload)
    response_payload.update({
        "response": result.response,
        "response_decision": result.response_decision.as_dict(),
    })
    publish(
        EventType.BREAKUP_RESPONSE,
        source="breakup_negotiation",
        event_id="{}:response".format(result.transaction_id),
        actor_id=result.recipient_id,
        target_id=result.proposer_id,
        payload=response_payload,
    )
    resolution_payload = dict(base_payload)
    resolution_payload.update(result.as_dict())
    publish(
        EventType.BREAKUP_NEGOTIATION_RESOLVED,
        source="breakup_negotiation",
        event_id="{}:resolved".format(result.transaction_id),
        actor_id=result.proposer_id,
        target_id=result.recipient_id,
        payload=resolution_payload,
    )


def _notify_negotiation(proposer, recipient, result):
    # Authorization means the proposer may now attempt EA's official breakup
    # interaction; it does not mean the partner relationship has ended.  Show
    # the tug-of-war immediately, then let BREAKUP_COMPLETED publish the
    # separate final result only after EA actually removes the partner bit.
    try:
        from fgeh_cheatingharder_notification import (
            show_breakup_negotiation_notification,
        )

        show_breakup_negotiation_notification(
            proposer,
            recipient,
            result,
        )
        if result.official_breakup_authorized:
            log(
                "breakup negotiation shown while official completion remains pending transaction={} proposer={} recipient={}",
                result.transaction_id,
                proposer.sim_id,
                recipient.sim_id,
            )
    except Exception:
        log_exception(
            "breakup negotiation notification failed transaction={}".format(
                result.transaction_id
            )
        )


def _complete_negotiation(
    request_key,
    proposer,
    recipient,
    result,
    evidence,
    policy_details,
    occurred_ticks,
):
    result, created = _NEGOTIATIONS.remember(request_key, result)
    if created:
        _publish_negotiation_events(
            result,
            evidence,
            policy_details,
            occurred_ticks,
        )
        _notify_negotiation(proposer, recipient, result)
        if result.outcome == BreakupNegotiationOutcome.RELATIONSHIP_DELAYED:
            try:
                from fgeh_cheatingharder_crisis_runtime import (
                    open_delayed_breakup_crisis,
                )

                open_delayed_breakup_crisis(
                    result,
                    occurred_at=occurred_ticks,
                )
            except Exception:
                log_exception(
                    "delayed breakup crisis projection failed transaction={}".format(
                        result.transaction_id
                    )
                )
    return result, created


def begin_player_breakup_negotiation(
    proposer,
    recipient,
    evidence,
    policy_details,
    occurred_ticks=None,
    on_authorized=None,
):
    """Begin a player proposal and pause EA only when a reply is needed.

    Returns ``(result, pending)``.  An accepting recipient authorizes the
    current EA transaction synchronously.  A refusal or plea opens the
    player decision dialogs and returns ``(None, True)``.  The proposer may
    insist, delay the decision into a persistent crisis, or withdraw the
    breakup; the supplied continuation is called only if the player insists.
    """
    try:
        request_key = _request_key(
            proposer.sim_id,
            recipient.sim_id,
            evidence,
            occurred_ticks,
        )
        existing = _NEGOTIATIONS.get(request_key)
        if existing is not None:
            return existing, False
        if request_key in _PLAYER_PENDING_NEGOTIATIONS:
            return None, True

        proposer_devoted = _is_permanently_devoted(
            proposer.sim_id,
            recipient.sim_id,
        )
        recipient_devoted = _is_permanently_devoted(
            recipient.sim_id,
            proposer.sim_id,
        )
        initial_result = evaluate_breakup_negotiation(
            request_key,
            proposer.sim_id,
            recipient.sim_id,
            proposer_state=_state_values(proposer, recipient),
            recipient_state=_state_values(recipient, proposer),
            motive=BreakupMotive.FINAL_DECISION,
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
        )
        if initial_result.response == BreakupResponse.ACCEPT:
            result, _ = _complete_negotiation(
                request_key,
                proposer,
                recipient,
                initial_result,
                evidence,
                policy_details,
                occurred_ticks,
            )
            log(
                "player breakup proposal accepted transaction={} proposer={} recipient={}",
                result.transaction_id,
                proposer.sim_id,
                recipient.sim_id,
            )
            return result, False

        pending = {
            "initial_result": initial_result,
            "evidence": dict(evidence or {}),
            "policy_details": dict(policy_details or {}),
            "occurred_ticks": occurred_ticks,
        }
        _PLAYER_PENDING_NEGOTIATIONS[request_key] = pending

        def _finish(final_choice):
            if _PLAYER_PENDING_NEGOTIATIONS.pop(request_key, None) is None:
                return
            result = force_breakup_final_decision(
                initial_result,
                final_choice,
            )
            result, _ = _complete_negotiation(
                request_key,
                proposer,
                recipient,
                result,
                evidence,
                policy_details,
                occurred_ticks,
            )
            log(
                "player breakup negotiation resolved transaction={} proposer={} recipient={} response={} final={} authorized={}",
                result.transaction_id,
                proposer.sim_id,
                recipient.sim_id,
                result.response,
                result.proposer_decision,
                result.official_breakup_authorized,
            )
            if result.official_breakup_authorized and on_authorized is not None:
                try:
                    on_authorized(result)
                except Exception:
                    log_exception(
                        "player breakup authorized continuation failed transaction={}".format(
                            result.transaction_id
                        )
                    )

        from fgeh_cheatingharder_confirmation import (
            show_breakup_second_stage_dialog,
        )

        shown = show_breakup_second_stage_dialog(
            proposer,
            recipient,
            initial_result.response,
            on_insist=lambda: _finish(BreakupFinalDecision.INSIST),
            on_delay=lambda: _finish(BreakupFinalDecision.DELAY),
            on_withdraw=lambda: _finish(BreakupFinalDecision.WITHDRAW),
        )
        if shown:
            log(
                "player breakup negotiation pending transaction={} proposer={} recipient={} response={}",
                initial_result.transaction_id,
                proposer.sim_id,
                recipient.sim_id,
                initial_result.response,
            )
            return None, True

        _PLAYER_PENDING_NEGOTIATIONS.pop(request_key, None)
        result, _ = _complete_negotiation(
            request_key,
            proposer,
            recipient,
            initial_result,
            evidence,
            policy_details,
            occurred_ticks,
        )
        log(
            "player breakup dialog unavailable; used model final transaction={} authorized={}",
            result.transaction_id,
            result.official_breakup_authorized,
        )
        return result, False
    except Exception:
        log_exception(
            "player breakup negotiation failed proposer={} recipient={}".format(
                getattr(proposer, "sim_id", None),
                getattr(recipient, "sim_id", None),
            )
        )
        return None, False


def evaluate_ea_breakup_negotiation(
    proposer,
    recipient,
    evidence,
    policy_details,
    occurred_ticks=None,
    forced_response=None,
):
    """Return one deduplicated result or ``None`` on a guarded failure."""
    try:
        request_key = _request_key(
            proposer.sim_id,
            recipient.sim_id,
            evidence,
            occurred_ticks,
        )
        existing = _NEGOTIATIONS.get(request_key)
        if existing is not None:
            log(
                "breakup negotiation reused transaction={} proposer={} recipient={} outcome={}",
                existing.transaction_id,
                proposer.sim_id,
                recipient.sim_id,
                existing.outcome,
            )
            return existing
        pair_session = _NEGOTIATIONS.get_pair_session(
            proposer.sim_id,
            recipient.sim_id,
            occurred_ticks,
            _reaction_session_window_ticks(),
        )
        if pair_session is not None:
            log(
                "breakup reaction session reused transaction={} request={} proposer={} recipient={} outcome={}",
                pair_session.transaction_id,
                request_key,
                proposer.sim_id,
                recipient.sim_id,
                pair_session.outcome,
            )
            return pair_session
        proposer_devoted = _is_permanently_devoted(
            proposer.sim_id,
            recipient.sim_id,
        )
        recipient_devoted = _is_permanently_devoted(
            recipient.sim_id,
            proposer.sim_id,
        )
        result = evaluate_breakup_negotiation(
            request_key,
            proposer.sim_id,
            recipient.sim_id,
            proposer_state=_state_values(proposer, recipient),
            recipient_state=_state_values(recipient, proposer),
            motive=_motive(evidence, policy_details),
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
            forced_response=forced_response,
        )
        result, created = _complete_negotiation(
            request_key,
            proposer,
            recipient,
            result,
            evidence,
            policy_details,
            occurred_ticks,
        )
        result, _ = _NEGOTIATIONS.remember_pair_session(
            proposer.sim_id,
            recipient.sim_id,
            occurred_ticks,
            result,
        )
        log(
            "breakup negotiation resolved transaction={} proposer={} recipient={} motive={} response={} response_scores={} final={} final_scores={} outcome={} official_authorized={} proposer_devoted={} recipient_devoted={}",
            result.transaction_id,
            proposer.sim_id,
            recipient.sim_id,
            result.motive,
            result.response,
            tuple(
                value.as_dict()
                for value in result.response_decision.candidates
            ),
            result.proposer_decision,
            (
                ()
                if result.final_decision is None
                else tuple(
                    value.as_dict()
                    for value in result.final_decision.candidates
                )
            ),
            result.outcome,
            result.official_breakup_authorized,
            proposer_devoted,
            recipient_devoted,
        )
        return result
    except Exception:
        log_exception(
            "breakup negotiation evaluation failed proposer={} recipient={}".format(
                getattr(proposer, "sim_id", None),
                getattr(recipient, "sim_id", None),
            )
        )
        return None

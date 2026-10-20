"""Apply model-selected relationship reactions as controlled Buff expressions.

This runtime is deliberately downstream of relationship interpretation.  It
does not decide what happened or mutate the five dimensions; it only projects
one already-selected response into a visible, temporary expression.  Missing
Buff tuning fails closed without affecting the relationship decision.
"""

import alarms
import date_and_time
import services
import sims4.resources

import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_emotion_expressions import (
    ExpressionPhase,
    ExpressionType,
    select_expression,
)


_ACTIVE_REACTIONS = {}
_REACTION_ALARMS = {}


def _sim_now_ticks():
    try:
        now = services.time_service().sim_now
        absolute_ticks = getattr(now, "absolute_ticks", None)
        return int(absolute_ticks() if callable(absolute_ticks) else now)
    except Exception:
        return None


def _buff_tuning(expression_type):
    instance_id = settings.RELATIONSHIP_REACTION_BUFF_INSTANCE_IDS.get(
        str(expression_type)
    )
    if instance_id is None:
        return None
    try:
        manager = services.get_instance_manager(sims4.resources.Types.BUFF)
        return manager.get(instance_id)
    except Exception:
        log_exception(
            "relationship reaction Buff lookup failed type={}".format(
                expression_type
            )
        )
        return None


def _reaction_expression_types():
    return (
        ExpressionType.BETRAYAL_PRESSURE,
        ExpressionType.BETRAYAL_HURT,
        ExpressionType.BETRAYAL_ANGER,
        ExpressionType.REPAIR_REOPENING,
        ExpressionType.REPAIR_WARY,
        ExpressionType.REPAIR_INSUFFICIENT,
    )


def _remove_reaction_buffs(sim_info):
    if sim_info is None:
        return
    for expression_type in _reaction_expression_types():
        buff = _buff_tuning(expression_type)
        if buff is None:
            continue
        try:
            if sim_info.has_buff(buff):
                sim_info.remove_buff_by_type(buff)
        except Exception:
            log_exception(
                "relationship reaction Buff removal failed sim={} type={}".format(
                    getattr(sim_info, "sim_id", None),
                    expression_type,
                )
            )


def _cancel_expiry(sim_id):
    handle = _REACTION_ALARMS.pop(int(sim_id), None)
    if handle is None:
        return
    try:
        alarms.cancel_alarm(handle)
    except Exception:
        pass


def _schedule_expiry(sim_info, partner_id, duration_minutes):
    sim_id = int(sim_info.sim_id)
    _cancel_expiry(sim_id)

    def _expire(_handle):
        _REACTION_ALARMS.pop(sim_id, None)
        _ACTIVE_REACTIONS.pop(sim_id, None)
        try:
            manager = services.sim_info_manager()
            current = manager.get(sim_id) if manager is not None else None
            _remove_reaction_buffs(current)
            log(
                "relationship reaction expired observer={} partner={}",
                sim_id,
                partner_id,
            )
        except Exception:
            log_exception(
                "relationship reaction expiry failed observer={}".format(
                    sim_id
                )
            )

    try:
        alarm_owner = sim_info.get_sim_instance() or sim_info
        handle = alarms.add_alarm(
            alarm_owner,
            date_and_time.create_time_span(
                minutes=max(1.0, float(duration_minutes))
            ),
            _expire,
            cross_zone=True,
        )
        _REACTION_ALARMS[sim_id] = handle
        return True
    except Exception:
        log_exception(
            "relationship reaction expiry schedule failed observer={}".format(
                sim_id
            )
        )
        return False


def _directed_state(observer_info, partner_info):
    try:
        from fgeh_cheatingharder_state import get_directed_state

        return get_directed_state(observer_info, partner_info)
    except Exception:
        log_exception(
            "relationship reaction state lookup failed observer={} partner={}".format(
                getattr(observer_info, "sim_id", None),
                getattr(partner_info, "sim_id", None),
            )
        )
        return None


def apply_breakup_takeover_expression(
    observer_info,
    partner_info,
    policy_details,
):
    """Select and apply at most one Buff for a newly-owned breakup request."""
    if observer_info is None or partner_info is None:
        return None
    state = _directed_state(observer_info, partner_info)
    if state is None:
        return None
    policy_details = dict(policy_details or {})
    context = dict(policy_details.get("reaction_context", {}) or {})
    context.setdefault(
        "selected_intent",
        policy_details.get("selected_intent"),
    )
    context.setdefault("severity", 100.0)
    selected, decision = select_expression(
        ExpressionPhase.BETRAYAL,
        state,
        context,
    )
    sim_id = int(observer_info.sim_id)
    partner_id = int(partner_info.sim_id)
    _cancel_expiry(sim_id)
    _remove_reaction_buffs(observer_info)
    if selected is None:
        _ACTIVE_REACTIONS.pop(sim_id, None)
        return None

    applied = selected.expression_type == ExpressionType.NONE
    if selected.expression_type != ExpressionType.NONE:
        buff = _buff_tuning(selected.expression_type)
        if buff is not None:
            try:
                if not observer_info.has_buff(buff):
                    observer_info.add_buff(buff)
                applied = bool(observer_info.has_buff(buff))
            except Exception:
                log_exception(
                    "relationship reaction Buff add failed observer={} type={}".format(
                        sim_id,
                        selected.expression_type,
                    )
                )
                applied = False

    record = {
        "observer_id": sim_id,
        "partner_id": partner_id,
        "expression_type": selected.expression_type,
        "started_at": _sim_now_ticks(),
        "duration_minutes": selected.duration_minutes,
        "applied": bool(applied),
        "selected_intent": context.get("selected_intent"),
        "decision": decision,
    }
    _ACTIVE_REACTIONS[sim_id] = record
    if selected.expression_type != ExpressionType.NONE and applied:
        _schedule_expiry(
            observer_info,
            partner_id,
            selected.duration_minutes,
        )
    log(
        "relationship reaction selected phase=betrayal observer={} partner={} intent={} expression={} duration={:.1f} applied={} roll={} total={} candidates={}",
        sim_id,
        partner_id,
        context.get("selected_intent"),
        selected.expression_type,
        selected.duration_minutes,
        applied,
        decision.get("roll"),
        decision.get("total"),
        tuple(
            (
                item.get("expression_type"),
                item.get("score"),
                item.get("eligible"),
                item.get("blockers"),
            )
            for item in decision.get("candidates", ())
        ),
    )
    return dict(record)


def apply_repair_action_expression(
    actor_info,
    recipient_info,
    action_type,
    accepted,
    action_tags=(),
    expression_score_modifiers=None,
    source_event_id=None,
):
    """Project one recipient-side response to a resolved repair action."""
    if actor_info is None or recipient_info is None:
        return None
    state = _directed_state(recipient_info, actor_info)
    if state is None:
        return None
    sim_id = int(recipient_info.sim_id)
    partner_id = int(actor_info.sim_id)
    active = _ACTIVE_REACTIONS.get(sim_id)
    if (
        active is not None
        and active.get("applied", False)
        and active.get("phase") == ExpressionPhase.REPAIR_RESPONSE
        and active.get("partner_id") == partner_id
        and active.get("repair_action_type") == str(action_type)
    ):
        record = dict(active)
        record["suppressed_by_active_reaction"] = True
        log(
            "relationship reaction suppressed by active repair response recipient={} actor={} action={} expression={}",
            sim_id,
            partner_id,
            action_type,
            active.get("expression_type"),
        )
        return record
    context = {
        "repair_action_type": str(action_type),
        "accepted": bool(accepted),
        "action_tags": tuple(str(value) for value in action_tags or ()),
        "expression_score_modifiers": dict(
            expression_score_modifiers or {}
        ),
    }
    selected, decision = select_expression(
        ExpressionPhase.REPAIR_RESPONSE,
        state,
        context,
    )
    _cancel_expiry(sim_id)
    _remove_reaction_buffs(recipient_info)
    if selected is None:
        _ACTIVE_REACTIONS.pop(sim_id, None)
        return None

    applied = selected.expression_type == ExpressionType.NONE
    if selected.expression_type != ExpressionType.NONE:
        buff = _buff_tuning(selected.expression_type)
        if buff is not None:
            try:
                if not recipient_info.has_buff(buff):
                    recipient_info.add_buff(buff)
                applied = bool(recipient_info.has_buff(buff))
            except Exception:
                log_exception(
                    "repair response Buff add failed recipient={} type={}".format(
                        sim_id,
                        selected.expression_type,
                    )
                )
                applied = False

    record = {
        "observer_id": sim_id,
        "partner_id": partner_id,
        "phase": ExpressionPhase.REPAIR_RESPONSE,
        "expression_type": selected.expression_type,
        "started_at": _sim_now_ticks(),
        "duration_minutes": selected.duration_minutes,
        "applied": bool(applied),
        "repair_action_type": str(action_type),
        "accepted": bool(accepted),
        "decision": decision,
    }
    _ACTIVE_REACTIONS[sim_id] = record
    if applied:
        _schedule_expiry(
            recipient_info,
            partner_id,
            selected.duration_minutes,
        )
    log(
        "relationship reaction selected phase=repair_response recipient={} actor={} action={} accepted={} expression={} duration={:.1f} applied={} roll={} total={} candidates={}",
        sim_id,
        partner_id,
        action_type,
        bool(accepted),
        selected.expression_type,
        selected.duration_minutes,
        applied,
        decision.get("roll"),
        decision.get("total"),
        tuple(
            (
                item.get("expression_type"),
                item.get("score"),
                item.get("eligible"),
                item.get("blockers"),
            )
            for item in decision.get("candidates", ())
        ),
    )
    try:
        from fgeh_cheatingharder_domain import EventType
        from fgeh_cheatingharder_event_center import publish

        publish(
            EventType.REACTION_EXPRESSION_SELECTED,
            source="relationship_reaction_runtime",
            event_id=(
                "{}:reaction:{}".format(
                    source_event_id,
                    selected.expression_type,
                )
                if source_event_id
                else None
            ),
            observer_id=sim_id,
            partner_id=partner_id,
            payload={
                "cause_id": source_event_id,
                "phase": ExpressionPhase.REPAIR_RESPONSE,
                "expression_type": selected.expression_type,
                "duration_minutes": selected.duration_minutes,
                "applied": bool(applied),
                "repair_action_type": str(action_type),
                "accepted": bool(accepted),
                "decision_roll": decision.get("roll"),
                "decision_total": decision.get("total"),
                "candidates": tuple(
                    {
                        "expression_type": item.get("expression_type"),
                        "score": item.get("score"),
                        "eligible": item.get("eligible"),
                        "blockers": tuple(item.get("blockers", ())),
                    }
                    for item in decision.get("candidates", ())
                ),
            },
        )
    except Exception:
        log_exception(
            "repair response expression ledger publish failed recipient={}".format(
                sim_id
            )
        )
    return dict(record)


def get_relationship_reaction_status(sim_id):
    record = _ACTIVE_REACTIONS.get(int(sim_id))
    return None if record is None else dict(record)


def reset_relationship_reaction_runtime():
    for handle in tuple(_REACTION_ALARMS.values()):
        try:
            alarms.cancel_alarm(handle)
        except Exception:
            pass
    _REACTION_ALARMS.clear()
    _ACTIVE_REACTIONS.clear()
    log("relationship reaction runtime reset")

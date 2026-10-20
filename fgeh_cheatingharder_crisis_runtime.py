"""Game boundary for persistent relationship-crisis cases and follow-ups."""

import services

import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_crisis_cases import (
    RelationshipCrisisAction,
    RelationshipCrisisStatus,
)
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_domain import ExecutionResult


def _store():
    from fgeh_cheatingharder_memory_runtime import get_memory_service

    return get_memory_service().store


def _sim_now_ticks():
    try:
        now = services.time_service().sim_now
        absolute_ticks = getattr(now, "absolute_ticks", None)
        return int(absolute_ticks() if callable(absolute_ticks) else now)
    except Exception:
        return None


def get_active_relationship_crisis(sim_a_id, sim_b_id):
    return _store().find_active_relationship_crisis(sim_a_id, sim_b_id)


def build_crisis_decision_context(observer, partner):
    record = get_active_relationship_crisis(
        observer.sim_id,
        partner.sim_id,
    )
    if record is None:
        return {
            "relationship_crisis": {
                "active": False,
            }
        }
    return {
        "relationship_crisis": {
            "active": True,
            "case_id": record.case_id,
            "status": record.status,
            "stage": record.stage,
            "cause_type": record.cause_type,
            "role": record.role_for(observer.sim_id),
            "proposer_id": record.proposer_id,
            "recipient_id": record.recipient_id,
            "severity": record.severity,
            "proposal_count": record.proposal_count,
            "round_index": record.round_index,
        }
    }


def _schedule_direction(record, actor_id, target_id, minutes, reason):
    try:
        manager = services.sim_info_manager()
        actor = manager.get(int(actor_id))
        target = manager.get(int(target_id))
        if actor is None or target is None:
            return None
        from fgeh_cheatingharder_scheduler import (
            schedule_relationship_reevaluation,
        )

        return schedule_relationship_reevaluation(
            actor,
            target,
            reason="relationship_crisis:{}:{}".format(
                record.case_id,
                reason,
            ),
            minutes=minutes,
            payload={
                "relationship_crisis_case_id": record.case_id,
                "relationship_crisis_reason": reason,
            },
        )
    except Exception:
        log_exception(
            "relationship crisis direction scheduling failed case={}".format(
                record.case_id
            )
        )
        return None


def schedule_relationship_crisis_round(record, restored=False):
    """Schedule one asymmetric decision for each side of an active case."""
    if record is None or not record.is_active:
        return ()
    first_delay = (
        settings.RELATIONSHIP_CRISIS_RESTORE_FIRST_SIM_MINUTES
        if restored
        else settings.RELATIONSHIP_CRISIS_FIRST_RESPONSE_SIM_MINUTES
    )
    values = (
        _schedule_direction(
            record,
            record.recipient_id,
            record.proposer_id,
            first_delay,
            "recipient_response",
        ),
        _schedule_direction(
            record,
            record.proposer_id,
            record.recipient_id,
            first_delay + settings.RELATIONSHIP_CRISIS_ROLE_STAGGER_SIM_MINUTES,
            "proposer_follow_up",
        ),
    )
    log(
        "relationship crisis round scheduled case={} proposer={} recipient={} "
        "restored={} handles={}",
        record.case_id,
        record.proposer_id,
        record.recipient_id,
        restored,
        tuple(value is not None for value in values),
    )
    return values


def open_delayed_breakup_crisis(result, occurred_at=None):
    """Project one delayed negotiation into a durable, idempotent case."""
    if getattr(result, "outcome", None) != "relationship_delayed":
        return None
    response = getattr(result, "response", None)
    final_decision = getattr(result, "proposer_decision", None)
    severity = 50.0
    if response == "plead_to_stay":
        severity += 15.0
    if final_decision == "delay_breakup":
        severity += 10.0
    record, created = _store().open_relationship_crisis(
        result.proposer_id,
        result.recipient_id,
        result.transaction_id,
        occurred_at=occurred_at,
        severity=severity,
        cause_type="delayed_breakup",
    )
    schedule_relationship_crisis_round(record)
    log(
        "relationship crisis opened case={} created={} transaction={} "
        "proposer={} recipient={} proposals={} severity={}",
        record.case_id,
        created,
        result.transaction_id,
        result.proposer_id,
        result.recipient_id,
        record.proposal_count,
        record.severity,
    )
    return record


def _record_action(record, action_type, actor, target, outcome, details=None):
    action_id = "crisis-action:{}:{}:{}:{}".format(
        record.case_id,
        action_type,
        actor.sim_id,
        record.round_index + 1,
    )
    _store().record_relationship_crisis_action(
        record.case_id,
        action_type,
        actor.sim_id,
        target.sim_id,
        outcome,
        occurred_at=_sim_now_ticks(),
        details=details,
        action_id=action_id,
    )
    return action_id


def execute_crisis_seek_reassurance(intent, observer, partner):
    record = get_active_relationship_crisis(observer.sim_id, partner.sim_id)
    if record is None:
        return ExecutionResult(False, "relationship_crisis_missing")
    try:
        from fgeh_cheatingharder_autonomous_behavior_runtime import (
            schedule_relationship_crisis_reassurance,
        )

        handle = schedule_relationship_crisis_reassurance(
            observer,
            partner,
            record.case_id,
            source_transaction_id=(
                record.source_transaction_ids[-1]
                if record.source_transaction_ids
                else None
            ),
        )
        action_id = _record_action(
            record,
            RelationshipCrisisAction.SEEK_REASSURANCE,
            observer,
            partner,
            "scheduled" if handle is not None else "scheduling_failed",
        )
        return ExecutionResult(
            handle is not None,
            (
                "crisis_reassurance_scheduled"
                if handle is not None
                else "crisis_reassurance_schedule_failed"
            ),
            {"crisis_case_id": record.case_id, "action_id": action_id},
        )
    except Exception:
        log_exception(
            "relationship crisis reassurance failed case={}".format(
                record.case_id
            )
        )
        return ExecutionResult(False, "crisis_reassurance_exception")


def execute_crisis_give_space(intent, observer, partner):
    record = get_active_relationship_crisis(observer.sim_id, partner.sim_id)
    if record is None:
        return ExecutionResult(False, "relationship_crisis_missing")
    action_id = _record_action(
        record,
        RelationshipCrisisAction.GIVE_SPACE,
        observer,
        partner,
        "completed",
    )
    _schedule_direction(
        record,
        observer.sim_id,
        partner.sim_id,
        settings.RELATIONSHIP_CRISIS_GIVE_SPACE_SIM_MINUTES,
        "space_elapsed",
    )
    try:
        from fgeh_cheatingharder_notification import (
            show_relationship_crisis_action_notification,
        )

        show_relationship_crisis_action_notification(
            observer,
            partner,
            RelationshipCrisisAction.GIVE_SPACE,
        )
    except Exception:
        log_exception("relationship crisis give-space notification failed")
    return ExecutionResult(
        True,
        "crisis_give_space_selected",
        {"crisis_case_id": record.case_id, "action_id": action_id},
    )


def execute_crisis_repeat_breakup(intent, observer, partner):
    record = get_active_relationship_crisis(observer.sim_id, partner.sim_id)
    if record is None:
        return ExecutionResult(False, "relationship_crisis_missing")
    if record.proposer_id != int(observer.sim_id):
        return ExecutionResult(False, "crisis_actor_is_not_proposer")
    try:
        from fgeh_cheatingharder_autonomous_breakup import push_breakup_proposal

        result = push_breakup_proposal(observer, partner, intent)
        action_id = _record_action(
            record,
            RelationshipCrisisAction.REPEAT_BREAKUP,
            observer,
            partner,
            result.status,
            details=result.details,
        )
        if record.is_active:
            _schedule_direction(
                record,
                observer.sim_id,
                partner.sim_id,
                settings.RELATIONSHIP_CRISIS_REPEAT_DECISION_SIM_MINUTES,
                "repeat_breakup_follow_up",
            )
        return ExecutionResult(
            result.accepted,
            result.status,
            dict(
                result.details,
                crisis_case_id=record.case_id,
                action_id=action_id,
            ),
        )
    except Exception:
        log_exception(
            "relationship crisis repeat breakup failed case={}".format(
                record.case_id
            )
        )
        return ExecutionResult(False, "crisis_repeat_breakup_exception")


def on_autonomous_action_resolved(event):
    payload = dict(getattr(event, "payload", {}) or {})
    case_id = payload.get("crisis_case_id")
    if not case_id:
        return False
    record = _store().get_relationship_crisis(case_id)
    if record is None or not record.is_active:
        return False
    actor_id = int(event.observer_id)
    target_id = int(event.partner_id)
    _store().record_relationship_crisis_action(
        case_id,
        payload.get("crisis_action", payload.get("intent")),
        actor_id,
        target_id,
        payload.get("status", "unknown"),
        occurred_at=payload.get("occurred_at"),
        source_event_id=event.event_id,
        details={"success": bool(payload.get("success", False))},
        action_id="{}:crisis-resolution".format(event.event_id),
    )
    _schedule_direction(
        record,
        actor_id,
        target_id,
        settings.RELATIONSHIP_CRISIS_ACTION_COOLDOWN_SIM_MINUTES,
        "action_resolved",
    )
    return True


def close_crisis_after_relationship_end(sim_a_id, sim_b_id, event_id=None):
    changed = _store().close_relationship_crises_for_pair(
        sim_a_id,
        sim_b_id,
        status=RelationshipCrisisStatus.RELATIONSHIP_ENDED,
        occurred_at=_sim_now_ticks(),
        details={"source_event_id": event_id},
    )
    if changed:
        log(
            "relationship crisis closed after official breakup pair={}-{} "
            "count={} event={}",
            sim_a_id,
            sim_b_id,
            changed,
            event_id,
        )
    return changed


def restore_active_relationship_crises():
    records = tuple(
        record
        for record in _store().relationship_crises()
        if record.is_active
    )
    for record in records:
        schedule_relationship_crisis_round(record, restored=True)
    log("active relationship crises restored count={}", len(records))
    return len(records)

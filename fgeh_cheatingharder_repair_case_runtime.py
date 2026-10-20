"""Narrow game-facing bridge between negotiations, actions, and repair cases."""

from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_repair_cases import SINCERE_APOLOGY_REQUIREMENT
from fgeh_cheatingharder_repair_responsibility import (
    resolve_repair_responsibility,
)


def _store():
    from fgeh_cheatingharder_memory_runtime import get_memory_service

    return get_memory_service().store


def open_case_for_reconciliation(result):
    """Create the first repair requirement when the recipient asks for repair."""
    try:
        if getattr(result, "outcome", None) != "repair_required":
            return None
        store = _store()
        responsibility = resolve_repair_responsibility(
            store.events_for_relationship(
                result.proposer_id,
                result.recipient_id,
            ),
            result.proposer_id,
            result.recipient_id,
        )
        if not responsibility.requester_may_demand_repair:
            log(
                "repair case skipped invalid requester transaction={} responsibility={}",
                result.transaction_id,
                responsibility.to_data(),
            )
            return None
        record, created = store.open_repair_case(
            accountable_id=responsibility.accountable_id,
            harmed_id=responsibility.harmed_id,
            requirement_keys=(SINCERE_APOLOGY_REQUIREMENT.key,),
            source_transaction_id=result.transaction_id,
            reconciliation_proposer_id=(
                responsibility.reconciliation_proposer_id
            ),
            repair_requester_id=responsibility.repair_requester_id,
            responsibility_basis=responsibility.basis,
            responsibility_confidence=responsibility.confidence,
            responsibility_confirmed=responsibility.confirmed,
            responsibility_source_event_id=(
                responsibility.source_event_id
            ),
        )
        log(
            "repair case {} case={} accountable={} harmed={} requirements={} basis={} confidence={} confirmed={} evidence={}",
            "opened" if created else "reused",
            record.case_id,
            record.accountable_id,
            record.harmed_id,
            record.requirement_keys,
            record.responsibility_basis,
            record.responsibility_confidence,
            record.responsibility_confirmed,
            record.responsibility_source_event_id,
        )
        return record
    except Exception:
        log_exception(
            "repair case open failed transaction={}".format(
                getattr(result, "transaction_id", None)
            )
        )
        return None


def apply_repair_action(
    actor_id,
    recipient_id,
    action_type,
    accepted,
    source_event_id=None,
):
    try:
        record = _store().apply_repair_action_to_case(
            actor_id,
            recipient_id,
            action_type,
            accepted,
            source_event_id=source_event_id,
        )
        if record is not None:
            log(
                "repair case action case={} action={} accepted={} status={} satisfied={}",
                record.case_id,
                action_type,
                bool(accepted),
                record.status,
                record.satisfied_requirement_keys,
            )
        return record
    except Exception:
        log_exception(
            "repair case action failed actor={} recipient={} action={}".format(
                actor_id,
                recipient_id,
                action_type,
            )
        )
        return None


def reconciliation_context(proposer_id, recipient_id):
    """Return recipient-facing facts consumed by the pure utility model."""
    try:
        store = _store()
        record = store.find_active_repair_case_for_pair(
            proposer_id,
            recipient_id,
        )
        responsibility = resolve_repair_responsibility(
            store.events_for_relationship(proposer_id, recipient_id),
            proposer_id,
            recipient_id,
        )
        return {
            "repair_case_exists": record is not None,
            "repair_case_satisfied": bool(
                record is not None and record.is_satisfied
            ),
            "repair_case_id": (
                None if record is None else record.case_id
            ),
            "repair_request_valid": (
                responsibility.requester_may_demand_repair
            ),
            "responsibility": responsibility.to_data(),
        }
    except Exception:
        log_exception(
            "repair case context failed proposer={} recipient={}".format(
                proposer_id,
                recipient_id,
            )
        )
        return {}


def repair_case_view_for_action(actor_id, recipient_id):
    """Return primitive UI facts without exposing the mutable case record."""
    try:
        record = _store().find_active_repair_case(actor_id, recipient_id)
        if record is None:
            return None
        return {
            "case_id": record.case_id,
            "status": record.status,
            "requirement_keys": tuple(record.requirement_keys),
            "satisfied_requirement_keys": tuple(
                record.satisfied_requirement_keys
            ),
            "is_satisfied": bool(record.is_satisfied),
            "accountable_id": record.accountable_id,
            "harmed_id": record.harmed_id,
            "repair_requester_id": record.repair_requester_id,
            "responsibility_basis": record.responsibility_basis,
            "responsibility_confidence": (
                record.responsibility_confidence
            ),
            "responsibility_confirmed": (
                record.responsibility_confirmed
            ),
        }
    except Exception:
        log_exception(
            "repair case view failed actor={} recipient={}".format(
                actor_id,
                recipient_id,
            )
        )
        return None


def repair_case_view_for_pair(sim_a_id, sim_b_id):
    try:
        record = _store().find_active_repair_case_for_pair(
            sim_a_id,
            sim_b_id,
        )
        if record is None:
            return None
        return {
            "case_id": record.case_id,
            "status": record.status,
            "accountable_id": record.accountable_id,
            "harmed_id": record.harmed_id,
            "repair_requester_id": record.repair_requester_id,
            "requirement_keys": tuple(record.requirement_keys),
            "responsibility_basis": record.responsibility_basis,
            "responsibility_confidence": (
                record.responsibility_confidence
            ),
            "responsibility_confirmed": (
                record.responsibility_confirmed
            ),
            "responsibility_source_event_id": (
                record.responsibility_source_event_id
            ),
        }
    except Exception:
        log_exception(
            "repair case pair view failed first={} second={}".format(
                sim_a_id,
                sim_b_id,
            )
        )
        return None


def close_completed_cases(sim_a_id, sim_b_id):
    try:
        return _store().close_satisfied_repair_cases(sim_a_id, sim_b_id)
    except Exception:
        log_exception(
            "repair case close failed sim_a={} sim_b={}".format(
                sim_a_id,
                sim_b_id,
            )
        )
        return 0

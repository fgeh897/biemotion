"""Narrow game-facing bridge for completed relationship-repair actions."""

from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_domain import EventType
from fgeh_cheatingharder_repair import get_repair_action
from fgeh_cheatingharder_relationship import get_sim_info


def record_repair_action_resolution(
    actor_sim_or_info,
    recipient_sim_or_info,
    repair_action_type,
    accepted,
    source="repair_interaction",
    event_id=None,
):
    """Publish one concrete repair result without changing EA track values."""
    actor = get_sim_info(actor_sim_or_info)
    recipient = get_sim_info(recipient_sim_or_info)
    definition = get_repair_action(repair_action_type)
    if (
        actor is None
        or recipient is None
        or actor.sim_id == recipient.sim_id
        or definition is None
    ):
        log(
            "repair action rejected before ledger actor={} recipient={} action={} definition_found={}",
            getattr(actor, "sim_id", None),
            getattr(recipient, "sim_id", None),
            repair_action_type,
            definition is not None,
        )
        return False
    try:
        from fgeh_cheatingharder_event_center import publish

        event = publish(
            EventType.REPAIR_ACTION_RESOLVED,
            source=source,
            event_id=event_id,
            actor_id=actor.sim_id,
            target_id=recipient.sim_id,
            payload={
                "repair_action_type": definition.action_type,
                "repair_action_tags": definition.tags,
                "accepted": bool(accepted),
                # EA friendship/romance mutation is intentionally absent.
                "ea_track_effect_applied": False,
            },
        )
        from fgeh_cheatingharder_repair_case_runtime import apply_repair_action

        apply_repair_action(
            actor.sim_id,
            recipient.sim_id,
            definition.action_type,
            bool(accepted),
            source_event_id=event.event_id,
        )
        log(
            "repair action recorded actor={} recipient={} action={} accepted={}",
            actor.sim_id,
            recipient.sim_id,
            definition.action_type,
            bool(accepted),
        )
        return True
    except Exception:
        log_exception(
            "repair action publish failed actor={} recipient={} action={}".format(
                actor.sim_id,
                recipient.sim_id,
                definition.action_type,
            )
        )
        return False

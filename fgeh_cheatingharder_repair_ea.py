"""Adapter from EA's post-breakup apology outcome into relationship repair."""

import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_reconciliation_ea import (
    are_official_partners,
    have_former_relationship_marker,
)
from fgeh_cheatingharder_relationship import get_sim_info
from fgeh_cheatingharder_repair import (
    is_supported_ea_apology_affordance_id,
)
from fgeh_cheatingharder_repair_runtime import (
    record_repair_action_resolution,
)


def _affordance_id(interaction):
    affordance = getattr(interaction, "affordance", None)
    return getattr(affordance, "guid64", None)


def is_ea_apology_interaction(interaction):
    affordance_id = _affordance_id(interaction)
    return (
        affordance_id
        == settings.EA_INTERACTION_APOLOGIZE_TARGETED_FRIENDLY
        and is_supported_ea_apology_affordance_id(affordance_id)
    )


def is_post_breakup_repair_pair(actor_sim_info, recipient_sim_info):
    """Require EA's saved former-partner state, not a guessed low romance bar."""
    if actor_sim_info is None or recipient_sim_info is None:
        return False
    if actor_sim_info.sim_id == recipient_sim_info.sim_id:
        return False
    if (
        are_official_partners(actor_sim_info, recipient_sim_info)
        or are_official_partners(recipient_sim_info, actor_sim_info)
    ):
        return False
    return have_former_relationship_marker(
        actor_sim_info,
        recipient_sim_info,
    )


def observe_ea_apology_outcome(
    interaction,
    accepted,
    event_id=None,
):
    """Record one EA apology result; return True only when it was adapted."""
    if not is_ea_apology_interaction(interaction):
        return False
    actor = get_sim_info(getattr(interaction, "sim", None))
    recipient = get_sim_info(getattr(interaction, "target", None))
    if not is_post_breakup_repair_pair(actor, recipient):
        log(
            "EA apology ignored outside post-breakup repair actor={} recipient={}",
            getattr(actor, "sim_id", None),
            getattr(recipient, "sim_id", None),
        )
        return False
    try:
        recorded = record_repair_action_resolution(
            actor,
            recipient,
            "apology",
            bool(accepted),
            source="ea_post_breakup_apology",
            event_id=event_id,
        )
        if not recorded:
            return False
        log(
            "EA post-breakup apology adapted actor={} recipient={} accepted={} event={}",
            actor.sim_id,
            recipient.sim_id,
            bool(accepted),
            event_id,
        )
        try:
            from fgeh_cheatingharder_reaction_runtime import (
                apply_repair_action_expression,
            )

            apply_repair_action_expression(
                actor,
                recipient,
                "apology",
                bool(accepted),
                action_tags=("communication", "accountability", "post_breakup"),
                source_event_id=event_id,
            )
        except Exception:
            log_exception("EA apology repair expression failed")
        try:
            from fgeh_cheatingharder_notification import (
                show_repair_action_notification,
            )

            show_repair_action_notification(
                actor,
                recipient,
                "apology",
                bool(accepted),
            )
        except Exception:
            log_exception("EA apology repair notification failed")
        return True
    except Exception:
        log_exception("EA post-breakup apology adaptation failed")
        return False

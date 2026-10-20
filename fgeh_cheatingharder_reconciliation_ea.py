"""Narrow EA boundary for reading and restoring official partnership state."""

import services
import sims4.resources

from event_testing.resolver import DoubleSimResolver
from sims4.resources import Types

import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception


_BIT_CACHE = {}
_ADD_BOTH_LOOT = None


def _get_tuning(resource_type, instance_id):
    key = sims4.resources.get_resource_key(
        int(instance_id),
        resource_type,
    )
    manager = services.get_instance_manager(resource_type)
    return None if manager is None else manager.get(key)


def _relationship_bit(instance_id):
    instance_id = int(instance_id)
    if instance_id not in _BIT_CACHE:
        try:
            _BIT_CACHE[instance_id] = _get_tuning(
                Types.RELATIONSHIP_BIT,
                instance_id,
            )
        except Exception:
            _BIT_CACHE[instance_id] = None
            log_exception(
                "reconciliation relationship bit lookup failed id={}".format(
                    instance_id
                )
            )
    return _BIT_CACHE[instance_id]


def _has_bit(first_sim_info, second_sim_info, instance_id):
    bit = _relationship_bit(instance_id)
    if bit is None:
        return False
    try:
        return bool(
            first_sim_info.relationship_tracker.has_bit(
                second_sim_info.sim_id,
                bit,
            )
        )
    except Exception:
        log_exception(
            "reconciliation relationship bit test failed first={} second={} bit={}".format(
                getattr(first_sim_info, "sim_id", None),
                getattr(second_sim_info, "sim_id", None),
                instance_id,
            )
        )
        return False


def are_official_partners(first_sim_info, second_sim_info):
    return _has_bit(
        first_sim_info,
        second_sim_info,
        settings.EA_REL_BIT_ROMANTIC_SIGNIFICANT_OTHER,
    )


def have_former_relationship_marker(first_sim_info, second_sim_info):
    """Read EA's saved ex-partner markers; memory is not substituted here."""
    for bit_id in settings.EA_FORMER_ROMANTIC_RELATIONSHIP_BIT_IDS:
        if (
            _has_bit(first_sim_info, second_sim_info, bit_id)
            or _has_bit(second_sim_info, first_sim_info, bit_id)
        ):
            return True
    return False


def _significant_other_add_both_loot():
    global _ADD_BOTH_LOOT
    if _ADD_BOTH_LOOT is None:
        try:
            _ADD_BOTH_LOOT = _get_tuning(
                Types.ACTION,
                settings.EA_LOOT_SIGNIFICANT_OTHER_ADD_BOTH,
            )
            log(
                "EA reconciliation loot lookup found={} id={}",
                _ADD_BOTH_LOOT is not None,
                settings.EA_LOOT_SIGNIFICANT_OTHER_ADD_BOTH,
            )
        except Exception:
            log_exception("EA reconciliation loot lookup failed")
    return _ADD_BOTH_LOOT


def _resend_relationship_info(first_sim_info, second_sim_info):
    for owner, target in (
        (first_sim_info, second_sim_info),
        (second_sim_info, first_sim_info),
    ):
        try:
            owner.relationship_tracker.send_relationship_info(
                target_sim_id=target.sim_id
            )
        except Exception:
            log_exception(
                "reconciliation relationship info refresh failed owner={} target={}".format(
                    owner.sim_id,
                    target.sim_id,
                )
            )


def restore_official_partnership(proposer_sim_info, recipient_sim_info):
    """Commit mutual acceptance through EA's own AddBoth relationship loot.

    Tuning 279989 removes the ordinary broken-up, broken-up-engaged, and
    divorced markers in both directions, restores romantic-Significant_Other,
    and runs EA's pack-safe satisfaction/status follow-up loots.
    """
    if proposer_sim_info is None or recipient_sim_info is None:
        return False
    if proposer_sim_info.sim_id == recipient_sim_info.sim_id:
        return False
    if are_official_partners(proposer_sim_info, recipient_sim_info):
        _resend_relationship_info(
            proposer_sim_info,
            recipient_sim_info,
        )
        return True
    loot = _significant_other_add_both_loot()
    if loot is None:
        log(
            "EA reconciliation commit unavailable proposer={} recipient={}",
            proposer_sim_info.sim_id,
            recipient_sim_info.sim_id,
        )
        return False
    try:
        resolver = DoubleSimResolver(
            proposer_sim_info,
            recipient_sim_info,
        )
        loot.apply_to_resolver(resolver)
        restored = (
            are_official_partners(
                proposer_sim_info,
                recipient_sim_info,
            )
            and are_official_partners(
                recipient_sim_info,
                proposer_sim_info,
            )
        )
        _resend_relationship_info(
            proposer_sim_info,
            recipient_sim_info,
        )
        log(
            "EA reconciliation commit proposer={} recipient={} restored={} former_marker_remaining={}",
            proposer_sim_info.sim_id,
            recipient_sim_info.sim_id,
            restored,
            have_former_relationship_marker(
                proposer_sim_info,
                recipient_sim_info,
            ),
        )
        return restored
    except Exception:
        log_exception(
            "EA reconciliation commit failed proposer={} recipient={}".format(
                proposer_sim_info.sim_id,
                recipient_sim_info.sim_id,
            )
        )
        return False

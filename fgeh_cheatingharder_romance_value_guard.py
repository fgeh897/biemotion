"""Deep EA romance-track invariant for permanent one-way devotion.

Interaction filters provide good UI and autonomy behavior, but third-party
mods can bypass those entry points.  This adapter guards the concrete EA
relationship-track mutation boundary as a final safety net.
"""

from relationships.relationship_track import RelationshipTrack

import fgeh_cheatingharder_injector as injector
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_devotion import evaluate_romance_value_change
from fgeh_cheatingharder_devotion_runtime import get_devotion_bond


_INSTALLED = False
_BLOCK_LOG_KEYS = set()


def _guid64(value):
    value = getattr(value, "guid64", None)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_ea_romance_track(track):
    stat_type = getattr(track, "stat_type", None)
    romance_type = getattr(RelationshipTrack, "ROMANCE_TRACK", None)
    if stat_type is romance_type and romance_type is not None:
        return True
    stat_guid = _guid64(stat_type)
    romance_guid = _guid64(romance_type)
    return (
        stat_guid is not None
        and romance_guid is not None
        and stat_guid == romance_guid
    )


def _relationship_pair(track):
    tracker = getattr(track, "tracker", None)
    if tracker is None:
        tracker = getattr(track, "_tracker", None)
    rel_data = getattr(tracker, "rel_data", None)
    relationship = getattr(rel_data, "relationship", None)
    sim_id_a = getattr(relationship, "sim_id_a", None)
    sim_id_b = getattr(relationship, "sim_id_b", None)
    try:
        sim_id_a = int(sim_id_a)
        sim_id_b = int(sim_id_b)
    except (TypeError, ValueError):
        return None
    if sim_id_a <= 0 or sim_id_b <= 0 or sim_id_a == sim_id_b:
        return None
    return sim_id_a, sim_id_b


def _is_loading(track, kwargs):
    if kwargs.get("from_load", False):
        return True
    tracker = getattr(track, "tracker", None)
    if tracker is None:
        tracker = getattr(track, "_tracker", None)
    return bool(
        getattr(tracker, "load_in_progress", False)
        or getattr(tracker, "suppress_callback_setup_during_load", False)
    )


def is_romance_value_guard_installed():
    return _INSTALLED


def install_romance_value_guard():
    global _INSTALLED
    if _INSTALLED:
        return True
    try:
        @injector.inject(RelationshipTrack, "set_value", safe=True)
        def _guard_romance_value(original, track, value, *args, **kwargs):
            try:
                if not _is_loading(track, kwargs) and _is_ea_romance_track(track):
                    pair = _relationship_pair(track)
                    if pair is not None:
                        current_value = track.get_value()
                        permission = evaluate_romance_value_change(
                            pair[0],
                            pair[1],
                            current_value,
                            value,
                            get_devotion_bond,
                        )
                        if not permission.allowed:
                            log_key = (
                                pair,
                                round(float(current_value), 3),
                                round(float(value), 3),
                                permission.reason,
                            )
                            if log_key not in _BLOCK_LOG_KEYS:
                                _BLOCK_LOG_KEYS.add(log_key)
                                if len(_BLOCK_LOG_KEYS) > 512:
                                    _BLOCK_LOG_KEYS.clear()
                                    _BLOCK_LOG_KEYS.add(log_key)
                                log(
                                    "devotion romance value blocked pair={}<->{} current={} requested={} owner={} beloved={} reason={}",
                                    pair[0],
                                    pair[1],
                                    current_value,
                                    value,
                                    permission.devoted_owner_id,
                                    permission.beloved_id,
                                    permission.reason,
                                )
                            return None
            except Exception:
                # A relationship invariant failure must not break saving,
                # loading, or the global EA statistic system.
                log_exception("devotion romance value guard failed open")
            return original(track, value, *args, **kwargs)

        _INSTALLED = True
        log("permanent devotion romance value guard installed")
        return True
    except Exception:
        log_exception("permanent devotion romance value guard install failed")
        return False

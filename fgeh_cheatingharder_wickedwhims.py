"""Optional WickedWhims adapter for permanent one-way devotion.

WickedWhims is never imported at module load.  Installation is retried after
zone load, patches the central pair test, and guards the final pre-sex start
and join boundaries.  Missing or changed WW APIs fail open with diagnostics.
"""

import functools
import importlib
import sys

from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_devotion import (
    evaluate_intimate_group,
    evaluate_romantic_pair,
)
from fgeh_cheatingharder_domain import EventType


_INSTALLED = False
_PUBLISHED_ATTEMPTS = set()
_PAIR_MODULE = "wickedwhims.sex.autonomy.utils.sims_pairs"
_START_MODULE = (
    "wickedwhims.sex.integral.sex_handlers.pre_sex.pre_sex_handlers"
)
_JOIN_MODULE = "wickedwhims.sex.integral.joining_sex.utils"


def _turbo_sim_id(turbo_sim):
    if turbo_sim is None:
        return None
    getter = getattr(turbo_sim, "get_sim_id", None)
    if callable(getter):
        try:
            value = int(getter())
            return value if value > 0 else None
        except (TypeError, ValueError):
            return None
    sim_info = getattr(turbo_sim, "sim_info", None)
    value = getattr(sim_info, "sim_id", getattr(turbo_sim, "sim_id", None))
    try:
        value = int(value)
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def _bond_lookup(owner_id):
    from fgeh_cheatingharder_devotion_runtime import get_devotion_bond

    return get_devotion_bond(owner_id)


def _pair_permission(first_turbo_sim, second_turbo_sim):
    first_id = _turbo_sim_id(first_turbo_sim)
    second_id = _turbo_sim_id(second_turbo_sim)
    if first_id is None or second_id is None:
        return None
    return evaluate_romantic_pair(first_id, second_id, _bond_lookup)


def _group_permission(turbo_sims):
    participant_ids = tuple(
        sim_id
        for sim_id in (_turbo_sim_id(value) for value in turbo_sims)
        if sim_id is not None
    )
    if len(participant_ids) < 2:
        return None
    return evaluate_intimate_group(participant_ids, _bond_lookup)


def _pre_sex_actors(pre_sex_instance):
    getter = getattr(pre_sex_instance, "get_actors_as_turbo_sim", None)
    if not callable(getter):
        return ()
    try:
        return tuple(getter())
    except Exception:
        log_exception("WW devotion actor extraction failed")
        return ()


def _cleanup_blocked_start(pre_sex_instance, actors):
    try:
        persistence = importlib.import_module(
            "wickedwhims.sex.integral.persistence"
        )
        clear_variables = getattr(
            persistence,
            "clear_sim_sex_variables",
            None,
        )
        if callable(clear_variables):
            for turbo_sim in actors:
                try:
                    clear_variables(turbo_sim)
                except Exception:
                    log_exception("WW devotion Sim cleanup failed")
        clear_reservation = getattr(
            pre_sex_instance,
            "clear_location_reservation",
            None,
        )
        if callable(clear_reservation):
            clear_reservation()
    except Exception:
        log_exception("WW devotion blocked-start cleanup failed")


def _publish_rejection(permission, source, attempt):
    if permission is None or permission.allowed:
        return
    attempt_key = "{}:{}:{}:{}".format(
        source,
        id(attempt),
        permission.actor_id,
        permission.target_id,
    )
    if attempt_key in _PUBLISHED_ATTEMPTS:
        return
    _PUBLISHED_ATTEMPTS.add(attempt_key)
    if len(_PUBLISHED_ATTEMPTS) > 512:
        _PUBLISHED_ATTEMPTS.clear()
        _PUBLISHED_ATTEMPTS.add(attempt_key)
    try:
        from fgeh_cheatingharder_event_center import publish

        publish(
            EventType.OUTSIDE_ROMANCE_REJECTED,
            source=source,
            event_id="ww-devotion-rejection:{}".format(attempt_key),
            actor_id=permission.actor_id,
            target_id=permission.target_id,
            observer_id=permission.devoted_owner_id,
            partner_id=permission.beloved_id,
            payload={
                "interaction_name": "wickedwhims.sex",
                "activity_kind": "sex",
                "provider": "wickedwhims",
                "block_reason": permission.reason,
            },
        )
    except Exception:
        log_exception("WW devotion rejection event publish failed")


def _replace_imported_aliases(symbol_name, original, replacement):
    replaced = 0
    for module_name, module in tuple(sys.modules.items()):
        if not module_name.startswith("wickedwhims.sex.") or module is None:
            continue
        try:
            if getattr(module, symbol_name, None) is original:
                setattr(module, symbol_name, replacement)
                replaced += 1
        except Exception:
            continue
    return replaced


def _install_pair_guard():
    module = importlib.import_module(_PAIR_MODULE)
    original = getattr(module, "is_acceptable_sims_sex_pair")
    if getattr(original, "_fgeh_devotion_guard", False):
        return 0

    @functools.wraps(original)
    def _guarded_pair(asking_turbo_sim, asked_turbo_sim, *args, **kwargs):
        try:
            permission = _pair_permission(
                asking_turbo_sim,
                asked_turbo_sim,
            )
            if permission is not None and not permission.allowed:
                return False
        except Exception:
            log_exception("WW devotion pair test failed open")
        return original(asking_turbo_sim, asked_turbo_sim, *args, **kwargs)

    _guarded_pair._fgeh_devotion_guard = True
    setattr(module, "is_acceptable_sims_sex_pair", _guarded_pair)
    return _replace_imported_aliases(
        "is_acceptable_sims_sex_pair",
        original,
        _guarded_pair,
    )


def _install_start_guard():
    module = importlib.import_module(_START_MODULE)
    original = getattr(module, "start_sex_interaction_from_pre_sex_instance")
    if getattr(original, "_fgeh_devotion_guard", False):
        return 0

    @functools.wraps(original)
    def _guarded_start(pre_sex_instance, *args, **kwargs):
        try:
            actors = _pre_sex_actors(pre_sex_instance)
            permission = _group_permission(actors)
            if permission is not None and not permission.allowed:
                log(
                    "WW sex start blocked actor={} target={} owner={} beloved={} reason={}",
                    permission.actor_id,
                    permission.target_id,
                    permission.devoted_owner_id,
                    permission.beloved_id,
                    permission.reason,
                )
                _cleanup_blocked_start(pre_sex_instance, actors)
                _publish_rejection(
                    permission,
                    "wickedwhims_start_guard",
                    pre_sex_instance,
                )
                return False
        except Exception:
            log_exception("WW devotion start guard failed open")
        return original(pre_sex_instance, *args, **kwargs)

    _guarded_start._fgeh_devotion_guard = True
    setattr(
        module,
        "start_sex_interaction_from_pre_sex_instance",
        _guarded_start,
    )
    return _replace_imported_aliases(
        "start_sex_interaction_from_pre_sex_instance",
        original,
        _guarded_start,
    )


def _install_join_guard():
    module = importlib.import_module(_JOIN_MODULE)
    original = getattr(module, "join_sex_interaction_from_pre_sex_instance")
    if getattr(original, "_fgeh_devotion_guard", False):
        return 0

    @functools.wraps(original)
    def _guarded_join(
        pre_sex_instance,
        join_sims_list,
        *args,
        **kwargs
    ):
        try:
            current_actors = _pre_sex_actors(pre_sex_instance)
            joining_actors = tuple(join_sims_list or ())
            permission = _group_permission(
                current_actors + joining_actors
            )
            if permission is not None and not permission.allowed:
                log(
                    "WW sex join blocked actor={} target={} owner={} beloved={} reason={}",
                    permission.actor_id,
                    permission.target_id,
                    permission.devoted_owner_id,
                    permission.beloved_id,
                    permission.reason,
                )
                _publish_rejection(
                    permission,
                    "wickedwhims_join_guard",
                    pre_sex_instance,
                )
                return False
        except Exception:
            log_exception("WW devotion join guard failed open")
        return original(
            pre_sex_instance,
            join_sims_list,
            *args,
            **kwargs
        )

    _guarded_join._fgeh_devotion_guard = True
    setattr(
        module,
        "join_sex_interaction_from_pre_sex_instance",
        _guarded_join,
    )
    return _replace_imported_aliases(
        "join_sex_interaction_from_pre_sex_instance",
        original,
        _guarded_join,
    )


def install_wickedwhims_devotion_adapter():
    """Install optional v185k-compatible guards; safe when WW is absent."""
    global _INSTALLED
    if _INSTALLED:
        return True
    try:
        pair_aliases = _install_pair_guard()
        start_aliases = _install_start_guard()
        join_aliases = _install_join_guard()
        _INSTALLED = True
        log(
            "WW devotion adapter installed pair_aliases={} start_aliases={} join_aliases={}",
            pair_aliases,
            start_aliases,
            join_aliases,
        )
        return True
    except ImportError:
        log("WW devotion adapter waiting: WickedWhims is not available")
        return False
    except Exception:
        log_exception("WW devotion adapter installation failed")
        return False


def is_wickedwhims_devotion_adapter_installed():
    return _INSTALLED

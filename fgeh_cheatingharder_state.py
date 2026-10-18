"""Directed-state adapter.

The romantic-memory store is the only in-session authority.  EA
UnidirectionalRelationshipTracks are a persistence/compatibility mirror and an
old-save bootstrap source, never a second decision source.
"""

import services
import sims4.resources

from sims4.resources import Types

import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_domain import DirectedState, StateChange
from fgeh_cheatingharder_memory_models import (
    DirectedStateDelta,
    StateChangeMode,
)
from fgeh_cheatingharder_relationship import get_sim_info


_TRACK_CACHE = {}


def reset_session_fallback():
    """Compatibility hook retained for callers from the previous architecture."""
    log("directed state compatibility reset requested")


def _clamp(value):
    return max(0.0, min(100.0, float(value)))


def _get_track_tuning(dimension):
    if dimension in _TRACK_CACHE:
        return _TRACK_CACHE[dimension]
    instance_id = settings.STATE_TRACK_INSTANCE_IDS.get(dimension)
    tuning = None
    if instance_id is not None:
        try:
            key = sims4.resources.get_resource_key(instance_id, Types.STATISTIC)
            tuning = services.get_instance_manager(Types.STATISTIC).get(key)
        except Exception:
            log_exception("directed state track lookup failed dimension={}".format(dimension))
    _TRACK_CACHE[dimension] = tuning
    log(
        "directed state track lookup dimension={} instance={} found={}",
        dimension,
        instance_id,
        tuning is not None,
    )
    return tuning


def _read_ea_dimension(observer, partner, dimension):
    tuning = _get_track_tuning(dimension)
    if tuning is not None:
        try:
            track = observer.relationship_tracker.get_relationship_track(
                partner.sim_id,
                track=tuning,
                add=False,
            )
            if track is not None:
                return (float(track.get_value()), True)
        except Exception:
            log_exception(
                "directed state read failed observer={} partner={} dimension={}".format(
                    observer.sim_id,
                    partner.sim_id,
                    dimension,
                )
            )
    return (0.0, False)


def _memory_store():
    from fgeh_cheatingharder_memory_runtime import get_memory_service

    return get_memory_service().store


def _ensure_memory_state(observer, partner):
    store = _memory_store()
    record = store.get_directed_state(observer.sim_id, partner.sim_id)
    if record is not None:
        return record
    values = {}
    initialized = {}
    for dimension in DirectedState.DIMENSIONS:
        value, is_persisted = _read_ea_dimension(observer, partner, dimension)
        values[dimension] = value
        initialized[dimension] = is_persisted
    record = store.seed_directed_state(
        observer.sim_id,
        partner.sim_id,
        values,
        initialized=initialized,
    )
    log(
        "directed state bootstrapped observer={} partner={} values={} initialized={}",
        observer.sim_id,
        partner.sim_id,
        record.values,
        record.initialized,
    )
    return record


def get_directed_state(observer_sim_or_info, partner_sim_or_info):
    observer = get_sim_info(observer_sim_or_info)
    partner = get_sim_info(partner_sim_or_info)
    if observer is None or partner is None:
        return None
    record = _ensure_memory_state(observer, partner)
    return DirectedState(
        observer.sim_id,
        partner.sim_id,
        record.values,
        record.initialized,
    )


def has_initialized_directed_state(observer_sim_or_info, partner_sim_or_info):
    """Return whether this direction is already owned by the five-dimension model.

    Unlike ``get_directed_state``, this query never bootstraps a new record.
    It is therefore safe to use from interaction visibility and takeover
    guards: merely opening a pie menu must not enroll an unrelated pair.
    """
    observer = get_sim_info(observer_sim_or_info)
    partner = get_sim_info(partner_sim_or_info)
    if observer is None or partner is None:
        return False
    try:
        record = _memory_store().get_directed_state(
            observer.sim_id,
            partner.sim_id,
        )
        return bool(
            record is not None
            and any(bool(value) for value in record.initialized.values())
        )
    except Exception:
        log_exception(
            "initialized directed state test failed observer={} partner={}".format(
                getattr(observer, "sim_id", None),
                getattr(partner, "sim_id", None),
            )
        )
        return False


def has_initialized_relationship_pair(first_sim_or_info, second_sim_or_info):
    """Return whether either asymmetric direction has explicit five-D data."""
    return (
        has_initialized_directed_state(first_sim_or_info, second_sim_or_info)
        or has_initialized_directed_state(second_sim_or_info, first_sim_or_info)
    )


def set_directed_dimension(
    observer_sim_or_info,
    partner_sim_or_info,
    dimension,
    value,
    reason="player_picker",
):
    """Set one directed value through the authoritative memory boundary.

    Registered state constraints run immediately afterward.  For example, a
    permanent-devotion edge may reassert its attachment/commitment floors.
    """
    observer = get_sim_info(observer_sim_or_info)
    partner = get_sim_info(partner_sim_or_info)
    if observer is None or partner is None or observer.sim_id == partner.sim_id:
        return None
    if dimension not in DirectedState.DIMENSIONS:
        raise ValueError("Unknown directed dimension: {}".format(dimension))
    value = _clamp(value)
    _ensure_memory_state(observer, partner)
    store = _memory_store()
    delta = DirectedStateDelta(
        observer.sim_id,
        partner.sim_id,
        dimension,
        value,
        reason,
        mode=StateChangeMode.SET,
    )
    _, old_value, new_value, changed = store.apply_state_delta(delta)
    log(
        "directed state player set observer={} partner={} dimension={} old={:.1f} requested={:.1f} changed={}",
        observer.sim_id,
        partner.sim_id,
        dimension,
        old_value,
        value,
        changed,
    )

    try:
        from fgeh_cheatingharder_domain import RelationshipEvent
        from fgeh_cheatingharder_registry import STATE_CONSTRAINTS

        constraint_event = RelationshipEvent(
            "player_state_edited",
            "player-state-edit:{}:{}:{}".format(
                observer.sim_id,
                partner.sim_id,
                dimension,
            ),
            reason,
            observer_id=observer.sim_id,
            partner_id=partner.sim_id,
            payload={
                "dimension": dimension,
                "requested_value": value,
            },
        )
        for constraint_delta in STATE_CONSTRAINTS.invoke(
            constraint_event,
            observer.sim_id,
            partner.sim_id,
            store,
        ):
            if isinstance(constraint_delta, DirectedStateDelta):
                store.apply_state_delta(constraint_delta)
    except Exception:
        log_exception(
            "directed state player constraints failed observer={} partner={} dimension={}".format(
                observer.sim_id,
                partner.sim_id,
                dimension,
            )
        )

    final_state = get_directed_state(observer, partner)
    log(
        "directed state player result observer={} partner={} dimension={} requested={:.1f} actual={:.1f}",
        observer.sim_id,
        partner.sim_id,
        dimension,
        value,
        final_state.get(dimension),
    )
    return final_state


def apply_changes(event, observer_sim_or_info, partner_sim_or_info, changes):
    """The sole write entry for directed relationship state."""
    observer = get_sim_info(observer_sim_or_info)
    partner = get_sim_info(partner_sim_or_info)
    if observer is None or partner is None:
        return get_directed_state(observer, partner)
    _ensure_memory_state(observer, partner)
    store = _memory_store()
    for change in tuple(changes or ()):
        if not isinstance(change, StateChange):
            continue
        if change.dimension not in DirectedState.DIMENSIONS:
            log("directed state change skipped unknown_dimension={}", change.dimension)
            continue
        mode = (
            StateChangeMode.SET_IF_MISSING
            if change.mode == StateChange.SET_IF_MISSING
            else StateChangeMode.ADD
        )
        delta = DirectedStateDelta(
            observer.sim_id,
            partner.sim_id,
            change.dimension,
            change.value,
            change.reason,
            mode=mode,
            event_id=getattr(event, "event_id", None),
        )
        _, old_value, new_value, changed = store.apply_state_delta(delta)
        log(
            "state mutation event={} source={} observer={} partner={} dimension={} old={:.1f} new={:.1f} mode={} reason={} changed={}",
            getattr(event, "event_type", "unknown"),
            getattr(event, "source", "unknown"),
            observer.sim_id,
            partner.sim_id,
            change.dimension,
            old_value,
            new_value,
            change.mode,
            change.reason,
            changed,
        )
    try:
        from fgeh_cheatingharder_registry import STATE_CONSTRAINTS

        constraint_deltas = STATE_CONSTRAINTS.invoke(
            event,
            observer.sim_id,
            partner.sim_id,
            store,
        )
        for delta in constraint_deltas:
            if not isinstance(delta, DirectedStateDelta):
                continue
            _, old_value, new_value, changed = store.apply_state_delta(delta)
            log(
                "state constraint event={} observer={} partner={} dimension={} old={:.1f} new={:.1f} reason={} changed={}",
                getattr(event, "event_type", "unknown"),
                observer.sim_id,
                partner.sim_id,
                delta.dimension,
                old_value,
                new_value,
                delta.reason,
                changed,
            )
    except Exception:
        log_exception(
            "directed state constraints failed observer={} partner={}".format(
                observer.sim_id,
                partner.sim_id,
            )
        )
    return get_directed_state(observer, partner)


def mirror_memory_dimension_to_ea(
    observer_id,
    partner_id,
    dimension,
    value,
    reason="memory_state_change",
):
    """Mirror one authoritative memory value into an EA relationship track."""
    tuning = _get_track_tuning(dimension)
    if tuning is None:
        log(
            "directed state EA mirror unavailable observer={} partner={} dimension={} reason={}",
            observer_id,
            partner_id,
            dimension,
            reason,
        )
        return False
    try:
        observer = services.sim_info_manager().get(int(observer_id))
        partner = services.sim_info_manager().get(int(partner_id))
        if observer is None or partner is None:
            return False
        observer.relationship_tracker.set_relationship_score(
            partner.sim_id,
            _clamp(value),
            track=tuning,
        )
        log(
            "directed state mirrored observer={} partner={} dimension={} value={:.1f} reason={}",
            observer_id,
            partner_id,
            dimension,
            value,
            reason,
        )
        return True
    except Exception:
        log_exception(
            "directed state EA mirror failed observer={} partner={} dimension={}".format(
                observer_id,
                partner_id,
                dimension,
            )
        )
        return False


def tuning_status():
    return {
        dimension: _get_track_tuning(dimension) is not None
        for dimension in DirectedState.DIMENSIONS
    }

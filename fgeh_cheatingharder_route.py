"""First-route coordinator for the possessive partner gameplay profile."""

import services

import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_relationship import get_sim_info, has_claim, is_enabled


CHECK_IN_SCHEDULED = "check_in_scheduled"
CHECK_IN_ARRIVED = "check_in_arrived"
CAUGHT = "caught"
COMPLETED = "completed"
FAILED = "failed"
RECONCILIATION = "reconciliation"

_CHECK_IN_RECORDS = {}
_RECONCILIATION_TARGETS = {}


def reset_route_runtime():
    _CHECK_IN_RECORDS.clear()
    _RECONCILIATION_TARGETS.clear()
    log("check-in route runtime reset")


def _sim_id(sim_info):
    return getattr(sim_info, "sim_id", None)


def _live_sim(sim_info):
    try:
        return sim_info.get_sim_instance()
    except Exception:
        return None


def _zone_id(sim_info):
    instance = _live_sim(sim_info)
    return getattr(instance, "zone_id", None)


def _active_zone_id():
    try:
        return getattr(services.current_zone(), "id", None)
    except Exception:
        return None


def _room_and_level(sim_info):
    instance = _live_sim(sim_info)
    if instance is None:
        return (None, None)
    position = getattr(instance, "position", None)
    level = getattr(instance, "level", None)
    zone_id = getattr(instance, "zone_id", None)
    if position is None or level is None or zone_id is None:
        return (None, level)
    try:
        from build_buy import get_room_id

        return (get_room_id(zone_id, position, level), level)
    except Exception:
        log_exception("witness room lookup failed")
        return (None, level)


def _horizontal_distance_squared(first_sim_info, second_sim_info):
    first = _live_sim(first_sim_info)
    second = _live_sim(second_sim_info)
    first_position = getattr(first, "position", None)
    second_position = getattr(second, "position", None)
    if first_position is None or second_position is None:
        return None
    try:
        return (first_position - second_position).magnitude_2d_squared()
    except Exception:
        return None


def _is_local_witness(observer, partner, rival):
    room_levels = [_room_and_level(sim_info) for sim_info in (observer, partner, rival)]
    room_ids = [room_level[0] for room_level in room_levels]
    levels = [room_level[1] for room_level in room_levels]
    if None in room_ids or None in levels:
        return False, "room_or_level_unavailable", None
    if len(set(room_ids)) != 1 or len(set(levels)) != 1:
        return False, "different_room_or_level", None

    radius = max(0.1, float(settings.CHEATING_WITNESS_RADIUS))
    radius_squared = radius * radius
    distances = (
        _horizontal_distance_squared(observer, partner),
        _horizontal_distance_squared(observer, rival),
    )
    if any(distance is None for distance in distances):
        return False, "position_unavailable", distances
    # The visitor must be close to the whole interaction, not merely near one
    # participant.  The game's own caught/secret events remain authoritative
    # whenever they fire.
    if max(distances) > radius_squared:
        return False, "witness_too_far", distances
    return True, "local_witness", distances


def _same_active_zone(*sim_infos):
    active_zone_id = _active_zone_id()
    if active_zone_id is None or not sim_infos:
        return False
    return all(_zone_id(sim_info) == active_zone_id for sim_info in sim_infos)


def evaluate_local_witness(
    observer_sim_or_info,
    partner_sim_or_info,
    rival_sim_or_info,
):
    """Public snapshot API; callers must not duplicate route geometry rules."""
    observer = get_sim_info(observer_sim_or_info)
    partner = get_sim_info(partner_sim_or_info)
    rival = get_sim_info(rival_sim_or_info)
    if observer is None or partner is None or rival is None:
        return False, "sim_info_unavailable", None
    if not _same_active_zone(observer, partner, rival):
        return False, "not_all_on_active_zone", None
    return _is_local_witness(observer, partner, rival)


def register_check_in(visitor_sim_or_info, partner_sim_or_info, trigger_reason="manual_force_command"):
    visitor = get_sim_info(visitor_sim_or_info)
    partner = get_sim_info(partner_sim_or_info)
    if visitor is None or partner is None:
        return False
    existing = _CHECK_IN_RECORDS.get((_sim_id(visitor), _sim_id(partner)))
    if existing is not None and existing.get("state") in (CHECK_IN_SCHEDULED, CHECK_IN_ARRIVED):
        log(
            "check-in registration skipped: route already active visitor={} partner={} state={}",
            _sim_id(visitor),
            _sim_id(partner),
            existing.get("state"),
        )
        return False
    active_visitors = {
        record.get("visitor_id")
        for record in _CHECK_IN_RECORDS.values()
        if record.get("state") in (CHECK_IN_SCHEDULED, CHECK_IN_ARRIVED)
    }
    if _sim_id(visitor) not in active_visitors and len(active_visitors) >= settings.MAX_CHECK_IN_VISITORS:
        log(
            "check-in skipped: visitor limit reached visitor={} limit={}",
            _sim_id(visitor),
            settings.MAX_CHECK_IN_VISITORS,
        )
        return False
    _CHECK_IN_RECORDS[(_sim_id(visitor), _sim_id(partner))] = {
        "visitor_id": _sim_id(visitor),
        "partner_id": _sim_id(partner),
        "state": CHECK_IN_SCHEDULED,
        "trigger_reason": trigger_reason,
    }
    log(
        "check-in registered source={} visitor={} partner={}",
        trigger_reason,
        _sim_id(visitor),
        _sim_id(partner),
    )
    return True


def mark_check_in_arrived(visitor_sim_or_info, partner_sim_or_info=None):
    visitor = get_sim_info(visitor_sim_or_info)
    partner = get_sim_info(partner_sim_or_info)
    record = None
    if visitor is not None and partner is not None:
        record = _CHECK_IN_RECORDS.get((_sim_id(visitor), _sim_id(partner)))
    elif visitor is not None:
        for candidate in _CHECK_IN_RECORDS.values():
            if candidate.get("visitor_id") == _sim_id(visitor):
                record = candidate
                break
    if record is None:
        return False
    record["state"] = CHECK_IN_ARRIVED
    log("check-in visitor arrived visitor={} partner={}", record["visitor_id"], record["partner_id"])
    try:
        from fgeh_cheatingharder_domain import EventType
        from fgeh_cheatingharder_event_center import publish
        from fgeh_cheatingharder_scheduler import schedule_visit_completion

        publish(
            EventType.VISIT_ARRIVED,
            source="unexpected_visit_situation",
            observer_id=record["visitor_id"],
            partner_id=record["partner_id"],
        )
        schedule_visit_completion(visitor, _find_sim_info(record["partner_id"]))
    except Exception:
        log_exception("check-in arrival feedback failed")
    return True


def is_check_in_active(visitor_sim_or_info, partner_sim_or_info):
    visitor = get_sim_info(visitor_sim_or_info)
    partner = get_sim_info(partner_sim_or_info)
    if visitor is None or partner is None:
        return False
    record = _CHECK_IN_RECORDS.get((_sim_id(visitor), _sim_id(partner)))
    return (
        record is not None
        and record.get("state") in (CHECK_IN_SCHEDULED, CHECK_IN_ARRIVED)
    )


def complete_check_in_no_finding(visitor_sim_or_info, partner_sim_or_info):
    visitor = get_sim_info(visitor_sim_or_info)
    partner = get_sim_info(partner_sim_or_info)
    if visitor is None or partner is None:
        return False
    record = _CHECK_IN_RECORDS.get((_sim_id(visitor), _sim_id(partner)))
    if record is None or record.get("state") != CHECK_IN_ARRIVED:
        return False
    record["state"] = COMPLETED
    record["outcome"] = "no_finding"
    try:
        from fgeh_cheatingharder_domain import EventType
        from fgeh_cheatingharder_event_center import publish
        from fgeh_cheatingharder_relationship import start_check_in_cooldown
        from fgeh_cheatingharder_scheduler import schedule_relationship_reevaluation

        start_check_in_cooldown(visitor, partner)
        publish(
            EventType.VISIT_FINISHED,
            source="visit_timeout",
            observer_id=visitor.sim_id,
            partner_id=partner.sim_id,
            payload={"outcome": "no_finding"},
        )
        schedule_relationship_reevaluation(
            visitor,
            partner,
            reason="visit_cooldown_complete",
            minutes=settings.CHECK_IN_COOLDOWN_SIM_MINUTES,
        )
    except Exception:
        log_exception("check-in completion feedback failed")
    log(
        "check-in completed without finding visitor={} partner={}",
        visitor.sim_id,
        partner.sim_id,
    )
    return True


def mark_check_in_failed(visitor_sim_or_info, partner_sim_or_info, reason):
    visitor = get_sim_info(visitor_sim_or_info)
    partner = get_sim_info(partner_sim_or_info)
    if visitor is None or partner is None:
        return False
    record = _CHECK_IN_RECORDS.get((_sim_id(visitor), _sim_id(partner)))
    if record is not None:
        record["state"] = FAILED
        record["outcome"] = str(reason)
    try:
        from fgeh_cheatingharder_scheduler import schedule_relationship_reevaluation

        schedule_relationship_reevaluation(
            visitor,
            partner,
            reason="visit_failed:{}".format(reason),
            minutes=settings.RELATIONSHIP_RETRY_SIM_MINUTES,
        )
    except Exception:
        log_exception("failed check-in retry scheduling failed")
    return True


def get_check_in_partners_for_visitor(visitor_sim_or_info):
    """Resolve active check-in targets for a visitor's live Sim lifecycle."""
    visitor = get_sim_info(visitor_sim_or_info)
    if visitor is None:
        return ()
    visitor_id = _sim_id(visitor)
    partner_infos = []
    for record in tuple(_CHECK_IN_RECORDS.values()):
        if record.get("visitor_id") != visitor_id:
            continue
        if record.get("state") not in (CHECK_IN_SCHEDULED, CHECK_IN_ARRIVED):
            continue
        partner = _find_sim_info(record.get("partner_id"))
        if partner is not None:
            partner_infos.append(partner)
    return tuple(partner_infos)


def on_claim_established(observer_sim_or_info, target_sim_or_info):
    """Compatibility entry: publish a claim event into the unified center."""
    observer = get_sim_info(observer_sim_or_info)
    target = get_sim_info(target_sim_or_info)
    if observer is None or target is None:
        return False
    try:
        from fgeh_cheatingharder_domain import EventType
        from fgeh_cheatingharder_event_center import publish

        publish(
            EventType.CLAIM_ESTABLISHED,
            source="route_compatibility",
            event_id="claim:{}:{}".format(observer.sim_id, target.sim_id),
            observer_id=observer.sim_id,
            partner_id=target.sim_id,
        )
        return True
    except Exception:
        log_exception("claim route scheduling failed")
        return False


def ensure_claim_route(observer_sim_or_info, target_sim_or_info, trigger_reason="existing_claim"):
    """Compatibility entry: request a fresh relationship reevaluation."""
    observer = get_sim_info(observer_sim_or_info)
    target = get_sim_info(target_sim_or_info)
    if observer is None or target is None:
        return False
    try:
        from fgeh_cheatingharder_domain import EventType
        from fgeh_cheatingharder_event_center import publish

        publish(
            EventType.RELATIONSHIP_REEVALUATION,
            source=trigger_reason,
            observer_id=observer.sim_id,
            partner_id=target.sim_id,
        )
        return True
    except Exception:
        log_exception("claim route ensure failed")
        return False


def ensure_incoming_claim_routes_for_interaction(actor_sim_or_info, target_sim_or_info):
    """Deprecated: absent observers must not learn romance omnisciently."""
    log("incoming claim scan suppressed: knowledge must come from EA discovery or local witness")
    return False


def on_romantic_interaction(
    actor_sim_or_info,
    target_sim_or_info,
    cause_id=None,
):
    """Check whether an active check-in visitor witnesses this interaction."""
    actor = get_sim_info(actor_sim_or_info)
    target = get_sim_info(target_sim_or_info)
    if actor is None or target is None:
        return False

    caught_any = False
    for record in tuple(_CHECK_IN_RECORDS.values()):
        if record.get("state") != CHECK_IN_ARRIVED:
            continue
        visitor_id = record.get("visitor_id")
        partner_id = record.get("partner_id")
        log(
            "check-in witness scan visitor={} partner={} actor={} target={} state={}",
            visitor_id,
            partner_id,
            _sim_id(actor),
            _sim_id(target),
            record.get("state"),
        )
        if partner_id not in (_sim_id(actor), _sim_id(target)):
            log(
                "check-in witness skipped: partner not in interaction visitor={} partner={}",
                visitor_id,
                partner_id,
            )
            continue

        visitor = _find_sim_info(visitor_id)
        partner = actor if _sim_id(actor) == partner_id else target
        rival = target if partner is actor else actor
        if visitor is None:
            continue
        if _sim_id(partner) == visitor_id or _sim_id(rival) == visitor_id:
            log("check-in witness skipped: visitor is interaction participant visitor={}", visitor_id)
            continue
        if not _same_active_zone(visitor, partner, rival):
            log(
                "check-in witness skipped: not same active zone visitor={} partner={} rival={}",
                _zone_id(visitor),
                _zone_id(partner),
                _zone_id(rival),
            )
            continue
        local_witness, reason, distances = _is_local_witness(visitor, partner, rival)
        if not local_witness:
            log(
                "check-in witness skipped: {} visitor={} partner={} rival={} distances={} radius={}",
                reason,
                visitor_id,
                partner_id,
                _sim_id(rival),
                distances,
                settings.CHEATING_WITNESS_RADIUS,
            )
            continue
        log(
            "check-in local witness confirmed visitor={} partner={} rival={} distances={} radius={}",
            visitor_id,
            partner_id,
            _sim_id(rival),
            distances,
            settings.CHEATING_WITNESS_RADIUS,
        )
        caught_any = (
            resolve_caught_cheating(
                visitor,
                partner,
                rival,
                cause_id=cause_id,
            )
            or caught_any
        )
    return caught_any


def _find_sim_info(sim_id):
    if sim_id is None:
        return None
    try:
        return services.sim_info_manager().get(sim_id)
    except Exception:
        log_exception("route Sim lookup failed sim_id={}".format(sim_id))
        return None


def resolve_caught_cheating(observer, partner, rival, cause_id=None):
    observer_id = _sim_id(observer)
    for record in _CHECK_IN_RECORDS.values():
        if record.get("visitor_id") == observer_id and record.get("partner_id") == _sim_id(partner):
            record["state"] = CAUGHT
            record["outcome"] = "caught_cheating"
            break
    log(
        "caught cheating observer={} partner={} rival={}",
        observer_id,
        _sim_id(partner),
        _sim_id(rival),
    )

    try:
        from fgeh_cheatingharder_betrayal_reactions import BetrayalProfileKey
        from fgeh_cheatingharder_domain import EventType
        from fgeh_cheatingharder_event_center import publish
        from fgeh_cheatingharder_relationship import start_check_in_cooldown
        from fgeh_cheatingharder_scheduler import schedule_relationship_reevaluation

        profile_key = (
            BetrayalProfileKey.RIVAL_BLAMING
            if is_enabled(observer)
            else BetrayalProfileKey.BALANCED
        )
        start_check_in_cooldown(observer, partner)
        publish(
            EventType.CAUGHT_CHEATING,
            source="local_check_in_witness",
            observer_id=observer.sim_id,
            partner_id=partner.sim_id,
            rival_id=rival.sim_id,
            payload={
                "cause_id": cause_id,
                "witness_ids": (observer.sim_id,),
                "severity": 100,
                "reaction_profile_key": profile_key,
            },
        )
        schedule_relationship_reevaluation(
            observer,
            partner,
            reason="caught_cooldown_complete",
            minutes=settings.CHECK_IN_COOLDOWN_SIM_MINUTES,
        )
    except Exception:
        log_exception("caught behavior feedback failed")

    # V1 only scores reactions.  It does not yet force confrontation,
    # forgiveness, or breakup, and keeps the existing directed edge available
    # for a later behavior executor.
    _RECONCILIATION_TARGETS[observer_id] = _sim_id(partner)
    return True


def handle_breakup_interaction(actor_sim_or_info, target_sim_or_info):
    """Keep the former target available for the V1 reconciliation route."""
    actor = get_sim_info(actor_sim_or_info)
    target = get_sim_info(target_sim_or_info)
    for observer, former_partner in ((actor, target), (target, actor)):
        if observer is None or former_partner is None:
            continue
        if not is_enabled(observer) or not has_claim(observer, former_partner):
            continue
        _RECONCILIATION_TARGETS[_sim_id(observer)] = _sim_id(former_partner)
        log(
            "reconciliation target retained observer={} partner={}",
            _sim_id(observer),
            _sim_id(former_partner),
        )
        return True
    return False


def get_reconciliation_target(observer_sim_or_info):
    observer = get_sim_info(observer_sim_or_info)
    target_id = _RECONCILIATION_TARGETS.get(_sim_id(observer)) if observer else None
    return _find_sim_info(target_id)


def get_check_in_status():
    """Return a compact debug snapshot without exposing the registry itself."""
    return tuple(
        {
            "visitor_id": record.get("visitor_id"),
            "partner_id": record.get("partner_id"),
            "state": record.get("state"),
            "trigger_reason": record.get("trigger_reason"),
            "outcome": record.get("outcome"),
        }
        for record in _CHECK_IN_RECORDS.values()
    )

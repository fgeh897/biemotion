import alarms
import date_and_time
import services

from sims.sim import Sim

import fgeh_cheatingharder_injector as injector
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_relationship import get_sim_info
import fgeh_cheatingharder_settings as settings


_ARRIVAL_LIFECYCLE_INSTALLED = False
_ARRIVAL_BEHAVIOR_ALARMS = {}
_ARRIVAL_BEHAVIOR_TOKENS = {}
_DELAYED_CHECK_IN_ALARMS = {}
_RELATIONSHIP_REEVALUATION_ALARMS = {}
_VISIT_COMPLETION_ALARMS = {}


def reset_zone_runtime():
    """Discard zone-bound handles; persisted claims/state are restored later."""
    alarm_maps = (
        _ARRIVAL_BEHAVIOR_ALARMS,
        _DELAYED_CHECK_IN_ALARMS,
        _RELATIONSHIP_REEVALUATION_ALARMS,
        _VISIT_COMPLETION_ALARMS,
    )
    for alarm_map in alarm_maps:
        for handle in tuple(alarm_map.values()):
            try:
                alarms.cancel_alarm(handle)
            except Exception:
                pass
        alarm_map.clear()
    try:
        from fgeh_cheatingharder_longing_runtime import reset_longing_runtime

        reset_longing_runtime()
    except Exception:
        log_exception("devotion longing zone reset failed")
    try:
        from fgeh_cheatingharder_autonomous_behavior_runtime import (
            reset_autonomous_behavior_runtime,
        )

        reset_autonomous_behavior_runtime()
    except Exception:
        log_exception("autonomous behavior zone reset failed")
    _ARRIVAL_BEHAVIOR_TOKENS.clear()
    try:
        from fgeh_cheatingharder_route import reset_route_runtime

        reset_route_runtime()
    except Exception:
        log_exception("route runtime reset failed")
    log("zone-bound relationship runtime reset")


def schedule_unexpected_check_in(
    visitor_sim_or_info,
    partner_sim_or_info=None,
    trigger_reason="manual_force_command",
):
    """Use the vanilla unexpected-visit system for an existing Sim.

    The vanilla situation is created on the active zone, so a partner must be
    instantiated on that zone before we ask the game to send the visitor.
    """
    visitor_info = get_sim_info(visitor_sim_or_info)
    partner_info = get_sim_info(partner_sim_or_info)
    visitor = getattr(visitor_info, "get_sim_instance", lambda: None)()
    if visitor is None:
        visitor = getattr(visitor_sim_or_info, "sim_instance", None)
    if visitor is None:
        # The vanilla manager accepts SimInfo and will instantiate the visitor
        # as part of the visit situation.
        visitor = visitor_info
    if partner_info is not None:
        partner = getattr(partner_info, "get_sim_instance", lambda: None)()
        active_zone = getattr(services.current_zone(), "id", None)
        if partner is None or getattr(partner, "zone_id", None) != active_zone:
            log(
                "unexpected visit skipped: partner is not on active zone partner={} active_zone={}",
                getattr(partner_info, "sim_id", None),
                active_zone,
            )
            return None
    try:
        situation_manager = services.get_zone_situation_manager()
        if situation_manager is None:
            log("unexpected visit skipped: no zone situation manager")
            return None
        default_visit = getattr(situation_manager, "DEFAULT_VISIT_SITUATION", None)
        if default_visit is None:
            log("unexpected visit skipped: no DEFAULT_VISIT_SITUATION")
            return None
        situation_id = situation_manager.create_visit_situation(visitor)
        if situation_id is None:
            log(
                "check-in generation failed reason=situation_creation visitor={} partner={}",
                getattr(visitor_info, "sim_id", None),
                getattr(partner_info, "sim_id", None),
            )
            return None
        if partner_info is not None and settings.is_check_in_warning_enabled():
            try:
                from fgeh_cheatingharder_notification import show_check_in_warning

                show_check_in_warning(visitor_info, partner_info)
            except Exception:
                log_exception("check-in warning notification failed")
        if partner_info is not None:
            try:
                from fgeh_cheatingharder_route import mark_check_in_arrived

                mark_check_in_arrived(visitor_info, partner_info)
            except Exception:
                log_exception("check-in arrival state update failed")
            schedule_arrival_behavior(visitor_info, partner_info)
        log(
            "check-in generation succeeded reason={} visitor={} partner={} situation_id={} default_visit={}",
            trigger_reason,
            getattr(visitor_info, "sim_id", None),
            getattr(partner_info, "sim_id", None),
            situation_id,
            default_visit,
        )
        return True
    except Exception:
        log_exception("unexpected visit scheduling failed")
        return None


def _social_affordance_score(affordance):
    name = getattr(affordance, "__name__", "").lower()
    if any(word in name for word in ("fight", "argue", "argument", "insult", "mock", "yell", "shout")):
        return -1000
    score = 0
    for word in ("greet", "chat", "talk", "friendly", "ask", "day"):
        if word in name:
            score += 10
    return score


def _push_first_safe_social(visitor, partner):
    try:
        from interactions.context import InteractionContext
        from interactions.context import QueueInsertStrategy
        from interactions.priority import Priority

        context = InteractionContext(
            visitor,
            InteractionContext.SOURCE_SCRIPT,
            Priority.High,
            insert_strategy=QueueInsertStrategy.FIRST,
            must_run_next=True,
        )
        affordances = []
        seen = set()
        try:
            # This is the same source used to build the target Sim's social
            # menu, so the selected affordance has already passed its target
            # and relationship filtering before we try to enqueue it.
            for aop in tuple(partner.potential_interactions(context)):
                affordance = getattr(aop, "affordance", None)
                if affordance is None or not getattr(affordance, "is_social", False):
                    continue
                if affordance in seen:
                    continue
                seen.add(affordance)
                affordances.append(affordance)
        except Exception:
            log_exception("check-in target social menu lookup failed")

        if not affordances:
            affordances = [
                affordance
                for affordance in tuple(visitor.super_affordances(context))
                if getattr(affordance, "is_social", False)
            ]
        affordances.sort(key=_social_affordance_score, reverse=True)
        for affordance in affordances:
            if _social_affordance_score(affordance) < 0:
                continue
            try:
                result = visitor.push_super_affordance(affordance, partner, context)
                interaction = getattr(result, "interaction", None)
                if result and not getattr(interaction, "is_finishing", False):
                    log(
                        "check-in arrival social pushed visitor={} partner={} affordance={}",
                        getattr(visitor, "id", None),
                        getattr(partner, "id", None),
                        getattr(affordance, "__name__", affordance),
                    )
                    return True
            except Exception:
                continue
        log(
            "check-in arrival social unavailable visitor={} partner={} candidates={}",
            getattr(visitor, "id", None),
            getattr(partner, "id", None),
            len(affordances),
        )
    except Exception:
        log_exception("check-in arrival social lookup failed")
    return False


def schedule_arrival_behavior(visitor_sim_or_info, partner_sim_or_info, retry_count=0, owner_sim=None):
    """After arrival, let the vanilla social affordance route to the partner."""
    visitor_info = get_sim_info(visitor_sim_or_info)
    partner_info = get_sim_info(partner_sim_or_info)
    if visitor_info is None or partner_info is None:
        return None

    visitor_instance = getattr(visitor_info, "get_sim_instance", lambda: None)()
    if visitor_instance is None and getattr(visitor_sim_or_info, "sim_info", None) is visitor_info:
        visitor_instance = visitor_sim_or_info
    alarm_owner = owner_sim or visitor_instance or visitor_info
    behavior_key = (visitor_info.sim_id, partner_info.sim_id)
    behavior_token = _ARRIVAL_BEHAVIOR_TOKENS.get(behavior_key, 0) + 1
    _ARRIVAL_BEHAVIOR_TOKENS[behavior_key] = behavior_token
    log(
        "check-in arrival behavior scheduled visitor={} partner={} retry={} owner={}",
        visitor_info.sim_id,
        partner_info.sim_id,
        retry_count,
        getattr(alarm_owner, "id", getattr(alarm_owner, "sim_id", None)),
    )

    def _arrival_behavior_alarm(_alarm_handle):
        if _ARRIVAL_BEHAVIOR_TOKENS.get(behavior_key) != behavior_token:
            return
        visitor = visitor_info.get_sim_instance() or visitor_instance
        partner = partner_info.get_sim_instance()
        active_zone = getattr(services.current_zone(), "id", None)
        log(
            "check-in arrival behavior callback visitor={} live={} partner={} active_zone={}",
            visitor_info.sim_id,
            getattr(visitor, "id", None),
            partner_info.sim_id,
            active_zone,
        )
        if visitor is not None and partner is not None:
            if getattr(visitor, "zone_id", None) == active_zone and getattr(partner, "zone_id", None) == active_zone:
                if _push_first_safe_social(visitor, partner):
                    _ARRIVAL_BEHAVIOR_ALARMS.pop(behavior_key, None)
                    _ARRIVAL_BEHAVIOR_TOKENS.pop(behavior_key, None)
                    return
        if retry_count >= settings.CHECK_IN_ARRIVAL_MAX_RETRIES:
            _ARRIVAL_BEHAVIOR_ALARMS.pop(behavior_key, None)
            _ARRIVAL_BEHAVIOR_TOKENS.pop(behavior_key, None)
            log(
                "check-in arrival behavior gave up visitor={} partner={} retries={}",
                visitor_info.sim_id,
                partner_info.sim_id,
                retry_count,
            )
            return
        schedule_arrival_behavior(visitor_info, partner_info, retry_count + 1, owner_sim=visitor)

    try:
        handle = alarms.add_alarm(
            alarm_owner,
            date_and_time.create_time_span(minutes=settings.CHECK_IN_ARRIVAL_RETRY_MINUTES),
            _arrival_behavior_alarm,
            cross_zone=True,
        )
        # Sims 4 alarm handles are weakly retained by the alarm service.
        # Keep our own strong reference until the callback succeeds or gives up.
        _ARRIVAL_BEHAVIOR_ALARMS[behavior_key] = handle
        return handle
    except Exception:
        log_exception("check-in arrival behavior alarm failed")
        return None


def on_sim_pre_add(sim):
    """Attach arrival behavior when the visit situation creates the live Sim."""
    try:
        from fgeh_cheatingharder_route import get_check_in_partners_for_visitor

        visitor_info = get_sim_info(sim)
        partners = get_check_in_partners_for_visitor(visitor_info)
        for partner_info in partners:
            log(
                "check-in live visitor detected visitor={} partner={}",
                getattr(visitor_info, "sim_id", None),
                getattr(partner_info, "sim_id", None),
            )
            schedule_arrival_behavior(sim, partner_info, owner_sim=sim)
    except Exception:
        log_exception("check-in live visitor lifecycle failed")


def install_arrival_lifecycle():
    global _ARRIVAL_LIFECYCLE_INSTALLED
    if _ARRIVAL_LIFECYCLE_INSTALLED:
        return True
    try:
        @injector.inject(Sim, "pre_add", safe=True)
        def _observe_sim_pre_add(original, sim, manager, *args, **kwargs):
            result = original(sim, manager, *args, **kwargs)
            on_sim_pre_add(sim)
            return result

        _ARRIVAL_LIFECYCLE_INSTALLED = True
        log("check-in live visitor lifecycle injector installed")
        return True
    except Exception:
        log_exception("check-in live visitor lifecycle injector failed")
        return False


def schedule_delayed_check_in(
    visitor_sim_or_info,
    partner_sim_or_info,
    trigger_reason="claim_established",
):
    visitor_info = get_sim_info(visitor_sim_or_info)
    partner_info = get_sim_info(partner_sim_or_info)
    if visitor_info is None or partner_info is None:
        log("delayed check-in skipped: missing visitor or partner")
        return None
    try:
        from fgeh_cheatingharder_route import register_check_in

        if not register_check_in(visitor_info, partner_info, trigger_reason=trigger_reason):
            log(
                "check-in generation declined reason=registration_failed source={} visitor={} partner={}",
                trigger_reason,
                visitor_info.sim_id,
                partner_info.sim_id,
            )
            return None

        def _on_check_in_alarm(_alarm_handle):
            _DELAYED_CHECK_IN_ALARMS.pop((visitor_info.sim_id, partner_info.sim_id), None)
            result = schedule_unexpected_check_in(
                visitor_info,
                partner_info,
                trigger_reason=trigger_reason,
            )
            if result is None:
                try:
                    from fgeh_cheatingharder_route import mark_check_in_failed

                    mark_check_in_failed(
                        visitor_info,
                        partner_info,
                        "unexpected_visit_creation_failed",
                    )
                except Exception:
                    log_exception("failed visit feedback failed")

        handle = alarms.add_alarm(
            visitor_info,
            date_and_time.create_time_span(
                minutes=settings.CHECK_IN_DELAY_SIM_MINUTES,
            ),
            _on_check_in_alarm,
            cross_zone=True,
        )
        _DELAYED_CHECK_IN_ALARMS[(visitor_info.sim_id, partner_info.sim_id)] = handle
        log(
            "check-in generation armed source={} visitor={} partner={} delay_minutes={}",
            trigger_reason,
            visitor_info.sim_id,
            partner_info.sim_id,
            settings.CHECK_IN_DELAY_SIM_MINUTES,
        )
        return handle
    except Exception:
        log_exception("delayed check-in setup failed")
        return None


def schedule_relationship_reevaluation(
    observer_sim_or_info,
    partner_sim_or_info,
    reason,
    minutes=None,
    payload=None,
):
    observer = get_sim_info(observer_sim_or_info)
    partner = get_sim_info(partner_sim_or_info)
    if observer is None or partner is None:
        return None
    key = (observer.sim_id, partner.sim_id)
    existing = _RELATIONSHIP_REEVALUATION_ALARMS.get(key)
    if existing is not None:
        log(
            "relationship reevaluation already scheduled observer={} partner={} reason={}",
            observer.sim_id,
            partner.sim_id,
            reason,
        )
        return existing
    delay = (
        settings.RELATIONSHIP_REEVALUATION_SIM_MINUTES
        if minutes is None
        else max(0.1, float(minutes))
    )

    def _on_reevaluation_alarm(_alarm_handle):
        _RELATIONSHIP_REEVALUATION_ALARMS.pop(key, None)
        try:
            from fgeh_cheatingharder_domain import EventType
            from fgeh_cheatingharder_event_center import publish

            publish(
                EventType.RELATIONSHIP_REEVALUATION,
                source="relationship_alarm",
                observer_id=observer.sim_id,
                partner_id=partner.sim_id,
                payload=dict(
                    {"scheduled_reason": reason},
                    **dict(payload or {})
                ),
            )
        except Exception:
            log_exception("relationship reevaluation callback failed")

    try:
        handle = alarms.add_alarm(
            observer,
            date_and_time.create_time_span(minutes=delay),
            _on_reevaluation_alarm,
            cross_zone=True,
        )
        _RELATIONSHIP_REEVALUATION_ALARMS[key] = handle
        log(
            "relationship reevaluation scheduled observer={} partner={} reason={} minutes={}",
            observer.sim_id,
            partner.sim_id,
            reason,
            delay,
        )
        return handle
    except Exception:
        log_exception("relationship reevaluation alarm failed")
        return None


def schedule_visit_completion(visitor_sim_or_info, partner_sim_or_info):
    visitor = get_sim_info(visitor_sim_or_info)
    partner = get_sim_info(partner_sim_or_info)
    if visitor is None or partner is None:
        return None
    key = (visitor.sim_id, partner.sim_id)
    existing = _VISIT_COMPLETION_ALARMS.get(key)
    if existing is not None:
        return existing

    def _on_visit_completion(_alarm_handle):
        _VISIT_COMPLETION_ALARMS.pop(key, None)
        try:
            from fgeh_cheatingharder_route import complete_check_in_no_finding

            complete_check_in_no_finding(visitor, partner)
        except Exception:
            log_exception("visit completion callback failed")

    try:
        handle = alarms.add_alarm(
            visitor,
            date_and_time.create_time_span(
                minutes=settings.CHECK_IN_VISIT_DURATION_SIM_MINUTES,
            ),
            _on_visit_completion,
            cross_zone=True,
        )
        _VISIT_COMPLETION_ALARMS[key] = handle
        log(
            "visit completion scheduled visitor={} partner={} minutes={}",
            visitor.sim_id,
            partner.sim_id,
            settings.CHECK_IN_VISIT_DURATION_SIM_MINUTES,
        )
        return handle
    except Exception:
        log_exception("visit completion alarm failed")
        return None

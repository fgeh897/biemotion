"""Unified relationship event pipeline and explainable decision center."""

from collections import deque

import services

from fgeh_cheatingharder_behaviors import (
    apply_score_terms,
    build_break_up_candidate,
    build_longing_wait_candidate,
    build_repair_relationship_candidate,
    build_seek_beloved_candidate,
    build_visit_candidate,
    build_wait_candidate,
    build_crisis_give_space_candidate,
    build_crisis_repeat_breakup_candidate,
    build_crisis_seek_reassurance_candidate,
    select_behavior,
)
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_domain import (
    EventIdWindow,
    EventType,
    IntentType,
    RelationshipEvent,
)
from fgeh_cheatingharder_execution import EXECUTOR_BY_INTENT
from fgeh_cheatingharder_profiles import possessive_devotion_score_modifier
from fgeh_cheatingharder_registry import (
    BEHAVIOR_DEFINITIONS,
    EXECUTORS,
    OPPORTUNITY_PROVIDERS,
    SCORE_MODIFIERS,
    STATE_CONSTRAINTS,
    STATE_RULES,
    register_executor,
)
from fgeh_cheatingharder_rules import core_opportunity_provider, core_state_rules
from fgeh_cheatingharder_devotion import devotion_state_constraint
from fgeh_cheatingharder_state import apply_changes, get_directed_state


_INSTALLED = False
_EVENT_COUNTER = 0
_EVENT_ID_WINDOW = EventIdWindow(256)
_EVENT_QUEUE = deque()
_PROCESSING = False
_EVENT_HISTORY = deque(maxlen=100)
_LAST_DECISIONS = {}
_LAST_EXECUTIONS = {}
_RECENT_CAUGHT_EDGES = {}


def reset_save_runtime(reset_memory=True):
    """Clear idempotency/debug state when the game replaces the SimInfo manager."""
    _EVENT_ID_WINDOW.clear()
    _EVENT_QUEUE.clear()
    _EVENT_HISTORY.clear()
    _LAST_DECISIONS.clear()
    _LAST_EXECUTIONS.clear()
    _RECENT_CAUGHT_EDGES.clear()
    try:
        from fgeh_cheatingharder_autonomous_breakup import (
            reset_autonomous_breakup_runtime,
        )

        reset_autonomous_breakup_runtime()
    except Exception:
        log_exception("autonomous breakup runtime reset failed")
    try:
        from fgeh_cheatingharder_state import reset_session_fallback
        from fgeh_cheatingharder_events import reset_event_adapter_runtime
        from fgeh_cheatingharder_reconciliation_runtime import (
            reset_reconciliation_runtime,
        )
        if reset_memory:
            from fgeh_cheatingharder_memory_runtime import reset_memory_service

            reset_memory_service()
        reset_session_fallback()
        reset_event_adapter_runtime()
        reset_reconciliation_runtime()
    except Exception:
        log_exception("relationship memory reset failed")
    log("relationship event runtime reset for new save")


def install_framework():
    global _INSTALLED
    if _INSTALLED:
        return True
    STATE_RULES.register("core_directed_state_rules", core_state_rules, priority=100)
    STATE_CONSTRAINTS.register(
        "permanent_devotion_floors",
        devotion_state_constraint,
        priority=100,
    )
    OPPORTUNITY_PROVIDERS.register(
        "core_relationship_opportunities",
        core_opportunity_provider,
        priority=100,
    )
    BEHAVIOR_DEFINITIONS.register("wait", build_wait_candidate, priority=100)
    BEHAVIOR_DEFINITIONS.register(
        "repair_relationship",
        build_repair_relationship_candidate,
        priority=98,
    )
    BEHAVIOR_DEFINITIONS.register(
        "break_up",
        build_break_up_candidate,
        priority=96,
    )
    BEHAVIOR_DEFINITIONS.register(
        "visit_unannounced",
        build_visit_candidate,
        priority=90,
    )
    BEHAVIOR_DEFINITIONS.register(
        "seek_beloved",
        build_seek_beloved_candidate,
        priority=85,
    )
    BEHAVIOR_DEFINITIONS.register(
        "longing_wait",
        build_longing_wait_candidate,
        priority=80,
    )
    BEHAVIOR_DEFINITIONS.register(
        "crisis_seek_reassurance",
        build_crisis_seek_reassurance_candidate,
        priority=94,
    )
    BEHAVIOR_DEFINITIONS.register(
        "crisis_give_space",
        build_crisis_give_space_candidate,
        priority=93,
    )
    BEHAVIOR_DEFINITIONS.register(
        "crisis_repeat_breakup",
        build_crisis_repeat_breakup_candidate,
        priority=92,
    )
    SCORE_MODIFIERS.register(
        "possessive_devotion_profile",
        possessive_devotion_score_modifier,
        priority=100,
    )
    for intent_type, executor in EXECUTOR_BY_INTENT.items():
        register_executor(intent_type, executor)
    try:
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        get_memory_service()
    except Exception:
        log_exception("romantic memory framework install failed")
    _INSTALLED = True
    log("directed relationship behavior framework installed")
    return True


def _next_event_id(event_type, source):
    global _EVENT_COUNTER
    _EVENT_COUNTER += 1
    return "{}:{}:{}".format(source, event_type, _EVENT_COUNTER)


def publish(
    event_type,
    source,
    event_id=None,
    actor_id=None,
    target_id=None,
    observer_id=None,
    partner_id=None,
    rival_id=None,
    payload=None,
):
    install_framework()
    event = RelationshipEvent(
        event_type,
        event_id or _next_event_id(event_type, source),
        source,
        actor_id=actor_id,
        target_id=target_id,
        observer_id=observer_id,
        partner_id=partner_id,
        rival_id=rival_id,
        payload=payload,
    )
    _EVENT_QUEUE.append(event)
    _drain_queue()
    return event


def _remember_event(event):
    if not _EVENT_ID_WINDOW.add(event.event_id):
        log("relationship event deduplicated id={} type={}", event.event_id, event.event_type)
        return False
    return True


def _drain_queue():
    global _PROCESSING
    if _PROCESSING:
        return
    _PROCESSING = True
    try:
        while _EVENT_QUEUE:
            event = _EVENT_QUEUE.popleft()
            if not _remember_event(event):
                continue
            try:
                _process_event(event)
            except Exception:
                log_exception("relationship event processing failed event={}".format(event))
    finally:
        _PROCESSING = False


def _find_sim_info(sim_id):
    if sim_id is None:
        return None
    try:
        return services.sim_info_manager().get(sim_id)
    except Exception:
        return None


def _resolve_edges(event):
    from fgeh_cheatingharder_relationship import has_claim

    def has_directed_relationship(observer, partner):
        if has_claim(observer, partner):
            return True
        try:
            from fgeh_cheatingharder_devotion_runtime import (
                get_devotion_bond,
            )

            bond = get_devotion_bond(observer.sim_id)
            if bond is not None and bond.beloved_id == partner.sim_id:
                return True
        except Exception:
            log_exception(
                "devotion edge lookup failed observer={} partner={}".format(
                    observer.sim_id,
                    partner.sim_id,
                )
            )
        try:
            from fgeh_cheatingharder_crisis_runtime import (
                get_active_relationship_crisis,
            )

            return get_active_relationship_crisis(
                observer.sim_id,
                partner.sim_id,
            ) is not None
        except Exception:
            log_exception(
                "relationship crisis edge lookup failed observer={} partner={}".format(
                    observer.sim_id,
                    partner.sim_id,
                )
            )
            return False

    if event.directed_edge is not None:
        observer = _find_sim_info(event.observer_id)
        partner = _find_sim_info(event.partner_id)
        if (
            observer is not None
            and partner is not None
            and has_directed_relationship(observer, partner)
        ):
            return ((observer, partner),)
        log(
            "relationship event has no valid directed claim type={} observer={} partner={}",
            event.event_type,
            event.observer_id,
            event.partner_id,
        )
        return ()
    if event.event_type not in (
        EventType.ROMANCE_COMPLETED,
        EventType.BREAKUP_COMPLETED,
        EventType.DEVOTION_CONTACT_COMPLETED,
        EventType.REPAIR_ACTION_RESOLVED,
    ):
        return ()
    actor_id = event.actor_id
    target_id = event.target_id
    if (
        event.event_type == EventType.BREAKUP_COMPLETED
        and (actor_id is None or target_id is None)
    ):
        relationship_member_ids = tuple(
            event.payload.get("relationship_member_ids", ())
        )
        if len(relationship_member_ids) == 2:
            actor_id, target_id = relationship_member_ids
    actor = _find_sim_info(actor_id)
    target = _find_sim_info(target_id)
    if actor is None or target is None:
        return ()
    edges = []
    if has_directed_relationship(actor, target):
        edges.append((actor, target))
    if has_directed_relationship(target, actor):
        edges.append((target, actor))
    return tuple(edges)


def _decision_context(observer, partner):
    from fgeh_cheatingharder_relationship import has_check_in_cooldown, has_claim
    from fgeh_cheatingharder_route import is_check_in_active

    active_zone_id = getattr(services.current_zone(), "id", None)
    partner_instance = partner.get_sim_instance()
    observer_instance = observer.get_sim_instance()
    known_affair_count = 0
    try:
        import fgeh_cheatingharder_settings as settings

        secret_service = services.sim_secrets_service()
        if secret_service is not None:
            known_affair_count = sum(
                1
                for secret in secret_service.get_sim_known_secrets(
                    observer.sim_id,
                    target_sim_id=partner.sim_id,
                )
                if secret.guid64 == settings.EA_AFFAIR_SECRET_INSTANCE_ID
                and partner.sim_id in secret.complicit_sims
            )
    except Exception:
        known_affair_count = 0
    relationship_history_summary = None
    try:
        from fgeh_cheatingharder_memory_runtime import get_memory_summary

        summary = get_memory_summary(observer.sim_id, partner.sim_id)
        if summary is not None:
            relationship_history_summary = summary.to_data()
    except Exception:
        log_exception(
            "relationship history summary lookup failed observer={} partner={}".format(
                observer.sim_id,
                partner.sim_id,
            )
        )
    context = {
        "observer": observer,
        "partner": partner,
        "has_claim": has_claim(observer, partner),
        "cooldown": has_check_in_cooldown(observer, partner),
        "active_route": is_check_in_active(observer, partner),
        "partner_on_active_zone": (
            partner_instance is not None
            and getattr(partner_instance, "zone_id", None) == active_zone_id
        ),
        "observer_on_active_zone": (
            observer_instance is not None
            and getattr(observer_instance, "zone_id", None) == active_zone_id
        ),
        "active_zone_id": active_zone_id,
        # Read directly from the original persisted knowledge service.  This is
        # a decision fact, not a duplicated intelligence database or mutation.
        "known_affair_count": known_affair_count,
        # Score modifiers may read this precomputed projection.  They must not
        # scan the full event ledger during every utility evaluation.
        "relationship_history_summary": relationship_history_summary,
    }
    try:
        from fgeh_cheatingharder_reconciliation_ea import (
            are_official_partners,
        )

        context["are_official_partners"] = bool(
            are_official_partners(observer, partner)
        )
    except Exception:
        context["are_official_partners"] = False
        log_exception(
            "official partnership lookup failed observer={} partner={}".format(
                observer.sim_id,
                partner.sim_id,
            )
        )
    try:
        from fgeh_cheatingharder_autonomous_breakup import (
            has_autonomous_breakup_cooldown,
        )

        context["autonomous_breakup_cooldown"] = (
            has_autonomous_breakup_cooldown(
                observer.sim_id,
                partner.sim_id,
            )
        )
    except Exception:
        context["autonomous_breakup_cooldown"] = False
        log_exception(
            "autonomous breakup cooldown lookup failed observer={} partner={}".format(
                observer.sim_id,
                partner.sim_id,
            )
        )
    try:
        from fgeh_cheatingharder_longing_runtime import (
            build_longing_decision_context,
        )

        context.update(build_longing_decision_context(observer, partner))
    except Exception:
        log_exception(
            "devotion longing context failed observer={} partner={}".format(
                observer.sim_id,
                partner.sim_id,
            )
        )
    try:
        from fgeh_cheatingharder_crisis_runtime import (
            build_crisis_decision_context,
        )

        context.update(build_crisis_decision_context(observer, partner))
    except Exception:
        log_exception(
            "relationship crisis context failed observer={} partner={}".format(
                observer.sim_id,
                partner.sim_id,
            )
        )
    return context


def _evaluate_opportunity(opportunity, state, observer, partner):
    context = _decision_context(observer, partner)
    candidates = []
    for _, key, definition in BEHAVIOR_DEFINITIONS.entries():
        try:
            candidate = definition(state, opportunity, context)
            extra_terms = SCORE_MODIFIERS.invoke(
                candidate,
                opportunity,
                state,
                context,
            )
            candidates.append(apply_score_terms(candidate, extra_terms))
        except Exception:
            log_exception("behavior candidate failed key={}".format(key))
    intent, record = select_behavior(opportunity, state, candidates)
    if record is None or intent is None:
        log(
            "behavior decision unavailable observer={} partner={} reason={} candidates={}",
            observer.sim_id,
            partner.sim_id,
            opportunity.reason,
            tuple(candidate.as_dict() for candidate in candidates),
        )
        return
    _LAST_DECISIONS[(observer.sim_id, partner.sim_id)] = record
    log(
        "behavior decision observer={} partner={} reason={} state={} candidates={} total={:.3f} roll={:.3f} selected={}",
        observer.sim_id,
        partner.sim_id,
        opportunity.reason,
        record.state,
        tuple(candidate.as_dict() for candidate in record.candidates),
        record.total_score,
        record.roll,
        record.selected_intent,
    )
    executor = EXECUTORS.get(intent.intent_type)
    if executor is None:
        log("behavior executor missing intent={}", intent.intent_type)
        return
    result = executor(intent, observer, partner)
    _LAST_EXECUTIONS[(observer.sim_id, partner.sim_id)] = {
        "intent": intent.intent_type,
        "accepted": result.accepted,
        "status": result.status,
        "details": dict(result.details),
    }
    log(
        "behavior execution observer={} partner={} intent={} accepted={} status={} details={}",
        observer.sim_id,
        partner.sim_id,
        intent.intent_type,
        result.accepted,
        result.status,
        result.details,
    )
    # Longing retries are transient decisions.  A successful seek already
    # publishes DEVOTION_CONTACT_SOUGHT; waiting and failed pushes are not
    # important life events and must not flood the romantic ledger.
    if intent.intent_type not in (
        IntentType.LONGING_WAIT,
        IntentType.SEEK_BELOVED,
    ):
        publish(
            EventType.BEHAVIOR_EXECUTED,
            source="behavior_executor",
            observer_id=observer.sim_id,
            partner_id=partner.sim_id,
            payload={
                "intent": intent.intent_type,
                "accepted": result.accepted,
                "status": result.status,
                "details": dict(result.details),
                "crisis_case_id": result.details.get("crisis_case_id"),
            },
        )
    return result.accepted


def evaluate_directed_opportunity(opportunity):
    """Evaluate a transient opportunity without writing a fake ledger event."""
    observer = _find_sim_info(opportunity.observer_id)
    partner = _find_sim_info(opportunity.partner_id)
    if observer is None or partner is None:
        return False
    try:
        from fgeh_cheatingharder_devotion_runtime import get_devotion_bond
        from fgeh_cheatingharder_relationship import has_claim

        bond = get_devotion_bond(observer.sim_id)
        if (
            not has_claim(observer, partner)
            and (bond is None or bond.beloved_id != partner.sim_id)
        ):
            return False
        state = get_directed_state(observer, partner)
        return bool(
            _evaluate_opportunity(
                opportunity,
                state,
                observer,
                partner,
            )
        )
    except Exception:
        log_exception(
            "transient opportunity evaluation failed observer={} partner={}".format(
                opportunity.observer_id,
                opportunity.partner_id,
            )
        )
        return False


def _process_event(event):
    log(
        "relationship event id={} type={} source={} actor={} target={} observer={} partner={} rival={} payload={}",
        event.event_id,
        event.event_type,
        event.source,
        event.actor_id,
        event.target_id,
        event.observer_id,
        event.partner_id,
        event.rival_id,
        event.payload,
    )
    _EVENT_HISTORY.append(event)
    if event.event_type in (
        EventType.CAUGHT_CHEATING,
        EventType.ROMANTIC_BOUNDARY_DISCOVERED,
    ) and event.directed_edge is not None:
        try:
            now = services.time_service().sim_now
            semantic_key = (
                event.observer_id,
                event.partner_id,
                event.rival_id,
            )
            previous = _RECENT_CAUGHT_EDGES.get(semantic_key)
            if previous is not None and (now - previous).in_minutes() < 5:
                log(
                    "betrayal awareness semantically deduplicated observer={} partner={} rival={} source={}",
                    event.observer_id,
                    event.partner_id,
                    event.rival_id,
                    event.source,
                )
                return
            _RECENT_CAUGHT_EDGES[semantic_key] = now
        except Exception:
            log_exception("caught semantic dedupe lookup failed")
    # Secret creation is intentionally retained as an objective debug fact
    # only.  It has no directed edge until the original game reports discovery.
    resolved_edges = _resolve_edges(event)
    try:
        from fgeh_cheatingharder_memory_runtime import record_relationship_event

        record_relationship_event(
            event,
            directed_edges=tuple(
                (observer.sim_id, partner.sim_id)
                for observer, partner in resolved_edges
            ),
        )
    except Exception:
        log_exception("romantic memory event bridge failed event={}".format(event))
    if event.event_type == EventType.AUTONOMOUS_ACTION_RESOLVED:
        try:
            from fgeh_cheatingharder_crisis_runtime import (
                on_autonomous_action_resolved,
            )

            on_autonomous_action_resolved(event)
        except Exception:
            log_exception(
                "relationship crisis action projection failed event={}".format(
                    event.event_id
                )
            )
    if event.event_type == EventType.BREAKUP_COMPLETED:
        try:
            from fgeh_cheatingharder_crisis_runtime import (
                close_crisis_after_relationship_end,
            )

            first_id = event.actor_id
            second_id = event.target_id
            if first_id is None or second_id is None:
                member_ids = tuple(
                    event.payload.get("relationship_member_ids", ())
                )
                if len(member_ids) == 2:
                    first_id, second_id = member_ids
            if first_id is not None and second_id is not None:
                close_crisis_after_relationship_end(
                    first_id,
                    second_id,
                    event_id=event.event_id,
                )
        except Exception:
            log_exception(
                "relationship crisis breakup close failed event={}".format(
                    event.event_id
                )
            )
    if event.event_type in (
        EventType.DEVOTION_LONGING_STARTED,
        EventType.DEVOTION_CONTACT_COMPLETED,
    ):
        try:
            from fgeh_cheatingharder_longing_runtime import (
                on_longing_started,
                on_meaningful_contact,
            )

            for observer, partner in resolved_edges:
                if event.event_type == EventType.DEVOTION_LONGING_STARTED:
                    on_longing_started(observer, partner)
                else:
                    on_meaningful_contact(observer, partner)
        except Exception:
            log_exception(
                "devotion longing projection failed event={}".format(event)
            )
    for observer, partner in resolved_edges:
        state_before = get_directed_state(observer, partner)
        changes = STATE_RULES.invoke(event, state_before)
        state_after = apply_changes(event, observer, partner, changes)
        opportunities = OPPORTUNITY_PROVIDERS.invoke(event, state_after)
        for opportunity in opportunities:
            _evaluate_opportunity(opportunity, state_after, observer, partner)


def get_last_decision(observer_id, partner_id):
    record = _LAST_DECISIONS.get((observer_id, partner_id))
    return record.as_dict() if record is not None else None


def get_last_execution(observer_id, partner_id):
    execution = _LAST_EXECUTIONS.get((observer_id, partner_id))
    return dict(execution) if execution is not None else None


def get_event_history():
    return tuple(
        {
            "id": event.event_id,
            "type": event.event_type,
            "source": event.source,
            "observer_id": event.observer_id,
            "partner_id": event.partner_id,
        }
        for event in _EVENT_HISTORY
    )

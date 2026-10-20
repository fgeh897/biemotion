"""Queue model-authorized breakup proposals through EA's normal interaction."""

import alarms
import date_and_time
import services
import sims4.resources

import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_domain import ExecutionResult


_LAST_PROPOSAL_TICKS = {}
_CONFIRMED_BREAKUP_RETRY_ALARMS = {}
_PENDING_RECIPIENT_RESPONSE_PAIRS = set()


def _sim_now_ticks():
    try:
        now = services.time_service().sim_now
        absolute_ticks = getattr(now, "absolute_ticks", None)
        return int(absolute_ticks() if callable(absolute_ticks) else now)
    except Exception:
        return None


def _cooldown_ticks():
    try:
        import date_and_time

        return int(date_and_time.create_time_span(
            minutes=settings.AUTONOMOUS_BREAKUP_PROPOSAL_COOLDOWN_SIM_MINUTES,
        ).in_ticks())
    except Exception:
        return int(settings.AUTONOMOUS_BREAKUP_PROPOSAL_COOLDOWN_SIM_MINUTES)


def has_autonomous_breakup_cooldown(observer_id, partner_id):
    last_ticks = _LAST_PROPOSAL_TICKS.get((int(observer_id), int(partner_id)))
    now_ticks = _sim_now_ticks()
    if last_ticks is None or now_ticks is None:
        return False
    return 0 <= now_ticks - last_ticks < _cooldown_ticks()


def reset_autonomous_breakup_runtime():
    _LAST_PROPOSAL_TICKS.clear()
    _PENDING_RECIPIENT_RESPONSE_PAIRS.clear()
    for handle in tuple(_CONFIRMED_BREAKUP_RETRY_ALARMS.values()):
        try:
            alarms.cancel_alarm(handle)
        except Exception:
            pass
    _CONFIRMED_BREAKUP_RETRY_ALARMS.clear()


def _breakup_affordance():
    try:
        key = sims4.resources.get_resource_key(
            next(iter(settings.EA_MANUAL_BREAKUP_AFFORDANCE_IDS)),
            sims4.resources.Types.INTERACTION,
        )
        return services.affordance_manager().get(key)
    except Exception:
        log_exception("autonomous breakup affordance lookup failed")
        return None


def _safe_social_starter(aops):
    exclusions = (
        "argue",
        "breakup",
        "break_up",
        "divorce",
        "fight",
        "flirt",
        "insult",
        "kiss",
        "mean",
        "propose",
        "woohoo",
        "sex",
    )
    for aop in tuple(aops or ()):
        affordance = getattr(aop, "affordance", None)
        if affordance is None or not getattr(affordance, "is_social", False):
            continue
        name = "{} {}".format(
            getattr(affordance, "__name__", ""),
            getattr(affordance, "name", ""),
        ).lower()
        if not any(marker in name for marker in exclusions):
            return affordance
    return None


def _breakup_mixer_aop(observer_sim, partner_sim, mixer, context):
    """Build the EA mixer under a real social SI instead of pushing it as SI."""
    try:
        from interactions.aop import AffordanceObjectPair

        rejected = []
        for social_si in tuple(observer_sim.si_state.sis_actor_gen()):
            if getattr(social_si, "is_finishing", False):
                continue
            try:
                potential_targets = tuple(
                    social_si.get_potential_mixer_targets()
                )
            except Exception:
                potential_targets = ()
            if (
                partner_sim not in potential_targets
                and getattr(social_si, "target", None) is not partner_sim
            ):
                continue
            aop = AffordanceObjectPair(
                mixer,
                partner_sim,
                social_si.affordance,
                social_si,
            )
            test_result = aop.test(context)
            if test_result:
                return aop, "running_social_mixer"
            if len(rejected) < 4:
                rejected.append(str(test_result))

        starter = _safe_social_starter(
            partner_sim.potential_interactions(context)
        )
        if starter is None:
            log(
                "autonomous breakup mixer has no social starter observer={} partner={} rejected={}",
                observer_sim.sim_id,
                partner_sim.sim_id,
                tuple(rejected),
            )
            return None, "no_social_starter"
        aop = AffordanceObjectPair(
            mixer,
            partner_sim,
            starter,
            None,
            push_super_on_prepare=True,
        )
        test_result = aop.test(context)
        if test_result:
            return aop, "started_social_mixer"
        log(
            "autonomous breakup mixer rejected observer={} partner={} result={} rejected={}",
            observer_sim.sim_id,
            partner_sim.sim_id,
            test_result,
            tuple(rejected),
        )
        return None, "mixer_tests_failed"
    except Exception:
        log_exception(
            "autonomous breakup mixer discovery failed observer={} partner={}".format(
                getattr(observer_sim, "sim_id", None),
                getattr(partner_sim, "sim_id", None),
            )
        )
        return None, "mixer_discovery_failed"


def _watch_breakup_interaction(
    interaction,
    observer_info,
    partner_info,
    selection_mode,
    transaction_id,
    negotiation_details,
    reason,
    retry_attempt,
):
    def _on_finishing(finished_interaction):
        try:
            from fgeh_cheatingharder_reconciliation_ea import (
                are_official_partners,
            )
            from fgeh_cheatingharder_breakup_adapter import (
                clear_model_breakup_authorization,
            )

            still_partners = bool(
                are_official_partners(observer_info, partner_info)
                or are_official_partners(partner_info, observer_info)
            )
            log(
                "autonomous breakup interaction finished interaction_id={} mode={} finishing_type={} still_official_partners={}",
                getattr(finished_interaction, "id", None),
                selection_mode,
                getattr(finished_interaction, "finishing_type", None),
                still_partners,
            )
            if still_partners:
                clear_model_breakup_authorization(
                    observer_info.sim_id,
                    partner_info.sim_id,
                )
                if retry_attempt < settings.CONFIRMED_BREAKUP_MAX_RETRIES:
                    _schedule_confirmed_breakup_retry(
                        observer_info,
                        partner_info,
                        transaction_id,
                        negotiation_details,
                        reason,
                        retry_attempt + 1,
                    )
                else:
                    fallback = _complete_confirmed_breakup_without_animation(
                        observer_info,
                        partner_info,
                        transaction_id,
                        negotiation_details,
                        reason,
                    )
                    if not fallback.accepted:
                        _report_confirmed_breakup_not_completed(
                            observer_info,
                            partner_info,
                        )
        except Exception:
            log_exception("autonomous breakup finishing callback failed")

    try:
        interaction.register_on_finishing_callback(_on_finishing)
    except Exception:
        log_exception("autonomous breakup finishing callback registration failed")


def _report_confirmed_breakup_not_completed(observer_info, partner_info):
    try:
        from fgeh_cheatingharder_notification import (
            show_breakup_not_completed_notification,
        )

        show_breakup_not_completed_notification(
            observer_info,
            partner_info,
        )
    except Exception:
        log_exception("confirmed breakup failure notification failed")


def _complete_confirmed_breakup_without_animation(
    observer_info,
    partner_info,
    transaction_id,
    negotiation_details,
    reason,
):
    """Apply EA's complete breakup loot after presentation repeatedly fails.

    This is an execution fallback, never a decision shortcut.  Callers reach
    it only after negotiation has authorized the official breakup.
    """
    try:
        from event_testing.resolver import DoubleSimResolver
        from fgeh_cheatingharder_breakup_adapter import (
            clear_model_breakup_authorization,
            grant_direct_model_breakup_authorization,
        )
        from fgeh_cheatingharder_reconciliation_ea import (
            are_official_partners,
        )

        if not (
            are_official_partners(observer_info, partner_info)
            or are_official_partners(partner_info, observer_info)
        ):
            return ExecutionResult(
                True,
                "confirmed_breakup_already_completed",
                {"negotiation": negotiation_details},
            )
        key = sims4.resources.get_resource_key(
            settings.EA_CONFIRMED_BREAKUP_FALLBACK_LOOT_ID,
            sims4.resources.Types.ACTION,
        )
        loot = services.get_instance_manager(
            sims4.resources.Types.ACTION
        ).get(key)
        if loot is None:
            return ExecutionResult(False, "confirmed_breakup_loot_missing")
        grant_direct_model_breakup_authorization(
            observer_info.sim_id,
            partner_info.sim_id,
            transaction_id,
        )
        loot.apply_to_resolver(
            DoubleSimResolver(observer_info, partner_info)
        )
        still_partners = bool(
            are_official_partners(observer_info, partner_info)
            or are_official_partners(partner_info, observer_info)
        )
        log(
            "confirmed breakup direct fallback applied transaction={} "
            "proposer={} recipient={} reason={} loot_id={} "
            "still_official_partners={}",
            transaction_id,
            observer_info.sim_id,
            partner_info.sim_id,
            reason,
            settings.EA_CONFIRMED_BREAKUP_FALLBACK_LOOT_ID,
            still_partners,
        )
        if still_partners:
            clear_model_breakup_authorization(
                observer_info.sim_id,
                partner_info.sim_id,
            )
            return ExecutionResult(
                False,
                "confirmed_breakup_direct_fallback_failed",
                {"negotiation": negotiation_details},
            )
        return ExecutionResult(
            True,
            "confirmed_breakup_direct_fallback_completed",
            {"negotiation": negotiation_details},
        )
    except Exception:
        log_exception(
            "confirmed breakup direct fallback failed transaction={}".format(
                transaction_id,
            )
        )
        return ExecutionResult(
            False,
            "confirmed_breakup_direct_fallback_exception",
            {"negotiation": negotiation_details},
        )


def _schedule_confirmed_breakup_retry(
    observer_info,
    partner_info,
    transaction_id,
    negotiation_details,
    reason,
    retry_attempt,
):
    key = (int(observer_info.sim_id), int(partner_info.sim_id))
    existing = _CONFIRMED_BREAKUP_RETRY_ALARMS.get(key)
    if existing is not None:
        return existing

    def _on_retry_alarm(_alarm_handle):
        _CONFIRMED_BREAKUP_RETRY_ALARMS.pop(key, None)
        try:
            from fgeh_cheatingharder_reconciliation_ea import (
                are_official_partners,
            )

            if not (
                are_official_partners(observer_info, partner_info)
                or are_official_partners(partner_info, observer_info)
            ):
                log(
                    "confirmed breakup retry skipped: relationship already ended transaction={} proposer={} recipient={}",
                    transaction_id,
                    observer_info.sim_id,
                    partner_info.sim_id,
                )
                return
            result = _queue_confirmed_breakup_execution(
                observer_info,
                partner_info,
                transaction_id,
                negotiation_details,
                reason,
                retry_attempt=retry_attempt,
            )
            if result.accepted:
                return
            if retry_attempt < settings.CONFIRMED_BREAKUP_MAX_RETRIES:
                _schedule_confirmed_breakup_retry(
                    observer_info,
                    partner_info,
                    transaction_id,
                    negotiation_details,
                    reason,
                    retry_attempt + 1,
                )
            else:
                fallback = _complete_confirmed_breakup_without_animation(
                    observer_info,
                    partner_info,
                    transaction_id,
                    negotiation_details,
                    reason,
                )
                if not fallback.accepted:
                    _report_confirmed_breakup_not_completed(
                        observer_info,
                        partner_info,
                    )
        except Exception:
            log_exception(
                "confirmed breakup retry failed transaction={}".format(
                    transaction_id,
                )
            )

    handle = alarms.add_alarm(
        observer_info,
        date_and_time.create_time_span(
            minutes=settings.CONFIRMED_BREAKUP_RETRY_SIM_MINUTES,
        ),
        _on_retry_alarm,
        cross_zone=True,
    )
    _CONFIRMED_BREAKUP_RETRY_ALARMS[key] = handle
    log(
        "confirmed breakup execution retry scheduled transaction={} proposer={} recipient={} attempt={} delay_minutes={}",
        transaction_id,
        observer_info.sim_id,
        partner_info.sim_id,
        retry_attempt,
        settings.CONFIRMED_BREAKUP_RETRY_SIM_MINUTES,
    )
    return handle


def _remember_proposal_and_schedule(observer_info, partner_info, now_ticks):
    if now_ticks is not None:
        _LAST_PROPOSAL_TICKS[(
            int(observer_info.sim_id),
            int(partner_info.sim_id),
        )] = now_ticks
    try:
        from fgeh_cheatingharder_scheduler import schedule_relationship_reevaluation

        schedule_relationship_reevaluation(
            observer_info,
            partner_info,
            reason="autonomous_breakup_negotiated",
            minutes=settings.AUTONOMOUS_BREAKUP_PROPOSAL_COOLDOWN_SIM_MINUTES,
        )
    except Exception:
        log_exception("autonomous breakup follow-up scheduling failed")


def _selected_breakup_candidate(intent):
    decision = dict(intent.context.get("decision", {}) or {})
    for candidate in tuple(decision.get("candidates", ()) or ()):
        candidate = dict(candidate or {})
        if candidate.get("intent") == "break_up":
            return candidate
    return {}


def _queue_confirmed_breakup_execution(
    observer_info,
    partner_info,
    transaction_id,
    negotiation_details,
    reason,
    retry_attempt=0,
):
    """Retry one already-confirmed breakup without reopening negotiation."""
    observer_sim = observer_info.get_sim_instance()
    partner_sim = partner_info.get_sim_instance()
    if observer_sim is None or partner_sim is None:
        return ExecutionResult(False, "confirmed_breakup_pair_not_instanced")
    if getattr(observer_sim, "zone_id", None) != getattr(partner_sim, "zone_id", None):
        return ExecutionResult(False, "confirmed_breakup_pair_not_on_same_zone")
    authorization_granted = False
    try:
        from fgeh_cheatingharder_breakup_adapter import (
            bind_model_breakup_interaction,
            clear_model_breakup_authorization,
            grant_model_breakup_authorization,
        )

        grant_model_breakup_authorization(
            observer_info.sim_id,
            partner_info.sim_id,
            transaction_id,
        )
        authorization_granted = True
        affordance = _breakup_affordance()
        if affordance is None:
            clear_model_breakup_authorization(
                observer_info.sim_id,
                partner_info.sim_id,
            )
            return ExecutionResult(False, "breakup_affordance_missing")
        from interactions.context import InteractionContext, QueueInsertStrategy
        from interactions.priority import Priority

        context = InteractionContext(
            observer_sim,
            InteractionContext.SOURCE_SCRIPT,
            Priority.High,
            insert_strategy=QueueInsertStrategy.NEXT,
            must_run_next=True,
        )
        breakup_aop, selection_mode = _breakup_mixer_aop(
            observer_sim,
            partner_sim,
            affordance,
            context,
        )
        if breakup_aop is None:
            clear_model_breakup_authorization(
                observer_info.sim_id,
                partner_info.sim_id,
            )
            authorization_granted = False
            return ExecutionResult(
                False,
                "breakup_mixer_unavailable",
                {
                    "selection_mode": selection_mode,
                    "negotiation": negotiation_details,
                    "retry_attempt": retry_attempt,
                },
            )
        result = breakup_aop.test_and_execute(context)
        interaction = getattr(result, "interaction", None)
        accepted = bool(result) and not getattr(interaction, "is_finishing", False)
        if not accepted:
            clear_model_breakup_authorization(
                observer_info.sim_id,
                partner_info.sim_id,
            )
            authorization_granted = False
            return ExecutionResult(
                False,
                "breakup_authorized_interaction_rejected",
                {
                    "negotiation": negotiation_details,
                    "retry_attempt": retry_attempt,
                },
            )
        bind_model_breakup_interaction(
            observer_info.sim_id,
            partner_info.sim_id,
            getattr(interaction, "id", None),
        )
        _watch_breakup_interaction(
            interaction,
            observer_info,
            partner_info,
            selection_mode,
            transaction_id,
            negotiation_details,
            reason,
            retry_attempt,
        )
        log(
            "confirmed breakup execution queued transaction={} proposer={} recipient={} interaction_id={} attempt={} selection_mode={}",
            transaction_id,
            observer_info.sim_id,
            partner_info.sim_id,
            getattr(interaction, "id", None),
            retry_attempt,
            selection_mode,
        )
        return ExecutionResult(
            True,
            "confirmed_breakup_execution_queued",
            {
                "interaction_id": getattr(interaction, "id", None),
                "selection_mode": selection_mode,
                "retry_attempt": retry_attempt,
                "negotiation": negotiation_details,
            },
        )
    except Exception:
        if authorization_granted:
            try:
                from fgeh_cheatingharder_breakup_adapter import (
                    clear_model_breakup_authorization,
                )

                clear_model_breakup_authorization(
                    observer_info.sim_id,
                    partner_info.sim_id,
                )
            except Exception:
                log_exception("confirmed breakup authorization cleanup failed")
        log_exception(
            "confirmed breakup execution failed transaction={}".format(
                transaction_id,
            )
        )
        return ExecutionResult(False, "confirmed_breakup_execution_failed")


def push_breakup_proposal(
    observer_info,
    partner_info,
    intent,
    forced_recipient_response=None,
):
    observer_sim = observer_info.get_sim_instance()
    partner_sim = partner_info.get_sim_instance()
    if observer_sim is None or partner_sim is None:
        return ExecutionResult(False, "breakup_pair_not_instanced")
    if getattr(observer_sim, "zone_id", None) != getattr(partner_sim, "zone_id", None):
        return ExecutionResult(False, "breakup_pair_not_on_same_zone")
    pair_key = (int(observer_info.sim_id), int(partner_info.sim_id))
    if forced_recipient_response is None:
        try:
            active_sim = services.get_active_sim()
            recipient_is_active = (
                active_sim is not None
                and int(active_sim.sim_id) == int(partner_info.sim_id)
                and bool(getattr(partner_sim, "is_selectable", False))
            )
        except Exception:
            recipient_is_active = False
        if recipient_is_active:
            if pair_key in _PENDING_RECIPIENT_RESPONSE_PAIRS:
                return ExecutionResult(
                    True,
                    "breakup_recipient_response_pending",
                )
            try:
                from fgeh_cheatingharder_breakup_negotiation import (
                    BreakupResponse,
                )
                from fgeh_cheatingharder_confirmation import (
                    show_breakup_recipient_response_dialog,
                )

                _PENDING_RECIPIENT_RESPONSE_PAIRS.add(pair_key)

                def _continue_with_response(response):
                    _PENDING_RECIPIENT_RESPONSE_PAIRS.discard(pair_key)
                    result = push_breakup_proposal(
                        observer_info,
                        partner_info,
                        intent,
                        forced_recipient_response=response,
                    )
                    log(
                        "autonomous breakup continued after player recipient response proposer={} recipient={} response={} accepted={} status={}",
                        observer_info.sim_id,
                        partner_info.sim_id,
                        response,
                        result.accepted,
                        result.status,
                    )

                shown = show_breakup_recipient_response_dialog(
                    observer_info,
                    partner_info,
                    on_accept=lambda: _continue_with_response(
                        BreakupResponse.ACCEPT
                    ),
                    on_plead=lambda: _continue_with_response(
                        BreakupResponse.PLEAD
                    ),
                )
                if shown:
                    return ExecutionResult(
                        True,
                        "breakup_recipient_response_pending",
                    )
                _PENDING_RECIPIENT_RESPONSE_PAIRS.discard(pair_key)
            except Exception:
                _PENDING_RECIPIENT_RESPONSE_PAIRS.discard(pair_key)
                log_exception(
                    "autonomous breakup recipient dialog dispatch failed"
                )
    now_ticks = _sim_now_ticks()
    evidence = {
        "origin": "ea_scripted",
        "intentional": True,
        "affordance_id": next(iter(
            settings.EA_MANUAL_BREAKUP_AFFORDANCE_IDS
        )),
        "affordance_name": "model_authorized_ea_breakup",
        "manual_breakup_authorized": False,
        "relationship_model_proposal": True,
    }
    decision = dict(intent.context.get("decision", {}) or {})
    policy_details = {
        "reason": "relationship_model_selected_breakup",
        "selected_intent": "break_up",
        "breakup_candidate": _selected_breakup_candidate(intent),
        "decision_reference": "behavior:{}:{}:{}".format(
            observer_info.sim_id,
            partner_info.sim_id,
            now_ticks,
        ),
        "reaction_context": {},
        "behavior_decision": decision,
    }
    authorization_granted = False
    try:
        from fgeh_cheatingharder_breakup_negotiation_runtime import (
            evaluate_ea_breakup_negotiation,
        )

        negotiation = evaluate_ea_breakup_negotiation(
            observer_info,
            partner_info,
            evidence,
            policy_details,
            occurred_ticks=now_ticks,
            forced_response=forced_recipient_response,
        )
        if negotiation is None:
            return ExecutionResult(False, "breakup_negotiation_failed")
        _remember_proposal_and_schedule(
            observer_info,
            partner_info,
            now_ticks,
        )
        negotiation_details = negotiation.as_dict()
        if not negotiation.official_breakup_authorized:
            log(
                "autonomous breakup negotiation retained relationship transaction={} proposer={} recipient={} response={} final={} outcome={}",
                negotiation.transaction_id,
                observer_info.sim_id,
                partner_info.sim_id,
                negotiation.response,
                negotiation.proposer_decision,
                negotiation.outcome,
            )
            return ExecutionResult(
                True,
                "breakup_negotiation_{}".format(negotiation.outcome),
                {"negotiation": negotiation_details},
            )

        from fgeh_cheatingharder_breakup_adapter import (
            bind_model_breakup_interaction,
            clear_model_breakup_authorization,
            grant_model_breakup_authorization,
        )

        grant_model_breakup_authorization(
            observer_info.sim_id,
            partner_info.sim_id,
            negotiation.transaction_id,
        )
        authorization_granted = True
        affordance = _breakup_affordance()
        if affordance is None:
            clear_model_breakup_authorization(
                observer_info.sim_id,
                partner_info.sim_id,
            )
            return ExecutionResult(False, "breakup_affordance_missing")
        from interactions.context import InteractionContext, QueueInsertStrategy
        from interactions.priority import Priority

        context = InteractionContext(
            observer_sim,
            # EA's manual breakup mixer is visible in the pie menu but is not
            # an autonomy-enabled affordance.  The relationship model has
            # already made the autonomous decision, so queue the resulting
            # action as a script request.  The breakup adapter still classifies
            # this as EA_SCRIPTED (never as a player override), and the normal
            # negotiation/policy gate remains authoritative.
            InteractionContext.SOURCE_SCRIPT,
            Priority.High,
            insert_strategy=QueueInsertStrategy.NEXT,
            must_run_next=True,
        )
        breakup_aop, selection_mode = _breakup_mixer_aop(
            observer_sim,
            partner_sim,
            affordance,
            context,
        )
        if breakup_aop is None:
            clear_model_breakup_authorization(
                observer_info.sim_id,
                partner_info.sim_id,
            )
            authorization_granted = False
            return ExecutionResult(
                False,
                "breakup_mixer_unavailable",
                {
                    "selection_mode": selection_mode,
                    "negotiation": negotiation_details,
                },
            )
        result = breakup_aop.test_and_execute(context)
        interaction = getattr(result, "interaction", None)
        accepted = bool(result) and not getattr(interaction, "is_finishing", False)
        if not accepted:
            clear_model_breakup_authorization(
                observer_info.sim_id,
                partner_info.sim_id,
            )
            authorization_granted = False
            # The EA mixer can return a truthy EnqueueResult while the
            # interaction it created is already finishing (most commonly
            # KILLED during queue append).  Negotiation has nevertheless
            # reached a final, authoritative ``confirm_breakup`` decision.
            # Preserve that decision and retry its execution instead of
            # silently falling back to an unchanged official partnership.
            _schedule_confirmed_breakup_retry(
                observer_info,
                partner_info,
                negotiation.transaction_id,
                negotiation_details,
                intent.reason,
                1,
            )
            log(
                "confirmed autonomous breakup could not enter EA queue; retry retained transaction={} proposer={} recipient={} interaction_id={} finishing_type={}",
                negotiation.transaction_id,
                observer_info.sim_id,
                partner_info.sim_id,
                getattr(interaction, "id", None),
                getattr(interaction, "finishing_type", None),
            )
            log(
                "autonomous breakup proposal rejected by EA tests proposer={} recipient={} reason={} push_result={} interaction={}",
                observer_info.sim_id,
                partner_info.sim_id,
                intent.reason,
                result,
                interaction,
            )
            return ExecutionResult(
                True,
                "confirmed_breakup_retry_scheduled",
                {
                    "negotiation": negotiation_details,
                    "retry_attempt": 1,
                    "interaction_id": getattr(interaction, "id", None),
                    "finishing_type": str(
                        getattr(interaction, "finishing_type", None)
                    ),
                },
            )
        bind_model_breakup_interaction(
            observer_info.sim_id,
            partner_info.sim_id,
            getattr(interaction, "id", None),
        )
        _watch_breakup_interaction(
            interaction,
            observer_info,
            partner_info,
            selection_mode,
            negotiation.transaction_id,
            negotiation_details,
            intent.reason,
            0,
        )
        log(
            "autonomous breakup proposal queued proposer={} recipient={} reason={} interaction_id={} selection_mode={}",
            observer_info.sim_id,
            partner_info.sim_id,
            intent.reason,
            getattr(interaction, "id", None),
            selection_mode,
        )
        return ExecutionResult(
            True,
            "breakup_proposal_queued",
            {
                "interaction_id": getattr(interaction, "id", None),
                "selection_mode": selection_mode,
                "negotiation": negotiation_details,
            },
        )
    except Exception:
        if authorization_granted:
            try:
                from fgeh_cheatingharder_breakup_adapter import (
                    clear_model_breakup_authorization,
                )

                clear_model_breakup_authorization(
                    observer_info.sim_id,
                    partner_info.sim_id,
                )
            except Exception:
                log_exception("failed model breakup authorization cleanup failed")
        log_exception(
            "autonomous breakup proposal push failed proposer={} recipient={}".format(
                observer_info.sim_id,
                partner_info.sim_id,
            )
        )
        return ExecutionResult(False, "breakup_proposal_push_failed")

"""Active-lot executor for registered memory-driven autonomous actions.

Only this module may translate a memory opportunity into a queued EA
interaction.  Decision rules stay pure, and every game-facing action must be
registered by (opportunity_type, intent) before it can execute.
"""

import alarms
import date_and_time
import services

import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_autonomy import admit_memory_opportunity
from fgeh_cheatingharder_behavior_registry import (
    AffordanceSelectionProfile,
    AutonomousBehaviorDefinition,
    AutonomousBehaviorRegistry,
    BehaviorExecutionStrategy,
)
from fgeh_cheatingharder_betrayal_memory_rules import (
    OPPORTUNITY_BETRAYAL_RESPONSE,
)
from fgeh_cheatingharder_betrayal_reactions import BetrayalIntent
from fgeh_cheatingharder_betrayal_episode import (
    BETRAYAL_REACTION_EPISODES,
    BetrayalEpisodeStatus,
    reset_betrayal_reaction_episodes,
)
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_domain import BehaviorIntent, EventType
from fgeh_cheatingharder_memory_models import MemoryOpportunity


OPPORTUNITY_RELATIONSHIP_CRISIS = "relationship_crisis"
CRISIS_INTENT_SEEK_REASSURANCE = "seek_reassurance"


_BEHAVIOR_REGISTRY = AutonomousBehaviorRegistry()
_ACTION_HANDLERS = {}
_ACTION_ALARMS = {}
_ACTION_TOKENS = {}
_PENDING_INTERACTIONS = {}
_COOLDOWN_STARTED_AT = {}

_REASSURANCE_PROFILE = AffordanceSelectionProfile(
    "core.social.seek_reassurance.v1",
    weights=(
        ("reassur", 120),
        ("comfort", 115),
        ("console", 110),
        ("deepconversation", 95),
        ("deep_conversation", 95),
        ("heartfeltcompliment", 90),
        ("heartfelt_compliment", 90),
        ("hug", 85),
        ("embrace", 80),
        ("askaboutday", 65),
        ("ask_about_day", 65),
        ("friendly", 35),
        ("chat", 25),
        ("talk", 20),
    ),
    exclusions=(
        "argue",
        "breakup",
        "break_up",
        "divorce",
        "fight",
        "flirt",
        "insult",
        "kiss",
        "mean",
        "mock",
        "propose",
        "shout",
        "try_for_baby",
        "woohoo",
        "yell",
        "sex",
    ),
)

_CLING_TO_PARTNER_PROFILE = AffordanceSelectionProfile(
    "core.social.cling_to_partner.v1",
    weights=(
        ("hug", 160),
        ("embrace", 150),
    ),
    exclusions=(
        "argue",
        "breakup",
        "break_up",
        "divorce",
        "fight",
        "flirt",
        "insult",
        "kiss",
        "mean",
        "mock",
        "propose",
        "shout",
        "try_for_baby",
        "woohoo",
        "yell",
        "sex",
    ),
)

_CONFRONT_PARTNER_PROFILE = AffordanceSelectionProfile(
    "core.social.confront_partner.v1",
    weights=(
        ("accuseofcheating", 140),
        ("accuse_of_cheating", 140),
        ("accuse", 125),
        ("confront", 120),
        ("demandexplanation", 115),
        ("demand_explanation", 115),
        ("argue", 90),
        ("insult", 100),
        ("yell", 80),
        ("shout", 75),
    ),
    exclusions=(
        "apolog",
        "breakup",
        "break_up",
        "comfort",
        "divorce",
        "embrace",
        "fight",
        "flirt",
        "hug",
        "kiss",
        "propose",
        "try_for_baby",
        "woohoo",
        "sex",
    ),
    # Confirmed base-game SocialMixerInteraction tunings. Mixers are not
    # exposed by Sim.potential_interactions(), so the executor attaches them
    # to an existing or safely started social super interaction.
    fallback_mixer_ids=(
        25674,  # mixer_social_Insult_Mean_STC
        26151,  # mixer_social_YellAT_targeted_mean
    ),
)

_CONFRONT_RIVAL_PROFILE = AffordanceSelectionProfile(
    "core.social.confront_rival.v1",
    weights=(
        ("insult", 140),
        ("yell", 125),
        ("shout", 120),
        ("argue", 110),
        ("confront", 100),
        ("accuse", 90),
        ("mock", 80),
    ),
    exclusions=(
        "apolog",
        "breakup",
        "break_up",
        "comfort",
        "divorce",
        "embrace",
        "fight",
        "flirt",
        "hug",
        "kiss",
        "propose",
        "try_for_baby",
        "woohoo",
        "sex",
    ),
    fallback_mixer_ids=(
        25674,  # mixer_social_Insult_Mean_STC
        26151,  # mixer_social_YellAT_targeted_mean
    ),
)


def _sim_now_ticks():
    try:
        now = services.time_service().sim_now
        absolute_ticks = getattr(now, "absolute_ticks", None)
        return absolute_ticks() if callable(absolute_ticks) else int(now)
    except Exception:
        return None


def _elapsed_minutes(previous_ticks):
    now_ticks = _sim_now_ticks()
    if now_ticks is None or previous_ticks is None:
        return None
    try:
        return max(
            0.0,
            date_and_time.TimeSpan(
                int(now_ticks) - int(previous_ticks)
            ).in_minutes(),
        )
    except (TypeError, ValueError):
        return None


def register_autonomous_action(
    opportunity_type,
    intent,
    handler,
    definition=None,
):
    """Register a behavior without breaking the original handler API."""
    key = (str(opportunity_type), str(intent))
    if definition is None:
        definition = AutonomousBehaviorDefinition(
            key[0],
            key[1],
            BehaviorExecutionStrategy.CUSTOM_HANDLER,
        )
    elif definition.key != key:
        raise ValueError(
            "Behavior definition key {} does not match handler key {}".format(
                definition.key,
                key,
            )
        )
    if key in _ACTION_HANDLERS and _ACTION_HANDLERS[key] is not handler:
        raise ValueError(
            "Autonomous action already registered: {}".format(key)
        )
    _BEHAVIOR_REGISTRY.register(definition)
    _ACTION_HANDLERS[key] = handler
    return key


def registered_autonomous_actions():
    return _BEHAVIOR_REGISTRY.keys()


def registered_autonomous_behavior_definitions():
    return tuple(
        value.to_data()
        for value in _BEHAVIOR_REGISTRY.definitions()
    )


def _summary_cooldown_started(observer_id, partner_id, timestamp_key):
    if not timestamp_key:
        return None
    try:
        from fgeh_cheatingharder_memory_runtime import get_memory_summary

        summary = get_memory_summary(observer_id, partner_id)
        if summary is None:
            return None
        return summary.timestamps.get(str(timestamp_key))
    except Exception:
        return None


def _behavior_cooldown(definition, observer_id, partner_id):
    if definition is None or definition.cooldown_minutes <= 0.0:
        return False
    key = (int(observer_id), int(partner_id), definition.intent)
    previous = _COOLDOWN_STARTED_AT.get(key)
    persisted = _summary_cooldown_started(
        observer_id,
        partner_id,
        definition.cooldown_timestamp_key,
    )
    if previous is None or (
        persisted is not None and int(persisted) > int(previous)
    ):
        previous = persisted
    elapsed = _elapsed_minutes(previous)
    return (
        elapsed is not None
        and elapsed < definition.cooldown_minutes
    )


def _seek_reassurance_cooldown(observer_id, partner_id):
    """Compatibility wrapper retained for existing debug tooling."""
    definition = _BEHAVIOR_REGISTRY.get(
        OPPORTUNITY_BETRAYAL_RESPONSE,
        BetrayalIntent.SEEK_REASSURANCE,
    )
    return _behavior_cooldown(definition, observer_id, partner_id)


def _is_cooldown_active(opportunity):
    context = dict(opportunity.context)
    if context.get("debug_bypass_cooldown"):
        return False
    selected = context.get("selected_intent")
    definition = _BEHAVIOR_REGISTRY.get(
        opportunity.opportunity_type,
        selected,
    )
    return _behavior_cooldown(
        definition,
        opportunity.observer_id,
        opportunity.partner_id,
    )


def _has_valid_recorded_target(opportunity):
    """Fail closed when a relationship action declares an event target role."""
    context = dict(getattr(opportunity, "context", {}) or {})
    target_role = context.get("target_role")
    if not target_role:
        return True
    source_event_id = context.get("source_betrayal_event_id")
    try:
        from fgeh_cheatingharder_betrayal_memory_rules import (
            betrayal_target_matches_event,
        )
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        event = get_memory_service().store.get_event(source_event_id)
        valid = betrayal_target_matches_event(
            event,
            opportunity.observer_id,
            opportunity.partner_id,
            target_role,
        )
        if not valid:
            log(
                "autonomous target provenance rejected source_event={} "
                "observer={} target={} role={}",
                source_event_id,
                opportunity.observer_id,
                opportunity.partner_id,
                target_role,
            )
        return valid
    except Exception:
        log_exception(
            "autonomous target provenance validation failed event={}".format(
                source_event_id
            )
        )
        return False


def consume_memory_opportunities(opportunities, report=None):
    """Admit and schedule registered opportunities; never execute inline."""
    results = []
    for opportunity in tuple(opportunities or ()):
        admission = admit_memory_opportunity(
            opportunity,
            registered_autonomous_actions(),
            cooldown_active=_is_cooldown_active(opportunity),
            target_provenance_valid=_has_valid_recorded_target(opportunity),
        )
        results.append(admission)
        log(
            "autonomous opportunity admission event={} decision={}",
            getattr(getattr(report, "event", None), "event_id", None),
            admission.to_data(),
        )
        episode_id = dict(opportunity.context or {}).get(
            "betrayal_episode_id"
        )
        if not admission.admitted:
            if episode_id:
                BETRAYAL_REACTION_EPISODES.resolve(
                    episode_id,
                    "admission_{}".format(admission.status),
                    success=False,
                )
            continue
        handler = _ACTION_HANDLERS.get(admission.action_key)
        if handler is None:
            if episode_id:
                BETRAYAL_REACTION_EPISODES.resolve(
                    episode_id,
                    "handler_missing",
                    success=False,
                )
            continue
        try:
            scheduled = handler(opportunity, admission)
            if episode_id:
                if scheduled is None:
                    BETRAYAL_REACTION_EPISODES.resolve(
                        episode_id,
                        "scheduling_failed",
                        success=False,
                    )
                else:
                    BETRAYAL_REACTION_EPISODES.mark(
                        episode_id,
                        BetrayalEpisodeStatus.SCHEDULED,
                    )
        except Exception:
            if episode_id:
                BETRAYAL_REACTION_EPISODES.resolve(
                    episode_id,
                    "scheduling_exception",
                    success=False,
                )
            log_exception(
                "autonomous action scheduling failed key={}".format(
                    admission.action_key
                )
            )
    return tuple(results)


def _live_pair(observer_id, partner_id):
    try:
        manager = services.sim_info_manager()
        observer_info = manager.get(int(observer_id))
        partner_info = manager.get(int(partner_id))
        if observer_info is None or partner_info is None:
            return (observer_info, partner_info, None, None, False)
        observer = observer_info.get_sim_instance()
        partner = partner_info.get_sim_instance()
        active_zone_id = getattr(services.current_zone(), "id", None)
        together = (
            observer is not None
            and partner is not None
            and getattr(observer, "zone_id", None) == active_zone_id
            and getattr(partner, "zone_id", None) == active_zone_id
        )
        return (
            observer_info,
            partner_info,
            observer,
            partner,
            together,
        )
    except Exception:
        return (None, None, None, None, False)


def _affordance_name(affordance):
    return str(getattr(affordance, "__name__", affordance)).lower()


def _reassurance_affordance_score(affordance):
    """Compatibility wrapper for the original reassurance selector."""
    score = _REASSURANCE_PROFILE.score_name(_affordance_name(affordance))
    return -1000 if score is None else score


def _profiled_affordance_score(profile, affordance):
    if (
        profile.require_social
        and not getattr(affordance, "is_social", False)
    ):
        return None
    return profile.score_name(_affordance_name(affordance))


def _safe_social_starter(aops):
    """Select a neutral social SI that can host a fallback EA mixer."""
    preferred = (
        "chat",
        "talk",
        "askaboutday",
        "ask_about_day",
        "deepconversation",
        "deep_conversation",
    )
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
    ranked = []
    for aop in tuple(aops or ()):
        affordance = getattr(aop, "affordance", None)
        if affordance is None or not getattr(affordance, "is_social", False):
            continue
        name = _affordance_name(affordance)
        if any(marker in name for marker in exclusions):
            continue
        rank = 0
        for index, marker in enumerate(preferred):
            if marker in name:
                rank = len(preferred) - index
                break
        ranked.append((rank, name, aop))
    if not ranked:
        return None
    ranked.sort(key=lambda value: (value[0], value[1]), reverse=True)
    return ranked[0][2]


def _fallback_mixer_candidates(
    observer,
    partner,
    context,
    profile,
    target_aops,
):
    """Build tested EA mixer AOPs without bypassing interaction tests."""
    if not profile.fallback_mixer_ids:
        return ()
    try:
        from interactions.aop import AffordanceObjectPair
        from sims4.resources import Types

        manager = services.get_instance_manager(Types.INTERACTION)
        mixers = tuple(
            affordance
            for affordance in (
                manager.get(int(instance_id))
                for instance_id in profile.fallback_mixer_ids
            )
            if affordance is not None
        )
        if not mixers:
            return ()

        candidates = []
        rejected = []
        seen = set()
        running_si_count = 0
        for si in tuple(observer.si_state.sis_actor_gen()):
            if getattr(si, "is_finishing", False):
                continue
            running_si_count += 1
            try:
                potential_targets = tuple(si.get_potential_mixer_targets())
            except Exception:
                potential_targets = ()
            if partner not in potential_targets and getattr(
                si,
                "target",
                None,
            ) is not partner:
                continue
            for mixer in mixers:
                key = (mixer, getattr(si, "id", None))
                if key in seen:
                    continue
                seen.add(key)
                aop = AffordanceObjectPair(
                    mixer,
                    partner,
                    si.affordance,
                    si,
                )
                test_result = aop.test(context)
                if test_result:
                    score = profile.score_name(_affordance_name(mixer))
                    if score is not None:
                        candidates.append((
                            score + 10.0,
                            mixer,
                            aop,
                            "running_social_mixer",
                            context,
                        ))
                elif len(rejected) < 6:
                    rejected.append(
                        "running:{}:{}".format(
                            _affordance_name(mixer),
                            str(test_result),
                        )
                    )

        if candidates:
            log(
                "fallback social mixer scan profile={} running_sis={} "
                "starter=unused accepted={} rejected={}",
                profile.key,
                running_si_count,
                len(candidates),
                tuple(rejected),
            )
            return tuple(candidates)

        starter_aop = _safe_social_starter(target_aops)
        if starter_aop is None:
            log(
                "fallback social mixer scan profile={} running_sis={} "
                "starter=missing accepted=0 rejected={}",
                profile.key,
                running_si_count,
                tuple(rejected),
            )
            return ()
        starter = getattr(starter_aop, "affordance", None)
        for mixer in mixers:
            key = (mixer, None)
            if key in seen:
                continue
            seen.add(key)
            aop = AffordanceObjectPair(
                mixer,
                partner,
                starter,
                None,
                push_super_on_prepare=True,
            )
            test_result = aop.test(context)
            if test_result:
                score = profile.score_name(_affordance_name(mixer))
                if score is not None:
                    candidates.append((
                        score,
                        mixer,
                        aop,
                        "started_social_mixer",
                        context,
                    ))
            elif len(rejected) < 6:
                rejected.append(
                    "starter:{}:{}".format(
                        _affordance_name(mixer),
                        str(test_result),
                    )
                )
        log(
            "fallback social mixer scan profile={} running_sis={} "
            "starter={} accepted={} rejected={}",
            profile.key,
            running_si_count,
            _affordance_name(starter),
            len(candidates),
            tuple(rejected),
        )
        return tuple(candidates)
    except Exception:
        log_exception(
            "fallback social mixer discovery failed profile={}".format(
                profile.key
            )
        )
        return ()


def _evaluate_counterpart_response(record, success):
    """Let the relationship partner answer a completed crisis action."""
    if not success or str(record.get("target_role") or "partner") != "partner":
        return None
    intent = str(record.get("intent") or "")
    if intent not in (
        BetrayalIntent.SEEK_REASSURANCE,
        BetrayalIntent.CLING_TO_PARTNER,
        BetrayalIntent.CONFRONT_PARTNER,
    ):
        return None
    try:
        from fgeh_cheatingharder_counterpart_response import (
            evaluate_counterpart_response,
        )
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        observer_id = int(record["observer_id"])
        responder_id = int(record["partner_id"])
        store = get_memory_service().store
        state_record = store.get_directed_state(
            responder_id,
            observer_id,
        )
        responder_state = (
            {}
            if state_record is None
            else dict(state_record.values)
        )
        injured_summary = store.get_summary(observer_id, responder_id)
        evaluation = evaluate_counterpart_response(
            intent,
            responder_state,
            injured_history=injured_summary.counters,
        )
        if evaluation is None:
            return None
        result = evaluation.as_dict()
        log(
            "betrayal counterpart response injured={} responder={} intent={} response={} roll={:.3f} candidates={}",
            observer_id,
            responder_id,
            intent,
            result.get("selected_response"),
            result.get("roll", 0.0),
            tuple(
                (
                    value.get("response"),
                    value.get("score"),
                )
                for value in result.get("candidates", ())
            ),
        )
        return result
    except Exception:
        log_exception(
            "betrayal counterpart response failed intent={}".format(intent)
        )
        return None


def _publish_action_outcome(record, success, status):
    episode_id = record.get("betrayal_episode_id")
    if episode_id:
        BETRAYAL_REACTION_EPISODES.resolve(
            episode_id,
            status,
            success=success,
        )
    try:
        from fgeh_cheatingharder_event_center import publish

        now_ticks = _sim_now_ticks()
        target_id = int(record["partner_id"])
        relationship_partner_id = int(
            record.get("relationship_partner_id") or target_id
        )
        target_role = str(record.get("target_role") or "partner")
        rival_id = (
            target_id
            if target_role == "rival"
            else record.get("rival_id")
        )
        counterpart = _evaluate_counterpart_response(record, success)
        payload = {
            "occurred_at": now_ticks,
            "cause_id": record.get("source_event_id"),
            "source_event_id": record.get("source_event_id"),
            "target_id": target_id,
            "target_role": target_role,
            "relationship_partner_id": relationship_partner_id,
            "rival_id": rival_id,
            "intent": record["intent"],
            "success": bool(success),
            "status": str(status),
            "journal_visibility": "timeline",
            "journal_importance": "normal",
            "journal_title": "关系危机后的回应",
            "salience": 60 if success else 45,
            "semantic_tags": ("conflict", "betrayal"),
            "opportunity_type": record.get("opportunity_type"),
            "execution_strategy": record.get("execution_strategy"),
            "affordance_profile": record.get("affordance_profile"),
            "affordance_name": record.get("affordance_name"),
            "selection_mode": record.get("selection_mode"),
            "decision_source": record.get("decision_source"),
            "ai_recommended_intent": record.get(
                "ai_recommended_intent"
            ),
            "player_override": bool(record.get("player_override", False)),
            "interaction_id": record.get("interaction_id"),
            "completion_interaction_id": record.get(
                "completion_interaction_id"
            ),
            "debug_executor_test": bool(
                record.get("debug_executor_test", False)
            ),
            "betrayal_episode_id": episode_id,
            "crisis_case_id": record.get("crisis_case_id"),
            "crisis_action": record.get("crisis_action"),
        }
        if counterpart is not None:
            payload["counterpart_response"] = counterpart.get(
                "selected_response"
            )
            payload["counterpart_response_decision"] = counterpart
        publish(
            EventType.AUTONOMOUS_ACTION_RESOLVED,
            source="autonomous_behavior_runtime",
            event_id="autonomous-action:{}:{}:{}:{}".format(
                record["intent"],
                record["observer_id"],
                record["partner_id"],
                now_ticks,
            ),
            actor_id=record["observer_id"],
            target_id=target_id,
            observer_id=record["observer_id"],
            partner_id=relationship_partner_id,
            rival_id=rival_id,
            payload=payload,
        )
    except Exception:
        log_exception(
            "autonomous action outcome publish failed intent={}".format(
                record.get("intent")
            )
        )


def _watch_pending_interaction(record, alarm_owner):
    interaction_id = int(record["interaction_id"])

    def _on_timeout(_handle):
        pending = _PENDING_INTERACTIONS.pop(interaction_id, None)
        if pending is None:
            return
        _publish_action_outcome(
            pending,
            False,
            "interaction_outcome_timeout",
        )
        log(
            "autonomous action timed out observer={} partner={} intent={} interaction={}",
            pending["observer_id"],
            pending["partner_id"],
            pending["intent"],
            interaction_id,
        )

    try:
        record["timeout_handle"] = alarms.add_alarm(
            alarm_owner,
            date_and_time.create_time_span(
                minutes=settings.AUTONOMOUS_ACTION_OUTCOME_TIMEOUT_SIM_MINUTES
            ),
            _on_timeout,
            cross_zone=True,
        )
    except Exception:
        log_exception("autonomous action outcome timeout scheduling failed")


def _push_profiled_social(opportunity, definition):
    opportunity_context = dict(opportunity.context or {})
    source_event_id = (
        opportunity_context.get("source_betrayal_event_id")
        or opportunity.event_id
    )
    (
        observer_info,
        partner_info,
        observer,
        partner,
        together,
    ) = _live_pair(opportunity.observer_id, opportunity.partner_id)
    if not together:
        return (False, "pair_not_together", None)
    if bool(getattr(observer, "is_dying", False)):
        return (False, "observer_unavailable", None)
    if definition.intent in (
        BetrayalIntent.CONFRONT_PARTNER,
        BetrayalIntent.CONFRONT_RIVAL,
    ):
        try:
            from fgeh_cheatingharder_devotion_runtime import (
                evaluate_mean_interaction_permission,
            )

            permission = evaluate_mean_interaction_permission(
                observer_info,
                partner_info,
            )
            if permission is not None and not permission.allowed:
                return (
                    False,
                    "devotion_mean_target_blocked",
                    permission.to_data(),
                )
        except Exception:
            log_exception(
                "autonomous confrontation devotion permission failed"
            )
    try:
        from interactions.context import InteractionContext
        from interactions.context import QueueInsertStrategy
        from interactions.priority import Priority

        autonomy_context = InteractionContext(
            observer,
            InteractionContext.SOURCE_AUTONOMY,
            Priority.Low,
            insert_strategy=QueueInsertStrategy.LAST,
        )
        # A clinging hug is the visible result of a relationship-director
        # decision, usually made while EA's jealousy reaction still owns the
        # social queue.  Re-submitting it as low-priority autonomy lets that
        # reaction silently displace it even after push_super_affordance()
        # reports success.  Run only this selected attachment response as the
        # next high-priority scripted interaction; NEXT preserves the current
        # reaction and does not flush later player-directed work.
        cling_context = InteractionContext(
            observer,
            InteractionContext.SOURCE_SCRIPT,
            Priority.High,
            insert_strategy=QueueInsertStrategy.NEXT,
        )
        primary_context = (
            cling_context
            if definition.intent == BetrayalIntent.CLING_TO_PARTNER
            else autonomy_context
        )
        # The relationship director has already selected this registered
        # behavior.  EA uses SOURCE_SCRIPT for the same "decision made, now
        # execute a tested interaction" boundary in situations and scripted
        # reactions.  Keep ordinary super-affordance discovery autonomous,
        # but execute the explicitly configured fallback mixer as scripted so
        # its own autonomous-only gate cannot erase the director's decision.
        script_context = InteractionContext(
            observer,
            InteractionContext.SOURCE_SCRIPT,
            Priority.Low,
            insert_strategy=QueueInsertStrategy.LAST,
        )
        candidates = []
        seen = set()
        target_aops = tuple(partner.potential_interactions(primary_context))
        for aop in target_aops:
            affordance = getattr(aop, "affordance", None)
            if (
                affordance is None
                or affordance in seen
            ):
                continue
            seen.add(affordance)
            score = _profiled_affordance_score(
                definition.affordance_profile,
                affordance,
            )
            if score is not None:
                candidates.append((
                    score,
                    affordance,
                    None,
                    "super_affordance",
                    primary_context,
                ))
        scripted_target_aops = tuple(
            partner.potential_interactions(script_context)
        )
        candidates.extend(_fallback_mixer_candidates(
            observer,
            partner,
            script_context,
            definition.affordance_profile,
            scripted_target_aops,
        ))
        candidates.sort(key=lambda value: value[0], reverse=True)
        for (
            _score,
            affordance,
            candidate_aop,
            selection_mode,
            candidate_context,
        ) in candidates:
            try:
                if candidate_aop is None:
                    result = observer.push_super_affordance(
                        affordance,
                        partner,
                        candidate_context,
                    )
                    interaction = getattr(result, "interaction", None)
                else:
                    result = candidate_aop.test_and_execute(
                        candidate_context
                    )
                    interaction = getattr(result, "interaction", None)
                if (
                    result
                    and interaction is not None
                    and not getattr(interaction, "is_finishing", False)
                ):
                    record = {
                        "observer_id": observer_info.sim_id,
                        "partner_id": partner_info.sim_id,
                        "opportunity_type": definition.opportunity_type,
                        "intent": definition.intent,
                        "execution_strategy": (
                            definition.execution_strategy
                        ),
                        "affordance_profile": (
                            definition.affordance_profile.key
                        ),
                        "source_event_id": source_event_id,
                        "relationship_partner_id": opportunity_context.get(
                            "relationship_partner_id",
                            partner_info.sim_id,
                        ),
                        "target_role": opportunity_context.get(
                            "target_role",
                            "partner",
                        ),
                        "rival_id": opportunity_context.get("rival_id"),
                        "debug_executor_test": bool(
                            opportunity_context.get(
                                "debug_executor_test",
                                False,
                            )
                        ),
                        "betrayal_episode_id": opportunity_context.get(
                            "betrayal_episode_id"
                        ),
                        "decision_source": opportunity_context.get(
                            "decision_source"
                        ),
                        "ai_recommended_intent": opportunity_context.get(
                            "ai_recommended_intent"
                        ),
                        "player_override": bool(
                            opportunity_context.get(
                                "player_override",
                                False,
                            )
                        ),
                        "crisis_case_id": opportunity_context.get(
                            "crisis_case_id"
                        ),
                        "crisis_action": opportunity_context.get(
                            "crisis_action"
                        ),
                        "interaction_id": int(interaction.id),
                        "affordance_name": _affordance_name(affordance),
                        "selection_mode": selection_mode,
                    }
                    _PENDING_INTERACTIONS[int(interaction.id)] = record
                    if record.get("betrayal_episode_id"):
                        BETRAYAL_REACTION_EPISODES.mark(
                            record["betrayal_episode_id"],
                            BetrayalEpisodeStatus.PENDING,
                        )
                    _COOLDOWN_STARTED_AT[(
                        observer_info.sim_id,
                        partner_info.sim_id,
                        definition.intent,
                    )] = _sim_now_ticks()
                    _watch_pending_interaction(record, observer)
                    return (True, "interaction_queued", record)
            except Exception:
                continue
        return (
            False,
            definition.no_candidate_status,
            {
                "candidate_count": len(candidates),
                "affordance_profile": definition.affordance_profile.key,
            },
        )
    except Exception:
        log_exception(
            "profiled social push failed intent={} observer={} partner={}".format(
                definition.intent,
                opportunity.observer_id,
                opportunity.partner_id,
            )
        )
        return (False, "interaction_push_failed", None)


def _push_seek_reassurance(opportunity):
    """Compatibility wrapper retained for existing callers and logs."""
    definition = _BEHAVIOR_REGISTRY.require(
        OPPORTUNITY_BETRAYAL_RESPONSE,
        BetrayalIntent.SEEK_REASSURANCE,
    )
    return _push_profiled_social(opportunity, definition)


def _schedule_profiled_social(
    opportunity,
    definition,
    retry_count=0,
):
    opportunity_context = dict(opportunity.context or {})
    key = (
        int(opportunity.observer_id),
        int(opportunity.partner_id),
        definition.intent,
    )
    token = _ACTION_TOKENS.get(key, 0) + 1
    _ACTION_TOKENS[key] = token
    (
        observer_info,
        _partner_info,
        observer,
        _partner,
        _together,
    ) = _live_pair(opportunity.observer_id, opportunity.partner_id)
    if observer_info is None:
        episode_id = opportunity_context.get("betrayal_episode_id")
        if episode_id:
            BETRAYAL_REACTION_EPISODES.resolve(
                episode_id,
                "observer_missing",
                success=False,
            )
        return None
    alarm_owner = observer or observer_info
    delay = (
        settings.AUTONOMOUS_ACTION_FIRST_ATTEMPT_SIM_MINUTES
        if retry_count == 0
        else settings.AUTONOMOUS_ACTION_RETRY_SIM_MINUTES
    )

    def _on_attempt(_handle):
        if _ACTION_TOKENS.get(key) != token:
            return
        _ACTION_ALARMS.pop(key, None)
        accepted, status, details = _push_profiled_social(
            opportunity,
            definition,
        )
        log(
            "autonomous action attempt observer={} partner={} intent={} retry={} accepted={} status={} details={}",
            opportunity.observer_id,
            opportunity.partner_id,
            definition.intent,
            retry_count,
            accepted,
            status,
            details,
        )
        if accepted:
            _ACTION_TOKENS.pop(key, None)
            return
        if (
            retry_count < settings.AUTONOMOUS_ACTION_MAX_RETRIES
            and status in definition.retryable_statuses
        ):
            _schedule_profiled_social(
                opportunity,
                definition,
                retry_count=retry_count + 1,
            )
            return
        _ACTION_TOKENS.pop(key, None)
        _publish_action_outcome(
            {
                "observer_id": opportunity.observer_id,
                "partner_id": opportunity.partner_id,
                "opportunity_type": definition.opportunity_type,
                "intent": definition.intent,
                "execution_strategy": definition.execution_strategy,
                "affordance_profile": definition.affordance_profile.key,
                "source_event_id": (
                    opportunity_context.get("source_betrayal_event_id")
                    or opportunity.event_id
                ),
                "relationship_partner_id": opportunity_context.get(
                    "relationship_partner_id",
                    opportunity.partner_id,
                ),
                "target_role": opportunity_context.get(
                    "target_role",
                    "partner",
                ),
                "rival_id": opportunity_context.get("rival_id"),
                "debug_executor_test": bool(
                    opportunity_context.get(
                        "debug_executor_test",
                        False,
                    )
                ),
                "betrayal_episode_id": opportunity_context.get(
                    "betrayal_episode_id"
                ),
                "crisis_case_id": opportunity_context.get(
                    "crisis_case_id"
                ),
                "crisis_action": opportunity_context.get(
                    "crisis_action"
                ),
                "interaction_id": None,
                "affordance_name": None,
            },
            False,
            status,
        )

    try:
        handle = alarms.add_alarm(
            alarm_owner,
            date_and_time.create_time_span(minutes=delay),
            _on_attempt,
            cross_zone=True,
        )
        _ACTION_ALARMS[key] = handle
        log(
            "autonomous action scheduled observer={} partner={} intent={} retry={} delay={}",
            opportunity.observer_id,
            opportunity.partner_id,
            definition.intent,
            retry_count,
            delay,
        )
        return handle
    except Exception:
        log_exception(
            "profiled social alarm scheduling failed intent={}".format(
                definition.intent
            )
        )
        return None


def schedule_seek_reassurance(
    opportunity,
    _admission=None,
    retry_count=0,
):
    definition = _BEHAVIOR_REGISTRY.require(
        OPPORTUNITY_BETRAYAL_RESPONSE,
        BetrayalIntent.SEEK_REASSURANCE,
    )
    return _schedule_profiled_social(
        opportunity,
        definition,
        retry_count=retry_count,
    )


def schedule_crisis_seek_reassurance(
    opportunity,
    _admission=None,
    retry_count=0,
):
    definition = _BEHAVIOR_REGISTRY.require(
        OPPORTUNITY_RELATIONSHIP_CRISIS,
        CRISIS_INTENT_SEEK_REASSURANCE,
    )
    return _schedule_profiled_social(
        opportunity,
        definition,
        retry_count=retry_count,
    )


def schedule_relationship_crisis_reassurance(
    observer_sim_info,
    partner_sim_info,
    crisis_case_id,
    source_transaction_id=None,
):
    """Public adapter from the generic five-D director to one safe social."""
    opportunity = MemoryOpportunity(
        OPPORTUNITY_RELATIONSHIP_CRISIS,
        observer_sim_info.sim_id,
        partner_sim_info.sim_id,
        reason="relationship_crisis",
        event_id=(
            source_transaction_id
            or "relationship-crisis:{}".format(crisis_case_id)
        ),
        context={
            "execution_enabled": True,
            "selected_intent": CRISIS_INTENT_SEEK_REASSURANCE,
            "relationship_partner_id": partner_sim_info.sim_id,
            "crisis_case_id": str(crisis_case_id),
            "crisis_action": CRISIS_INTENT_SEEK_REASSURANCE,
        },
    )
    return schedule_crisis_seek_reassurance(opportunity)


def schedule_cling_to_partner(
    opportunity,
    _admission=None,
    retry_count=0,
):
    definition = _BEHAVIOR_REGISTRY.require(
        OPPORTUNITY_BETRAYAL_RESPONSE,
        BetrayalIntent.CLING_TO_PARTNER,
    )
    return _schedule_profiled_social(
        opportunity,
        definition,
        retry_count=retry_count,
    )


def schedule_confront_partner(
    opportunity,
    _admission=None,
    retry_count=0,
):
    definition = _BEHAVIOR_REGISTRY.require(
        OPPORTUNITY_BETRAYAL_RESPONSE,
        BetrayalIntent.CONFRONT_PARTNER,
    )
    return _schedule_profiled_social(
        opportunity,
        definition,
        retry_count=retry_count,
    )


def schedule_confront_rival(
    opportunity,
    _admission=None,
    retry_count=0,
):
    definition = _BEHAVIOR_REGISTRY.require(
        OPPORTUNITY_BETRAYAL_RESPONSE,
        BetrayalIntent.CONFRONT_RIVAL,
    )
    return _schedule_profiled_social(
        opportunity,
        definition,
        retry_count=retry_count,
    )


def schedule_breakup_negotiation(opportunity, _admission=None):
    """Bridge a ledger-selected breakup into the existing negotiation state machine.

    This adapter deliberately does not remove relationship bits itself.  The
    established autonomous-breakup runtime owns recipient response, proposer
    follow-up, authorization, and the final EA interaction.
    """
    opportunity_context = dict(opportunity.context or {})
    relationship_partner_id = int(opportunity_context.get(
        "relationship_partner_id",
        opportunity.partner_id,
    ))
    key = (
        int(opportunity.observer_id),
        relationship_partner_id,
        BetrayalIntent.BREAK_UP,
    )
    token = _ACTION_TOKENS.get(key, 0) + 1
    _ACTION_TOKENS[key] = token
    (
        observer_info,
        partner_info,
        observer,
        _partner,
        _together,
    ) = _live_pair(opportunity.observer_id, relationship_partner_id)
    if observer_info is None or partner_info is None:
        _ACTION_TOKENS.pop(key, None)
        episode_id = opportunity_context.get("betrayal_episode_id")
        if episode_id:
            BETRAYAL_REACTION_EPISODES.resolve(
                episode_id,
                "breakup_pair_missing",
                success=False,
            )
        return None
    alarm_owner = observer or observer_info

    def _on_attempt(_handle):
        if _ACTION_TOKENS.get(key) != token:
            return
        _ACTION_ALARMS.pop(key, None)
        _ACTION_TOKENS.pop(key, None)
        try:
            from fgeh_cheatingharder_autonomous_breakup import (
                push_breakup_proposal,
            )

            episode_id = opportunity_context.get("betrayal_episode_id")
            if episode_id:
                BETRAYAL_REACTION_EPISODES.mark(
                    episode_id,
                    BetrayalEpisodeStatus.NEGOTIATING,
                )

            decision = {
                "selected": BetrayalIntent.BREAK_UP,
                "roll": opportunity_context.get("decision_roll"),
                "candidates": tuple(
                    opportunity_context.get("behavior_candidates", ()) or ()
                ),
                "state_before": dict(
                    opportunity_context.get("state_before", {}) or {}
                ),
                "state_after": dict(
                    opportunity_context.get("state_after", {}) or {}
                ),
            }
            intent = BehaviorIntent(
                BetrayalIntent.BREAK_UP,
                int(opportunity.observer_id),
                relationship_partner_id,
                opportunity.reason,
                context={
                    "decision": decision,
                    "source_event_id": (
                        opportunity_context.get("source_betrayal_event_id")
                        or opportunity.event_id
                    ),
                },
            )
            result = push_breakup_proposal(
                observer_info,
                partner_info,
                intent,
            )
            log(
                "autonomous breakup bridge resolved proposer={} recipient={} "
                "accepted={} status={} details={}",
                opportunity.observer_id,
                relationship_partner_id,
                result.accepted,
                result.status,
                result.details,
            )
            if episode_id:
                BETRAYAL_REACTION_EPISODES.resolve(
                    episode_id,
                    "breakup_{}".format(result.status),
                    success=result.accepted,
                )
        except Exception:
            episode_id = opportunity_context.get("betrayal_episode_id")
            if episode_id:
                BETRAYAL_REACTION_EPISODES.resolve(
                    episode_id,
                    "breakup_bridge_exception",
                    success=False,
                )
            log_exception(
                "autonomous breakup bridge failed proposer={} recipient={}"
                .format(
                    opportunity.observer_id,
                    relationship_partner_id,
                )
            )

    try:
        delay = settings.AUTONOMOUS_ACTION_FIRST_ATTEMPT_SIM_MINUTES
        handle = alarms.add_alarm(
            alarm_owner,
            date_and_time.create_time_span(minutes=delay),
            _on_attempt,
            cross_zone=True,
        )
        _ACTION_ALARMS[key] = handle
        log(
            "autonomous breakup bridge scheduled proposer={} recipient={} "
            "delay={} source_event={}",
            opportunity.observer_id,
            relationship_partner_id,
            delay,
            (
                opportunity_context.get("source_betrayal_event_id")
                or opportunity.event_id
            ),
        )
        return handle
    except Exception:
        _ACTION_TOKENS.pop(key, None)
        episode_id = opportunity_context.get("betrayal_episode_id")
        if episode_id:
            BETRAYAL_REACTION_EPISODES.resolve(
                episode_id,
                "breakup_scheduling_exception",
                success=False,
            )
        log_exception(
            "autonomous breakup bridge scheduling failed proposer={} "
            "recipient={}".format(
                opportunity.observer_id,
                relationship_partner_id,
            )
        )
        return None


def _completed_interaction_pair(interaction):
    try:
        from fgeh_cheatingharder_relationship import get_sim_info

        actor_info = get_sim_info(getattr(interaction, "sim", None))
        target_info = get_sim_info(getattr(interaction, "target", None))
        if actor_info is None or target_info is None:
            return (None, None)
        return (int(actor_info.sim_id), int(target_info.sim_id))
    except Exception:
        return (None, None)


def _semantic_child_record(interaction, success):
    """Match EA child mixers spawned by a queued relationship action."""
    if not success:
        return (None, None)
    name = "{} {}".format(
        _affordance_name(getattr(interaction, "affordance", None)),
        getattr(interaction, "__class__", type(interaction)).__name__,
    ).lower()
    if not any(marker in name for marker in ("hug", "embrace")):
        return (None, None)
    actor_id, target_id = _completed_interaction_pair(interaction)
    if actor_id is None or target_id is None:
        return (None, None)
    for queued_id, pending in tuple(_PENDING_INTERACTIONS.items()):
        if (
            pending.get("intent") == BetrayalIntent.CLING_TO_PARTNER
            and int(pending.get("observer_id")) == actor_id
            and int(pending.get("partner_id")) == target_id
        ):
            return (queued_id, pending)
    return (None, None)


def observe_autonomous_interaction_outcome(interaction, success):
    """Join EA's final interaction outcome to the queued action record.

    Some quick socials are parent super interactions whose visible completion
    is reported by a generated mixer with a different interaction id.  In that
    case, pair + intent + semantic affordance is the stable correlation key.
    """
    interaction_id = getattr(interaction, "id", None)
    if interaction_id is None:
        return False
    record = _PENDING_INTERACTIONS.pop(int(interaction_id), None)
    queued_interaction_id = int(interaction_id)
    if record is None:
        queued_interaction_id, record = _semantic_child_record(
            interaction,
            success,
        )
        if record is None:
            return False
        _PENDING_INTERACTIONS.pop(queued_interaction_id, None)
        record["completion_interaction_id"] = int(interaction_id)
    timeout_handle = record.pop("timeout_handle", None)
    if timeout_handle is not None:
        try:
            alarms.cancel_alarm(timeout_handle)
        except Exception:
            pass
    status = "interaction_succeeded" if success else "interaction_failed"
    _publish_action_outcome(record, success, status)
    log(
        "autonomous action resolved observer={} partner={} intent={} "
        "success={} status={} queued_interaction={} "
        "completion_interaction={}",
        record["observer_id"],
        record["partner_id"],
        record["intent"],
        bool(success),
        status,
        queued_interaction_id,
        interaction_id,
    )
    return True


def reset_autonomous_behavior_runtime():
    for handle in tuple(_ACTION_ALARMS.values()):
        try:
            alarms.cancel_alarm(handle)
        except Exception:
            pass
    for record in tuple(_PENDING_INTERACTIONS.values()):
        handle = record.get("timeout_handle")
        if handle is not None:
            try:
                alarms.cancel_alarm(handle)
            except Exception:
                pass
    _ACTION_ALARMS.clear()
    _ACTION_TOKENS.clear()
    _PENDING_INTERACTIONS.clear()
    _COOLDOWN_STARTED_AT.clear()
    reset_betrayal_reaction_episodes()
    try:
        from fgeh_cheatingharder_betrayal_choice import (
            reset_betrayal_choice_runtime,
        )

        reset_betrayal_choice_runtime()
    except Exception:
        log_exception("betrayal choice runtime reset failed")


def get_autonomous_behavior_status(observer_id=None, partner_id=None):
    observer_id = None if observer_id is None else int(observer_id)
    partner_id = None if partner_id is None else int(partner_id)

    def matches(record):
        return (
            (observer_id is None or record.get("observer_id") == observer_id)
            and (
                partner_id is None
                or record.get("partner_id") == partner_id
            )
        )

    scheduled = tuple(
        {
            "observer_id": key[0],
            "partner_id": key[1],
            "intent": key[2],
        }
        for key in _ACTION_ALARMS
        if (
            (observer_id is None or key[0] == observer_id)
            and (partner_id is None or key[1] == partner_id)
        )
    )
    pending = tuple(
        {
            key: value
            for key, value in record.items()
            if key != "timeout_handle"
        }
        for record in _PENDING_INTERACTIONS.values()
        if matches(record)
    )
    return {
        "registered_actions": registered_autonomous_actions(),
        "registered_definitions": (
            registered_autonomous_behavior_definitions()
        ),
        "scheduled": scheduled,
        "pending_interactions": pending,
        "betrayal_episodes": BETRAYAL_REACTION_EPISODES.status(
            observer_id=observer_id,
            partner_id=partner_id,
        ),
    }


SEEK_REASSURANCE_BEHAVIOR = AutonomousBehaviorDefinition(
    OPPORTUNITY_BETRAYAL_RESPONSE,
    BetrayalIntent.SEEK_REASSURANCE,
    BehaviorExecutionStrategy.PROFILED_SOCIAL,
    affordance_profile=_REASSURANCE_PROFILE,
    cooldown_minutes=settings.SEEK_REASSURANCE_COOLDOWN_SIM_MINUTES,
    cooldown_timestamp_key="last_seek_reassurance_at",
    no_candidate_status="no_safe_reassurance_affordance",
)

CLING_TO_PARTNER_BEHAVIOR = AutonomousBehaviorDefinition(
    OPPORTUNITY_BETRAYAL_RESPONSE,
    BetrayalIntent.CLING_TO_PARTNER,
    BehaviorExecutionStrategy.PROFILED_SOCIAL,
    affordance_profile=_CLING_TO_PARTNER_PROFILE,
    cooldown_minutes=settings.CLING_TO_PARTNER_COOLDOWN_SIM_MINUTES,
    cooldown_timestamp_key="last_cling_to_partner_at",
    no_candidate_status="no_safe_cling_to_partner_affordance",
)

CONFRONT_PARTNER_BEHAVIOR = AutonomousBehaviorDefinition(
    OPPORTUNITY_BETRAYAL_RESPONSE,
    BetrayalIntent.CONFRONT_PARTNER,
    BehaviorExecutionStrategy.PROFILED_SOCIAL,
    affordance_profile=_CONFRONT_PARTNER_PROFILE,
    cooldown_minutes=settings.CONFRONT_PARTNER_COOLDOWN_SIM_MINUTES,
    cooldown_timestamp_key="last_confront_partner_at",
    no_candidate_status="no_safe_confront_partner_affordance",
)

CONFRONT_RIVAL_BEHAVIOR = AutonomousBehaviorDefinition(
    OPPORTUNITY_BETRAYAL_RESPONSE,
    BetrayalIntent.CONFRONT_RIVAL,
    BehaviorExecutionStrategy.PROFILED_SOCIAL,
    affordance_profile=_CONFRONT_RIVAL_PROFILE,
    cooldown_minutes=settings.CONFRONT_RIVAL_COOLDOWN_SIM_MINUTES,
    cooldown_timestamp_key="last_confront_rival_at",
    no_candidate_status="no_safe_confront_rival_affordance",
)

BREAKUP_NEGOTIATION_BEHAVIOR = AutonomousBehaviorDefinition(
    OPPORTUNITY_BETRAYAL_RESPONSE,
    BetrayalIntent.BREAK_UP,
    BehaviorExecutionStrategy.CUSTOM_HANDLER,
)

CRISIS_SEEK_REASSURANCE_BEHAVIOR = AutonomousBehaviorDefinition(
    OPPORTUNITY_RELATIONSHIP_CRISIS,
    CRISIS_INTENT_SEEK_REASSURANCE,
    BehaviorExecutionStrategy.PROFILED_SOCIAL,
    affordance_profile=_REASSURANCE_PROFILE,
    cooldown_minutes=settings.RELATIONSHIP_CRISIS_ACTION_COOLDOWN_SIM_MINUTES,
    no_candidate_status="no_safe_crisis_reassurance_affordance",
)

register_autonomous_action(
    OPPORTUNITY_BETRAYAL_RESPONSE,
    BetrayalIntent.SEEK_REASSURANCE,
    schedule_seek_reassurance,
    definition=SEEK_REASSURANCE_BEHAVIOR,
)
register_autonomous_action(
    OPPORTUNITY_BETRAYAL_RESPONSE,
    BetrayalIntent.CLING_TO_PARTNER,
    schedule_cling_to_partner,
    definition=CLING_TO_PARTNER_BEHAVIOR,
)
register_autonomous_action(
    OPPORTUNITY_BETRAYAL_RESPONSE,
    BetrayalIntent.CONFRONT_PARTNER,
    schedule_confront_partner,
    definition=CONFRONT_PARTNER_BEHAVIOR,
)
register_autonomous_action(
    OPPORTUNITY_BETRAYAL_RESPONSE,
    BetrayalIntent.CONFRONT_RIVAL,
    schedule_confront_rival,
    definition=CONFRONT_RIVAL_BEHAVIOR,
)
register_autonomous_action(
    OPPORTUNITY_BETRAYAL_RESPONSE,
    BetrayalIntent.BREAK_UP,
    schedule_breakup_negotiation,
    definition=BREAKUP_NEGOTIATION_BEHAVIOR,
)
register_autonomous_action(
    OPPORTUNITY_RELATIONSHIP_CRISIS,
    CRISIS_INTENT_SEEK_REASSURANCE,
    schedule_crisis_seek_reassurance,
    definition=CRISIS_SEEK_REASSURANCE_BEHAVIOR,
)

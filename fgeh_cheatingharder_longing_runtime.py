"""Active-lot runtime for permanent-devotion longing.

The ledger owns durable timestamps.  This module owns only zone alarms, Buff
projection and low-priority interaction pushing.
"""

import alarms
import date_and_time
import services
import sims4.resources

import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_domain import (
    BehaviorOpportunity,
    EventType,
    ExecutionResult,
    OpportunityType,
)
from fgeh_cheatingharder_emotion_expressions import (
    ExpressionPhase,
    ExpressionType,
    select_expression,
)
from fgeh_cheatingharder_longing import compute_longing_intensity


_LONGING_ALARMS = {}
_ACTIVE_LONGING_EXPRESSIONS = {}
_ACTIVE_REUNION_EXPRESSIONS = {}

_AFFECTION_EXCLUSIONS = (
    "argue",
    "breakup",
    "break_up",
    "divorce",
    "fight",
    "insult",
    "mean",
    "mock",
    "propose",
    "shout",
    "try_for_baby",
    "woohoo",
    "yell",
    "sex",
)

_AFFECTION_WEIGHTS = (
    ("embrace", 90),
    ("hug", 85),
    ("holdhand", 80),
    ("hold_hand", 80),
    ("kisscheek", 75),
    ("kiss_cheek", 75),
    ("expressfondness", 70),
    ("express_fondness", 70),
    ("caress", 65),
    ("cuddle", 65),
    ("kisshand", 60),
    ("complimentappearance", 50),
    ("compliment_appearance", 50),
    ("kiss", 40),
    ("flirt", 30),
    ("chat", 20),
    ("talk", 15),
    ("friendly", 10),
)


def _sim_now_ticks():
    try:
        now = services.time_service().sim_now
        absolute_ticks = getattr(now, "absolute_ticks", None)
        return absolute_ticks() if callable(absolute_ticks) else int(now)
    except Exception:
        return None


def _elapsed_minutes(now_ticks, previous_ticks):
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


def longing_intensity(elapsed_minutes):
    """Return 0..100 after the configured threshold (pure numeric boundary)."""
    return compute_longing_intensity(
        elapsed_minutes,
        settings.DEVOTION_LONGING_START_SIM_MINUTES,
        settings.DEVOTION_LONGING_FULL_INTENSITY_SIM_MINUTES,
    )


def _summary_and_bond(owner_id, beloved_id):
    try:
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        store = get_memory_service().store
        bond = store.get_devotion_bond(owner_id)
        if bond is None or bond.beloved_id != int(beloved_id):
            return (None, None)
        return (store.get_summary(owner_id, beloved_id), bond)
    except Exception:
        log_exception(
            "longing memory lookup failed owner={} beloved={}".format(
                owner_id,
                beloved_id,
            )
        )
        return (None, None)


def _last_contact_ticks(summary, bond):
    timestamps = {} if summary is None else summary.timestamps
    for key in (
        "last_meaningful_devotion_contact_at",
        "last_positive_romantic_contact_at",
        "devotion_established_at",
    ):
        value = timestamps.get(key)
        if value is not None:
            return value
    return getattr(bond, "established_at", None)


def _live_pair(owner_id, beloved_id):
    try:
        manager = services.sim_info_manager()
        owner = manager.get(int(owner_id))
        beloved = manager.get(int(beloved_id))
        if owner is None or beloved is None:
            return (owner, beloved, None, None, False)
        owner_sim = owner.get_sim_instance()
        beloved_sim = beloved.get_sim_instance()
        active_zone_id = getattr(services.current_zone(), "id", None)
        together = (
            owner_sim is not None
            and beloved_sim is not None
            and getattr(owner_sim, "zone_id", None) == active_zone_id
            and getattr(beloved_sim, "zone_id", None) == active_zone_id
        )
        return (owner, beloved, owner_sim, beloved_sim, together)
    except Exception:
        return (None, None, None, None, False)


def _buff_tuning(expression_type):
    instance_id = settings.DEVOTION_EXPRESSION_BUFF_INSTANCE_IDS.get(
        str(expression_type)
    )
    if instance_id is None:
        return None
    try:
        manager = services.get_instance_manager(sims4.resources.Types.BUFF)
        return manager.get(instance_id)
    except Exception:
        log_exception(
            "devotion expression Buff tuning lookup failed type={}".format(
                expression_type
            )
        )
        return None


def _expression_buff_types(include_reunion=True):
    expression_types = [
        ExpressionType.GENTLE_LONGING,
        ExpressionType.ANXIOUS_LONGING,
    ]
    if include_reunion:
        expression_types.append(ExpressionType.REUNION_RELIEF)
    return tuple(expression_types)


def _remove_expression_buffs(owner_info, include_reunion=True):
    if owner_info is None:
        return
    for expression_type in _expression_buff_types(
        include_reunion=include_reunion
    ):
        buff = _buff_tuning(expression_type)
        if buff is None:
            continue
        try:
            if owner_info.has_buff(buff):
                owner_info.remove_buff_by_type(buff)
        except Exception:
            log_exception(
                "devotion expression Buff removal failed owner={} type={}".format(
                    getattr(owner_info, "sim_id", None),
                    expression_type,
                )
            )


def _ensure_expression_buff(owner_info, expression_type):
    if expression_type == ExpressionType.NONE:
        return True
    buff = _buff_tuning(expression_type)
    if owner_info is None or buff is None:
        return False
    try:
        if not owner_info.has_buff(buff):
            return owner_info.add_buff(buff) is not None
        return True
    except Exception:
        log_exception(
            "devotion expression Buff add failed owner={} type={}".format(
                getattr(owner_info, "sim_id", None),
                expression_type,
            )
        )
        return False


def _expiry_ticks(duration_minutes):
    now_ticks = _sim_now_ticks()
    if now_ticks is None:
        return None
    try:
        return int(now_ticks) + int(
            date_and_time.create_time_span(
                minutes=max(1.0, float(duration_minutes))
            ).in_ticks()
        )
    except Exception:
        return None


def _remaining_expression_minutes(record):
    if not record:
        return None
    return _elapsed_minutes(record.get("expires_at"), _sim_now_ticks())


def _directed_state(owner_info, beloved_info):
    try:
        from fgeh_cheatingharder_state import get_directed_state

        return get_directed_state(owner_info, beloved_info)
    except Exception:
        log_exception(
            "devotion expression directed-state lookup failed owner={} beloved={}".format(
                getattr(owner_info, "sim_id", None),
                getattr(beloved_info, "sim_id", None),
            )
        )
        return None


def _has_positive_romance(owner_info, beloved_info):
    try:
        from relationships.relationship_track import RelationshipTrack

        score = services.relationship_service().get_relationship_score(
            owner_info.sim_id,
            beloved_info.sim_id,
            track=RelationshipTrack.ROMANCE_TRACK,
        )
        return float(score) > 0.0
    except Exception:
        return False


def _expression_context(owner_info, beloved_info, context=None):
    values = dict(context or {})
    values["has_positive_romance"] = _has_positive_romance(
        owner_info,
        beloved_info,
    )
    return values


def _choose_longing_expression(owner_info, beloved_info, context):
    key = (owner_info.sim_id, beloved_info.sim_id)
    state = _directed_state(owner_info, beloved_info)
    if state is None:
        return None
    context = _expression_context(owner_info, beloved_info, context)
    selected, decision = select_expression(
        ExpressionPhase.LONGING,
        state,
        context,
    )
    _remove_expression_buffs(owner_info, include_reunion=False)
    if selected is None:
        _ACTIVE_LONGING_EXPRESSIONS.pop(key, None)
        return None
    record = {
        "expression_type": selected.expression_type,
        "started_at": _sim_now_ticks(),
        "expires_at": _expiry_ticks(selected.duration_minutes),
        "duration_minutes": selected.duration_minutes,
        "longing_intensity": float(
            context.get("longing_intensity", 0.0)
        ),
        "decision": decision,
    }
    _ACTIVE_LONGING_EXPRESSIONS[key] = record
    _ensure_expression_buff(owner_info, selected.expression_type)
    log(
        "devotion emotion selected phase=longing owner={} beloved={} type={} duration={:.1f} roll={} total={} candidates={}",
        owner_info.sim_id,
        beloved_info.sim_id,
        selected.expression_type,
        selected.duration_minutes,
        decision.get("roll"),
        decision.get("total"),
        tuple(
            (
                item.get("expression_type"),
                item.get("score"),
                item.get("eligible"),
                item.get("blockers"),
            )
            for item in decision.get("candidates", ())
        ),
    )
    return record


def _maintain_longing_expression(owner_info, beloved_info, context):
    key = (owner_info.sim_id, beloved_info.sim_id)
    record = _ACTIVE_LONGING_EXPRESSIONS.get(key)
    now_ticks = _sim_now_ticks()
    if (
        record is not None
        and record.get("expires_at") is not None
        and now_ticks is not None
        and int(now_ticks) < int(record["expires_at"])
    ):
        _ensure_expression_buff(
            owner_info,
            record.get("expression_type"),
        )
        return record
    _ACTIVE_LONGING_EXPRESSIONS.pop(key, None)
    _remove_expression_buffs(owner_info, include_reunion=False)
    return _choose_longing_expression(owner_info, beloved_info, context)


def _maintain_reunion_expression(owner_info, beloved_info):
    key = (owner_info.sim_id, beloved_info.sim_id)
    record = _ACTIVE_REUNION_EXPRESSIONS.get(key)
    buff = _buff_tuning(ExpressionType.REUNION_RELIEF)
    now_ticks = _sim_now_ticks()
    if record is None:
        # A saved Buff without its zone-bound runtime expiry must not become
        # permanent after loading a different zone.
        if buff is not None:
            try:
                if owner_info.has_buff(buff):
                    owner_info.remove_buff_by_type(buff)
            except Exception:
                pass
        return
    if (
        record.get("expires_at") is not None
        and now_ticks is not None
        and int(now_ticks) >= int(record["expires_at"])
    ):
        _ACTIVE_REUNION_EXPRESSIONS.pop(key, None)
        if buff is not None:
            try:
                owner_info.remove_buff_by_type(buff)
            except Exception:
                pass
        log(
            "devotion reunion expression expired owner={} beloved={}",
            owner_info.sim_id,
            beloved_info.sim_id,
        )
        return
    _ensure_expression_buff(owner_info, ExpressionType.REUNION_RELIEF)


def build_longing_decision_context(owner_info, beloved_info):
    owner_id = getattr(owner_info, "sim_id", None)
    beloved_id = getattr(beloved_info, "sim_id", None)
    summary, bond = _summary_and_bond(owner_id, beloved_id)
    now_ticks = _sim_now_ticks()
    last_contact = (
        None if bond is None else _last_contact_ticks(summary, bond)
    )
    elapsed = _elapsed_minutes(now_ticks, last_contact)
    last_seek = (
        None
        if summary is None
        else summary.timestamps.get("last_devotion_seek_at")
    )
    seek_elapsed = _elapsed_minutes(now_ticks, last_seek)
    _, _, owner_sim, _, together = _live_pair(owner_id, beloved_id)
    return {
        "is_only_beloved": bond is not None,
        "both_on_active_zone": together,
        "owner_can_autonomously_seek": (
            owner_sim is not None
            and not bool(getattr(owner_sim, "is_dying", False))
        ),
        "longing_elapsed_minutes": elapsed,
        "longing_intensity": longing_intensity(elapsed),
        "has_positive_romance": _has_positive_romance(
            owner_info,
            beloved_info,
        ),
        "seek_cooldown": (
            seek_elapsed is not None
            and seek_elapsed
            < float(settings.DEVOTION_SEEK_COOLDOWN_SIM_MINUTES)
        ),
    }


def on_longing_started(owner_info, beloved_info):
    context = build_longing_decision_context(owner_info, beloved_info)
    _maintain_longing_expression(owner_info, beloved_info, context)
    log(
        "devotion longing expression evaluated owner={} beloved={}",
        getattr(owner_info, "sim_id", None),
        getattr(beloved_info, "sim_id", None),
    )


def on_meaningful_contact(owner_info, beloved_info):
    key = (owner_info.sim_id, beloved_info.sim_id)
    previous = _ACTIVE_LONGING_EXPRESSIONS.pop(key, None)
    _remove_expression_buffs(owner_info, include_reunion=False)
    if previous is not None:
        state = _directed_state(owner_info, beloved_info)
        context = _expression_context(
            owner_info,
            beloved_info,
            {
                "was_longing": True,
                "longing_intensity": previous.get(
                    "longing_intensity",
                    0.0,
                ),
            },
        )
        selected, decision = select_expression(
            ExpressionPhase.REUNION,
            state,
            context,
        )
        _ACTIVE_REUNION_EXPRESSIONS.pop(key, None)
        _remove_expression_buffs(owner_info, include_reunion=True)
        if (
            selected is not None
            and selected.expression_type
            == ExpressionType.REUNION_RELIEF
        ):
            _ensure_expression_buff(
                owner_info,
                ExpressionType.REUNION_RELIEF,
            )
            _ACTIVE_REUNION_EXPRESSIONS[key] = {
                "expression_type": selected.expression_type,
                "started_at": _sim_now_ticks(),
                "expires_at": _expiry_ticks(
                    selected.duration_minutes
                ),
                "duration_minutes": selected.duration_minutes,
                "decision": decision,
            }
        log(
            "devotion emotion selected phase=reunion owner={} beloved={} type={} roll={} total={}",
            owner_info.sim_id,
            beloved_info.sim_id,
            None if selected is None else selected.expression_type,
            decision.get("roll"),
            decision.get("total"),
        )
    log(
        "devotion longing relieved owner={} beloved={}",
        getattr(owner_info, "sim_id", None),
        getattr(beloved_info, "sim_id", None),
    )


def get_longing_status(owner_info, beloved_info):
    context = build_longing_decision_context(owner_info, beloved_info)
    key = (owner_info.sim_id, beloved_info.sim_id)
    longing_record = _ACTIVE_LONGING_EXPRESSIONS.get(key)
    reunion_record = _ACTIVE_REUNION_EXPRESSIONS.get(key)
    buff_tunings = {
        expression_type: _buff_tuning(expression_type)
        for expression_type in _expression_buff_types()
    }
    summary, _ = _summary_and_bond(
        owner_info.sim_id,
        beloved_info.sim_id,
    )
    context.update(
        {
            "owner_id": owner_info.sim_id,
            "beloved_id": beloved_info.sim_id,
            "buff_tuning_found": all(
                buff is not None for buff in buff_tunings.values()
            ),
            "buff_tunings": {
                key: value is not None
                for key, value in buff_tunings.items()
            },
            "owner_has_longing_buff": (
                any(
                    buff is not None and owner_info.has_buff(buff)
                    for expression_type, buff in buff_tunings.items()
                    if expression_type != ExpressionType.REUNION_RELIEF
                )
            ),
            "active_longing_expression": (
                None
                if longing_record is None
                else longing_record.get("expression_type")
            ),
            "active_longing_expression_minutes": (
                _remaining_expression_minutes(longing_record)
            ),
            "active_reunion_expression": (
                None
                if reunion_record is None
                else reunion_record.get("expression_type")
            ),
            "active_reunion_expression_minutes": (
                _remaining_expression_minutes(reunion_record)
            ),
            "last_expression_decision": (
                None
                if longing_record is None
                else longing_record.get("decision")
            ),
            "summary_longing_flag": (
                False
                if summary is None
                else summary.flags.get(
                    "is_longing_for_only_beloved",
                    False,
                )
            ),
        }
    )
    return context


def _publish_longing_started(owner, beloved, elapsed, intensity):
    from fgeh_cheatingharder_event_center import publish

    now_ticks = _sim_now_ticks()
    return publish(
        EventType.DEVOTION_LONGING_STARTED,
        source="devotion_longing_sensor",
        event_id="devotion-longing:{}:{}:{}".format(
            owner.sim_id,
            beloved.sim_id,
            now_ticks,
        ),
        observer_id=owner.sim_id,
        partner_id=beloved.sim_id,
        payload={
            "occurred_at": now_ticks,
            "elapsed_without_contact_minutes": elapsed,
            "longing_intensity": intensity,
        },
    )


def evaluate_longing(owner_id, beloved_id):
    owner, beloved, _, _, together = _live_pair(owner_id, beloved_id)
    summary, bond = _summary_and_bond(owner_id, beloved_id)
    if owner is None or beloved is None or bond is None:
        return False
    _maintain_reunion_expression(owner, beloved)
    if not together:
        # This first slice deliberately owns no travel or off-lot autonomy.
        _ACTIVE_LONGING_EXPRESSIONS.pop((owner_id, beloved_id), None)
        _remove_expression_buffs(owner, include_reunion=False)
        return False

    elapsed = _elapsed_minutes(
        _sim_now_ticks(),
        _last_contact_ticks(summary, bond),
    )
    intensity = longing_intensity(elapsed)
    if intensity <= 0:
        _ACTIVE_LONGING_EXPRESSIONS.pop((owner_id, beloved_id), None)
        _remove_expression_buffs(owner, include_reunion=False)
        return False

    already_longing = (
        summary is not None
        and summary.flags.get("is_longing_for_only_beloved", False)
    )
    if not already_longing:
        _publish_longing_started(owner, beloved, elapsed, intensity)
        return True

    _maintain_longing_expression(
        owner,
        beloved,
        build_longing_decision_context(owner, beloved),
    )
    from fgeh_cheatingharder_event_center import evaluate_directed_opportunity

    return evaluate_directed_opportunity(
        BehaviorOpportunity(
            owner.sim_id,
            beloved.sim_id,
            reason="devotion_longing_retry",
            urgency=intensity,
            opportunity_type=OpportunityType.DEVOTION_LONGING,
            context={"elapsed_without_contact_minutes": elapsed},
        )
    )


def schedule_longing_check(owner_id, beloved_id, minutes=None):
    key = (int(owner_id), int(beloved_id))
    existing = _LONGING_ALARMS.get(key)
    if existing is not None:
        return existing
    owner, beloved, owner_sim, _, _ = _live_pair(*key)
    if owner is None or beloved is None:
        return None
    alarm_owner = owner_sim or owner
    delay = (
        settings.DEVOTION_LONGING_CHECK_SIM_MINUTES
        if minutes is None
        else max(0.1, float(minutes))
    )

    def _on_longing_alarm(_handle):
        _LONGING_ALARMS.pop(key, None)
        try:
            evaluate_longing(*key)
        except Exception:
            log_exception(
                "devotion longing evaluation failed owner={} beloved={}".format(
                    key[0],
                    key[1],
                )
            )
        schedule_longing_check(*key)

    try:
        handle = alarms.add_alarm(
            alarm_owner,
            date_and_time.create_time_span(minutes=delay),
            _on_longing_alarm,
            cross_zone=True,
        )
        _LONGING_ALARMS[key] = handle
        return handle
    except Exception:
        log_exception(
            "devotion longing alarm failed owner={} beloved={}".format(*key)
        )
        return None


def start_longing_cycles():
    try:
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        bonds = get_memory_service().store.devotion_bonds()
        for index, bond in enumerate(bonds):
            schedule_longing_check(
                bond.owner_id,
                bond.beloved_id,
                minutes=(
                    settings.DEVOTION_LONGING_FIRST_CHECK_SIM_MINUTES
                    + index
                ),
            )
        log("devotion longing cycles restored count={}", len(bonds))
        return len(bonds)
    except Exception:
        log_exception("devotion longing cycle restore failed")
        return 0


def reset_longing_runtime():
    for handle in tuple(_LONGING_ALARMS.values()):
        try:
            alarms.cancel_alarm(handle)
        except Exception:
            pass
    _LONGING_ALARMS.clear()
    _ACTIVE_LONGING_EXPRESSIONS.clear()
    _ACTIVE_REUNION_EXPRESSIONS.clear()


def _affordance_name(affordance):
    return str(getattr(affordance, "__name__", affordance)).lower()


def _affection_score(affordance):
    name = _affordance_name(affordance)
    if any(marker in name for marker in _AFFECTION_EXCLUSIONS):
        return -1000
    score = 0
    for marker, weight in _AFFECTION_WEIGHTS:
        if marker in name:
            score = max(score, weight)
    return score


def push_devotion_affection(owner_info, beloved_info):
    """Queue one tested, low-priority social chosen from the target's menu."""
    _, _, owner_sim, beloved_sim, together = _live_pair(
        owner_info.sim_id,
        beloved_info.sim_id,
    )
    if not together:
        return ExecutionResult(False, "not_together_on_active_zone")
    try:
        from interactions.context import InteractionContext
        from interactions.context import QueueInsertStrategy
        from interactions.priority import Priority

        context = InteractionContext(
            owner_sim,
            InteractionContext.SOURCE_AUTONOMY,
            Priority.Low,
            insert_strategy=QueueInsertStrategy.LAST,
        )
        affordances = []
        seen = set()
        for aop in tuple(beloved_sim.potential_interactions(context)):
            affordance = getattr(aop, "affordance", None)
            if (
                affordance is None
                or affordance in seen
                or not getattr(affordance, "is_social", False)
            ):
                continue
            seen.add(affordance)
            # A zero means no reviewed affection marker matched.  Treating it
            # as safe previously admitted every social in the menu, including
            # GiveFakeBadNews, and incorrectly relieved devotion longing.
            if _affection_score(affordance) > 0:
                affordances.append(affordance)
        affordances.sort(key=_affection_score, reverse=True)
        for affordance in affordances:
            try:
                result = owner_sim.push_super_affordance(
                    affordance,
                    beloved_sim,
                    context,
                )
                interaction = getattr(result, "interaction", None)
                if result and not getattr(interaction, "is_finishing", False):
                    now_ticks = _sim_now_ticks()
                    from fgeh_cheatingharder_event_center import publish

                    publish(
                        EventType.DEVOTION_CONTACT_SOUGHT,
                        source="devotion_longing_executor",
                        event_id="devotion-seek:{}:{}:{}".format(
                            owner_info.sim_id,
                            beloved_info.sim_id,
                            now_ticks,
                        ),
                        observer_id=owner_info.sim_id,
                        partner_id=beloved_info.sim_id,
                        payload={
                            "occurred_at": now_ticks,
                            "affordance_name": _affordance_name(affordance),
                            "interaction_id": getattr(interaction, "id", None),
                        },
                    )
                    return ExecutionResult(
                        True,
                        "affection_queued",
                        {"affordance": _affordance_name(affordance)},
                    )
            except Exception:
                continue
        return ExecutionResult(
            False,
            "no_safe_affection_available",
            {"candidate_count": len(affordances)},
        )
    except Exception:
        log_exception(
            "devotion affection push failed owner={} beloved={}".format(
                owner_info.sim_id,
                beloved_info.sim_id,
            )
        )
        return ExecutionResult(False, "affection_push_failed")

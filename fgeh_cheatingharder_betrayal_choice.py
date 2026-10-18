"""Unified player/character-brain routing for betrayal reactions.

The pure helpers in this module are deliberately importable outside The Sims
4.  Game UI and service imports stay inside the small runtime boundary so the
choice contract can be covered by normal unit tests.
"""

from fgeh_cheatingharder_betrayal_episode import (
    BETRAYAL_REACTION_EPISODES,
)
from fgeh_cheatingharder_betrayal_memory_rules import (
    OPPORTUNITY_BETRAYAL_RESPONSE,
    betrayal_action_target,
)
from fgeh_cheatingharder_betrayal_reactions import (
    BetrayalIntent,
)
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_memory_models import MemoryOpportunity


PLAYER_DECISION_AUTONOMOUS = "autonomous"
PLAYER_DECISION_ACTIVE_SIM = "active_sim"

DECISION_SOURCE_CHARACTER_BRAIN = "character_brain"
DECISION_SOURCE_PLAYER = "player"

INTERNAL_BETRAYAL_INTENTS = frozenset((
    BetrayalIntent.FORGIVE_PARTNER,
    BetrayalIntent.ENDURE_SILENTLY,
))

_PENDING_DECISIONS = set()


_INTENT_PRESENTATION = {
    BetrayalIntent.FORGIVE_PARTNER: (
        "选择原谅",
        "暂时放下这次伤害，但信任不会立刻恢复。",
    ),
    BetrayalIntent.SEEK_REASSURANCE: (
        "寻求安慰与保证",
        "去找伴侣确认这段关系是否仍然值得相信。",
    ),
    BetrayalIntent.CLING_TO_PARTNER: (
        "靠近并挽留伴侣",
        "因为害怕失去对方而主动寻求亲近。",
    ),
    BetrayalIntent.CONFRONT_PARTNER: (
        "质问伴侣",
        "直接要求伴侣面对这次越界和造成的伤害。",
    ),
    BetrayalIntent.CONFRONT_RIVAL: (
        "质问第三者",
        "把矛头转向这次事件中的第三者。",
    ),
    BetrayalIntent.BREAK_UP: (
        "提出分手",
        "结束关系；仍会进入已有的分手协商流程。",
    ),
    BetrayalIntent.ENDURE_SILENTLY: (
        "沉默忍耐",
        "不立刻采取行动，把受伤和不满留在心里。",
    ),
}


class BetrayalChoiceOption:

    def __init__(
        self,
        intent,
        score,
        recommended=False,
        terms=None,
    ):
        self.intent = str(intent)
        self.score = max(0.0, float(score or 0.0))
        self.recommended = bool(recommended)
        self.terms = tuple(terms or ())

    def to_data(self):
        return {
            "intent": self.intent,
            "score": self.score,
            "recommended": self.recommended,
            "terms": tuple(self.terms),
        }


def _candidate_data(candidate):
    if isinstance(candidate, dict):
        return dict(candidate)
    as_dict = getattr(candidate, "as_dict", None)
    if callable(as_dict):
        return dict(as_dict())
    return {
        "intent": getattr(candidate, "intent", None),
        "score": getattr(candidate, "score", 0.0),
        "terms": getattr(candidate, "terms", ()),
        "eligible": getattr(candidate, "eligible", False),
        "blockers": getattr(candidate, "blockers", ()),
    }


def build_betrayal_choice_options(candidates, recommended_intent=None):
    """Return every eligible reaction from the same pool used by the AI."""
    recommended_intent = str(recommended_intent or "")
    by_intent = {}
    for raw_candidate in tuple(candidates or ()):
        data = _candidate_data(raw_candidate)
        intent = str(data.get("intent") or "")
        if intent not in BetrayalIntent.ALL:
            continue
        if not bool(data.get("eligible", True)):
            continue
        by_intent[intent] = BetrayalChoiceOption(
            intent,
            data.get("score", 0.0),
            recommended=(intent == recommended_intent),
            terms=data.get("terms", ()),
        )
    return tuple(
        by_intent[intent]
        for intent in BetrayalIntent.ALL
        if intent in by_intent
    )


def player_decision_required(mode, is_selectable, is_active):
    """Beta authority rule: only the active selectable Sim prompts once."""
    if str(mode or PLAYER_DECISION_ACTIVE_SIM) == PLAYER_DECISION_AUTONOMOUS:
        return False
    return bool(is_selectable and is_active)


def with_selected_betrayal_intent(
    opportunity,
    selected_intent,
    decision_source,
):
    """Clone an opportunity without mutating the pipeline's audit record."""
    context = dict(getattr(opportunity, "context", {}) or {})
    selected_intent = str(selected_intent)
    original_intent = str(context.get("selected_intent") or "")
    partner_id = context.get("relationship_partner_id")
    rival_id = context.get("rival_id")
    target_id, target_role = betrayal_action_target(
        selected_intent,
        partner_id,
        rival_id,
    )
    if target_id is None:
        target_id = getattr(opportunity, "partner_id", None)
    context.update({
        "ai_recommended_intent": (
            context.get("ai_recommended_intent") or original_intent
        ),
        "selected_intent": selected_intent,
        "decision_source": str(decision_source),
        "player_override": (
            str(decision_source) == DECISION_SOURCE_PLAYER
            and selected_intent != original_intent
        ),
        "target_id": target_id,
        "target_role": target_role,
    })
    return MemoryOpportunity(
        opportunity.opportunity_type,
        opportunity.observer_id,
        target_id,
        opportunity.reason,
        urgency=opportunity.urgency,
        event_id=opportunity.event_id,
        context=context,
    )


def _decision_key(opportunity):
    context = dict(getattr(opportunity, "context", {}) or {})
    return (
        int(opportunity.observer_id),
        str(
            context.get("betrayal_episode_id")
            or opportunity.event_id
            or "unknown"
        ),
    )


def _bind_selected_episode(opportunity):
    context = dict(getattr(opportunity, "context", {}) or {})
    episode_id = context.get("betrayal_episode_id")
    if not episode_id:
        return None
    episode = BETRAYAL_REACTION_EPISODES.get(episode_id)
    details = dict(getattr(episode, "reaction_details", {}) or {})
    details.update({
        "selected_intent": context.get("selected_intent"),
        "ai_recommended_intent": context.get("ai_recommended_intent"),
        "decision_source": context.get("decision_source"),
        "player_override": bool(context.get("player_override", False)),
    })
    return BETRAYAL_REACTION_EPISODES.bind_primary_reaction(
        episode_id,
        context.get("selected_intent"),
        details=details,
    )


def _publish_internal_choice_outcome(opportunity):
    """Record forgive/silence as completed decisions, not missing handlers."""
    context = dict(getattr(opportunity, "context", {}) or {})
    intent = str(context.get("selected_intent") or "")
    episode_id = context.get("betrayal_episode_id")
    if episode_id:
        BETRAYAL_REACTION_EPISODES.resolve(
            episode_id,
            "internal_choice_{}".format(intent),
            success=True,
        )
    try:
        import services
        from fgeh_cheatingharder_domain import EventType
        from fgeh_cheatingharder_event_center import publish

        now = services.time_service().sim_now
        absolute_ticks = getattr(now, "absolute_ticks", None)
        now_ticks = (
            absolute_ticks() if callable(absolute_ticks) else int(now)
        )
        relationship_partner_id = int(
            context.get("relationship_partner_id")
            or opportunity.partner_id
        )
        publish(
            EventType.AUTONOMOUS_ACTION_RESOLVED,
            source="betrayal_choice_runtime",
            event_id="betrayal-choice:{}:{}".format(
                episode_id or opportunity.event_id,
                intent,
            ),
            actor_id=opportunity.observer_id,
            target_id=relationship_partner_id,
            observer_id=opportunity.observer_id,
            partner_id=relationship_partner_id,
            rival_id=context.get("rival_id"),
            payload={
                "occurred_at": now_ticks,
                "cause_id": context.get("source_betrayal_event_id"),
                "source_event_id": context.get("source_betrayal_event_id"),
                "target_id": relationship_partner_id,
                "target_role": "partner",
                "relationship_partner_id": relationship_partner_id,
                "rival_id": context.get("rival_id"),
                "intent": intent,
                "success": True,
                "status": "internal_choice_completed",
                "journal_visibility": "timeline",
                "journal_importance": "normal",
                "journal_title": "我作出了背叛后的选择",
                "salience": 55,
                "semantic_tags": ("conflict", "betrayal"),
                "opportunity_type": opportunity.opportunity_type,
                "execution_strategy": "internal_decision",
                "selection_mode": context.get("decision_source"),
                "betrayal_episode_id": episode_id,
            },
        )
    except Exception:
        log_exception(
            "internal betrayal choice outcome publish failed intent={}".format(
                intent
            )
        )


def _dispatch_selected(
    opportunity,
    report,
    autonomous_consumer,
    internal_outcome_publisher=None,
):
    _bind_selected_episode(opportunity)
    context = dict(getattr(opportunity, "context", {}) or {})
    intent = str(context.get("selected_intent") or "")
    if intent in INTERNAL_BETRAYAL_INTENTS:
        publisher = internal_outcome_publisher or _publish_internal_choice_outcome
        publisher(opportunity)
        return "internal_choice"
    autonomous_consumer((opportunity,), report=report)
    return "scheduled"


def _runtime_player_authority(opportunity, mode):
    try:
        import services

        sim_info = services.sim_info_manager().get(
            int(opportunity.observer_id)
        )
        sim = None if sim_info is None else sim_info.get_sim_instance()
        active_sim = services.get_active_sim()
        active_id = getattr(
            getattr(active_sim, "sim_info", active_sim),
            "sim_id",
            None,
        )
        return player_decision_required(
            mode,
            bool(sim is not None and getattr(sim, "is_selectable", False)),
            active_id is not None
            and int(active_id) == int(opportunity.observer_id),
        )
    except Exception:
        return False


class _BetrayalChoiceTag:

    def __init__(self, intent):
        self.intent = str(intent)


def show_betrayal_choice_dialog(opportunity, options, on_decision):
    """Show EA's stable text picker while keeping all decision data ours."""
    try:
        import services
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog_picker import ObjectPickerRow, UiObjectPicker

        sim_info = services.sim_info_manager().get(
            int(opportunity.observer_id)
        )
        observer = None if sim_info is None else sim_info.get_sim_instance()
        if observer is None:
            return False

        raw = LocalizationHelperTuning.get_raw_text
        title = raw("我该如何面对这次背叛？")
        text = raw(
            "所有选项都来自这个角色自己的情感倾向。"
            "带★的是角色大脑最想做的事；关闭窗口则让角色自己决定。"
        )
        dialog = UiObjectPicker.TunableFactory().default(
            observer,
            title=lambda *args, **kwargs: title,
            text=lambda *args, **kwargs: text,
            min_selectable=1,
            max_selectable=1,
            picker_type=(
                UiObjectPicker.UiObjectPickerObjectPickerType.OBJECT_TEXT
            ),
            num_columns=1,
        )
        for index, option in enumerate(tuple(options or ()), 1):
            label, description = _INTENT_PRESENTATION.get(
                option.intent,
                (option.intent, ""),
            )
            prefix = "★ " if option.recommended else ""
            dialog.add_row(ObjectPickerRow(
                option_id=9000 + index,
                object_id=9000 + index,
                name=raw("{}{}".format(prefix, label)),
                row_description=raw(
                    "{}  角色倾向：{:.0f}".format(
                        description,
                        option.score,
                    )
                ),
                tag=_BetrayalChoiceTag(option.intent),
                is_selected=False,
                is_enable=True,
                use_catalog_product_thumbnails=False,
            ))

        def _on_response(response_dialog):
            selected_intent = None
            try:
                if response_dialog.accepted:
                    tags = tuple(response_dialog.get_result_tags() or ())
                    if tags:
                        selected_intent = getattr(
                            tags[0],
                            "intent",
                            tags[0],
                        )
            except Exception:
                log_exception("betrayal player choice response failed")
            on_decision(selected_intent)

        dialog.add_listener(_on_response)
        dialog.show_dialog()
        log(
            "betrayal player choice dialog shown observer={} options={}",
            opportunity.observer_id,
            tuple(option.intent for option in options),
        )
        return True
    except Exception:
        log_exception("betrayal player choice dialog failed")
        return False


def route_betrayal_opportunities(
    opportunities,
    report,
    autonomous_consumer,
    decision_presenter=None,
    player_authority=None,
    internal_outcome_publisher=None,
    player_mode=PLAYER_DECISION_ACTIVE_SIM,
):
    """Route one pipeline batch without making NPCs wait for player UI."""
    presenter = decision_presenter or show_betrayal_choice_dialog
    authority = player_authority or (
        lambda opportunity: _runtime_player_authority(
            opportunity,
            player_mode,
        )
    )
    passthrough = []
    statuses = []
    for opportunity in tuple(opportunities or ()):
        if opportunity.opportunity_type != OPPORTUNITY_BETRAYAL_RESPONSE:
            passthrough.append(opportunity)
            continue
        context = dict(opportunity.context or {})
        recommended = str(context.get("selected_intent") or "")
        brain_choice = with_selected_betrayal_intent(
            opportunity,
            recommended,
            DECISION_SOURCE_CHARACTER_BRAIN,
        )
        options = build_betrayal_choice_options(
            context.get("behavior_candidates", ()),
            recommended,
        )
        key = _decision_key(opportunity)
        requires_player = bool(authority(opportunity))
        log(
            "betrayal choice routed observer={} recommended={} player_required={} options={} pending={}",
            opportunity.observer_id,
            recommended,
            requires_player,
            tuple(option.intent for option in options),
            key in _PENDING_DECISIONS,
        )
        if requires_player and options and key not in _PENDING_DECISIONS:
            _PENDING_DECISIONS.add(key)

            def _on_decision(
                selected_intent,
                original=opportunity,
                fallback=brain_choice,
                pending_key=key,
            ):
                _PENDING_DECISIONS.discard(pending_key)
                try:
                    selected = (
                        fallback
                        if not selected_intent
                        else with_selected_betrayal_intent(
                            original,
                            selected_intent,
                            DECISION_SOURCE_PLAYER,
                        )
                    )
                    _dispatch_selected(
                        selected,
                        report,
                        autonomous_consumer,
                        internal_outcome_publisher,
                    )
                    log(
                        "betrayal decision completed observer={} intent={} "
                        "source={}",
                        selected.observer_id,
                        selected.context.get("selected_intent"),
                        selected.context.get("decision_source"),
                    )
                except Exception:
                    log_exception("betrayal decision callback dispatch failed")

            if presenter(opportunity, options, _on_decision):
                statuses.append("awaiting_player")
                continue
            log(
                "betrayal player choice presentation unavailable observer={} fallback={}",
                opportunity.observer_id,
                recommended,
            )
            _PENDING_DECISIONS.discard(key)
        statuses.append(_dispatch_selected(
            brain_choice,
            report,
            autonomous_consumer,
            internal_outcome_publisher,
        ))
    if passthrough:
        autonomous_consumer(tuple(passthrough), report=report)
        statuses.extend("passthrough" for _ in passthrough)
    return tuple(statuses)


def reset_betrayal_choice_runtime():
    _PENDING_DECISIONS.clear()

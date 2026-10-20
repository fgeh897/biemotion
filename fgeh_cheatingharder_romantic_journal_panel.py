"""Stable Python bridge for the custom romantic-journal home screen."""

from event_testing.results import TestResult
from interactions.base.immediate_interaction import ImmediateSuperInteraction

from fgeh_cheatingharder_debug import log, log_exception


_SHOW_MESSAGE = "ShowFgehRomanticJournal"
_VISIBLE_RELATIONSHIPS = 3
_VISIBLE_EVENTS = 3
_EXTENDED_RELATIONSHIP_START = 23
_EXTENDED_RELATIONSHIP_BLOCK_SIZE = 23
_HEADER_STATS_INDEX = 92
_FILTER_SUMMARY_INDEX = 93
_RELATIONSHIP_PAGE_INDEX = 94


def _sim_info(value):
    if value is None:
        return None
    return getattr(value, "sim_info", value)


def _live_sim(value):
    info = _sim_info(value)
    if info is None:
        return None
    getter = getattr(info, "get_sim_instance", None)
    if getter is not None:
        return getter()
    return value if getattr(value, "sim_info", None) is not None else None


def _constant_localized_string(value):
    def _factory(*args, **kwargs):
        del args, kwargs
        return value

    return _factory


def _event_title(entry):
    narrative = entry.get("narrative") or {}
    return str(
        narrative.get("headline")
        or entry.get("title")
        or "记录了一件恋爱事件"
    )


def _knowledge_suffix(entry):
    narrative = entry.get("narrative") or {}
    narrative_knowledge = narrative.get("knowledge") or {}
    if narrative_knowledge.get("access_label"):
        return str(narrative_knowledge["access_label"])
    knowledge = entry.get("knowledge") or {}
    access = knowledge.get("access")
    return {
        "experienced": "亲历",
        "witnessed": "目击",
        "confirmed": "确认",
        "told": "听说",
        "inferred": "推断",
        "player_asserted": "自述",
    }.get(access, "已知")


def _relationship_meta(card):
    display = card.get("display") or {}
    if display.get("status_label") and display.get("record_count_label"):
        return "{} · {}".format(
            display["status_label"],
            display["record_count_label"],
        )
    unresolved = card.get("unresolved") or {}
    if unresolved.get("relationship_crisis"):
        state = "关系危机未解决"
    elif unresolved.get("repair_case"):
        state = "正在尝试修复"
    else:
        state = "关系记录"
    return "{} · {} 条可见记录".format(
        state,
        int(card.get("known_event_count", 0)),
    )


def _relationship_details(card):
    if card is None:
        return (
            "还没有恋爱对象",
            "建立关系或产生恋爱记忆后，这里会出现记录。",
            "",
            "",
            "",
        )

    unresolved = card.get("unresolved") or {}
    if unresolved.get("relationship_crisis"):
        status = "未解决 · 这段关系正处于危机中"
    elif unresolved.get("repair_case"):
        status = "修复中 · 双方仍在处理过去的伤害"
    else:
        status = "最新事件在上"

    events = list(card.get("latest_events") or ())
    event_texts = []
    for index in range(_VISIBLE_EVENTS):
        if index < len(events):
            entry = events[index]
            event_texts.append("{}  ·  {}".format(
                _event_title(entry),
                _knowledge_suffix(entry),
            ))
        else:
            event_texts.append(
                "" if events else "还没有当前小人知道的事件"
            )
    return (
        "和 {} 的故事".format(card["partner"]["display_name"]),
        status,
        *event_texts,
    )


def _dimension_percentages(card):
    if card is None:
        return (0, 0, 0, 0, 0)
    display = card.get("display") or {}
    dimensions = {
        value.get("key"): value
        for value in display.get("mini_dimensions", ())
    }
    result = []
    for key in ("attachment", "trust", "exclusivity", "commitment", "boundary"):
        value = dimensions.get(key) or {}
        if not value.get("initialized", False) or value.get("value") is None:
            result.append(0)
            continue
        result.append(int(round(max(
            0.0,
            min(100.0, float(value.get("value", 0.0))),
        ))))
    return tuple(result)


def _event_narrative_fields(entry):
    if entry is None:
        return ("", "", "", "")
    narrative = entry.get("narrative") or {}
    fact = narrative.get("fact") or {}
    meaning = narrative.get("meaning") or {}
    badges = " · ".join(
        str(value.get("label"))
        for value in narrative.get("badges", ())
        if value.get("label")
    )
    return (
        _event_title(entry),
        str(fact.get("text") or ""),
        str(meaning.get("text") or ""),
        badges,
    )


def _extended_relationship_details(card):
    if card is None:
        return (
            "还没有恋爱对象",
            "建立关系或产生恋爱记忆后，这里会出现记录。",
            "",
            0, 0, 0, 0, 0,
            "", "", "", "",
            "", "", "", "",
            "", "", "", "",
            "暂无记录",
            "",
            "全部 0",
        )
    display = card.get("display") or {}
    unresolved = card.get("unresolved") or {}
    if unresolved.get("relationship_crisis"):
        badge = "存在未解决危机"
    elif unresolved.get("repair_case"):
        badge = "关系正在修复"
    else:
        badge = "关系仍在记录中"
    values = [
        "我与 {}".format(card["partner"]["display_name"]),
        "{} · 最新事件在上".format(
            display.get("record_count_label")
            or "{} 条可见记录".format(card.get("known_event_count", 0))
        ),
        badge,
    ]
    values.extend(_dimension_percentages(card))
    events = list(card.get("latest_events") or ())
    for index in range(_VISIBLE_EVENTS):
        values.extend(_event_narrative_fields(
            events[index] if index < len(events) else None
        ))
    total = int(card.get("known_event_count", 0))
    if total <= 0:
        event_page_label = "暂无记录"
    else:
        total_pages = (total + _VISIBLE_EVENTS - 1) // _VISIBLE_EVENTS
        event_page_label = "事件第 1 / {} 页".format(total_pages)
    values.extend((
        event_page_label,
        "",
        "全部 {}".format(total),
    ))
    return tuple(values)


def _relationship_page_label(view):
    page = view.get("relationship_page") or {}
    total = int(page.get("total_entries", view.get("total_relationships", 0)))
    size = max(1, int(page.get("page_size", _VISIBLE_RELATIONSHIPS)))
    if total <= 0:
        return "关系第 0 / 0 页"
    cursor = str(page.get("cursor") or "offset:0")
    try:
        offset = int(cursor.split(":", 1)[-1])
    except (TypeError, ValueError):
        offset = 0
    current = offset // size + 1
    total_pages = (total + size - 1) // size
    return "关系第 {} / {} 页".format(current, total_pages)


def _home_payload(view):
    cards = list(view.get("relationships") or ())
    payload = ["关闭"]
    for index in range(_VISIBLE_RELATIONSHIPS):
        if index < len(cards):
            card = cards[index]
            payload.extend((
                card["partner"]["display_name"],
                _relationship_meta(card),
            ))
        else:
            payload.extend(("", ""))

    for index in range(_VISIBLE_RELATIONSHIPS):
        payload.extend(_relationship_details(
            cards[index] if index < len(cards) else None
        ))

    hidden = int(view.get("hidden_relationship_count", 0))
    payload.append("" if hidden <= 0 else "另外还有 {} 位恋爱对象".format(hidden))

    for index in range(_VISIBLE_RELATIONSHIPS):
        payload.extend(_extended_relationship_details(
            cards[index] if index < len(cards) else None
        ))

    summary = view.get("summary") or {}
    payload.extend((
        "{} 位对象 · {} 条记录".format(
            int(summary.get("relationship_count", view.get("total_relationships", 0))),
            int(summary.get("known_event_count", 0)),
        ),
        "全部 {}".format(int(summary.get("known_event_count", 0))),
        _relationship_page_label(view),
    ))
    return tuple(payload)


def _sim_info_for_id(sim_id):
    try:
        import services

        return services.sim_info_manager().get(int(sim_id))
    except Exception:
        log_exception("romantic journal partner lookup failed id={}".format(sim_id))
        return None


def _display_name_for_info(sim_info):
    if sim_info is None:
        return None
    first_name = getattr(sim_info, "first_name", None)
    last_name = getattr(sim_info, "last_name", None)
    display_name = " ".join(
        str(part) for part in (first_name, last_name) if part
    )
    display_name = display_name or getattr(sim_info, "full_name", None)
    return None if not display_name else str(display_name)


def show_romantic_journal_panel(viewer_sim):
    """Open the first read-only journal home screen for the current Sim."""
    try:
        from distributor.shared_messages import IconInfoData, create_icon_info_msg
        from event_testing.resolver import SingleSimResolver
        from fgeh_cheatingharder_ui_adapter import build_romantic_journal_home_view
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog_labeled_icons import UiDialogIcons

        viewer_info = _sim_info(viewer_sim)
        owner = _live_sim(viewer_sim)
        if viewer_info is None or owner is None:
            log("romantic journal skipped: viewer is not live")
            return False

        view = build_romantic_journal_home_view(
            viewer_info,
            relationship_limit=_VISIBLE_RELATIONSHIPS,
            event_limit=_VISIBLE_EVENTS,
        )
        sim_directory = {
            int(viewer_info.sim_id): _display_name_for_info(viewer_info),
        }
        for card in view["relationships"]:
            partner_id = int(card["partner"]["sim_id"])
            partner_info = _sim_info_for_id(partner_id)
            partner_name = _display_name_for_info(partner_info)
            if partner_name:
                sim_directory[partner_id] = partner_name
        view = build_romantic_journal_home_view(
            viewer_info,
            relationship_limit=_VISIBLE_RELATIONSHIPS,
            event_limit=_VISIBLE_EVENTS,
            sim_directory=sim_directory,
        )
        payload = _home_payload(view)
        additional_texts = tuple(
            _constant_localized_string(
                LocalizationHelperTuning.get_raw_text(str(value))
            )
            for value in payload
        )
        partner_infos = []
        for card in view["relationships"]:
            partner_info = _sim_info_for_id(card["partner"]["sim_id"])
            if partner_info is not None:
                partner_infos.append(partner_info)
        additional_icons = tuple(
            create_icon_info_msg(IconInfoData(obj_instance=partner_info))
            for partner_info in partner_infos
        )

        title = LocalizationHelperTuning.get_raw_text("恋爱日志")
        text = LocalizationHelperTuning.get_raw_text(
            "{} 的主观记录 · 只显示亲历、目击、听说或推断出的事件".format(
                view["viewer"]["display_name"]
            )
        )
        dialog = UiDialogIcons.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(viewer_info),
            title=_constant_localized_string(title),
            text=_constant_localized_string(text),
            additional_texts=additional_texts,
            show_dialog_message_override=_SHOW_MESSAGE,
        )
        dialog.show_dialog(
            icon_override=IconInfoData(obj_instance=viewer_info),
            additional_icons=additional_icons,
        )
        log(
            "romantic journal home shown schema={} viewer={} relationships={} "
            "hidden={} payload_count={} icon_count={} narrative_schema={}",
            view.get("schema_version"),
            viewer_info.sim_id,
            len(view["relationships"]),
            view["hidden_relationship_count"],
            len(payload),
            len(additional_icons),
            (
                None
                if not view["relationships"]
                or not view["relationships"][0]["latest_events"]
                else view["relationships"][0]["latest_events"][0]
                .get("narrative", {}).get("schema_version")
            ),
        )
        return True
    except Exception:
        log_exception("romantic journal home show failed")
        return False


class FgehCheatingHarderRomanticJournalInteraction(ImmediateSuperInteraction):
    """Self-click entry for the active Sim's subjective romantic journal."""

    @classmethod
    def _test(cls, target, context, **interaction_parameters):
        result = super()._test(target, context, **interaction_parameters)
        if not result:
            return result
        actor = _sim_info(getattr(context, "sim", None))
        target_info = _sim_info(target)
        if actor is None or target_info is None or actor.sim_id != target_info.sim_id:
            return TestResult(False, "The romantic journal opens on self-click only.")
        if not bool(getattr(actor, "is_selectable", False)):
            return TestResult(False, "The romantic journal belongs to a selectable Sim.")
        return TestResult.TRUE

    def _run_interaction_gen(self, timeline):
        del timeline
        show_romantic_journal_panel(self.sim)
        return True
        if False:
            yield None

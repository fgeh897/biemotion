"""Bridge between the romantic-ledger view model and the custom GFX panel."""

from fgeh_cheatingharder_debug import log, log_exception


_SHOW_MESSAGE = "ShowFgehRelationshipPanel"
_UNFORMED_TOKEN = "?"
_STAGE2_DIMENSION_KEY = "attachment"
_STAGE7_DIMENSION_KEYS = (
    "attachment",
    "trust",
    "exclusivity",
    "commitment",
    "boundary",
)


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


def _dimension_token(dimension):
    value = dimension.get("value")
    if not dimension.get("initialized", False) or value is None:
        return _UNFORMED_TOKEN
    return "{:g}".format(max(0.0, min(100.0, float(value))))


def _payload_from_view(view):
    pair = view["pair"]
    directions = view["directions"]
    payload = [
        pair["sim_a"]["display_name"],
        pair["sim_b"]["display_name"],
    ]
    for direction in directions:
        payload.extend(
            _dimension_token(dimension)
            for dimension in direction["dimensions"]
        )
    return payload


def _stage5_relationship_payload(view):
    """Build the visible label and the clamped attachment percentage."""
    pair = view["pair"]
    direction = view["directions"][0]
    dimension = next(
        item
        for item in direction["dimensions"]
        if item["key"] == _STAGE2_DIMENSION_KEY
    )
    source_name = pair["sim_a"]["display_name"]
    target_name = pair["sim_b"]["display_name"]
    if not dimension.get("initialized", False):
        value_text = "未形成"
        bar_percentage = 0
    else:
        value = max(0.0, min(100.0, float(dimension.get("value", 0.0))))
        bar_percentage = int(round(value))
        value_text = "{} / 100".format(bar_percentage)
    body = (
        "{}  →  {}\n\n"
        "依恋\n"
        "当前真实值：{}"
    ).format(source_name, target_name, value_text)
    return body, bar_percentage


def _stage7_relationship_payload(view):
    """Build the direction label and five clamped graphical percentages."""
    pair = view["pair"]
    direction = view["directions"][0]
    dimensions = {
        item.get("key"): item
        for item in direction.get("dimensions", ())
    }
    percentages = []
    for key in _STAGE7_DIMENSION_KEYS:
        dimension = dimensions.get(key)
        if (
            dimension is None
            or not dimension.get("initialized", False)
            or dimension.get("value") is None
        ):
            percentages.append(0)
            continue
        value = max(0.0, min(100.0, float(dimension.get("value", 0.0))))
        percentages.append(int(round(value)))
    body = (
        "{}  →  {}\n"
        "未形成的维度显示为空条"
    ).format(
        pair["sim_a"]["display_name"],
        pair["sim_b"]["display_name"],
    )
    return body, tuple(percentages)


def _show_relationship_panel_full_quarantined(sim_a, sim_b, on_edit=None):
    """Show both directed five-dimensional states in the independent panel.

    ``on_edit`` is called only when the player presses the panel's edit button.
    Closing the panel does not open the numeric picker.
    """
    try:
        from event_testing.resolver import SingleSimResolver
        from fgeh_cheatingharder_ui_adapter import build_pair_view
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog import UiDialogOk

        sim_a_info = _sim_info(sim_a)
        sim_b_info = _sim_info(sim_b)
        owner = _live_sim(sim_a)
        if sim_a_info is None or sim_b_info is None or owner is None:
            log(
                "relationship panel skipped: invalid/live pair a={} b={} owner={}",
                getattr(sim_a_info, "sim_id", None),
                getattr(sim_b_info, "sim_id", None),
                owner is not None,
            )
            return False

        view = build_pair_view(sim_a_info, sim_b_info)
        payload = _payload_from_view(view)
        localized_payload = tuple(
            _constant_localized_string(
                LocalizationHelperTuning.get_raw_text(str(value))
            )
            for value in payload
        )
        blank = LocalizationHelperTuning.get_raw_text("")
        edit_text = LocalizationHelperTuning.get_raw_text("编辑数值")
        dialog = UiDialogOk.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(sim_a_info),
            title=_constant_localized_string(blank),
            text=_constant_localized_string(blank),
            text_ok=_constant_localized_string(edit_text),
            additional_texts=localized_payload,
            show_dialog_message_override=_SHOW_MESSAGE,
        )

        def _on_response(response_dialog):
            try:
                if response_dialog.accepted and on_edit is not None:
                    on_edit()
            except Exception:
                log_exception("relationship panel edit callback failed")

        dialog.show_dialog(on_response=_on_response)
        log(
            "relationship panel shown pair={}<->{} payload_count={}",
            sim_a_info.sim_id,
            sim_b_info.sim_id,
            len(payload),
        )
        return True
    except Exception:
        log_exception("relationship panel show failed")
        return False


def show_relationship_panel(sim_a, sim_b, on_edit=None):
    """Show five real values and the Stage-8 target portrait."""
    del on_edit
    try:
        from distributor.shared_messages import IconInfoData
        from event_testing.resolver import SingleSimResolver
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog import UiDialog

        sim_a_info = _sim_info(sim_a)
        sim_b_info = _sim_info(sim_b)
        owner = _live_sim(sim_a)
        if sim_a_info is None or sim_b_info is None or owner is None:
            log(
                "relationship panel safe shell skipped: invalid/live pair "
                "a={} b={} owner={}",
                getattr(sim_a_info, "sim_id", None),
                getattr(sim_b_info, "sim_id", None),
                owner is not None,
            )
            return False

        from fgeh_cheatingharder_ui_adapter import build_pair_view

        view = build_pair_view(sim_a_info, sim_b_info)
        body_text, bar_percentages = _stage7_relationship_payload(view)
        title = LocalizationHelperTuning.get_raw_text("五维关系")
        body = LocalizationHelperTuning.get_raw_text(body_text)
        close_text = LocalizationHelperTuning.get_raw_text("关闭")
        additional_texts = (
            _constant_localized_string(close_text),
        ) + tuple(
            _constant_localized_string(
                LocalizationHelperTuning.get_raw_text(str(percentage))
            )
            for percentage in bar_percentages
        )
        dialog = UiDialog.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(sim_a_info),
            title=_constant_localized_string(title),
            text=_constant_localized_string(body),
            additional_texts=additional_texts,
            show_dialog_message_override=_SHOW_MESSAGE,
        )
        dialog.show_dialog(
            icon_override=IconInfoData(obj_instance=sim_b_info),
        )
        log(
            "relationship panel stage8 target portrait shown pair={}->{} "
            "dimensions={} percentages={}",
            sim_a_info.sim_id,
            sim_b_info.sim_id,
            _STAGE7_DIMENSION_KEYS,
            bar_percentages,
        )
        return True
    except Exception:
        log_exception("relationship panel stage8 show failed")
        return False

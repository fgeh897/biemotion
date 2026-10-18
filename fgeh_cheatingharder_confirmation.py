def _sim_name(sim_info):
    first_name = getattr(sim_info, "first_name", None)
    last_name = getattr(sim_info, "last_name", None)
    if first_name and last_name:
        return "{} {}".format(first_name, last_name)
    if first_name:
        return str(first_name)
    return "这个小人"


def show_multiple_romance_confirmation(observer_sim_info, target_sim_info, on_accept, on_decline=None):
    """Ask the live player-facing Sim before creating a unique-partner claim."""
    from fgeh_cheatingharder_debug import log, log_exception

    try:
        from distributor.shared_messages import IconInfoData
        from event_testing.resolver import SingleSimResolver
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog import UiDialogOkCancel

        owner = observer_sim_info.get_sim_instance()
        if owner is None:
            log(
                "claim confirmation skipped: observer has no live instance observer={}",
                getattr(observer_sim_info, "sim_id", None),
            )
            return False

        observer_name = _sim_name(observer_sim_info)
        target_name = _sim_name(target_sim_info)
        title = LocalizationHelperTuning.get_raw_text("发现多段恋爱关系")
        text = LocalizationHelperTuning.get_raw_text(
            "{}目前和不止一个人存在浪漫关系。是否仍要把{}认定为唯一伴侣？".format(
                observer_name,
                target_name,
            )
        )
        text_ok = LocalizationHelperTuning.get_raw_text("仍然认定")
        text_cancel = LocalizationHelperTuning.get_raw_text("暂不认定")

        dialog = UiDialogOkCancel.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(observer_sim_info),
            title=lambda *args, **kwargs: title,
            text=lambda *args, **kwargs: text,
            text_ok=lambda *args, **kwargs: text_ok,
            text_cancel=lambda *args, **kwargs: text_cancel,
        )

        def _on_response(response_dialog):
            try:
                if response_dialog.accepted:
                    log(
                        "claim confirmation accepted observer={} target={}",
                        observer_sim_info.sim_id,
                        target_sim_info.sim_id,
                    )
                    on_accept()
                else:
                    log(
                        "claim confirmation declined observer={} target={} response={}",
                        observer_sim_info.sim_id,
                        target_sim_info.sim_id,
                        getattr(response_dialog, "response", None),
                    )
                    if on_decline is not None:
                        on_decline()
            except Exception:
                log_exception("claim confirmation response failed")

        dialog.show_dialog(
            on_response=_on_response,
            icon_override=IconInfoData(obj_instance=owner),
        )
        log(
            "claim confirmation shown observer={} target={}",
            observer_sim_info.sim_id,
            target_sim_info.sim_id,
        )
        return True
    except Exception:
        log_exception("claim confirmation failed")
        return False


def show_permanent_devotion_confirmation(
    owner_sim_info,
    beloved_sim_info,
    on_accept,
):
    """Confirm the intentionally extreme and normally irreversible bond."""
    from fgeh_cheatingharder_debug import log, log_exception

    try:
        from distributor.shared_messages import IconInfoData
        from event_testing.resolver import SingleSimResolver
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog import UiDialogOkCancel

        owner = owner_sim_info.get_sim_instance()
        if owner is None:
            return False
        owner_name = _sim_name(owner_sim_info)
        beloved_name = _sim_name(beloved_sim_info)
        title = LocalizationHelperTuning.get_raw_text(
            "认定此生唯一挚爱"
        )
        text = LocalizationHelperTuning.get_raw_text(
            "{}将把{}认定为此生唯一挚爱。分手、拒绝、背叛和死亡都不会自动解除；"
            "{}也不会再接受其他人的浪漫关系。确认继续吗？".format(
                owner_name,
                beloved_name,
                owner_name,
            )
        )
        dialog = UiDialogOkCancel.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(owner_sim_info),
            title=lambda *args, **kwargs: title,
            text=lambda *args, **kwargs: text,
            text_ok=lambda *args, **kwargs: (
                LocalizationHelperTuning.get_raw_text("此生只爱这个人")
            ),
            text_cancel=lambda *args, **kwargs: (
                LocalizationHelperTuning.get_raw_text("暂不认定")
            ),
        )

        def _on_response(response_dialog):
            try:
                if response_dialog.accepted:
                    on_accept()
                    log(
                        "permanent devotion confirmation accepted owner={} beloved={}",
                        owner_sim_info.sim_id,
                        beloved_sim_info.sim_id,
                    )
            except Exception:
                log_exception("permanent devotion confirmation response failed")

        dialog.show_dialog(
            on_response=_on_response,
            icon_override=IconInfoData(obj_instance=owner),
        )
        return True
    except Exception:
        log_exception("permanent devotion confirmation failed")
        return False


def show_breakup_second_stage_dialog(
    proposer_sim_info,
    recipient_sim_info,
    response,
    on_insist,
    on_delay,
    on_withdraw,
):
    """Let a player proposer answer the recipient's independent reaction.

    Refusing to insist is intentionally not treated as an automatic
    reconciliation.  A follow-up dialog separates an unresolved delay from a
    genuine withdrawal so the former can open a persistent relationship
    crisis.
    """
    from fgeh_cheatingharder_debug import log, log_exception

    try:
        from distributor.shared_messages import IconInfoData
        from event_testing.resolver import SingleSimResolver
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog import UiDialogOkCancel
        from fgeh_cheatingharder_breakup_negotiation import BreakupResponse

        owner = proposer_sim_info.get_sim_instance()
        if owner is None or not bool(getattr(owner, "is_selectable", False)):
            log(
                "player breakup dialog skipped: proposer unavailable or not selectable proposer={}",
                getattr(proposer_sim_info, "sim_id", None),
            )
            return False

        proposer_name = _sim_name(proposer_sim_info)
        recipient_name = _sim_name(recipient_sim_info)
        if response == BreakupResponse.REFUSE:
            title_text = "{}拒绝接受分手".format(recipient_name)
            body_text = (
                "{}不认为这段关系已经结束。{}仍然可以坚持离开，"
                "也可以先不立即结束关系。"
            ).format(recipient_name, proposer_name)
        else:
            title_text = "{}正在挽留你".format(recipient_name)
            body_text = (
                "{}请求{}不要结束这段关系。你仍然可以坚持分手，"
                "也可以先不立即结束关系。"
            ).format(recipient_name, proposer_name)

        dialog = UiDialogOkCancel.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(proposer_sim_info),
            title=lambda *args, **kwargs: (
                LocalizationHelperTuning.get_raw_text(title_text)
            ),
            text=lambda *args, **kwargs: (
                LocalizationHelperTuning.get_raw_text(body_text)
            ),
            text_ok=lambda *args, **kwargs: (
                LocalizationHelperTuning.get_raw_text("坚持分手")
            ),
            text_cancel=lambda *args, **kwargs: (
                LocalizationHelperTuning.get_raw_text("不立即分手")
            ),
        )

        def _show_non_breakup_choice():
            follow_up = UiDialogOkCancel.TunableFactory().default(
                owner,
                resolver=SingleSimResolver(proposer_sim_info),
                title=lambda *args, **kwargs: (
                    LocalizationHelperTuning.get_raw_text("接下来怎么办？")
                ),
                text=lambda *args, **kwargs: (
                    LocalizationHelperTuning.get_raw_text(
                        "你可以暂缓决定，让关系继续处于悬而未决的危机中；"
                        "也可以真正撤回分手，决定继续这段关系。"
                    )
                ),
                text_ok=lambda *args, **kwargs: (
                    LocalizationHelperTuning.get_raw_text("暂缓决定")
                ),
                text_cancel=lambda *args, **kwargs: (
                    LocalizationHelperTuning.get_raw_text("撤回分手")
                ),
            )

            def _on_follow_up(response_dialog):
                try:
                    if response_dialog.accepted:
                        log(
                            "player breakup second stage chose delay proposer={} recipient={} response={}",
                            proposer_sim_info.sim_id,
                            recipient_sim_info.sim_id,
                            response,
                        )
                        on_delay()
                    else:
                        log(
                            "player breakup second stage chose withdraw proposer={} recipient={} response={} dialog_response={}",
                            proposer_sim_info.sim_id,
                            recipient_sim_info.sim_id,
                            response,
                            getattr(response_dialog, "response", None),
                        )
                        on_withdraw()
                except Exception:
                    log_exception(
                        "player breakup second-stage follow-up response failed"
                    )

            follow_up.show_dialog(
                on_response=_on_follow_up,
                icon_override=IconInfoData(obj_instance=owner),
            )
            log(
                "player breakup second-stage follow-up shown proposer={} recipient={} response={}",
                proposer_sim_info.sim_id,
                recipient_sim_info.sim_id,
                response,
            )

        def _on_response(response_dialog):
            try:
                if response_dialog.accepted:
                    log(
                        "player breakup second stage chose insist proposer={} recipient={} response={}",
                        proposer_sim_info.sim_id,
                        recipient_sim_info.sim_id,
                        response,
                    )
                    on_insist()
                else:
                    log(
                        "player breakup second stage chose non-immediate path proposer={} recipient={} response={} dialog_response={}",
                        proposer_sim_info.sim_id,
                        recipient_sim_info.sim_id,
                        response,
                        getattr(response_dialog, "response", None),
                    )
                    _show_non_breakup_choice()
            except Exception:
                log_exception("player breakup second-stage response failed")

        dialog.show_dialog(
            on_response=_on_response,
            icon_override=IconInfoData(obj_instance=owner),
        )
        log(
            "player breakup second stage shown proposer={} recipient={} response={}",
            proposer_sim_info.sim_id,
            recipient_sim_info.sim_id,
            response,
        )
        return True
    except Exception:
        log_exception("player breakup second-stage dialog failed")
        return False


def show_breakup_recipient_response_dialog(
    proposer_sim_info,
    recipient_sim_info,
    on_accept,
    on_plead,
):
    """Let the actively controlled recipient answer an autonomous proposal."""
    from fgeh_cheatingharder_debug import log, log_exception

    try:
        from distributor.shared_messages import IconInfoData
        from event_testing.resolver import SingleSimResolver
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog import UiDialogOkCancel

        owner = recipient_sim_info.get_sim_instance()
        if owner is None or not bool(getattr(owner, "is_selectable", False)):
            log(
                "autonomous breakup recipient dialog skipped: recipient unavailable or not selectable recipient={}",
                getattr(recipient_sim_info, "sim_id", None),
            )
            return False

        proposer_name = _sim_name(proposer_sim_info)
        recipient_name = _sim_name(recipient_sim_info)
        title_text = "{}向你提出分手".format(proposer_name)
        body_text = (
            "{}想结束与你的关系。{}可以接受这次分手，也可以挽留{}；"
            "如果选择挽留，{}仍会按照自己的性格与感情决定是否坚持离开。"
        ).format(proposer_name, recipient_name, proposer_name, proposer_name)
        dialog = UiDialogOkCancel.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(recipient_sim_info),
            title=lambda *args, **kwargs: (
                LocalizationHelperTuning.get_raw_text(title_text)
            ),
            text=lambda *args, **kwargs: (
                LocalizationHelperTuning.get_raw_text(body_text)
            ),
            text_ok=lambda *args, **kwargs: (
                LocalizationHelperTuning.get_raw_text("接受分手")
            ),
            text_cancel=lambda *args, **kwargs: (
                LocalizationHelperTuning.get_raw_text("挽留对方")
            ),
        )

        def _on_response(response_dialog):
            try:
                if response_dialog.accepted:
                    log(
                        "player recipient accepted autonomous breakup proposer={} recipient={}",
                        proposer_sim_info.sim_id,
                        recipient_sim_info.sim_id,
                    )
                    on_accept()
                else:
                    log(
                        "player recipient pleaded against autonomous breakup proposer={} recipient={} dialog_response={}",
                        proposer_sim_info.sim_id,
                        recipient_sim_info.sim_id,
                        getattr(response_dialog, "response", None),
                    )
                    on_plead()
            except Exception:
                log_exception("autonomous breakup recipient response failed")

        dialog.show_dialog(
            on_response=_on_response,
            icon_override=IconInfoData(obj_instance=owner),
        )
        log(
            "autonomous breakup recipient response dialog shown proposer={} recipient={}",
            proposer_sim_info.sim_id,
            recipient_sim_info.sim_id,
        )
        return True
    except Exception:
        log_exception("autonomous breakup recipient response dialog failed")
        return False

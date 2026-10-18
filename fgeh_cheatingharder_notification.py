def _sim_name(sim_info):
    first_name = getattr(sim_info, "first_name", None)
    last_name = getattr(sim_info, "last_name", None)
    if first_name and last_name:
        return "{} {}".format(first_name, last_name)
    if first_name:
        return str(first_name)
    return "这个小人"


def show_claim_notification(observer_sim_info, target_sim_info):
    """Show a vanilla-style notification for a newly created directed claim."""
    from fgeh_cheatingharder_debug import log, log_exception

    try:
        from event_testing.resolver import SingleSimResolver
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog_notification import UiDialogNotification
        from distributor.shared_messages import IconInfoData

        owner = observer_sim_info.get_sim_instance()
        if owner is None:
            log(
                "claim notification skipped: observer has no live instance observer={}",
                getattr(observer_sim_info, "sim_id", None),
            )
            return False

        observer_name = _sim_name(observer_sim_info)
        target_name = _sim_name(target_sim_info)
        title = LocalizationHelperTuning.get_raw_text("新的恋爱认定")
        text = LocalizationHelperTuning.get_raw_text(
            "{} 已经把 {} 当成自己认定的唯一伴侣。".format(
                observer_name,
                target_name,
            )
        )

        notification = UiDialogNotification.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(observer_sim_info),
            title=lambda *args, **kwargs: title,
            text=lambda *args, **kwargs: text,
            information_level=UiDialogNotification.UiDialogNotificationLevel.SIM,
            visual_type=UiDialogNotification.UiDialogNotificationVisualType.INFORMATION,
        )
        notification.show_dialog(icon_override=IconInfoData(obj_instance=owner))
        log(
            "claim notification shown observer={} target={}",
            getattr(observer_sim_info, "sim_id", None),
            getattr(target_sim_info, "sim_id", None),
        )
        return True
    except Exception:
        log_exception("claim notification failed")
        return False


def show_caught_notification(observer_sim_info, partner_sim_info, rival_sim_info):
    """Show the V1 caught-in-the-act result without forcing a breakup."""
    from fgeh_cheatingharder_debug import log, log_exception

    try:
        from event_testing.resolver import SingleSimResolver
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog_notification import UiDialogNotification
        from distributor.shared_messages import IconInfoData

        owner = observer_sim_info.get_sim_instance()
        if owner is None:
            return False
        observer_name = _sim_name(observer_sim_info)
        partner_name = _sim_name(partner_sim_info)
        rival_name = _sim_name(rival_sim_info)
        title = LocalizationHelperTuning.get_raw_text("抓个正着")
        text = LocalizationHelperTuning.get_raw_text(
            "{} 抓到 {} 和 {} 进行浪漫互动，但暂时不打算放弃这段关系。".format(
                observer_name,
                partner_name,
                rival_name,
            )
        )
        notification = UiDialogNotification.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(observer_sim_info),
            title=lambda *args, **kwargs: title,
            text=lambda *args, **kwargs: text,
            information_level=UiDialogNotification.UiDialogNotificationLevel.SIM,
            visual_type=UiDialogNotification.UiDialogNotificationVisualType.INFORMATION,
        )
        notification.show_dialog(icon_override=IconInfoData(obj_instance=owner))
        log(
            "caught notification shown observer={} partner={} rival={}",
            observer_sim_info.sim_id,
            partner_sim_info.sim_id,
            rival_sim_info.sim_id,
        )
        return True
    except Exception:
        log_exception("caught notification failed")
        return False


def show_relationship_evaluation_notification(
    observer_sim_info,
    partner_sim_info,
    decision,
    execution=None,
):
    """Show one compact explanation for the explicit picker test action."""
    from fgeh_cheatingharder_debug import log_exception

    try:
        from distributor.shared_messages import IconInfoData
        from event_testing.resolver import SingleSimResolver
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog_notification import UiDialogNotification

        owner = observer_sim_info.get_sim_instance()
        if owner is None:
            return False
        decision = dict(decision or {})
        labels = {
            "wait": "\u7ef4\u6301\u73b0\u72b6",
            "repair_relationship": "\u4fee\u590d\u5173\u7cfb",
            "break_up": "\u63d0\u51fa\u5206\u624b",
            "visit_unannounced": "\u7a81\u7136\u67e5\u5c97",
        }
        scores = []
        for candidate in decision.get("candidates", ()):
            candidate = dict(candidate or {})
            intent = str(candidate.get("intent", "?"))
            if intent not in ("wait", "repair_relationship", "break_up"):
                continue
            scores.append("{} {:.1f}".format(
                labels.get(intent, intent),
                float(candidate.get("score", 0.0)),
            ))
        selected = decision.get("selected", decision.get("selected_intent"))
        execution = dict(execution or {})
        title = LocalizationHelperTuning.get_raw_text(
            "\u4e94\u7ef4\u5173\u7cfb\u590d\u8bc4\u7ed3\u679c"
        )
        if not decision:
            message = (
                "\u672a\u751f\u6210\u51b3\u7b56\u3002\u5f53\u524d\u65b9\u5411\u9700\u8981\u5df2\u5efa\u7acb\u7684"
                "\u5355\u5411\u8ba4\u5b9a\u6216\u552f\u4e00\u631a\u7231\u5173\u7cfb\u3002"
            )
        else:
            execution_text = ""
            if execution:
                status_labels = {
                    "breakup_proposal_queued": "\u5df2\u6392\u5165\u5206\u624b\u4e92\u52a8",
                    "breakup_interaction_rejected": (
                        "EA\u5206\u624b\u4e92\u52a8\u4e0d\u53ef\u7528\uff1a\u8bf7\u786e\u8ba4\u53cc\u65b9\u662f\u6b63\u5f0f\u4f34\u4fa3"
                    ),
                    "breakup_authorized_interaction_rejected": (
                        "\u62c9\u626f\u5df2\u5b8c\u6210\uff0c\u4f46EA\u672a\u80fd\u6267\u884c\u6700\u7ec8\u5206\u624b"
                    ),
                    "breakup_negotiation_relationship_retained": (
                        "\u62c9\u626f\u7ed3\u679c\uff1a\u4fdd\u7559\u5173\u7cfb"
                    ),
                    "breakup_negotiation_relationship_delayed": (
                        "\u62c9\u626f\u7ed3\u679c\uff1a\u6682\u7f13\u5206\u624b"
                    ),
                    "repair_intention_selected": "\u5df2\u9009\u62e9\u4fee\u590d\u5173\u7cfb\u610f\u56fe",
                    "reevaluation_scheduled": "\u5df2\u9009\u62e9\u7ef4\u6301\u73b0\u72b6",
                }
                status = str(execution.get("status", ""))
                execution_text = "\n\u6267\u884c\uff1a{}".format(
                    status_labels.get(status, status)
                )
            message = "{} \u2192 {}\n\u62bd\u4e2d\uff1a{}{}\n{}".format(
                _sim_name(observer_sim_info),
                _sim_name(partner_sim_info),
                labels.get(str(selected), str(selected)),
                execution_text,
                "\uff5c".join(scores),
            )
        notification = UiDialogNotification.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(observer_sim_info),
            title=lambda *args, **kwargs: title,
            text=lambda *args, **kwargs: LocalizationHelperTuning.get_raw_text(message),
            information_level=UiDialogNotification.UiDialogNotificationLevel.SIM,
            visual_type=UiDialogNotification.UiDialogNotificationVisualType.INFORMATION,
        )
        notification.show_dialog(icon_override=IconInfoData(obj_instance=owner))
        return True
    except Exception:
        log_exception("relationship evaluation notification failed")
        return False


def show_check_in_warning(visitor_sim_info, partner_sim_info):
    """Show the warning immediately before the vanilla visit is requested."""
    from fgeh_cheatingharder_debug import log, log_exception

    try:
        from event_testing.resolver import SingleSimResolver
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog_notification import UiDialogNotification
        from distributor.shared_messages import IconInfoData

        owner = partner_sim_info.get_sim_instance()
        if owner is None:
            owner = visitor_sim_info.get_sim_instance()
        if owner is None:
            log(
                "check-in warning skipped: no live owner visitor={} partner={}",
                getattr(visitor_sim_info, "sim_id", None),
                getattr(partner_sim_info, "sim_id", None),
            )
            return False

        title = LocalizationHelperTuning.get_raw_text("\u67e5\u5c97\u5373\u5c06\u5230\u6765")
        text = LocalizationHelperTuning.get_raw_text(
            "{} \u6b63\u5728\u524d\u5f80 {} \u6240\u5728\u7684\u5730\u6bb5\u3002".format(
                _sim_name(visitor_sim_info),
                _sim_name(partner_sim_info),
            )
        )
        notification = UiDialogNotification.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(partner_sim_info),
            title=lambda *args, **kwargs: title,
            text=lambda *args, **kwargs: text,
            information_level=UiDialogNotification.UiDialogNotificationLevel.SIM,
            visual_type=UiDialogNotification.UiDialogNotificationVisualType.INFORMATION,
        )
        notification.show_dialog(icon_override=IconInfoData(obj_instance=owner))
        log(
            "check-in warning shown visitor={} partner={}",
            getattr(visitor_sim_info, "sim_id", None),
            getattr(partner_sim_info, "sim_id", None),
        )
        return True
    except Exception:
        log_exception("check-in warning failed")
        return False


def show_breakup_negotiation_notification(
    proposer_sim_info,
    recipient_sim_info,
    result,
):
    """Show the single resolved tug-of-war instead of every EA retry."""
    from fgeh_cheatingharder_debug import log, log_exception

    try:
        from event_testing.resolver import SingleSimResolver
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog_notification import UiDialogNotification
        from distributor.shared_messages import IconInfoData
        from fgeh_cheatingharder_breakup_negotiation import (
            BreakupFinalDecision,
            BreakupResponse,
        )

        owner = recipient_sim_info.get_sim_instance()
        if owner is None:
            owner = proposer_sim_info.get_sim_instance()
        if owner is None:
            return False
        proposer_name = _sim_name(proposer_sim_info)
        recipient_name = _sim_name(recipient_sim_info)
        title = LocalizationHelperTuning.get_raw_text("关系走到了岔路口")
        if result.response == BreakupResponse.ACCEPT:
            message = (
                "{} 提出了分手，{} 接受了。正在等待正式关系完成解除。"
            ).format(proposer_name, recipient_name)
        elif result.response == BreakupResponse.REFUSE:
            if result.proposer_decision == BreakupFinalDecision.INSIST:
                message = (
                    "{}拒绝接受分手，但{}仍然坚持结束这段关系。"
                ).format(recipient_name, proposer_name)
            else:
                message = (
                    "{}拒绝接受分手，{}暂时没有继续坚持。"
                ).format(recipient_name, proposer_name)
        elif result.proposer_decision == BreakupFinalDecision.WITHDRAW:
            message = (
                "{} 试图挽留，{} 最终收回了分手决定。"
            ).format(recipient_name, proposer_name)
        elif result.proposer_decision == BreakupFinalDecision.DELAY:
            message = (
                "{} 请求不要现在结束，{} 决定暂时冷静一下。"
            ).format(recipient_name, proposer_name)
        else:
            message = (
                "{} 试图挽留，但 {} 仍然坚持结束这段关系。"
            ).format(recipient_name, proposer_name)
        text = LocalizationHelperTuning.get_raw_text(message)
        notification = UiDialogNotification.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(recipient_sim_info),
            title=lambda *args, **kwargs: title,
            text=lambda *args, **kwargs: text,
            information_level=(
                UiDialogNotification.UiDialogNotificationLevel.SIM
            ),
            visual_type=(
                UiDialogNotification.UiDialogNotificationVisualType.INFORMATION
            ),
        )
        notification.show_dialog(
            icon_override=IconInfoData(obj_instance=owner)
        )
        log(
            "breakup negotiation notification shown transaction={} proposer={} recipient={} outcome={}",
            result.transaction_id,
            proposer_sim_info.sim_id,
            recipient_sim_info.sim_id,
            result.outcome,
        )
        return True
    except Exception:
        log_exception("breakup negotiation notification failed")
        return False


def show_breakup_not_completed_notification(
    proposer_sim_info,
    recipient_sim_info,
):
    """Report that an authorized breakup attempt did not change EA state."""
    from fgeh_cheatingharder_debug import log, log_exception

    try:
        from event_testing.resolver import SingleSimResolver
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog_notification import UiDialogNotification
        from distributor.shared_messages import IconInfoData

        owner = recipient_sim_info.get_sim_instance()
        if owner is None:
            owner = proposer_sim_info.get_sim_instance()
        if owner is None:
            return False
        proposer_name = _sim_name(proposer_sim_info)
        recipient_name = _sim_name(recipient_sim_info)
        title = LocalizationHelperTuning.get_raw_text("分手尚未完成")
        text = LocalizationHelperTuning.get_raw_text(
            "{} 坚持提出了分手，但这次行动没有完成。{} 与 {} 目前仍是正式伴侣。".format(
                proposer_name,
                proposer_name,
                recipient_name,
            )
        )
        notification = UiDialogNotification.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(recipient_sim_info),
            title=lambda *args, **kwargs: title,
            text=lambda *args, **kwargs: text,
            information_level=(
                UiDialogNotification.UiDialogNotificationLevel.SIM
            ),
            visual_type=(
                UiDialogNotification.UiDialogNotificationVisualType.INFORMATION
            ),
        )
        notification.show_dialog(
            icon_override=IconInfoData(obj_instance=owner)
        )
        log(
            "breakup not completed notification shown proposer={} recipient={}",
            proposer_sim_info.sim_id,
            recipient_sim_info.sim_id,
        )
        return True
    except Exception:
        log_exception("breakup not completed notification failed")
        return False


def show_breakup_completed_notification(
    proposer_sim_info,
    recipient_sim_info,
):
    """Announce a breakup only after EA changed the official relationship."""
    from fgeh_cheatingharder_debug import log, log_exception

    try:
        from event_testing.resolver import SingleSimResolver
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog_notification import UiDialogNotification
        from distributor.shared_messages import IconInfoData

        owner = recipient_sim_info.get_sim_instance()
        if owner is None:
            owner = proposer_sim_info.get_sim_instance()
        if owner is None:
            return False
        proposer_name = _sim_name(proposer_sim_info)
        recipient_name = _sim_name(recipient_sim_info)
        title = LocalizationHelperTuning.get_raw_text("关系正式结束")
        text = LocalizationHelperTuning.get_raw_text(
            "{} 与 {} 已经结束了正式伴侣关系。".format(
                proposer_name,
                recipient_name,
            )
        )
        notification = UiDialogNotification.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(recipient_sim_info),
            title=lambda *args, **kwargs: title,
            text=lambda *args, **kwargs: text,
            information_level=(
                UiDialogNotification.UiDialogNotificationLevel.SIM
            ),
            visual_type=(
                UiDialogNotification.UiDialogNotificationVisualType.INFORMATION
            ),
        )
        notification.show_dialog(
            icon_override=IconInfoData(obj_instance=owner)
        )
        log(
            "breakup completed notification shown proposer={} recipient={}",
            proposer_sim_info.sim_id,
            recipient_sim_info.sim_id,
        )
        return True
    except Exception:
        log_exception("breakup completed notification failed")
        return False


def show_reconciliation_notification(
    proposer_sim_info,
    recipient_sim_info,
    result,
    official_partnership_restored=False,
):
    """Show the recipient's asymmetric answer and the official result."""
    from fgeh_cheatingharder_debug import log, log_exception

    try:
        from distributor.shared_messages import IconInfoData
        from event_testing.resolver import SingleSimResolver
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog_notification import UiDialogNotification
        from fgeh_cheatingharder_reconciliation import (
            ReconciliationResponse,
        )

        owner = proposer_sim_info.get_sim_instance()
        if owner is None:
            owner = recipient_sim_info.get_sim_instance()
        if owner is None:
            return False

        proposer_name = _sim_name(proposer_sim_info)
        recipient_name = _sim_name(recipient_sim_info)
        title = LocalizationHelperTuning.get_raw_text("复合请求有了回应")
        if official_partnership_restored:
            message = (
                "{} 接受了 {} 的复合请求。两人重新成为了正式伴侣。"
            ).format(recipient_name, proposer_name)
        elif result.response == ReconciliationResponse.ACCEPT:
            message = (
                "{} 和 {} 都愿意复合，但 EA 的正式伴侣状态没有成功恢复。"
            ).format(recipient_name, proposer_name)
        elif result.response == ReconciliationResponse.REPAIR_FIRST:
            title = LocalizationHelperTuning.get_raw_text("关系修复要求")
            case_view = None
            try:
                from fgeh_cheatingharder_repair_case_runtime import (
                    repair_case_view_for_pair,
                )

                case_view = repair_case_view_for_pair(
                    proposer_sim_info.sim_id,
                    recipient_sim_info.sim_id,
                )
            except Exception:
                log_exception("reconciliation repair case view failed")
            if (
                case_view is not None
                and case_view["responsibility_confirmed"]
            ):
                evidence_text = (
                    "这次责任方向来自恋爱账本中的明确事件证据。"
                )
            else:
                evidence_text = (
                    "目前没有足够证据判定谁有错，因此这里只把复合请求方"
                    "作为暂定执行者。"
                )
            message = (
                "{} 还没有答应复合，并向 {} 提出了修复要求："
                "点击 {}，使用原版“道歉”互动；只有道歉被接受，"
                "“真诚道歉”才算完成。当前没有截止时间，完成后可以再次"
                "提出复合。{}"
            ).format(
                recipient_name,
                proposer_name,
                recipient_name,
                evidence_text,
            )
        elif result.response == ReconciliationResponse.DEFER:
            title = LocalizationHelperTuning.get_raw_text("现在还需要一点时间")
            message = (
                "{} 没有彻底拒绝 {}，但刚刚的分手决定仍然太近。"
                "{} 想先冷静一段时间，再考虑是否重新开始。"
            ).format(
                recipient_name,
                proposer_name,
                recipient_name,
            )
        elif result.response == ReconciliationResponse.REFUSE:
            message = (
                "{} 拒绝了 {} 的复合请求，决定暂时维持分开的状态。"
            ).format(recipient_name, proposer_name)
        else:
            message = (
                "{} 想起了复合，却最终没有向 {} 开口。"
            ).format(proposer_name, recipient_name)
        text = LocalizationHelperTuning.get_raw_text(message)
        notification = UiDialogNotification.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(proposer_sim_info),
            title=lambda *args, **kwargs: title,
            text=lambda *args, **kwargs: text,
            information_level=(
                UiDialogNotification.UiDialogNotificationLevel.SIM
            ),
            visual_type=(
                UiDialogNotification.UiDialogNotificationVisualType.INFORMATION
            ),
        )
        notification.show_dialog(
            icon_override=IconInfoData(obj_instance=owner)
        )
        log(
            "reconciliation notification shown transaction={} proposer={} recipient={} response={} restored={}",
            result.transaction_id,
            proposer_sim_info.sim_id,
            recipient_sim_info.sim_id,
            result.response,
            official_partnership_restored,
        )
        return True
    except Exception:
        log_exception("reconciliation notification failed")
        return False


def show_repair_action_notification(
    actor_sim_info,
    recipient_sim_info,
    action_type,
    accepted,
):
    """Show the visible result of a concrete relationship-repair action."""
    from fgeh_cheatingharder_debug import log, log_exception

    try:
        from distributor.shared_messages import IconInfoData
        from event_testing.resolver import SingleSimResolver
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog_notification import UiDialogNotification

        owner = actor_sim_info.get_sim_instance()
        if owner is None:
            owner = recipient_sim_info.get_sim_instance()
        if owner is None:
            return False
        actor_name = _sim_name(actor_sim_info)
        recipient_name = _sim_name(recipient_sim_info)
        action_name = {
            "apology": "道歉",
            "seek_reassurance": "寻求保证",
        }.get(str(action_type), "修复关系")
        case_view = None
        try:
            from fgeh_cheatingharder_repair_case_runtime import (
                repair_case_view_for_action,
            )

            case_view = repair_case_view_for_action(
                actor_sim_info.sim_id,
                recipient_sim_info.sim_id,
            )
        except Exception:
            log_exception("repair action case view lookup failed")
        title = LocalizationHelperTuning.get_raw_text("修复关系有了回应")
        if accepted and case_view is not None and case_view["is_satisfied"]:
            message = (
                "{} 接受了 {} 的{}。“真诚道歉”修复要求已经完成，"
                "并已写入双方的关系记忆。现在可以再次尝试复合；"
                "是否答应仍由对方的五维、历史与性格决定。"
            ).format(recipient_name, actor_name, action_name)
        elif accepted:
            message = (
                "{} 接受了 {} 的{}。这次行动已写入双方的关系记忆，"
                "信任与承诺开始缓慢修复。"
            ).format(recipient_name, actor_name, action_name)
        elif case_view is not None:
            message = (
                "{} 没有接受 {} 的{}。“真诚道歉”要求仍未完成，"
                "本次尝试已经被记住；当前没有截止时间，可以稍后再试。"
            ).format(recipient_name, actor_name, action_name)
        else:
            message = (
                "{} 没有接受 {} 的{}。尝试已经被记住，"
                "但这次没有产生正向修复。"
            ).format(recipient_name, actor_name, action_name)
        text = LocalizationHelperTuning.get_raw_text(message)
        notification = UiDialogNotification.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(actor_sim_info),
            title=lambda *args, **kwargs: title,
            text=lambda *args, **kwargs: text,
            information_level=(
                UiDialogNotification.UiDialogNotificationLevel.SIM
            ),
            visual_type=(
                UiDialogNotification.UiDialogNotificationVisualType.INFORMATION
            ),
        )
        notification.show_dialog(
            icon_override=IconInfoData(obj_instance=owner)
        )
        log(
            "repair action notification shown actor={} recipient={} action={} accepted={}",
            actor_sim_info.sim_id,
            recipient_sim_info.sim_id,
            action_type,
            bool(accepted),
        )
        return True
    except Exception:
        log_exception("repair action notification failed")
        return False


def show_relationship_crisis_action_notification(
    actor_sim_info,
    partner_sim_info,
    action_type,
):
    """Make non-animated crisis choices visible without inventing an EA bit."""
    from fgeh_cheatingharder_debug import log, log_exception

    try:
        from distributor.shared_messages import IconInfoData
        from event_testing.resolver import SingleSimResolver
        from sims4.localization import LocalizationHelperTuning
        from ui.ui_dialog_notification import UiDialogNotification

        owner = actor_sim_info.get_sim_instance()
        if owner is None:
            return False
        actor_name = _sim_name(actor_sim_info)
        partner_name = _sim_name(partner_sim_info)
        if str(action_type) == "give_space":
            title_value = "关系危机：暂时留出空间"
            body_value = (
                "{} 没有立刻追问或再次提出分手，而是决定先与 {} "
                "保持一点距离。关系没有结束；这项选择已写入危机档案，"
                "稍后仍会根据双方的五维状态重新评估。"
            ).format(actor_name, partner_name)
        else:
            title_value = "关系危机有了新进展"
            body_value = "{} 对与 {} 的关系作出了新的选择。".format(
                actor_name,
                partner_name,
            )
        title = LocalizationHelperTuning.get_raw_text(title_value)
        text = LocalizationHelperTuning.get_raw_text(body_value)
        notification = UiDialogNotification.TunableFactory().default(
            owner,
            resolver=SingleSimResolver(actor_sim_info),
            title=lambda *args, **kwargs: title,
            text=lambda *args, **kwargs: text,
            information_level=(
                UiDialogNotification.UiDialogNotificationLevel.SIM
            ),
            visual_type=(
                UiDialogNotification.UiDialogNotificationVisualType.INFORMATION
            ),
        )
        notification.show_dialog(icon_override=IconInfoData(obj_instance=owner))
        log(
            "relationship crisis action notification shown actor={} partner={} action={}",
            actor_sim_info.sim_id,
            partner_sim_info.sim_id,
            action_type,
        )
        return True
    except Exception:
        log_exception("relationship crisis action notification failed")
        return False

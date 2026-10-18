"""Pure subjective narrative projection for romantic-journal entries.

The ledger stores facts, beliefs, and interpretations separately.  This
module keeps that boundary intact while preparing a compact UI-facing story:
``fact`` describes only what the viewer can know, while ``meaning`` is emitted
only when that viewer has an active interpretation.  The temporary Chinese
fallbacks accompany stable localization keys so the GFX prototype can render
before every locale has a String Table resource.
"""


NARRATIVE_SCHEMA_VERSION = 1


NARRATIVE_STRING_IDS = {
    "fgeh.journal.fact.romance.participant": 0x82C38600,
    "fgeh.journal.fact.romance.participant_unknown": 0x82C38601,
    "fgeh.journal.fact.romance.observed": 0x82C38602,
    "fgeh.journal.fact.betrayal.discovered": 0x82C38603,
    "fgeh.journal.fact.breakup.completed": 0x82C38604,
    "fgeh.journal.fact.breakup.proposed": 0x82C38605,
    "fgeh.journal.fact.breakup.updated": 0x82C38606,
    "fgeh.journal.fact.reconciliation.proposed": 0x82C38607,
    "fgeh.journal.fact.repair.updated": 0x82C38608,
    "fgeh.journal.fact.reconciliation.updated": 0x82C38609,
    "fgeh.journal.fact.generic.related": 0x82C3860A,
    "fgeh.journal.fact.generic": 0x82C3860B,
    "fgeh.journal.meaning.betrayal": 0x82C3860C,
    "fgeh.journal.meaning.positive_contact": 0x82C3860D,
    "fgeh.journal.meaning.breakup_proposal": 0x82C3860E,
    "fgeh.journal.meaning.breakup_response": 0x82C3860F,
    "fgeh.journal.meaning.breakup_resolution": 0x82C38610,
    "fgeh.journal.meaning.reconciliation_proposal": 0x82C38611,
    "fgeh.journal.meaning.reconciliation_response": 0x82C38612,
    "fgeh.journal.meaning.reconciliation_resolution": 0x82C38613,
    "fgeh.journal.meaning.repair_accepted": 0x82C38614,
    "fgeh.journal.meaning.repair_rejected": 0x82C38615,
    "fgeh.journal.meaning.only_beloved": 0x82C38616,
    "fgeh.journal.meaning.devotion_refusal": 0x82C38617,
    "fgeh.journal.meaning.known": 0x82C38618,
    "fgeh.journal.fact.crisis_response": 0x82C38619,
    "fgeh.journal.meaning.betrayal_forgiven": 0x82C3861A,
    "fgeh.journal.meaning.betrayal_endured": 0x82C3861B,
}


_ACCESS_LABELS = {
    "experienced": "亲历",
    "witnessed": "亲眼目睹",
    "confirmed": "EA确认",
    "told": "听说",
    "inferred": "推断",
    "player_asserted": "自述",
}


_BELIEF_LABELS = {
    "confirmed": "已确认",
    "believed": "相信",
    "suspected": "怀疑中",
    "disputed": "有争议",
    "disproved": "已证伪",
}


_IMPORTANCE_LABELS = {
    "major": "重要事件",
    "normal": "普通事件",
}


_BREAKUP_EVENTS = frozenset((
    "breakup_pressure",
    "breakup_proposed",
    "breakup_response",
    "breakup_negotiation_resolved",
    "breakup_declared",
    "breakup_completed",
))


_RECONCILIATION_EVENTS = frozenset((
    "reconciliation_proposed",
    "reconciliation_response",
    "reconciliation_resolved",
    "repair_action_resolved",
))


def _sim_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _participant_index(entry):
    by_role = {}
    by_id = {}
    for participant in tuple(entry.get("participants") or ()):
        if not isinstance(participant, dict):
            continue
        sim_id = _sim_id(participant.get("sim_id"))
        if sim_id <= 0:
            continue
        record = {
            "sim_id": sim_id,
            "display_name": str(
                participant.get("display_name") or "Sim {}".format(sim_id)
            ),
        }
        by_id[sim_id] = record
        for role in tuple(participant.get("roles") or ()):
            by_role.setdefault(str(role), record)
    return by_role, by_id


def _viewer_roles(viewer_id, by_role):
    return frozenset(
        role for role, participant in by_role.items()
        if participant["sim_id"] == viewer_id
    )


def _name(by_role, role):
    participant = by_role.get(role)
    return None if participant is None else participant["display_name"]


def _other_name(viewer_id, by_role, by_id, preferred_roles=()):
    for role in preferred_roles:
        participant = by_role.get(role)
        if participant is not None and participant["sim_id"] != viewer_id:
            return participant["display_name"]
    for sim_id, participant in by_id.items():
        if sim_id != viewer_id:
            return participant["display_name"]
    return None


def _known_name_for_id(sim_id, by_id):
    participant = by_id.get(_sim_id(sim_id))
    return None if participant is None else participant["display_name"]


def _knowledge_prefix(access):
    return {
        "witnessed": "我亲眼看见",
        "confirmed": "我确认",
        "told": "我听说",
        "inferred": "我怀疑",
        "player_asserted": "我记得",
    }.get(access, "我知道")


def _pair_phrase(actor_name, target_name):
    if actor_name and target_name:
        return "{} 和 {}".format(actor_name, target_name)
    return actor_name or target_name or "两个人"


def _fact_for_romance(viewer_id, viewer_roles, by_role, by_id, access):
    other_name = _other_name(
        viewer_id,
        by_role,
        by_id,
        preferred_roles=("target", "actor", "partner", "rival"),
    )
    if access == "experienced" and viewer_roles.intersection(("actor", "target")):
        if other_name:
            return (
                "fgeh.journal.fact.romance.participant",
                "我和 {} 发生了一次浪漫互动。".format(other_name),
            )
        return (
            "fgeh.journal.fact.romance.participant_unknown",
            "我参与了一次浪漫互动。",
        )
    actor_name = _name(by_role, "actor")
    target_name = _name(by_role, "target")
    return (
        "fgeh.journal.fact.romance.observed",
        "{} {} 发生了一次浪漫互动。".format(
            _knowledge_prefix(access),
            _pair_phrase(actor_name, target_name),
        ),
    )


def _fact_for_betrayal(viewer_id, by_role, by_id, access):
    partner_name = _name(by_role, "partner")
    rival_name = _name(by_role, "rival")
    if partner_name or rival_name:
        pair = _pair_phrase(partner_name, rival_name)
    else:
        pair = _pair_phrase(_name(by_role, "actor"), _name(by_role, "target"))
    if pair == "两个人":
        other_name = _other_name(viewer_id, by_role, by_id)
        pair = other_name or pair
    return (
        "fgeh.journal.fact.betrayal.discovered",
        "{} {} 发生了越过关系边界的浪漫互动。".format(
            _knowledge_prefix(access),
            pair,
        ),
    )


def _fact_for_breakup(viewer_id, viewer_roles, by_role, by_id, access, event_type):
    other_name = _other_name(
        viewer_id,
        by_role,
        by_id,
        preferred_roles=("target", "actor", "partner"),
    )
    if event_type == "breakup_completed":
        if other_name and viewer_roles.intersection(("actor", "target", "partner")):
            text = "我和 {} 的恋爱关系结束了。".format(other_name)
        else:
            text = "{} 一段恋爱关系已经结束。".format(
                _knowledge_prefix(access)
            )
        return "fgeh.journal.fact.breakup.completed", text
    if event_type in ("breakup_proposed", "breakup_declared"):
        actor_name = _name(by_role, "actor")
        target_name = _name(by_role, "target")
        if viewer_id == _sim_id((by_role.get("actor") or {}).get("sim_id")):
            text = "我向 {} 提出了分手。".format(other_name or "对方")
        elif viewer_id == _sim_id((by_role.get("target") or {}).get("sim_id")):
            text = "{} 向我提出了分手。".format(other_name or "对方")
        else:
            text = "{} {} 之间有人提出了分手。".format(
                _knowledge_prefix(access),
                _pair_phrase(actor_name, target_name),
            )
        return "fgeh.journal.fact.breakup.proposed", text
    return (
        "fgeh.journal.fact.breakup.updated",
        "{} 这段关系的分手协商有了新进展。".format(
            _knowledge_prefix(access)
        ),
    )


def _fact_for_reconciliation(viewer_id, viewer_roles, by_role, by_id, access, event_type):
    other_name = _other_name(
        viewer_id,
        by_role,
        by_id,
        preferred_roles=("target", "actor", "partner"),
    )
    if event_type == "reconciliation_proposed":
        actor = by_role.get("actor") or {}
        target = by_role.get("target") or {}
        if viewer_id == _sim_id(actor.get("sim_id")):
            text = "我向 {} 提出了复合。".format(other_name or "对方")
        elif viewer_id == _sim_id(target.get("sim_id")):
            text = "{} 向我提出了复合。".format(other_name or "对方")
        else:
            text = "{} 有人尝试重新开始一段关系。".format(
                _knowledge_prefix(access)
            )
        return "fgeh.journal.fact.reconciliation.proposed", text
    if event_type == "repair_action_resolved":
        return (
            "fgeh.journal.fact.repair.updated",
            "{} 这段关系出现了一次修复行动。".format(
                _knowledge_prefix(access)
            ),
        )
    return (
        "fgeh.journal.fact.reconciliation.updated",
        "{} 这段关系的复合尝试有了新进展。".format(
            _knowledge_prefix(access)
        ),
    )


def _counterpart_response_sentence(
    response,
    other_name,
    viewer_is_responder,
):
    injured_text = {
        "gave_reassurance": "{} 给了我明确的保证。",
        "evaded_reassurance": "{} 的回答很含糊。",
        "refused_reassurance": "{} 拒绝给我安慰或保证。",
        "apologized": "{} 为这次越界向我道歉了。",
        "deflected": "{} 回避了责任。",
        "counterattacked": "{} 反过来指责了我。",
        "withdrew": "{} 退出了这次谈话。",
        "reciprocated_closeness": "{} 回应了我的靠近。",
        "accepted_cautiously": "{} 接受了我的靠近，但仍很谨慎。",
        "pulled_away": "{} 随后又和我拉开了距离。",
    }
    responder_text = {
        "gave_reassurance": "我向 {} 作出了明确保证。",
        "evaded_reassurance": "我没有正面回答 {}。",
        "refused_reassurance": "我拒绝给 {} 安慰或保证。",
        "apologized": "我为这次越界向 {} 道歉了。",
        "deflected": "我回避了 {} 对我的追问。",
        "counterattacked": "我反过来指责了 {}。",
        "withdrew": "我退出了和 {} 的这次谈话。",
        "reciprocated_closeness": "我回应了 {} 的靠近。",
        "accepted_cautiously": "我接受了 {} 的靠近，但仍很谨慎。",
        "pulled_away": "我随后又和 {} 拉开了距离。",
    }
    template = (
        responder_text if viewer_is_responder else injured_text
    ).get(str(response or ""))
    if not template:
        return ""
    return template.format(other_name)


def _fact_for_crisis_response(viewer_id, by_role, by_id, entry):
    tokens = dict(entry.get("tokens") or {})
    intent = str(tokens.get("intent") or "")
    status = str(tokens.get("status") or "")
    viewer_roles = _viewer_roles(viewer_id, by_role)
    viewer_is_responder = bool(
        viewer_roles.intersection(("target", "partner"))
        and "observer" not in viewer_roles
    )
    other_name = _other_name(
        viewer_id,
        by_role,
        by_id,
        preferred_roles=("partner", "target", "rival"),
    ) or "对方"
    completed = status in (
        "interaction_succeeded",
        "internal_choice_completed",
    )
    if viewer_is_responder and intent == "seek_reassurance":
        text = "{} 向我寻求了安慰与保证。".format(other_name)
    elif viewer_is_responder and intent == "cling_to_partner":
        text = "{} 在关系危机后主动靠近了我。".format(other_name)
    elif viewer_is_responder and intent == "confront_partner":
        text = "{} 因那次越界当面质问了我。".format(other_name)
    elif viewer_is_responder and intent == "confront_rival":
        text = "{} 因那次关系事件当面质问了我。".format(other_name)
    elif intent == "forgive_partner":
        text = "我决定暂时原谅 {}。".format(other_name)
    elif intent == "endure_silently":
        text = "我选择暂时沉默，没有立刻采取行动。"
    elif intent == "seek_reassurance":
        text = (
            "我向 {} 寻求了安慰与保证。"
            if completed
            else "我试着向 {} 寻求安慰，但没有得到想要的回应。"
        ).format(other_name)
    elif intent == "cling_to_partner":
        text = (
            "我主动靠近并挽留了 {}。"
            if completed
            else "我试着靠近 {}，但这次没有成功。"
        ).format(other_name)
    elif intent == "confront_partner":
        text = (
            "我当面质问了 {}。"
            if completed
            else "我想质问 {}，但这次没有说出口。"
        ).format(other_name)
    elif intent == "confront_rival":
        text = (
            "我当面质问了这次事件中的第三者 {}。"
            if completed
            else "我想质问第三者 {}，但这次没有成功。"
        ).format(other_name)
    else:
        text = "我对这次关系危机作出了回应。"
    response_text = _counterpart_response_sentence(
        tokens.get("counterpart_response"),
        other_name,
        viewer_is_responder,
    )
    if completed and response_text:
        text = "{} {}".format(text, response_text)
    return "fgeh.journal.fact.crisis_response", text


def _build_fact(viewer_id, entry, by_role, by_id):
    event_type = str(entry.get("event_type") or "")
    knowledge = entry.get("knowledge") or {}
    access = str(knowledge.get("access") or "")
    viewer_roles = _viewer_roles(viewer_id, by_role)
    if event_type == "romance_completed":
        return _fact_for_romance(
            viewer_id, viewer_roles, by_role, by_id, access
        )
    if event_type in (
        "caught_cheating",
        "affair_secret_discovered",
        "romantic_boundary_discovered",
    ):
        return _fact_for_betrayal(viewer_id, by_role, by_id, access)
    if event_type in _BREAKUP_EVENTS:
        return _fact_for_breakup(
            viewer_id, viewer_roles, by_role, by_id, access, event_type
        )
    if event_type in _RECONCILIATION_EVENTS:
        return _fact_for_reconciliation(
            viewer_id, viewer_roles, by_role, by_id, access, event_type
        )
    if event_type == "autonomous_action_resolved":
        return _fact_for_crisis_response(
            viewer_id, by_role, by_id, entry
        )
    other_name = _other_name(viewer_id, by_role, by_id)
    if other_name:
        return (
            "fgeh.journal.fact.generic.related",
            "{} 发生了一件与 {} 有关的恋爱事件。".format(
                _knowledge_prefix(access),
                other_name,
            ),
        )
    return (
        "fgeh.journal.fact.generic",
        "{} 发生了一件恋爱事件。".format(_knowledge_prefix(access)),
    )


def _primary_interpretation(entry):
    interpretation = entry.get("interpretation") or {}
    items = tuple(interpretation.get("items") or ())
    for item in items:
        if isinstance(item, dict) and item.get("active", True):
            return item
    primary_type = interpretation.get("primary_type")
    if primary_type:
        return {
            "interpretation_type": str(primary_type),
            "details": {},
        }
    return None


def _build_meaning(viewer_id, entry, by_role, by_id):
    item = _primary_interpretation(entry)
    if item is None:
        return None, "", ()
    interpretation_type = str(item.get("interpretation_type") or "")
    details = item.get("details") or {}
    partner_name = _known_name_for_id(details.get("partner_id"), by_id)
    partner_name = partner_name or _name(by_role, "partner")
    other_name = partner_name or _other_name(viewer_id, by_role, by_id)
    templates = {
        "betrayal_responsibility_attribution": (
            "fgeh.journal.meaning.betrayal",
            "我觉得 {} 背叛了我，对这段关系的信任发生了动摇。".format(
                other_name or "对方"
            ),
        ),
        "positive_romantic_contact": (
            "fgeh.journal.meaning.positive_contact",
            "这次互动让我重新感受到我们之间的亲近。",
        ),
        "breakup_proposal_meaning": (
            "fgeh.journal.meaning.breakup_proposal",
            "我意识到这段关系已经走到了需要作出决定的时刻。",
        ),
        "breakup_response_meaning": (
            "fgeh.journal.meaning.breakup_response",
            "对这次回应，我还在判断这段关系是否值得继续。",
        ),
        "breakup_resolution_meaning": (
            "fgeh.journal.meaning.breakup_resolution",
            "这次协商改变了我对这段关系未来的看法。",
        ),
        "reconciliation_proposal_meaning": (
            "fgeh.journal.meaning.reconciliation_proposal",
            "我开始考虑，我们是否还能重新开始。",
        ),
        "reconciliation_response_meaning": (
            "fgeh.journal.meaning.reconciliation_response",
            "这次回应让我重新衡量彼此之间还剩下什么。",
        ),
        "reconciliation_resolution_meaning": (
            "fgeh.journal.meaning.reconciliation_resolution",
            "这次结果决定了我们是否愿意再次走到一起。",
        ),
        "repair_effort_was_accepted": (
            "fgeh.journal.meaning.repair_accepted",
            "我愿意把这次行动看作修复关系的一步。",
        ),
        "repair_effort_was_rejected": (
            "fgeh.journal.meaning.repair_rejected",
            "我还不能把这次行动当作真正的修复。",
        ),
        "only_beloved": (
            "fgeh.journal.meaning.only_beloved",
            "我仍然认定，对方是自己唯一的挚爱。",
        ),
        "devotion_refusal": (
            "fgeh.journal.meaning.devotion_refusal",
            "我无法接受把感情交给认定之人以外的对象。",
        ),
        "betrayal_forgiven": (
            "fgeh.journal.meaning.betrayal_forgiven",
            "我愿意先把关系保留下来，但受损的信任仍需要修复。",
        ),
        "betrayal_endured_silently": (
            "fgeh.journal.meaning.betrayal_endured",
            "我没有把受伤说出口，这件事仍留在我心里。",
        ),
    }
    template_key, text = templates.get(interpretation_type, (
        "fgeh.journal.meaning.known",
        "这件事改变了我对这段关系的看法。",
    ))
    return template_key, text, (interpretation_type,)


def _severity_label(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0
    if value >= 75.0:
        return "重大"
    if value >= 50.0:
        return "严重"
    if value >= 25.0:
        return "明显"
    return "轻微"


def _is_unresolved(entry):
    related = entry.get("related_cases") or {}
    return bool(
        related.get("repair_cases")
        or related.get("relationship_crises")
        or entry.get("processing_status") in ("unprocessed", "reopened")
    )


def build_journal_entry_narrative(viewer, entry):
    """Return a JSON-safe first-person narrative for one known event."""
    viewer_id = _sim_id((viewer or {}).get("sim_id"))
    by_role, by_id = _participant_index(entry)
    fact_key, fact_text = _build_fact(viewer_id, entry, by_role, by_id)
    meaning_key, meaning_text, meaning_tokens = _build_meaning(
        viewer_id, entry, by_role, by_id
    )
    knowledge = entry.get("knowledge") or {}
    access = knowledge.get("access")
    belief_state = knowledge.get("belief_state")
    unresolved = _is_unresolved(entry)
    badges = [
        {
            "key": "access:{}".format(access or "unknown"),
            "label": _ACCESS_LABELS.get(access, "已知"),
        },
        {
            "key": "belief:{}".format(belief_state or "unknown"),
            "label": _BELIEF_LABELS.get(belief_state, "认知中"),
        },
        {
            "key": "category:{}".format(entry.get("category") or "unknown"),
            "label": str(entry.get("category_label") or "其他记录"),
        },
    ]
    if unresolved:
        badges.append({"key": "status:unresolved", "label": "未解决"})
    return {
        "schema_version": NARRATIVE_SCHEMA_VERSION,
        "viewpoint_sim_id": viewer_id,
        "headline": str(entry.get("title") or "记录了一件恋爱事件"),
        "headline_key": str(entry.get("title_key") or ""),
        "fact": {
            "template_key": fact_key,
            "string_id": NARRATIVE_STRING_IDS.get(fact_key),
            "text": fact_text,
            "tokens": dict(entry.get("tokens") or {}),
        },
        "meaning": {
            "available": bool(meaning_text),
            "template_key": meaning_key,
            "string_id": NARRATIVE_STRING_IDS.get(meaning_key),
            "text": meaning_text,
            "tokens": list(meaning_tokens),
        },
        "knowledge": {
            "access": access,
            "access_label": _ACCESS_LABELS.get(access, "已知"),
            "belief_state": belief_state,
            "belief_label": _BELIEF_LABELS.get(belief_state, "认知中"),
            "confidence": knowledge.get("confidence"),
        },
        "category": {
            "key": entry.get("category"),
            "label": entry.get("category_label"),
        },
        "importance": {
            "key": entry.get("importance"),
            "label": _IMPORTANCE_LABELS.get(
                entry.get("importance"), "普通事件"
            ),
        },
        "severity": {
            "value": entry.get("severity", 0.0),
            "label": _severity_label(entry.get("severity", 0.0)),
        },
        "unresolved": unresolved,
        "badges": badges,
    }

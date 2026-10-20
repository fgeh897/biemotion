"""Read-only EA Notebook bridge for the romantic event ledger.

The pure blueprint builder is testable outside The Sims 4.  Runtime imports
stay inside ``show_romantic_journal`` so this module never makes the browser
viewer or unit tests depend on game-only modules.
"""

from fgeh_cheatingharder_ui_adapter import (
    build_character_journal_view,
    build_character_relationships_view,
)


NOTEBOOK_BRIDGE_SCHEMA_VERSION = 1
ROMANTIC_SUBCATEGORY_ID = 0xF6E10001
ROMANTIC_RELATIONSHIP_SUBCATEGORY_ID = 0xF6E10000


TEXT_IDS = {
    "title": 0x24C91E6B,
    "description": 0xF226468B,
    "relationships": 0x7B6A10D1,
    "relationships_description": 0x7B6A10D2,
    "known": 0x93DD26BC,
    "known_description": 0xCF7B02D7,
    "empty": 0x3C4CBE32,
    "generic": 0x4A417C76,
}


ACCESS_LABELS = {
    "experienced": "亲身经历",
    "witnessed": "亲眼所见",
    "confirmed": "已经确认",
    "told": "从别人那里听说",
    "inferred": "根据线索推测",
    "player_asserted": "由玩家补充",
}


def _stable_uint64(value):
    result = 0xCBF29CE484222325
    for byte in str(value).encode("utf-8"):
        result = ((result * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF) ^ byte
    return result or 1


def _entry_description(entry):
    lines = []
    participants = [
        value.get("display_name")
        for value in entry.get("participants", ())
        if value.get("display_name")
    ]
    if participants:
        lines.append("涉及角色：{}".format("、".join(participants)))

    knowledge = entry.get("knowledge", {})
    access = ACCESS_LABELS.get(
        knowledge.get("access"),
        "得知了这件事",
    )
    confidence = knowledge.get("confidence")
    if confidence is None:
        lines.append("获知方式：{}".format(access))
    else:
        lines.append(
            "获知方式：{}；确信度：{}%".format(
                access,
                int(round(float(confidence) * 100)),
            )
        )

    interpretation = entry.get("interpretation", {})
    if interpretation.get("primary_type"):
        lines.append("这名小人已经形成了自己的理解。")

    cases = entry.get("related_cases", {})
    crises = list(cases.get("relationship_crises", ()))
    repairs = list(cases.get("repair_cases", ()))
    if crises:
        severity = max(float(value.get("severity", 0)) for value in crises)
        lines.append("仍有关联的关系危机，严重度 {}。".format(int(round(severity))))
    if repairs:
        lines.append("仍有关联的关系修复事务。")
    return "\n".join(lines) or "这是一条已经进入小人记忆的恋爱事件。"


def _direction_description(direction):
    values = []
    for dimension in direction.get("dimensions", ()):
        value = dimension.get("value")
        if value is None:
            continue
        values.append("{} {}".format(
            dimension.get("label", dimension.get("key", "状态")),
            int(round(float(value))),
        ))
    if not values:
        values.append("尚未形成稳定判断")
    return "{}：{}".format(
        direction.get("direction_label", "关系状态"),
        " · ".join(values),
    )


def _relationship_description(relationship):
    lines = [
        _direction_description(direction)
        for direction in relationship.get("directions", ())
    ]
    status = relationship.get("status", {})
    if status.get("relationship_crisis") is not None:
        lines.append("当前状态：关系危机进行中")
    if status.get("repair_case") is not None:
        lines.append("当前状态：正在修复关系")
    return "\n".join(lines)


def build_notebook_blueprint(
    viewer_sim,
    store=None,
    sim_directory=None,
):
    """Translate the safe journal ViewModel into an EA-Notebook-shaped dict."""
    journal = build_character_journal_view(
        viewer_sim,
        store=store,
        sim_directory=sim_directory,
    )
    relationship_view = build_character_relationships_view(
        viewer_sim,
        store=store,
        sim_directory=sim_directory,
    )
    relationship_entries = []
    viewer_id = journal["viewer"]["sim_id"]
    for relationship in relationship_view["relationships"]:
        partner = relationship["pair"]["sim_b"]
        relationship_entries.append({
            "entry_id": _stable_uint64(
                "relationship:{}:{}".format(viewer_id, partner["sim_id"])
            ),
            "entry_kind": "relationship",
            "partner_id": partner["sim_id"],
            "title": partner["display_name"],
            "title_id": None,
            "description": _relationship_description(relationship),
            "new_entry": False,
        })

    event_entries = []
    for value in journal["entries"]:
        event_entries.append({
            "entry_id": _stable_uint64(value["entry_id"]),
            "entry_kind": "event",
            "event_id": value["event_id"],
            "event_type": value["event_type"],
            "title": value.get("title") or "恋爱记忆",
            "title_id": value.get("title_string_id") or TEXT_IDS["generic"],
            "description": _entry_description(value),
            "new_entry": False,
        })
    return {
        "schema_version": NOTEBOOK_BRIDGE_SCHEMA_VERSION,
        "view_kind": "ea_notebook_blueprint",
        "viewer": journal["viewer"],
        "title": "恋爱日记",
        "title_id": TEXT_IDS["title"],
        "description": "只显示这名小人亲历、目击、听说或推断出的恋爱事件。",
        "description_id": TEXT_IDS["description"],
        "subcategories": [
            {
                "subcategory_id": ROMANTIC_RELATIONSHIP_SUBCATEGORY_ID,
                "name": "我的关系",
                "name_id": TEXT_IDS["relationships"],
                "description": "当前小人参与并被恋爱账本记录的关系。",
                "description_id": TEXT_IDS["relationships_description"],
                "entry_type": 1,
                "entries": relationship_entries,
            },
            {
                "subcategory_id": ROMANTIC_SUBCATEGORY_ID,
                "name": "我知道的事",
                "name_id": TEXT_IDS["known"],
                "description": "这些内容来自当前小人自己的认知，不是玩家全知视角。",
                "description_id": TEXT_IDS["known_description"],
                "entry_type": 1,
                "entries": event_entries,
            },
        ],
        "total_relationships": len(relationship_entries),
        "total_events": len(event_entries),
        "total_entries": len(relationship_entries) + len(event_entries),
    }


def _runtime_sim_info(value):
    return getattr(value, "sim_info", value)


def _localized_string(string_id):
    import sims4.localization

    return sims4.localization._create_localized_string(int(string_id))


def _raw_text(value):
    from sims4.localization import LocalizationHelperTuning

    return LocalizationHelperTuning.get_raw_text(str(value))


def _runtime_sim_directory(blueprint):
    import services

    manager = services.sim_info_manager()
    if manager is None:
        return {}
    result = {}
    for subcategory in blueprint.get("subcategories", ()):
        for entry in subcategory.get("entries", ()):
            sim_id = entry.get("partner_id")
            if sim_id is None or sim_id in result:
                continue
            sim_info = manager.get(int(sim_id))
            if sim_info is None:
                continue
            name = " ".join(
                str(value)
                for value in (
                    getattr(sim_info, "first_name", None),
                    getattr(sim_info, "last_name", None),
                )
                if value
            )
            if name:
                result[int(sim_id)] = name
    return result


def _message_has_romantic_category(message):
    for category in message.categories:
        if getattr(category, "enum_name", "") == "FGEH_ROMANTIC_LEDGER":
            return True
    return False


def _set_notebook_entry_field(entry, field_name, value):
    try:
        setattr(entry, field_name, value)
        return True
    except Exception:
        from fgeh_cheatingharder_debug import log_exception

        log_exception(
            "romantic journal entry field failed field={}".format(field_name)
        )
        return False


def append_romantic_journal_category(message, viewer_sim):
    """Append the read-only journal to an existing EA NotebookView message."""
    from distributor.rollback import ProtocolBufferRollback

    sim_info = _runtime_sim_info(viewer_sim)
    blueprint = build_notebook_blueprint(sim_info)
    sim_directory = _runtime_sim_directory(blueprint)
    if sim_directory:
        blueprint = build_notebook_blueprint(
            sim_info,
            sim_directory=sim_directory,
        )
    if _message_has_romantic_category(message):
        return blueprint

    with ProtocolBufferRollback(message.categories) as category:
        category.enum_name = "FGEH_ROMANTIC_LEDGER"
        category.category_name = _localized_string(blueprint["title_id"])
        category.display_subcategory_title = True
        for subcategory_data in blueprint["subcategories"]:
            with ProtocolBufferRollback(category.subcategories) as subcategory:
                subcategory.subcategory_id = int(
                    subcategory_data["subcategory_id"]
                )
                subcategory.subcategory_name = _localized_string(
                    subcategory_data["name_id"]
                )
                subcategory.subcategory_tooltip = _localized_string(
                    subcategory_data["description_id"]
                )
                if hasattr(subcategory, "entry_type"):
                    subcategory.entry_type = int(
                        subcategory_data.get("entry_type", 1)
                    )
                else:
                    subcategory.is_sortable = False
                    subcategory.is_new_entry_sortable = False
                    subcategory.max_num_entries = len(
                        subcategory_data["entries"]
                    )
                for entry_data in subcategory_data["entries"]:
                    entry = subcategory.entries.add()
                    _set_notebook_entry_field(
                        entry,
                        "entry_id",
                        int(entry_data["entry_id"]),
                    )
                    if entry_data.get("title_id") is None:
                        entry_message = _raw_text(entry_data["title"])
                    else:
                        entry_message = _localized_string(
                            entry_data["title_id"]
                        )
                    _set_notebook_entry_field(
                        entry,
                        "entry_message",
                        entry_message,
                    )
                    _set_notebook_entry_field(
                        entry,
                        "entry_message_description",
                        _raw_text(entry_data["description"]),
                    )
                    if hasattr(entry, "new_entry"):
                        _set_notebook_entry_field(
                            entry,
                            "new_entry",
                            False,
                        )

    from fgeh_cheatingharder_debug import log

    log(
        "romantic journal appended viewer={} relationships={} events={}",
        getattr(sim_info, "sim_id", getattr(sim_info, "id", None)),
        blueprint.get("total_relationships", 0),
        blueprint.get("total_events", 0),
    )
    try:
        appended = message.categories[-1]
        log(
            "romantic journal protocol category_fields={} subcategories={}",
            tuple(field.name for field, _value in appended.ListFields()),
            len(appended.subcategories),
        )
        for index, subcategory in enumerate(appended.subcategories):
            entries = tuple(subcategory.entries)
            log(
                "romantic journal protocol subcategory={} id={} entry_type={} "
                "fields={} entries={} first_entry_fields={}",
                index,
                getattr(subcategory, "subcategory_id", None),
                getattr(subcategory, "entry_type", None),
                tuple(
                    field.name for field, _value in subcategory.ListFields()
                ),
                len(entries),
                (
                    ()
                    if not entries
                    else tuple(
                        field.name for field, _value in entries[0].ListFields()
                    )
                ),
            )
    except Exception:
        from fgeh_cheatingharder_debug import log_exception

        log_exception("romantic journal protocol diagnostics failed")
    return blueprint


def show_romantic_journal(viewer_sim):
    """Send one temporary, read-only romantic journal to the EA Notebook UI."""
    from distributor.ops import GenericProtocolBufferOp
    from distributor.system import Distributor
    from protocolbuffers import UI_pb2
    from protocolbuffers.DistributorOps_pb2 import Operation

    sim_info = _runtime_sim_info(viewer_sim)
    message = UI_pb2.NotebookView()
    tracker = getattr(sim_info, "notebook_tracker", None)
    message.notes = str(getattr(tracker, "_notes", "") or "")
    message.selected_category_index = 0
    message.selected_subcategory_index = 0
    message.open_page = True
    blueprint = append_romantic_journal_category(message, sim_info)

    operation = GenericProtocolBufferOp(Operation.NOTEBOOK_VIEW, message)
    Distributor.instance().add_op(sim_info, operation)
    return blueprint

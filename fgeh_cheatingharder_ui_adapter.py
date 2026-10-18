"""Read-only, versioned view models for romantic-ledger user interfaces.

The adapter is deliberately importable outside The Sims 4.  Runtime-only
modules are imported lazily when a caller does not supply a memory store.
Every public result contains JSON-safe primitive values only.
"""

from fgeh_cheatingharder_dimension_registry import DIMENSION_DEFINITIONS
from fgeh_cheatingharder_journal_catalog import (
    CATEGORY_LABELS,
    JournalCategory,
    JournalImportance,
    JournalVisibility,
    SEMANTIC_TAGS,
    get_journal_event_definition,
    get_journal_presentation,
)
from fgeh_cheatingharder_journal_narrative import (
    build_journal_entry_narrative,
)
from fgeh_cheatingharder_memory_models import (
    AcquisitionMode,
    BeliefStatus,
    DIRECTED_DIMENSIONS,
    copy_primitive,
)


UI_SCHEMA_VERSION = 3
DEFAULT_PAGE_SIZE = 40
MAX_PAGE_SIZE = 100
DEFAULT_JOURNAL_HOME_RELATIONSHIPS = 3
DEFAULT_JOURNAL_HOME_EVENTS = 3


_ACCESS_PRESENTATION = {
    AcquisitionMode.PARTICIPANT: ("experienced", "firsthand"),
    AcquisitionMode.EYEWITNESS: ("witnessed", "firsthand"),
    AcquisitionMode.EA_CONFIRMED: ("confirmed", "game_confirmed"),
    AcquisitionMode.TOLD: ("told", "hearsay"),
    AcquisitionMode.INFERRED: ("inferred", "inference"),
    AcquisitionMode.PLAYER_ASSERTED: ("player_asserted", "player"),
}


_ACQUISITION_STRENGTH = {
    AcquisitionMode.PARTICIPANT: 60,
    AcquisitionMode.EYEWITNESS: 50,
    AcquisitionMode.EA_CONFIRMED: 40,
    AcquisitionMode.TOLD: 30,
    AcquisitionMode.INFERRED: 20,
    AcquisitionMode.PLAYER_ASSERTED: 10,
}


_BELIEF_STRENGTH = {
    BeliefStatus.CONFIRMED: 50,
    BeliefStatus.BELIEVED: 40,
    BeliefStatus.SUSPECTED: 30,
    BeliefStatus.DISPUTED: 20,
    BeliefStatus.DISPROVED: 10,
}


_DISPLAY_TOKEN_KEYS = frozenset((
    "accepted",
    "action_type",
    "cause_type",
    "counterpart_response",
    "decision_source",
    "expression_type",
    "execution_strategy",
    "intent",
    "outcome",
    "response",
    "result",
    "selection_mode",
    "status",
))


def _resolve_store(store):
    if store is not None:
        return store
    from fgeh_cheatingharder_memory_runtime import get_memory_service

    return get_memory_service().store


def _sim_info(value):
    if value is None:
        return None
    return getattr(value, "sim_info", value)


def _sim_id(value):
    value = _sim_info(value)
    if isinstance(value, dict):
        value = value.get("sim_id", value.get("id"))
    else:
        value = getattr(value, "sim_id", getattr(value, "id", value))
    try:
        value = int(value)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def _directory_names(sim_directory):
    names = {}
    if isinstance(sim_directory, dict):
        values = sim_directory.items()
    else:
        values = (
            (
                record.get("sim_id", record.get("id")),
                record.get("display_name", record.get("name")),
            )
            for record in tuple(sim_directory or ())
            if isinstance(record, dict)
        )
    for sim_id, name in values:
        try:
            sim_id = int(sim_id)
        except (TypeError, ValueError):
            continue
        if sim_id > 0 and name:
            names[sim_id] = str(name)
    return names


def _sim_name(value, sim_directory=None):
    info = _sim_info(value)
    if isinstance(info, dict):
        direct_name = info.get("display_name", info.get("name"))
    else:
        first_name = getattr(info, "first_name", None)
        last_name = getattr(info, "last_name", None)
        direct_name = " ".join(
            str(part) for part in (first_name, last_name) if part
        )
        direct_name = direct_name or getattr(info, "full_name", None)
        direct_name = direct_name or getattr(info, "name", None)
    if direct_name:
        return str(direct_name)
    sim_id = _sim_id(value)
    directory_name = _directory_names(sim_directory).get(sim_id)
    return directory_name or "Sim {}".format(sim_id)


def _identity(value, sim_directory=None):
    sim_id = _sim_id(value)
    if sim_id <= 0:
        raise ValueError("A UI view requires a valid Sim id")
    return {
        "sim_id": sim_id,
        "display_name": _sim_name(value, sim_directory=sim_directory),
    }


def _identity_by_id(sim_id, sim_directory=None):
    return _identity(int(sim_id), sim_directory=sim_directory)


def _percent(value, default=0.0):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = float(default)
    return max(0.0, min(100.0, value))


def _event_presentation(event):
    event_definition = get_journal_event_definition(event.event_type)
    definition = get_journal_presentation(event.event_type)
    payload = dict(getattr(event, "payload", {}) or {})
    category = str(payload.get(
        "primary_category",
        definition.primary_category,
    ))
    if category not in JournalCategory.ALL:
        category = definition.primary_category
    tags = list(event_definition.semantic_tags)
    instance_tags = payload.get("semantic_tags", ())
    if isinstance(instance_tags, str):
        instance_tags = (instance_tags,)
    for tag in tuple(instance_tags or ()):
        tag = str(tag)
        if tag in SEMANTIC_TAGS and tag not in tags:
            tags.append(tag)
    visibility = str(payload.get(
        "journal_visibility",
        definition.visibility,
    ))
    if visibility not in JournalVisibility.ALL:
        visibility = definition.visibility
    importance = str(payload.get(
        "journal_importance",
        definition.importance,
    ))
    if importance not in JournalImportance.ALL:
        importance = definition.importance
    return {
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "semantic_tags": tags,
        "visibility": visibility,
        "importance": importance,
        "severity": _percent(getattr(event, "severity", 0.0)),
        "salience": _percent(
            payload.get("salience", definition.default_salience),
            default=definition.default_salience,
        ),
        "title_key": definition.title_key,
        "summary_key": definition.summary_key,
        "detail_key": definition.detail_key,
        "icon_key": definition.icon_key,
        "title_string_id": definition.title_string_id,
        "title": str(payload.get(
            "journal_title",
            definition.default_title,
        )),
    }


def _participants(event, sim_directory=None, known_sim_ids=None):
    known_sim_ids = (
        None
        if known_sim_ids is None
        else set(int(value) for value in known_sim_ids)
    )
    records = {}
    order = []
    for role, sim_ids in getattr(event, "participants", {}).items():
        for sim_id in tuple(sim_ids or ()):
            sim_id = int(sim_id)
            if known_sim_ids is not None and sim_id not in known_sim_ids:
                continue
            if sim_id not in records:
                records[sim_id] = {
                    "sim_id": sim_id,
                    "display_name": _sim_name(
                        sim_id,
                        sim_directory=sim_directory,
                    ),
                    "roles": [],
                }
                order.append(sim_id)
            if str(role) not in records[sim_id]["roles"]:
                records[sim_id]["roles"].append(str(role))
    return [records[sim_id] for sim_id in order]


def _display_tokens(event, participants):
    tokens = {
        "event_type": str(event.event_type),
    }
    for participant in participants:
        for role in participant["roles"]:
            tokens.setdefault("{}_sim_id".format(role), participant["sim_id"])
            tokens.setdefault("{}_name".format(role), participant["display_name"])
    for key, value in getattr(event, "payload", {}).items():
        if key in _DISPLAY_TOKEN_KEYS and isinstance(
            value,
            (str, int, float, bool, type(None)),
        ):
            tokens[key] = value
    return tokens


def _belief_view(belief, sim_directory=None):
    access, source = _ACCESS_PRESENTATION.get(
        belief.acquisition_mode,
        (str(belief.acquisition_mode), "unknown"),
    )
    return {
        "belief_id": belief.belief_id,
        "claim_id": belief.claim_id,
        "access": access,
        "source": source,
        "acquisition_mode": belief.acquisition_mode,
        "belief_state": belief.status,
        "credibility": round(float(belief.credibility) / 100.0, 4),
        "confidence": round(float(belief.confidence) / 100.0, 4),
        "source_sim": (
            None
            if belief.source_sim_id is None
            else _identity_by_id(
                belief.source_sim_id,
                sim_directory=sim_directory,
            )
        ),
        "acquired_at": copy_primitive(belief.acquired_at),
    }


def _knowledge_view(beliefs, sim_directory=None):
    ordered = sorted(beliefs, key=lambda value: value.sequence, reverse=True)
    items = [
        _belief_view(value, sim_directory=sim_directory)
        for value in ordered
    ]
    primary_belief = max(
        ordered,
        key=lambda value: (
            _ACQUISITION_STRENGTH.get(value.acquisition_mode, 0),
            _BELIEF_STRENGTH.get(value.status, 0),
            float(value.confidence),
            value.sequence,
        ),
    ) if ordered else None
    primary = (
        None
        if primary_belief is None
        else _belief_view(primary_belief, sim_directory=sim_directory)
    )
    return {
        "access": None if primary is None else primary["access"],
        "source": None if primary is None else primary["source"],
        "acquisition_mode": (
            None if primary is None else primary["acquisition_mode"]
        ),
        "confidence": None if primary is None else primary["confidence"],
        "credibility": None if primary is None else primary["credibility"],
        "belief_state": None if primary is None else primary["belief_state"],
        "primary_belief_id": (
            None if primary is None else primary["belief_id"]
        ),
        "belief_ids": [value["belief_id"] for value in items],
        "claim_ids": list(dict.fromkeys(
            value["claim_id"] for value in items
        )),
        "items": items,
    }


def _interpretation_view(interpretations):
    ordered = sorted(
        interpretations,
        key=lambda value: value.sequence,
        reverse=True,
    )
    items = [{
        "interpretation_id": value.interpretation_id,
        "claim_id": value.claim_id,
        "interpretation_type": value.interpretation_type,
        "confidence": round(float(value.confidence) / 100.0, 4),
        "active": bool(value.active),
        "created_at": copy_primitive(value.created_at),
        "details": copy_primitive(value.details),
    } for value in ordered]
    return {
        "primary_type": (
            None if not items else items[0]["interpretation_type"]
        ),
        "confidence": None if not items else items[0]["confidence"],
        "items": items,
    }


def _case_data(record):
    if record is None:
        return None
    return copy_primitive(record.to_data())


def _pair_cases(store, sim_a_id, sim_b_id):
    return {
        "repair_case": _case_data(
            store.find_active_repair_case_for_pair(sim_a_id, sim_b_id)
        ),
        "relationship_crisis": _case_data(
            store.find_active_relationship_crisis(sim_a_id, sim_b_id)
        ),
    }


def _related_cases(store, viewer_id, event, known_sim_ids=None):
    repairs = []
    crises = []
    seen_pairs = set()
    known_sim_ids = set(int(value) for value in tuple(known_sim_ids or ()))
    for pair in getattr(event, "relationship_pairs", ()):
        pair = tuple(sorted(int(value) for value in pair))
        other_id = pair[1] if pair[0] == viewer_id else pair[0]
        if (
            viewer_id not in pair
            or pair in seen_pairs
            or (known_sim_ids and other_id not in known_sim_ids)
        ):
            continue
        seen_pairs.add(pair)
        pair_cases = _pair_cases(store, pair[0], pair[1])
        if pair_cases["repair_case"] is not None:
            repairs.append(pair_cases["repair_case"])
        if pair_cases["relationship_crisis"] is not None:
            crises.append(pair_cases["relationship_crisis"])
    return {
        "repair_cases": repairs,
        "relationship_crises": crises,
    }


def _event_ids_for_belief(store, claim, belief):
    event_ids = []
    if claim is not None:
        event_ids.extend(claim.supporting_event_ids)
        event_ids.extend(claim.contradicting_event_ids)
    if not event_ids and belief.acquisition_event_id is not None:
        event_ids.append(belief.acquisition_event_id)
    return tuple(
        event_id
        for event_id in dict.fromkeys(str(value) for value in event_ids)
        if store.get_event(event_id) is not None
    )


def _knowledge_buckets(store, viewer_id):
    buckets = {}
    for belief in store.beliefs_for_knower(viewer_id):
        claim = store.get_claim(belief.claim_id)
        for event_id in _event_ids_for_belief(store, claim, belief):
            bucket = buckets.setdefault(event_id, {
                "event": store.get_event(event_id),
                "beliefs": [],
                "claims": {},
            })
            bucket["beliefs"].append(belief)
            if claim is not None:
                bucket["claims"][claim.claim_id] = claim
    return buckets


def _bucket_interpretations(store, viewer_id, bucket, include_inactive=False):
    claim_ids = set(bucket["claims"])
    belief_ids = set(value.belief_id for value in bucket["beliefs"])
    return [
        value
        for value in store.interpretations_for_knower(viewer_id)
        if (
            value.claim_id in claim_ids
            or value.source_belief_id in belief_ids
        )
        and (include_inactive or value.active)
    ]


def _known_sim_ids(viewer_id, bucket):
    result = {int(viewer_id)}
    for claim in bucket["claims"].values():
        result.update(int(value) for value in claim.subject_ids)
        result.update(int(value) for value in claim.object_ids)
        if claim.asserted_by_id is not None:
            result.add(int(claim.asserted_by_id))
    for belief in bucket["beliefs"]:
        if belief.source_sim_id is not None:
            result.add(int(belief.source_sim_id))
    return result


def _visible_event_time(event, beliefs):
    firsthand_modes = (
        AcquisitionMode.PARTICIPANT,
        AcquisitionMode.EYEWITNESS,
        AcquisitionMode.EA_CONFIRMED,
    )
    if any(value.acquisition_mode in firsthand_modes for value in beliefs):
        return copy_primitive(event.occurred_at)
    return None


def _claim_view(claim, sim_directory=None):
    return {
        "claim_id": claim.claim_id,
        "claim_type": claim.claim_type,
        "subject_sims": [
            _identity_by_id(value, sim_directory=sim_directory)
            for value in claim.subject_ids
        ],
        "object_sims": [
            _identity_by_id(value, sim_directory=sim_directory)
            for value in claim.object_ids
        ],
        "value": copy_primitive(claim.value),
        "asserted_by": (
            None
            if claim.asserted_by_id is None
            else _identity_by_id(
                claim.asserted_by_id,
                sim_directory=sim_directory,
            )
        ),
    }


def _journal_entry(
    store,
    viewer_id,
    bucket,
    sim_directory=None,
    include_inactive_interpretations=False,
):
    event = bucket["event"]
    presentation = _event_presentation(event)
    known_sim_ids = _known_sim_ids(viewer_id, bucket)
    participants = _participants(
        event,
        sim_directory=sim_directory,
        known_sim_ids=known_sim_ids,
    )
    interpretations = _bucket_interpretations(
        store,
        viewer_id,
        bucket,
        include_inactive=include_inactive_interpretations,
    )
    related_cases = _related_cases(
        store,
        viewer_id,
        event,
        known_sim_ids=known_sim_ids,
    )
    processing_status = getattr(event, "payload", {}).get(
        "processing_status"
    )
    if processing_status not in (
        "unprocessed",
        "acknowledged",
        "responded",
        "temporarily_resolved",
        "resolved",
        "reopened",
    ):
        processing_status = None
    entry = {
        "entry_id": "journal:event:{}:viewer:{}".format(
            event.event_id,
            viewer_id,
        ),
        "event_id": event.event_id,
        "sequence": event.sequence,
        "event_type": event.event_type,
        "occurred_at": _visible_event_time(event, bucket["beliefs"]),
        "learned_at": copy_primitive(max(
            bucket["beliefs"],
            key=lambda value: value.sequence,
        ).acquired_at),
        "category": presentation["category"],
        "category_label": presentation["category_label"],
        "semantic_tags": presentation["semantic_tags"],
        "visibility": presentation["visibility"],
        "severity": presentation["severity"],
        "salience": presentation["salience"],
        "importance": presentation["importance"],
        "title_key": presentation["title_key"],
        "summary_key": presentation["summary_key"],
        "detail_key": presentation["detail_key"],
        "icon_key": presentation["icon_key"],
        "title_string_id": presentation["title_string_id"],
        "title": presentation["title"],
        "tokens": _display_tokens(event, participants),
        "participants": participants,
        "knowledge": _knowledge_view(
            bucket["beliefs"],
            sim_directory=sim_directory,
        ),
        "interpretation": _interpretation_view(interpretations),
        "related_cases": related_cases,
        "processing_status": processing_status,
    }
    entry["narrative"] = build_journal_entry_narrative(
        _identity_by_id(viewer_id, sim_directory=sim_directory),
        entry,
    )
    return entry


def _normalized_filters(filters):
    requested = dict(filters or {})
    try:
        page_size = int(requested.get("limit", DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError):
        page_size = DEFAULT_PAGE_SIZE
    page_size = max(1, min(MAX_PAGE_SIZE, page_size))
    event_types = requested.get("event_types")
    if isinstance(event_types, str):
        event_types = (event_types,)
    event_types = tuple(str(value) for value in tuple(event_types or ()))
    belief_states = requested.get("belief_states")
    if isinstance(belief_states, str):
        belief_states = (belief_states,)
    belief_states = tuple(
        str(value) for value in tuple(belief_states or ())
    )
    categories = requested.get("categories")
    if isinstance(categories, str):
        categories = (categories,)
    categories = tuple(str(value) for value in tuple(categories or ()))
    access_modes = requested.get("access_modes")
    if isinstance(access_modes, str):
        access_modes = (access_modes,)
    access_modes = tuple(
        str(value) for value in tuple(access_modes or ())
    )
    importance = requested.get("importance")
    if isinstance(importance, str):
        importance = (importance,)
    importance = tuple(str(value) for value in tuple(importance or ()))
    visibilities = requested.get("visibilities")
    if isinstance(visibilities, str):
        visibilities = (visibilities,)
    if visibilities is None:
        visibilities = (
            JournalVisibility.ALL
            if bool(requested.get("include_internal", False))
            else (JournalVisibility.TIMELINE,)
        )
    visibilities = tuple(
        str(value) for value in tuple(visibilities or ())
        if str(value) in JournalVisibility.ALL
    )
    if not visibilities:
        visibilities = (JournalVisibility.TIMELINE,)
    relationship_sim_id = _sim_id(requested.get("relationship_sim_id"))
    return {
        "event_types": list(event_types),
        "belief_states": list(belief_states),
        "categories": list(categories),
        "access_modes": list(access_modes),
        "importance": list(importance),
        "visibilities": list(visibilities),
        "unresolved_only": bool(requested.get("unresolved_only", False)),
        "relationship_sim_id": relationship_sim_id or None,
        "include_internal": bool(requested.get("include_internal", False)),
        "include_inactive_interpretations": bool(
            requested.get("include_inactive_interpretations", False)
        ),
        "limit": page_size,
    }


def _cursor_offset(cursor):
    if cursor is None:
        return 0
    value = str(cursor)
    if value.startswith("offset:"):
        value = value.split(":", 1)[1]
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _entry_matches_filters(entry, filters, viewer_id):
    del viewer_id
    if filters["event_types"]:
        if entry["event_type"] not in filters["event_types"]:
            return False
    if filters["belief_states"]:
        if entry["knowledge"]["belief_state"] not in filters["belief_states"]:
            return False
    if filters["categories"]:
        if entry["category"] not in filters["categories"]:
            return False
    if filters["access_modes"]:
        if (
            entry["knowledge"]["acquisition_mode"]
            not in filters["access_modes"]
        ):
            return False
    if filters["importance"]:
        if entry["importance"] not in filters["importance"]:
            return False
    if filters["visibilities"]:
        if entry["visibility"] not in filters["visibilities"]:
            return False
    if filters["unresolved_only"]:
        related = entry["related_cases"]
        if not (
            related["repair_cases"]
            or related["relationship_crises"]
            or entry["processing_status"] in ("unprocessed", "reopened")
        ):
            return False
    return True


def _event_matches_relationship(event, viewer_id, relationship_sim_id):
    if relationship_sim_id is None:
        return True
    viewer_id = int(viewer_id)
    relationship_sim_id = int(relationship_sim_id)
    story_edges = tuple(getattr(event, "relationship_pairs", ()) or ())
    if story_edges:
        return any(
            set(int(value) for value in pair)
            == {viewer_id, relationship_sim_id}
            for pair in story_edges
            if len(tuple(pair)) == 2
        )
    # Compatibility fallback for old records without explicit story edges.
    participant_ids = set()
    for sim_ids in getattr(event, "participants", {}).values():
        participant_ids.update(int(value) for value in tuple(sim_ids or ()))
    return relationship_sim_id in participant_ids


def build_character_journal_view(
    viewer_sim,
    filters=None,
    cursor=None,
    store=None,
    sim_directory=None,
):
    """Return only events reachable through the viewer's own beliefs."""
    viewer = _identity(viewer_sim, sim_directory=sim_directory)
    store = _resolve_store(store)
    normalized_filters = _normalized_filters(filters)
    entries = []
    for bucket in _knowledge_buckets(store, viewer["sim_id"]).values():
        event = bucket["event"]
        if not _event_matches_relationship(
            event,
            viewer["sim_id"],
            normalized_filters["relationship_sim_id"],
        ):
            continue
        entry = _journal_entry(
            store,
            viewer["sim_id"],
            bucket,
            sim_directory=sim_directory,
            include_inactive_interpretations=normalized_filters[
                "include_inactive_interpretations"
            ],
        )
        if _entry_matches_filters(
            entry,
            normalized_filters,
            viewer["sim_id"],
        ):
            entries.append(entry)
    entries.sort(
        key=lambda value: (value["sequence"], value["event_id"]),
        reverse=True,
    )
    offset = _cursor_offset(cursor)
    limit = normalized_filters["limit"]
    page = entries[offset:offset + limit]
    next_offset = offset + len(page)
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "view_kind": "character_journal",
        "viewer": viewer,
        "filters": normalized_filters,
        "entries": page,
        "next_cursor": (
            None if next_offset >= len(entries) else "offset:{}".format(next_offset)
        ),
        "total_entries": len(entries),
    }


def build_character_relationships_view(
    viewer_sim,
    store=None,
    sim_directory=None,
):
    """Return every ledger relationship connected to the current viewer."""
    viewer = _identity(viewer_sim, sim_directory=sim_directory)
    viewer_id = viewer["sim_id"]
    store = _resolve_store(store)
    partner_ids = set()

    for state in store.directed_states():
        if state.observer_id == viewer_id:
            partner_ids.add(state.partner_id)
        elif state.partner_id == viewer_id:
            partner_ids.add(state.observer_id)

    for summary in store.summaries():
        if summary.observer_id == viewer_id:
            partner_ids.add(summary.partner_id)
        elif summary.partner_id == viewer_id:
            partner_ids.add(summary.observer_id)

    for bond in store.devotion_bonds():
        if bond.owner_id == viewer_id:
            partner_ids.add(bond.beloved_id)

    for bucket in _knowledge_buckets(store, viewer_id).values():
        for pair in getattr(bucket["event"], "relationship_pairs", ()):
            pair = tuple(int(value) for value in pair)
            if viewer_id not in pair:
                continue
            partner_ids.update(value for value in pair if value != viewer_id)

    relationships = []
    for partner_id in sorted(partner_ids):
        relationships.append(build_relationship_status_view(
            viewer_id,
            partner_id,
            store=store,
            sim_directory=sim_directory,
        ))
    relationships.sort(
        key=lambda value: (
            value["pair"]["sim_b"]["display_name"].casefold(),
            value["pair"]["sim_b"]["sim_id"],
        )
    )
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "view_kind": "character_relationships",
        "viewer": viewer,
        "relationships": relationships,
        "total_relationships": len(relationships),
    }


def _relationship_home_priority(card):
    status = card["relationship"]["status"]
    has_unresolved = bool(
        status.get("relationship_crisis") is not None
        or status.get("repair_case") is not None
    )
    latest_sequence = (
        0
        if not card["latest_events"]
        else int(card["latest_events"][0]["sequence"])
    )
    return (
        1 if has_unresolved else 0,
        latest_sequence,
        card["partner"]["display_name"].casefold(),
        card["partner"]["sim_id"],
    )


def _relationship_card_display(card):
    unresolved = card["unresolved"]
    if unresolved["relationship_crisis"]:
        status_key = "crisis"
        status_label = "关系危机未解决"
    elif unresolved["repair_case"]:
        status_key = "repairing"
        status_label = "正在尝试修复"
    else:
        status_key = "recorded"
        status_label = "关系记录"
    dimensions = []
    for value in card["viewer_direction"].get("dimensions", ()):
        dimensions.append({
            "key": value.get("key"),
            "label": value.get("label"),
            "value": value.get("value"),
            "initialized": bool(value.get("initialized", False)),
            "minimum": value.get("minimum", 0.0),
            "maximum": value.get("maximum", 100.0),
        })
    return {
        "status_key": status_key,
        "status_label": status_label,
        "record_count_label": "{} 条可见记录".format(
            int(card["known_event_count"])
        ),
        "latest_first": True,
        "mini_dimensions": dimensions,
    }


def _journal_filter_options():
    return {
        "categories": [
            {"key": key, "label": CATEGORY_LABELS[key]}
            for key in JournalCategory.PUBLIC
        ],
        "access_modes": [
            {"key": "participant", "label": "亲历"},
            {"key": "eyewitness", "label": "亲眼目睹"},
            {"key": "ea_confirmed", "label": "EA确认"},
            {"key": "told", "label": "听说"},
            {"key": "inferred", "label": "推断"},
            {"key": "player_asserted", "label": "自述"},
        ],
        "importance": [
            {"key": JournalImportance.MAJOR, "label": "重要事件"},
            {"key": JournalImportance.NORMAL, "label": "普通事件"},
        ],
        "unresolved": [
            {"key": "all", "label": "全部"},
            {"key": "unresolved", "label": "未解决"},
        ],
    }
def build_romantic_journal_home_view(
    viewer_sim,
    relationship_limit=DEFAULT_JOURNAL_HOME_RELATIONSHIPS,
    event_limit=DEFAULT_JOURNAL_HOME_EVENTS,
    store=None,
    sim_directory=None,
    relationship_cursor=None,
):
    """Build the journal home screen from the viewer's subjective knowledge.

    The relationship shell can contain objective pair state, but every event
    shown here is obtained through :func:`build_character_journal_view` for
    this exact viewer.  This is the privacy boundary used by the in-game GFX
    bridge: an event unknown to the active Sim cannot appear on the home page.
    """
    try:
        relationship_limit = int(relationship_limit)
    except (TypeError, ValueError):
        relationship_limit = DEFAULT_JOURNAL_HOME_RELATIONSHIPS
    try:
        event_limit = int(event_limit)
    except (TypeError, ValueError):
        event_limit = DEFAULT_JOURNAL_HOME_EVENTS
    relationship_limit = max(1, min(12, relationship_limit))
    event_limit = max(1, min(12, event_limit))

    resolved_store = _resolve_store(store)
    relationship_view = build_character_relationships_view(
        viewer_sim,
        store=resolved_store,
        sim_directory=sim_directory,
    )
    viewer = relationship_view["viewer"]
    cards = []
    for relationship in relationship_view["relationships"]:
        partner = relationship["pair"]["sim_b"]
        journal = build_character_journal_view(
            viewer["sim_id"],
            filters={
                "relationship_sim_id": partner["sim_id"],
                "limit": event_limit,
            },
            store=resolved_store,
            sim_directory=sim_directory,
        )
        card = {
            "partner": copy_primitive(partner),
            "relationship": relationship,
            "viewer_direction": relationship["directions"][0],
            "latest_events": journal["entries"],
            "known_event_count": journal["total_entries"],
            "has_more_events": journal["next_cursor"] is not None,
            "unresolved": {
                "relationship_crisis": (
                    relationship["status"].get("relationship_crisis")
                    is not None
                ),
                "repair_case": (
                    relationship["status"].get("repair_case") is not None
                ),
            },
            "event_page": {
                "cursor": None,
                "previous_cursor": None,
                "next_cursor": journal["next_cursor"],
                "page_size": event_limit,
                "total_entries": journal["total_entries"],
                "has_previous": False,
                "has_next": journal["next_cursor"] is not None,
            },
        }
        card["display"] = _relationship_card_display(card)
        cards.append(card)

    cards.sort(key=_relationship_home_priority, reverse=True)
    relationship_offset = _cursor_offset(relationship_cursor)
    relationship_offset = min(relationship_offset, len(cards))
    visible_cards = cards[
        relationship_offset:relationship_offset + relationship_limit
    ]
    next_offset = relationship_offset + len(visible_cards)
    previous_offset = max(0, relationship_offset - relationship_limit)
    selected_partner_id = (
        None if not visible_cards else visible_cards[0]["partner"]["sim_id"]
    )
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "view_kind": "romantic_journal_home",
        "viewer": viewer,
        "relationships": visible_cards,
        "selected_partner_id": selected_partner_id,
        "total_relationships": len(cards),
        "hidden_relationship_count": max(0, len(cards) - len(visible_cards)),
        "relationship_limit": relationship_limit,
        "event_limit": event_limit,
        "summary": {
            "relationship_count": len(cards),
            "known_event_count": sum(
                int(card["known_event_count"]) for card in cards
            ),
            "unresolved_relationship_count": sum(
                1 for card in cards
                if card["unresolved"]["relationship_crisis"]
                or card["unresolved"]["repair_case"]
            ),
        },
        "available_filters": _journal_filter_options(),
        "relationship_page": {
            "cursor": (
                None if relationship_offset == 0
                else "offset:{}".format(relationship_offset)
            ),
            "previous_cursor": (
                None if relationship_offset == 0
                else "offset:{}".format(previous_offset)
            ),
            "next_cursor": (
                None if next_offset >= len(cards)
                else "offset:{}".format(next_offset)
            ),
            "page_size": relationship_limit,
            "total_entries": len(cards),
            "has_previous": relationship_offset > 0,
            "has_next": next_offset < len(cards),
        },
    }


def build_event_detail_view(
    viewer_sim,
    event_id,
    store=None,
    sim_directory=None,
):
    """Return an event detail only when the viewer has a belief path to it."""
    viewer = _identity(viewer_sim, sim_directory=sim_directory)
    store = _resolve_store(store)
    event_id = str(event_id)
    bucket = _knowledge_buckets(store, viewer["sim_id"]).get(event_id)
    if bucket is None:
        return {
            "schema_version": UI_SCHEMA_VERSION,
            "view_kind": "event_detail",
            "viewer": viewer,
            "event_id": event_id,
            "available": False,
            "reason": "not_known_by_viewer",
        }
    entry = _journal_entry(
        store,
        viewer["sim_id"],
        bucket,
        sim_directory=sim_directory,
        include_inactive_interpretations=True,
    )
    presentation = _event_presentation(bucket["event"])
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "view_kind": "event_detail",
        "viewer": viewer,
        "event_id": event_id,
        "available": True,
        "title_key": presentation["title_key"],
        "summary_key": presentation["summary_key"],
        "detail_key": presentation["detail_key"],
        "entry": entry,
        "claims": [
            _claim_view(claim, sim_directory=sim_directory)
            for claim in sorted(
                bucket["claims"].values(),
                key=lambda value: value.sequence,
            )
        ],
    }


def _runtime_state(sim_a, sim_b):
    from fgeh_cheatingharder_state import get_directed_state

    return get_directed_state(sim_a, sim_b)


def _direction_view(
    observer,
    partner,
    store,
    runtime_state=None,
):
    observer_id = observer["sim_id"]
    partner_id = partner["sim_id"]
    record = store.get_directed_state(observer_id, partner_id)
    state = runtime_state if runtime_state is not None else record
    values = {} if state is None else dict(getattr(state, "values", {}))
    initialized = {}
    if state is not None:
        initialized = dict(
            getattr(state, "initialized", getattr(state, "persisted", {}))
        )
    dimensions = []
    definitions = {
        value.key: value for value in DIMENSION_DEFINITIONS.definitions()
    }
    for key in DIRECTED_DIMENSIONS:
        definition = definitions[key]
        is_initialized = bool(initialized.get(key, False))
        dimensions.append({
            "key": key,
            "label": definition.display_name,
            "description": definition.description,
            "value": (
                float(values.get(key, 0.0)) if is_initialized else None
            ),
            "initialized": is_initialized,
            "minimum": 0.0,
            "maximum": 100.0,
        })
    badges = []
    devotion = store.get_devotion_bond(observer_id)
    if devotion is not None and devotion.beloved_id == partner_id:
        badges.append({
            "key": "devotion",
            "status": devotion.status,
            "owner_id": observer_id,
            "beloved_id": partner_id,
        })
    return {
        "observer": copy_primitive(observer),
        "partner": copy_primitive(partner),
        "observer_id": observer_id,
        "partner_id": partner_id,
        "direction_label": "{} → {}".format(
            observer["display_name"],
            partner["display_name"],
        ),
        "revision": 0 if record is None else int(record.revision),
        "dimensions": dimensions,
        "badges": badges,
    }


def build_relationship_status_view(
    sim_a,
    sim_b,
    store=None,
    sim_directory=None,
):
    """Return both independent directions and pair-level unresolved cases."""
    identity_a = _identity(sim_a, sim_directory=sim_directory)
    identity_b = _identity(sim_b, sim_directory=sim_directory)
    if identity_a["sim_id"] == identity_b["sim_id"]:
        raise ValueError("A relationship view requires two different Sims")
    use_runtime_state = store is None
    store = _resolve_store(store)
    a_to_b = None
    b_to_a = None
    if use_runtime_state:
        a_to_b = _runtime_state(sim_a, sim_b)
        b_to_a = _runtime_state(sim_b, sim_a)
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "view_kind": "relationship_status",
        "pair": {
            "sim_a": identity_a,
            "sim_b": identity_b,
        },
        "directions": [
            _direction_view(
                identity_a,
                identity_b,
                store,
                runtime_state=a_to_b,
            ),
            _direction_view(
                identity_b,
                identity_a,
                store,
                runtime_state=b_to_a,
            ),
        ],
        "status": _pair_cases(
            store,
            identity_a["sim_id"],
            identity_b["sim_id"],
        ),
    }


def build_pair_view(sim_a, sim_b, store=None, sim_directory=None):
    """Stable alias used by the relationship-panel and future GFX bridge."""
    view = build_relationship_status_view(
        sim_a,
        sim_b,
        store=store,
        sim_directory=sim_directory,
    )
    view["view_kind"] = "pair"
    return view

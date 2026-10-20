"""Read-only export projection for the external romantic-ledger viewer.

The JSON file produced here is deliberately not a save backend.  EA-save
persistence remains owned by the romantic-memory carrier.  This module only
adds names and query indexes to one immutable snapshot so a browser can inspect
the ledger without importing Sims 4 code.
"""

import datetime
import json
import os

from fgeh_cheatingharder_debug import get_log_paths, log, log_exception
from fgeh_cheatingharder_ui_adapter import (
    UI_SCHEMA_VERSION,
    build_character_journal_view,
    build_pair_view,
)


EXPORT_SCHEMA_VERSION = 1
EXPORT_FILE_NAME = "fgeh_romantic_ledger_export.json"


def _normalize_sim_directory(sim_directory):
    records = []
    for sim_id, name in dict(sim_directory or {}).items():
        try:
            normalized_id = int(sim_id)
        except (TypeError, ValueError):
            continue
        if normalized_id <= 0:
            continue
        records.append({
            "sim_id": normalized_id,
            "name": str(name or normalized_id),
        })
    return sorted(records, key=lambda value: (value["name"], value["sim_id"]))


def _pair_key(first_id, second_id):
    first_id = int(first_id)
    second_id = int(second_id)
    return (
        (first_id, second_id)
        if first_id < second_id
        else (second_id, first_id)
    )


def _event_pair_keys(event):
    pairs = set()
    for value in event.get("relationship_pairs", ()):
        if isinstance(value, (tuple, list)) and len(value) == 2:
            try:
                pairs.add(_pair_key(value[0], value[1]))
            except (TypeError, ValueError):
                continue
    return pairs


def build_ledger_export(
    snapshot,
    sim_directory=None,
    exported_at=None,
    active_reactions=None,
    ui_views=None,
):
    """Build a browser-safe projection without duplicating objective events."""
    snapshot = dict(snapshot or {})
    events = tuple(snapshot.get("events", ()))
    claims = tuple(snapshot.get("claims", ()))
    beliefs = tuple(snapshot.get("beliefs", ()))
    interpretations = tuple(snapshot.get("interpretations", ()))
    states = tuple(snapshot.get("directed_states", ()))
    summaries = tuple(snapshot.get("summaries", ()))
    relationship_crises = tuple(
        snapshot.get("relationship_crises", ())
    )

    event_ids_by_pair = {}
    crisis_case_ids_by_pair = {}
    for event in events:
        for pair in _event_pair_keys(event):
            event_ids_by_pair.setdefault(pair, []).append(event.get("event_id"))
    for record in states:
        try:
            pair = _pair_key(record["observer_id"], record["partner_id"])
        except (KeyError, TypeError, ValueError):
            continue
        event_ids_by_pair.setdefault(pair, [])
    for record in summaries:
        try:
            pair = _pair_key(record["observer_id"], record["partner_id"])
        except (KeyError, TypeError, ValueError):
            continue
        event_ids_by_pair.setdefault(pair, [])
    for record in relationship_crises:
        pair_value = record.get("relationship_pair", ())
        if not isinstance(pair_value, (tuple, list)) or len(pair_value) != 2:
            continue
        try:
            pair = _pair_key(pair_value[0], pair_value[1])
        except (TypeError, ValueError):
            continue
        event_ids_by_pair.setdefault(pair, [])
        crisis_case_ids_by_pair.setdefault(pair, []).append(
            record.get("case_id")
        )

    claims_by_id = {
        str(record.get("claim_id")): record
        for record in claims
        if record.get("claim_id") is not None
    }
    interpretations_by_belief = {}
    for record in interpretations:
        source_belief_id = record.get("source_belief_id")
        if source_belief_id is not None:
            interpretations_by_belief.setdefault(
                str(source_belief_id),
                [],
            ).append(record.get("interpretation_id"))

    pair_views = []
    for pair in sorted(event_ids_by_pair):
        event_ids = tuple(
            value
            for value in event_ids_by_pair[pair]
            if value is not None
        )
        event_id_set = set(str(value) for value in event_ids)
        directions = []
        for observer_id, partner_id in (pair, tuple(reversed(pair))):
            state = next((
                record
                for record in states
                if int(record.get("observer_id", 0)) == observer_id
                and int(record.get("partner_id", 0)) == partner_id
            ), None)
            summary = next((
                record
                for record in summaries
                if int(record.get("observer_id", 0)) == observer_id
                and int(record.get("partner_id", 0)) == partner_id
            ), None)
            belief_ids = []
            interpretation_ids = []
            for belief in beliefs:
                if int(belief.get("knower_id", 0)) != observer_id:
                    continue
                claim = claims_by_id.get(str(belief.get("claim_id")))
                if claim is None:
                    continue
                supporting = set(
                    str(value)
                    for value in claim.get("supporting_event_ids", ())
                )
                subject_object_ids = set(
                    int(value)
                    for value in (
                        tuple(claim.get("subject_ids", ()))
                        + tuple(claim.get("object_ids", ()))
                    )
                )
                if not (
                    supporting.intersection(event_id_set)
                    or set(pair).issubset(subject_object_ids)
                ):
                    continue
                belief_id = str(belief.get("belief_id"))
                belief_ids.append(belief_id)
                interpretation_ids.extend(
                    interpretations_by_belief.get(belief_id, ())
                )
            directions.append({
                "observer_id": observer_id,
                "partner_id": partner_id,
                "state": state,
                "summary": summary,
                "belief_ids": belief_ids,
                "interpretation_ids": interpretation_ids,
            })
        pair_views.append({
            "sim_ids": list(pair),
            "event_ids": list(event_ids),
            "crisis_case_ids": list(
                crisis_case_ids_by_pair.get(pair, ())
            ),
            "directions": directions,
        })

    projection = {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "export_kind": "read_only_romantic_ledger_projection",
        "exported_at": (
            exported_at
            or datetime.datetime.now().isoformat(timespec="seconds")
        ),
        "notice": (
            "This JSON is a read-only viewer snapshot, not the canonical "
            "romantic-memory save format."
        ),
        "save_lineage_id": snapshot.get("save_lineage_id"),
        "memory_schema_version": snapshot.get("schema_version"),
        "sims": _normalize_sim_directory(sim_directory),
        "ledger": snapshot,
        "pair_views": pair_views,
        "active_reactions": list(active_reactions or ()),
    }
    if ui_views is not None:
        projection["ui_views"] = ui_views
    return projection


def build_ledger_ui_views(store, sim_directory=None):
    """Build ordinary player views beside the raw developer ledger export."""
    sim_directory = dict(sim_directory or {})
    sim_ids = set()
    pair_keys = set()
    for belief in store.beliefs():
        sim_ids.add(int(belief.knower_id))
    for event in store.events():
        sim_ids.update(int(value) for value in event.all_participant_ids())
        pair_keys.update(tuple(value) for value in event.relationship_pairs)
    for state in store.directed_states():
        sim_ids.update((int(state.observer_id), int(state.partner_id)))
        pair_keys.add(tuple(sorted((state.observer_id, state.partner_id))))
    for bond in store.devotion_bonds():
        sim_ids.update((int(bond.owner_id), int(bond.beloved_id)))
        pair_keys.add(tuple(sorted((bond.owner_id, bond.beloved_id))))
    for summary in store.summaries():
        sim_ids.update((int(summary.observer_id), int(summary.partner_id)))
        pair_keys.add(tuple(sorted((summary.observer_id, summary.partner_id))))
    for record in store.repair_cases():
        sim_ids.update(record.relationship_pair)
        pair_keys.add(tuple(record.relationship_pair))
    for record in store.relationship_crises():
        sim_ids.update(record.relationship_pair)
        pair_keys.add(tuple(record.relationship_pair))
    pair_keys = {
        tuple(sorted(int(value) for value in pair))
        for pair in pair_keys
        if (
            len(pair) == 2
            and int(pair[0]) > 0
            and int(pair[1]) > 0
            and int(pair[0]) != int(pair[1])
        )
    }
    for pair in pair_keys:
        sim_ids.update(pair)
    return {
        "schema_version": UI_SCHEMA_VERSION,
        "journals": [
            build_character_journal_view(
                sim_id,
                store=store,
                sim_directory=sim_directory,
            )
            for sim_id in sorted(sim_ids)
        ],
        "relationships": [
            build_pair_view(
                pair[0],
                pair[1],
                store=store,
                sim_directory=sim_directory,
            )
            for pair in sorted(pair_keys)
        ],
    }


def _sim_name(sim_info):
    first_name = getattr(sim_info, "first_name", None)
    last_name = getattr(sim_info, "last_name", None)
    if first_name and last_name:
        return "{} {}".format(first_name, last_name)
    return str(
        first_name
        or last_name
        or getattr(sim_info, "full_name", None)
        or getattr(sim_info, "sim_id", "?")
    )


def _game_sim_directory():
    import services

    return {
        int(sim_info.sim_id): _sim_name(sim_info)
        for sim_info in services.sim_info_manager().get_all()
        if getattr(sim_info, "sim_id", None)
    }


def _active_reactions(sim_ids):
    from fgeh_cheatingharder_reaction_runtime import (
        get_relationship_reaction_status,
    )

    records = []
    for sim_id in sim_ids:
        record = get_relationship_reaction_status(sim_id)
        if record is not None:
            records.append(record)
    return records


def _candidate_export_paths():
    seen = set()
    for log_path in get_log_paths():
        directory = os.path.dirname(log_path)
        path = os.path.join(directory, EXPORT_FILE_NAME)
        normalized = os.path.abspath(path)
        key = normalized.lower()
        if key not in seen:
            seen.add(key)
            yield normalized
    module_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        EXPORT_FILE_NAME,
    )
    if module_path.lower() not in seen:
        yield module_path


def export_current_ledger():
    """Write one UTF-8 viewer snapshot and return its successful path."""
    from fgeh_cheatingharder_memory_runtime import get_memory_service

    service = get_memory_service()
    snapshot = service.export_snapshot()
    sim_directory = _game_sim_directory()
    projection = build_ledger_export(
        snapshot,
        sim_directory=sim_directory,
        active_reactions=_active_reactions(sim_directory),
        ui_views=build_ledger_ui_views(
            service.store,
            sim_directory=sim_directory,
        ),
    )
    last_error = None
    for path in _candidate_export_paths():
        try:
            with open(path, "w", encoding="utf-8") as export_file:
                json.dump(
                    projection,
                    export_file,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            log(
                "romantic ledger viewer snapshot exported path={} events={} pairs={}",
                path,
                len(snapshot.get("events", ())),
                len(projection.get("pair_views", ())),
            )
            return path
        except Exception as exception:
            last_error = exception
    if last_error is not None:
        raise last_error
    raise RuntimeError("No writable romantic-ledger export path was found")


def safe_export_current_ledger():
    try:
        return export_current_ledger()
    except Exception:
        log_exception("romantic ledger viewer snapshot export failed")
        return None

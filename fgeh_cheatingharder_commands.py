import services
import sims4.commands

from fgeh_cheatingharder_debug import get_log_paths, log, log_exception
from fgeh_cheatingharder_events import is_interaction_observer_installed
from fgeh_cheatingharder_notification import show_claim_notification
from fgeh_cheatingharder_route import register_check_in
from fgeh_cheatingharder_route import get_check_in_status
from fgeh_cheatingharder_relationship import (
    get_check_in_cooldown_bit,
    get_claim_relationship_bit,
    get_devotion_relationship_bit,
    get_devotion_trait,
    get_possessive_trait,
    get_sim_info,
    has_claim,
    has_devotion_relationship_bit,
    is_enabled,
    is_devotion_enabled,
)
from fgeh_cheatingharder_state import get_directed_state, tuning_status


def _write(connection, message):
    sims4.commands.output(str(message), connection)


def _active_sim_info():
    try:
        return get_sim_info(services.get_active_sim())
    except Exception:
        log_exception("debug command active sim lookup failed")
        return None


def _find_sim_info(sim_id):
    try:
        manager = services.sim_info_manager()
        return manager.get(int(sim_id)) if sim_id else None
    except Exception:
        log_exception("debug command Sim lookup failed")
    return None


def _find_unexpected_visitor(partner_info):
    try:
        manager = services.sim_info_manager()
        current_zone_id = services.current_zone_id()
        for sim_info in manager.get_all():
            if getattr(sim_info, "sim_id", None) == getattr(partner_info, "sim_id", None):
                continue
            instance = sim_info.get_sim_instance()
            if instance is not None and getattr(instance, "zone_id", None) == current_zone_id:
                continue
            if has_claim(sim_info, partner_info) and is_enabled(sim_info):
                log(
                    "debug command selected claimed visitor visitor={} partner={} zone={}",
                    sim_info.sim_id,
                    partner_info.sim_id,
                    getattr(instance, "zone_id", None),
                )
                return sim_info
        log(
            "debug command found no claimed visitor partner={}",
            getattr(partner_info, "sim_id", None),
        )
    except Exception:
        log_exception("debug command visitor lookup failed")
    return None


def _find_claimed_target(observer_info):
    if observer_info is None:
        return None
    try:
        for target_info in services.sim_info_manager().get_all():
            if target_info.sim_id == observer_info.sim_id:
                continue
            if has_claim(observer_info, target_info):
                return target_info
    except Exception:
        log_exception("debug command claimed target lookup failed")
    return None


def _latest_recorded_betrayal_context(observer_info):
    """Resolve partner/rival only from a recorded betrayal event."""
    if observer_info is None:
        return (None, None, None)
    try:
        from fgeh_cheatingharder_betrayal_memory_rules import (
            latest_betrayal_event_for_observer,
        )
        from fgeh_cheatingharder_memory_models import ParticipantRole
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        event = latest_betrayal_event_for_observer(
            get_memory_service().store,
            observer_info.sim_id,
        )
        if event is None:
            return (None, None, None)
        partner_ids = event.participants_for(ParticipantRole.PARTNER)
        rival_ids = event.participants_for(ParticipantRole.RIVAL)
        partner = _find_sim_info(partner_ids[0]) if len(partner_ids) == 1 else None
        rival = _find_sim_info(rival_ids[0]) if len(rival_ids) == 1 else None
        return (event, partner, rival)
    except Exception:
        log_exception("recorded betrayal context lookup failed")
        return (None, None, None)


def _find_betrayal_partner(observer_info, explicit_sim_id=None):
    if explicit_sim_id:
        return _find_sim_info(explicit_sim_id)
    try:
        from fgeh_cheatingharder_devotion_runtime import get_devotion_bond

        bond = get_devotion_bond(observer_info.sim_id)
        if bond is not None:
            beloved = _find_sim_info(bond.beloved_id)
            if beloved is not None:
                return beloved
    except Exception:
        log_exception("betrayal preview devotion lookup failed")
    return _find_claimed_target(observer_info)


def _find_betrayal_rival(observer_info, partner_info, explicit_sim_id=None):
    if explicit_sim_id:
        return _find_sim_info(explicit_sim_id)
    try:
        current_zone_id = services.current_zone_id()
        for sim_info in services.sim_info_manager().get_all():
            if sim_info.sim_id in (
                observer_info.sim_id,
                partner_info.sim_id,
            ):
                continue
            instance = sim_info.get_sim_instance()
            if (
                instance is not None
                and getattr(instance, "zone_id", None) == current_zone_id
            ):
                return sim_info
    except Exception:
        log_exception("betrayal preview rival lookup failed")
    return None


@sims4.commands.Command(
    "fgeh.cheatingharder.status",
    command_type=sims4.commands.CommandType.Live,
)
def status(_connection=None):
    active_info = _active_sim_info()
    try:
        from fgeh_cheatingharder_wickedwhims import (
            is_wickedwhims_devotion_adapter_installed,
        )

        ww_devotion_adapter = (
            is_wickedwhims_devotion_adapter_installed()
        )
    except Exception:
        ww_devotion_adapter = False
    try:
        from fgeh_cheatingharder_romance_value_guard import (
            is_romance_value_guard_installed,
        )

        romance_value_guard = is_romance_value_guard_installed()
    except Exception:
        romance_value_guard = False
    try:
        from fgeh_cheatingharder_devotion_runtime import get_devotion_bond

        devotion_bond = (
            get_devotion_bond(active_info.sim_id)
            if active_info is not None
            else None
        )
    except Exception:
        devotion_bond = None
    lines = (
        "FGEH CheatingHarder status:",
        "observer_installed={}".format(is_interaction_observer_installed()),
        "trait_tuning_found={}".format(get_possessive_trait() is not None),
        "devotion_trait_tuning_found={}".format(
            get_devotion_trait() is not None
        ),
        "claim_bit_tuning_found={}".format(get_claim_relationship_bit() is not None),
        "cooldown_bit_tuning_found={}".format(get_check_in_cooldown_bit() is not None),
        "devotion_relationship_bit_tuning_found={}".format(
            get_devotion_relationship_bit() is not None
        ),
        "state_track_tunings={}".format(tuning_status()),
        "active_sim_id={}".format(getattr(active_info, "sim_id", None)),
        "active_sim_has_trait={}".format(is_enabled(active_info) if active_info else False),
        "active_sim_has_devotion_trait={}".format(
            is_devotion_enabled(active_info) if active_info else False
        ),
        "active_sim_only_beloved={}".format(
            getattr(devotion_bond, "beloved_id", None)
        ),
        "ww_devotion_adapter_installed={}".format(
            ww_devotion_adapter
        ),
        "romance_value_guard_installed={}".format(
            romance_value_guard
        ),
        "log_paths={}".format(" | ".join(get_log_paths()) or "<none>"),
        "check_ins={}".format(get_check_in_status()),
    )
    for line in lines:
        _write(_connection, line)
    log("manual status: {}", " | ".join(lines))
    return True


@sims4.commands.Command(
    "fgeh.cheatingharder.devotion_status",
    command_type=sims4.commands.CommandType.Live,
)
def devotion_status(_connection=None):
    owner = _active_sim_info()
    if owner is None:
        _write(_connection, "No active Sim.")
        return False
    try:
        from fgeh_cheatingharder_devotion_runtime import get_devotion_bond

        bond = get_devotion_bond(owner.sim_id)
        if bond is None:
            _write(
                _connection,
                "devotion owner={} beloved=<not chosen>".format(
                    owner.sim_id
                ),
            )
            return True
        beloved = _find_sim_info(bond.beloved_id)
        _write(
            _connection,
            "devotion owner={} beloved={} beloved_name={} status={} source={} visible_bit={}".format(
                owner.sim_id,
                bond.beloved_id,
                getattr(beloved, "full_name", None),
                bond.status,
                bond.source,
                has_devotion_relationship_bit(owner, beloved),
            ),
        )
        return True
    except Exception:
        log_exception("devotion status command failed")
        _write(_connection, "Devotion status failed; inspect the log.")
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.longing_status",
    command_type=sims4.commands.CommandType.Live,
)
def longing_status(_connection=None):
    owner = _active_sim_info()
    if owner is None:
        _write(_connection, "No active Sim.")
        return False
    try:
        from fgeh_cheatingharder_devotion_runtime import get_devotion_bond
        from fgeh_cheatingharder_longing_runtime import get_longing_status

        bond = get_devotion_bond(owner.sim_id)
        if bond is None:
            _write(
                _connection,
                "longing owner={} beloved=<not chosen>".format(owner.sim_id),
            )
            return True
        beloved = _find_sim_info(bond.beloved_id)
        if beloved is None:
            _write(
                _connection,
                "longing owner={} beloved={} missing_from_sim_info_manager=True".format(
                    owner.sim_id,
                    bond.beloved_id,
                ),
            )
            return False
        values = get_longing_status(owner, beloved)
        _write(_connection, "longing_status={}".format(values))
        log("manual longing status {}", values)
        return True
    except Exception:
        log_exception("longing status command failed")
        _write(_connection, "Longing status failed; inspect the log.")
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.longing_check",
    command_type=sims4.commands.CommandType.Live,
)
def longing_check(_connection=None):
    """Run the normal sensor now; this does not bypass its time/lot rules."""
    owner = _active_sim_info()
    if owner is None:
        _write(_connection, "No active Sim.")
        return False
    try:
        from fgeh_cheatingharder_devotion_runtime import get_devotion_bond
        from fgeh_cheatingharder_longing_runtime import evaluate_longing

        bond = get_devotion_bond(owner.sim_id)
        if bond is None:
            _write(_connection, "The active Sim has no only beloved.")
            return False
        result = evaluate_longing(owner.sim_id, bond.beloved_id)
        _write(
            _connection,
            "longing_check_result={} owner={} beloved={}".format(
                result,
                owner.sim_id,
                bond.beloved_id,
            ),
        )
        return bool(result)
    except Exception:
        log_exception("longing check command failed")
        _write(_connection, "Longing check failed; inspect the log.")
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.devote",
    command_type=sims4.commands.CommandType.Live,
)
def devote(target_sim_id: int=None, _connection=None):
    """Backup command; the normal flow is the clicked-Sim interaction."""
    owner = _active_sim_info()
    beloved = _find_sim_info(target_sim_id)
    if owner is None or beloved is None:
        _write(_connection, "Need an active Sim and a target Sim id.")
        return False
    if not bool(getattr(owner, "is_selectable", False)):
        _write(_connection, "Only a player-controlled Sim can bind devotion.")
        return False
    if not is_devotion_enabled(owner):
        _write(_connection, "The active Sim does not have the devotion trait.")
        return False
    try:
        from fgeh_cheatingharder_devotion_runtime import establish_devotion

        bond = establish_devotion(
            owner,
            beloved,
            source="debug_command",
        )
        _write(
            _connection,
            "devotion_created={} owner={} beloved={}".format(
                bond is not None,
                owner.sim_id,
                beloved.sim_id,
            ),
        )
        return bond is not None
    except Exception:
        log_exception("devotion command failed")
        _write(_connection, "Devotion creation failed; inspect the log.")
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.explain",
    command_type=sims4.commands.CommandType.Live,
)
def explain(target_sim_id: int=None, _connection=None):
    """Explain the active Sim's latest directed decision toward a target."""
    observer = _active_sim_info()
    target = _find_sim_info(target_sim_id) if target_sim_id else _find_claimed_target(observer)
    if observer is None or target is None or not has_claim(observer, target):
        _write(_connection, "Need an active observer with a directed claim on the target.")
        return False
    state = get_directed_state(observer, target)
    from fgeh_cheatingharder_event_center import get_last_decision

    decision = get_last_decision(observer.sim_id, target.sim_id)
    _write(
        _connection,
        "edge={}->{} state={}".format(
            observer.sim_id,
            target.sim_id,
            state.as_dict() if state is not None else None,
        ),
    )
    _write(_connection, "last_decision={}".format(decision or "<not evaluated yet>"))
    log(
        "manual explain observer={} target={} state={} decision={}",
        observer.sim_id,
        target.sim_id,
        state.as_dict() if state is not None else None,
        decision,
    )
    return True


@sims4.commands.Command(
    "fgeh.cheatingharder.betrayal_preview",
    command_type=sims4.commands.CommandType.Live,
)
def betrayal_preview(
    partner_sim_id: int=None,
    rival_sim_id: int=None,
    _connection=None,
):
    """Compare three personality bottoms without changing memory or state."""
    observer = _active_sim_info()
    partner = (
        _find_betrayal_partner(observer, partner_sim_id)
        if observer is not None
        else None
    )
    rival = (
        _find_betrayal_rival(observer, partner, rival_sim_id)
        if observer is not None and partner is not None
        else None
    )
    if observer is None or partner is None or rival is None:
        _write(
            _connection,
            "Need active observer, claimed/only-beloved partner, and a third Sim on the active lot.",
        )
        return False
    try:
        from fgeh_cheatingharder_betrayal_reactions import (
            BetrayalProfileKey,
            evaluate_caught_betrayal,
        )

        directed_state = get_directed_state(observer, partner)
        state = (
            directed_state.as_dict()
            if directed_state is not None
            else {
                "attachment": 68,
                "trust": 65,
                "exclusivity": 88,
                "commitment": 68,
                "boundary": 50,
            }
        )
        _write(
            _connection,
            "betrayal_preview observer={} partner={} rival={} state={}".format(
                observer.sim_id,
                partner.sim_id,
                rival.sim_id,
                state,
            ),
        )
        for profile_key in BetrayalProfileKey.TEST_PROFILES:
            evaluation = evaluate_caught_betrayal(
                state,
                profile_key=profile_key,
                severity=100,
                roll=0.42,
            )
            ranked = sorted(
                evaluation.candidates,
                key=lambda value: value.score,
                reverse=True,
            )
            summary = {
                "profile": profile_key,
                "attribution": {
                    key: round(value, 1)
                    for key, value in evaluation.attribution.items()
                },
                "deltas": {
                    key: round(value, 1)
                    for key, value in evaluation.state_deltas.items()
                },
                "top_behaviors": tuple(
                    (value.intent, round(value.score, 1))
                    for value in ranked[:3]
                ),
                "weighted_selection": evaluation.selected_intent,
            }
            _write(_connection, "betrayal_profile={}".format(summary))
            log("betrayal preview {}", evaluation.as_dict())
        _write(
            _connection,
            "Preview only: no ledger event, relationship value, or behavior was changed.",
        )
        return True
    except Exception:
        log_exception("betrayal preview command failed")
        _write(_connection, "Betrayal preview failed; inspect the log.")
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.memory_status",
    command_type=sims4.commands.CommandType.Live,
)
def memory_status(_connection=None):
    """Show counts for every layer of the romantic-memory service."""
    log("manual memory status command invoked")
    try:
        from fgeh_cheatingharder_memory_runtime import get_memory_status

        memory = get_memory_status()
        _write(_connection, "romantic_memory_lineage={}".format(memory["lineage"]))
        _write(_connection, "romantic_memory_counts={}".format(memory["counts"]))
        try:
            from fgeh_cheatingharder_memory_carrier import (
                get_memory_persistence_status,
            )

            _write(
                _connection,
                "romantic_memory_persistence={}".format(
                    get_memory_persistence_status()
                ),
            )
        except Exception:
            log_exception("memory persistence status lookup failed")
        for stage, rules in memory["registry"]["rules"].items():
            _write(
                _connection,
                "romantic_memory_stage={} rules={}".format(
                    stage,
                    tuple(rule["key"] for rule in rules),
                ),
            )
        log(
            "manual memory status lineage={} counts={}",
            memory["lineage"],
            memory["counts"],
        )
        return True
    except Exception:
        log_exception("memory status command failed")
        _write(_connection, "Romantic memory status failed; inspect the log.")
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.memory_edge",
    command_type=sims4.commands.CommandType.Live,
)
def memory_edge(target_sim_id: int=None, _connection=None):
    """Inspect the active Sim's directed state, beliefs, and hot summary."""
    observer = _active_sim_info()
    target = _find_sim_info(target_sim_id) if target_sim_id else _find_claimed_target(observer)
    if observer is None or target is None:
        _write(_connection, "Need an active Sim and target Sim.")
        return False
    try:
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        store = get_memory_service().store
        state = store.get_directed_state(observer.sim_id, target.sim_id)
        summary = store.get_summary(observer.sim_id, target.sim_id)
        beliefs = store.beliefs_for_knower(observer.sim_id)
        interpretations = store.interpretations_for_knower(observer.sim_id)
        _write(
            _connection,
            "memory_edge={}->{} state={}".format(
                observer.sim_id,
                target.sim_id,
                None if state is None else state.to_data(),
            ),
        )
        _write(
            _connection,
            "memory_summary={}".format(
                None if summary is None else summary.to_data()
            ),
        )
        _write(
            _connection,
            "knower_beliefs={} knower_interpretations={}".format(
                len(beliefs),
                len(interpretations),
            ),
        )
        return True
    except Exception:
        log_exception("memory edge command failed")
        _write(_connection, "Romantic memory edge inspection failed.")
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.repair_case",
    command_type=sims4.commands.CommandType.Live,
)
def repair_case_status(target_sim_id: int=None, _connection=None):
    """Inspect the active Sim pair's current directed repair cases."""
    active = _active_sim_info()
    target = _find_sim_info(target_sim_id) if target_sim_id else None
    if active is None:
        _write(_connection, "Need an active Sim.")
        return False
    try:
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        records = tuple(
            record
            for record in get_memory_service().store.repair_cases()
            if (
                active.sim_id in record.relationship_pair
                and (
                    target is None
                    or target.sim_id in record.relationship_pair
                )
            )
        )
        _write(
            _connection,
            "当前小人的关系修复要求 count={}".format(len(records)),
        )
        for record in records:
            accountable = _find_sim_info(record.accountable_id)
            harmed = _find_sim_info(record.harmed_id)
            accountable_name = (
                getattr(accountable, "full_name", None)
                or str(record.accountable_id)
            )
            harmed_name = (
                getattr(harmed, "full_name", None)
                or str(record.harmed_id)
            )
            if record.status == "open":
                instruction = (
                    "{} 需要向 {} 使用原版“道歉”，且道歉必须被接受。"
                    "当前无截止时间。"
                ).format(accountable_name, harmed_name)
            elif record.status == "satisfied":
                instruction = (
                    "“真诚道歉”已经完成；可以再次提出复合。"
                )
            elif record.status == "completed":
                instruction = "修复完成后，两人已经正式复合。"
            else:
                instruction = "此事务当前不再等待行动。"
            _write(
                _connection,
                "case={} status={} 要求={} {}".format(
                    record.case_id,
                    record.status,
                    tuple(record.requirement_keys),
                    instruction,
                ),
            )
            _write(
                _connection,
                "责任方向 accountable={} harmed={} basis={} confidence={} confirmed={} evidence={}".format(
                    accountable_name,
                    harmed_name,
                    record.responsibility_basis,
                    record.responsibility_confidence,
                    record.responsibility_confirmed,
                    record.responsibility_source_event_id,
                ),
            )
        return True
    except Exception:
        log_exception("repair case status command failed")
        _write(_connection, "Repair case inspection failed; inspect the log.")
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.crisis_status",
    command_type=sims4.commands.CommandType.Live,
)
def relationship_crisis_status(target_sim_id: int=None, _connection=None):
    """Inspect persistent crisis cases and the latest utility result."""
    active = _active_sim_info()
    target = _find_sim_info(target_sim_id) if target_sim_id else None
    if active is None:
        _write(_connection, "Need an active Sim.")
        return False
    try:
        from fgeh_cheatingharder_event_center import (
            get_last_decision,
            get_last_execution,
        )
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        records = tuple(
            record
            for record in get_memory_service().store.relationship_crises()
            if (
                active.sim_id in record.relationship_pair
                and (
                    target is None
                    or target.sim_id in record.relationship_pair
                )
            )
        )
        _write(_connection, "关系危机档案 count={}".format(len(records)))
        for record in records:
            other_id = next(
                value
                for value in record.relationship_pair
                if value != active.sim_id
            )
            _write(
                _connection,
                "case={} status={} stage={} proposer={} recipient={} "
                "severity={} proposals={} rounds={} actions={}".format(
                    record.case_id,
                    record.status,
                    record.stage,
                    record.proposer_id,
                    record.recipient_id,
                    record.severity,
                    record.proposal_count,
                    record.round_index,
                    len(record.action_history),
                ),
            )
            _write(
                _connection,
                "active_direction={} decision={} execution={}".format(
                    record.role_for(active.sim_id),
                    get_last_decision(active.sim_id, other_id),
                    get_last_execution(active.sim_id, other_id),
                ),
            )
        return True
    except Exception:
        log_exception("relationship crisis status command failed")
        _write(_connection, "Relationship crisis inspection failed.")
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.crisis_force",
    command_type=sims4.commands.CommandType.Live,
)
def force_relationship_crisis_round(target_sim_id: int=None, _connection=None):
    """Force one active-Sim direction through the normal utility pool."""
    active = _active_sim_info()
    if active is None:
        _write(_connection, "Need an active Sim.")
        return False
    try:
        from fgeh_cheatingharder_event_center import publish
        from fgeh_cheatingharder_domain import EventType
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        target = _find_sim_info(target_sim_id) if target_sim_id else None
        record = None
        if target is not None:
            record = get_memory_service().store.find_active_relationship_crisis(
                active.sim_id,
                target.sim_id,
            )
        else:
            record = next((
                value
                for value in get_memory_service().store.relationship_crises()
                if value.is_active and active.sim_id in value.relationship_pair
            ), None)
            if record is not None:
                other_id = next(
                    value
                    for value in record.relationship_pair
                    if value != active.sim_id
                )
                target = _find_sim_info(other_id)
        if record is None or target is None:
            _write(_connection, "No active relationship crisis for this Sim.")
            return False
        publish(
            EventType.RELATIONSHIP_REEVALUATION,
            source="debug_relationship_crisis",
            observer_id=active.sim_id,
            partner_id=target.sim_id,
            payload={
                "relationship_crisis_case_id": record.case_id,
                "scheduled_reason": "debug_force_crisis_round",
            },
        )
        _write(
            _connection,
            "crisis_round_forced case={} direction={}->{}".format(
                record.case_id,
                active.sim_id,
                target.sim_id,
            ),
        )
        return True
    except Exception:
        log_exception("relationship crisis force command failed")
        _write(_connection, "Relationship crisis force failed.")
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.open_journal",
    command_type=sims4.commands.CommandType.Live,
)
def open_romantic_journal(_connection=None):
    """Open the active Sim's read-only romantic journal in EA Notebook."""
    active = _active_sim_info()
    if active is None:
        _write(_connection, "Need an active Sim to open the romantic journal.")
        return False
    try:
        from fgeh_cheatingharder_notebook_ui import show_romantic_journal

        blueprint = show_romantic_journal(active)
        _write(
            _connection,
            "romantic_journal_opened viewer={} entries={}".format(
                active.sim_id,
                blueprint["total_entries"],
            ),
        )
        return True
    except Exception:
        log_exception("romantic journal command failed")
        _write(_connection, "Romantic journal failed; inspect the log.")
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.export_ledger",
    command_type=sims4.commands.CommandType.Live,
)
def export_ledger(_connection=None):
    """Export a read-only JSON snapshot for the external ledger viewer."""
    try:
        from fgeh_cheatingharder_ledger_export import export_current_ledger

        path = export_current_ledger()
        _write(_connection, "romantic_ledger_export={}".format(path))
        _write(
            _connection,
            "Load this JSON in the external Romantic Ledger Viewer.",
        )
        return True
    except Exception:
        log_exception("romantic ledger export command failed")
        _write(_connection, "Romantic ledger export failed; inspect the log.")
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.takeover_status",
    command_type=sims4.commands.CommandType.Live,
)
def takeover_status(target_sim_id: int=None, _connection=None):
    """Inspect breakup ownership and the active visible reaction."""
    observer = _active_sim_info()
    target = (
        _find_sim_info(target_sim_id)
        if target_sim_id
        else _find_claimed_target(observer)
    )
    if observer is None or target is None:
        _write(_connection, "Need an active Sim and target Sim.")
        return False
    try:
        from fgeh_cheatingharder_breakup_adapter import (
            get_breakup_takeover_status,
        )
        from fgeh_cheatingharder_reaction_runtime import (
            get_relationship_reaction_status,
        )

        takeover = get_breakup_takeover_status(
            observer.sim_id,
            target.sim_id,
        )
        reaction = get_relationship_reaction_status(observer.sim_id)
        _write(
            _connection,
            "breakup_takeover={}".format(takeover),
        )
        _write(
            _connection,
            "relationship_reaction={}".format(reaction),
        )
        return True
    except Exception:
        log_exception("takeover status command failed")
        _write(_connection, "Relationship takeover inspection failed.")
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.test_log",
    command_type=sims4.commands.CommandType.Live,
)
def test_log(_connection=None):
    log("manual test_log command received")
    _write(_connection, "FGEH CheatingHarder wrote a test log entry.")
    _write(_connection, "log_paths={}".format(" | ".join(get_log_paths()) or "<none>"))
    return True


@sims4.commands.Command(
    "fgeh.cheatingharder.test_notification",
    command_type=sims4.commands.CommandType.Live,
)
def test_notification(target_sim_id: int=None, _connection=None):
    observer = _active_sim_info()
    target = _find_sim_info(target_sim_id) if observer and target_sim_id else _find_unexpected_visitor(observer)
    if observer is None or target is None:
        _write(_connection, "Need an active Sim and an instanced target Sim.")
        log("manual notification test failed observer={} target={}", observer, target)
        return False
    result = show_claim_notification(observer, target)
    _write(_connection, "notification_result={} observer={} target={}".format(
        result,
        observer.sim_id,
        target.sim_id,
    ))
    log(
        "manual notification test result={} observer={} target={}",
        result,
        observer.sim_id,
        target.sim_id,
    )
    return result


@sims4.commands.Command(
    "fgeh.cheatingharder.force_check_in",
    command_type=sims4.commands.CommandType.Live,
)
def force_check_in(visitor_sim_id: int=None, partner_sim_id: int=None, _connection=None):
    """Force a visitor to the active Sim's lot, or use two explicit Sim IDs."""
    log(
        "manual force check-in command received visitor_id={} partner_id={}",
        visitor_sim_id,
        partner_sim_id,
    )
    _write(_connection, "FGEH CheatingHarder: force_check_in received.")
    partner = _active_sim_info() if partner_sim_id is None else _find_sim_info(partner_sim_id)
    visitor = _find_sim_info(visitor_sim_id) if visitor_sim_id else _find_unexpected_visitor(partner)
    if visitor is None or partner is None:
        _write(_connection, "Need a visitor Sim and an active-lot partner Sim.")
        return False
    try:
        from fgeh_cheatingharder_scheduler import schedule_unexpected_check_in

        if not register_check_in(visitor, partner, trigger_reason="manual_force_command"):
            _write(_connection, "check-in skipped by visitor limit or existing state.")
            return False
        result = schedule_unexpected_check_in(
            visitor,
            partner,
            trigger_reason="manual_force_command",
        )
        _write(_connection, "check_in_request_sent={} visitor={} partner={}".format(
            result,
            visitor.sim_id,
            partner.sim_id,
        ))
        log(
            "manual force check-in visitor={} target={} situation={}",
            visitor.sim_id,
            partner.sim_id,
            result,
        )
        return bool(result)
    except Exception:
        log_exception("manual force check-in failed")
        _write(_connection, "force check-in failed; inspect the debug log.")
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.test_seek_reassurance",
    command_type=sims4.commands.CommandType.Live,
)
def test_seek_reassurance(target_sim_id: int=None, _connection=None):
    """Exercise the real autonomy executor without fabricating betrayal."""
    observer = _active_sim_info()
    target = (
        _find_sim_info(target_sim_id)
        if target_sim_id
        else _find_betrayal_partner(observer)
    )
    if observer is None or target is None:
        _write(
            _connection,
            "Need an active Sim and a claimed/only-beloved target.",
        )
        return False
    try:
        from fgeh_cheatingharder_autonomous_behavior_runtime import (
            consume_memory_opportunities,
            get_autonomous_behavior_status,
        )
        from fgeh_cheatingharder_betrayal_memory_rules import (
            OPPORTUNITY_BETRAYAL_RESPONSE,
        )
        from fgeh_cheatingharder_betrayal_reactions import BetrayalIntent
        from fgeh_cheatingharder_memory_models import MemoryOpportunity

        now = services.time_service().sim_now
        event_id = "debug-seek-reassurance:{}:{}:{}".format(
            observer.sim_id,
            target.sim_id,
            now.absolute_ticks(),
        )
        results = consume_memory_opportunities((
            MemoryOpportunity(
                OPPORTUNITY_BETRAYAL_RESPONSE,
                observer.sim_id,
                target.sim_id,
                reason="debug_executor_test",
                urgency=100,
                event_id=event_id,
                context={
                    "selected_intent": BetrayalIntent.SEEK_REASSURANCE,
                    "execution_enabled": True,
                    "debug_executor_test": True,
                    "debug_bypass_cooldown": True,
                },
            ),
        ))
        status = get_autonomous_behavior_status(
            observer.sim_id,
            target.sim_id,
        )
        _write(
            _connection,
            "seek_reassurance_admission={} status={}".format(
                tuple(value.to_data() for value in results),
                status,
            ),
        )
        log(
            "manual seek reassurance test observer={} partner={} admission={} status={}",
            observer.sim_id,
            target.sim_id,
            tuple(value.to_data() for value in results),
            status,
        )
        return any(value.admitted for value in results)
    except Exception:
        log_exception("manual seek reassurance test failed")
        _write(
            _connection,
            "seek reassurance test failed; inspect the debug log.",
        )
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.test_confront_partner",
    command_type=sims4.commands.CommandType.Live,
)
def test_confront_partner(target_sim_id: int=None, _connection=None):
    """Confront the partner recorded in the latest betrayal event."""
    observer = _active_sim_info()
    betrayal_event, recorded_partner, recorded_rival = (
        _latest_recorded_betrayal_context(observer)
    )
    if observer is None or betrayal_event is None or recorded_partner is None:
        _write(
            _connection,
            "No complete betrayal event is recorded for the active Sim.",
        )
        return False
    if (
        target_sim_id
        and int(target_sim_id) != int(recorded_partner.sim_id)
    ):
        _write(
            _connection,
            "Target rejected: confront_partner must target recorded partner {} "
            "(recorded rival {}).".format(
                recorded_partner.sim_id,
                None if recorded_rival is None else recorded_rival.sim_id,
            ),
        )
        return False
    target = recorded_partner
    target_source = "ledger_partner"
    try:
        from fgeh_cheatingharder_autonomous_behavior_runtime import (
            consume_memory_opportunities,
            get_autonomous_behavior_status,
        )
        from fgeh_cheatingharder_betrayal_memory_rules import (
            OPPORTUNITY_BETRAYAL_RESPONSE,
        )
        from fgeh_cheatingharder_betrayal_reactions import BetrayalIntent
        from fgeh_cheatingharder_memory_models import MemoryOpportunity

        now = services.time_service().sim_now
        debug_event_id = "debug-confront-partner:{}:{}:{}".format(
            observer.sim_id,
            target.sim_id,
            now.absolute_ticks(),
        )
        results = consume_memory_opportunities((
            MemoryOpportunity(
                OPPORTUNITY_BETRAYAL_RESPONSE,
                observer.sim_id,
                target.sim_id,
                reason="debug_executor_test",
                urgency=100,
                event_id=debug_event_id,
                context={
                    "selected_intent": BetrayalIntent.CONFRONT_PARTNER,
                    "execution_enabled": True,
                    "debug_executor_test": True,
                    "debug_bypass_cooldown": True,
                    "target_role": "partner",
                    "target_id": target.sim_id,
                    "source_betrayal_event_id": betrayal_event.event_id,
                },
            ),
        ))
        status = get_autonomous_behavior_status(
            observer.sim_id,
            target.sim_id,
        )
        _write(
            _connection,
            "confront_partner_target={} source={} source_event={} "
            "recorded_rival={} admission={} status={}".format(
                target.sim_id,
                target_source,
                betrayal_event.event_id,
                None if recorded_rival is None else recorded_rival.sim_id,
                tuple(value.to_data() for value in results),
                status,
            ),
        )
        log(
            "manual confront partner test observer={} partner={} rival={} "
            "source_event={} target_source={} admission={} status={}",
            observer.sim_id,
            target.sim_id,
            None if recorded_rival is None else recorded_rival.sim_id,
            betrayal_event.event_id,
            target_source,
            tuple(value.to_data() for value in results),
            status,
        )
        return any(value.admitted for value in results)
    except Exception:
        log_exception("manual confront partner test failed")
        _write(
            _connection,
            "confront partner test failed; inspect the debug log.",
        )
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.test_confront_rival",
    command_type=sims4.commands.CommandType.Live,
)
def test_confront_rival(target_sim_id: int=None, _connection=None):
    """Confront only the rival recorded in the latest betrayal event."""
    observer = _active_sim_info()
    betrayal_event, recorded_partner, recorded_rival = (
        _latest_recorded_betrayal_context(observer)
    )
    if (
        observer is None
        or betrayal_event is None
        or recorded_partner is None
        or recorded_rival is None
    ):
        _write(
            _connection,
            "No complete betrayal event with a recorded rival is available.",
        )
        return False
    if target_sim_id and int(target_sim_id) != int(recorded_rival.sim_id):
        _write(
            _connection,
            "Target rejected: confront_rival must target recorded rival {} "
            "(relationship partner {}).".format(
                recorded_rival.sim_id,
                recorded_partner.sim_id,
            ),
        )
        return False
    try:
        from fgeh_cheatingharder_autonomous_behavior_runtime import (
            consume_memory_opportunities,
            get_autonomous_behavior_status,
        )
        from fgeh_cheatingharder_betrayal_memory_rules import (
            OPPORTUNITY_BETRAYAL_RESPONSE,
        )
        from fgeh_cheatingharder_betrayal_reactions import BetrayalIntent
        from fgeh_cheatingharder_memory_models import MemoryOpportunity

        now = services.time_service().sim_now
        debug_event_id = "debug-confront-rival:{}:{}:{}".format(
            observer.sim_id,
            recorded_rival.sim_id,
            now.absolute_ticks(),
        )
        results = consume_memory_opportunities((
            MemoryOpportunity(
                OPPORTUNITY_BETRAYAL_RESPONSE,
                observer.sim_id,
                recorded_rival.sim_id,
                reason="debug_executor_test",
                urgency=100,
                event_id=debug_event_id,
                context={
                    "selected_intent": BetrayalIntent.CONFRONT_RIVAL,
                    "execution_enabled": True,
                    "debug_executor_test": True,
                    "debug_bypass_cooldown": True,
                    "relationship_partner_id": recorded_partner.sim_id,
                    "rival_id": recorded_rival.sim_id,
                    "target_role": "rival",
                    "target_id": recorded_rival.sim_id,
                    "source_betrayal_event_id": betrayal_event.event_id,
                },
            ),
        ))
        status = get_autonomous_behavior_status(
            observer.sim_id,
            recorded_rival.sim_id,
        )
        _write(
            _connection,
            "confront_rival_target={} relationship_partner={} "
            "source_event={} admission={} status={}".format(
                recorded_rival.sim_id,
                recorded_partner.sim_id,
                betrayal_event.event_id,
                tuple(value.to_data() for value in results),
                status,
            ),
        )
        log(
            "manual confront rival test observer={} rival={} partner={} "
            "source_event={} admission={} status={}",
            observer.sim_id,
            recorded_rival.sim_id,
            recorded_partner.sim_id,
            betrayal_event.event_id,
            tuple(value.to_data() for value in results),
            status,
        )
        return any(value.admitted for value in results)
    except Exception:
        log_exception("manual confront rival test failed")
        _write(
            _connection,
            "confront rival test failed; inspect the debug log.",
        )
        return False


@sims4.commands.Command(
    "fgeh.cheatingharder.autonomy_status",
    command_type=sims4.commands.CommandType.Live,
)
def autonomy_status(target_sim_id: int=None, _connection=None):
    observer = _active_sim_info()
    target = (
        _find_sim_info(target_sim_id)
        if target_sim_id
        else _find_betrayal_partner(observer)
    )
    try:
        from fgeh_cheatingharder_autonomous_behavior_runtime import (
            get_autonomous_behavior_status,
        )

        status = get_autonomous_behavior_status(
            getattr(observer, "sim_id", None),
            getattr(target, "sim_id", None),
        )
        _write(_connection, "autonomy_status={}".format(status))
        return True
    except Exception:
        log_exception("autonomy status command failed")
        _write(_connection, "autonomy status failed; inspect the log.")
        return False


def install_debug_commands():
    log("debug commands installed")
    return True

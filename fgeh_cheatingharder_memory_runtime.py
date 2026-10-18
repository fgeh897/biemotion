"""Sims 4 boundary for the pure romantic-memory framework."""

from fgeh_cheatingharder_debug import log, log_exception
import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_betrayal_episode import (
    BETRAYAL_REACTION_EPISODES,
)
from fgeh_cheatingharder_domain import EventType
from fgeh_cheatingharder_memory_models import EventDraft, ParticipantRole
from fgeh_cheatingharder_memory_pipeline import RomanticMemoryPipeline
from fgeh_cheatingharder_memory_registry import RomanticMemoryRegistry
from fgeh_cheatingharder_memory_rules import register_core_memory_rules
from fgeh_cheatingharder_memory_store import RomanticMemoryStore
from fgeh_cheatingharder_devotion_memory_rules import (
    register_devotion_memory_rules,
)
from fgeh_cheatingharder_betrayal_memory_rules import (
    register_caught_betrayal_rules,
)
from fgeh_cheatingharder_breakup_memory_rules import (
    register_breakup_negotiation_memory_rules,
)
from fgeh_cheatingharder_reconciliation_memory_rules import (
    register_reconciliation_memory_rules,
)
from fgeh_cheatingharder_repair_memory_rules import (
    register_repair_memory_rules,
)
from fgeh_cheatingharder_reaction_memory_rules import (
    register_reaction_memory_rules,
)
from fgeh_cheatingharder_autonomous_action_memory_rules import (
    register_autonomous_action_memory_rules,
)


_SERVICE = None


class RomanticMemoryService:

    def __init__(self, store=None):
        self.store = store or RomanticMemoryStore()
        self.registry = register_core_memory_rules(RomanticMemoryRegistry())
        register_devotion_memory_rules(self.registry)
        register_caught_betrayal_rules(self.registry)
        register_breakup_negotiation_memory_rules(self.registry)
        register_reconciliation_memory_rules(self.registry)
        register_repair_memory_rules(self.registry)
        register_reaction_memory_rules(self.registry)
        register_autonomous_action_memory_rules(self.registry)
        self.pipeline = RomanticMemoryPipeline(
            self.store,
            self.registry,
            error_handler=self._on_pipeline_error,
            opportunity_sink=self._on_opportunities,
        )
        self.store.set_state_change_listener(self._on_state_change)

    def _on_pipeline_error(self, message, _exception):
        log("romantic memory pipeline error: {}", message)

    def _on_opportunities(self, opportunities, report):
        _bind_betrayal_episode_reaction(report)
        log(
            "romantic memory opportunities event={} values={}",
            report.event.event_id,
            tuple(value.to_data() for value in opportunities),
        )
        try:
            from fgeh_cheatingharder_autonomous_behavior_runtime import (
                consume_memory_opportunities,
            )
            from fgeh_cheatingharder_betrayal_choice import (
                route_betrayal_opportunities,
            )

            route_betrayal_opportunities(
                opportunities,
                report,
                consume_memory_opportunities,
                player_mode=settings.BETRAYAL_PLAYER_DECISION_MODE,
            )
        except Exception:
            log_exception(
                "romantic memory unified opportunity dispatch failed"
            )
            try:
                consume_memory_opportunities(opportunities, report=report)
            except Exception:
                log_exception(
                    "romantic memory fallback opportunity dispatch failed"
                )

    def _on_state_change(self, delta, old_value, new_value, _state):
        try:
            from fgeh_cheatingharder_state import mirror_memory_dimension_to_ea

            mirror_memory_dimension_to_ea(
                delta.observer_id,
                delta.partner_id,
                delta.dimension,
                new_value,
                reason=delta.reason,
            )
        except Exception:
            log_exception(
                "romantic memory state mirror failed edge={}->{} dimension={}".format(
                    delta.observer_id,
                    delta.partner_id,
                    delta.dimension,
                )
            )

    def export_snapshot(self):
        return self.store.to_snapshot()

    def status(self):
        return {
            "lineage": self.store.save_lineage_id,
            "counts": self.store.counts(),
            "registry": self.registry.describe(),
        }


def get_memory_service():
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = RomanticMemoryService()
        log(
            "romantic memory service created lineage={}",
            _SERVICE.store.save_lineage_id,
        )
    return _SERVICE


def reset_memory_service(snapshot=None):
    global _SERVICE
    BETRAYAL_REACTION_EPISODES.reset()
    store = (
        RomanticMemoryStore()
        if snapshot is None
        else RomanticMemoryStore.from_snapshot(snapshot)
    )
    _SERVICE = RomanticMemoryService(store=store)
    log(
        "romantic memory service reset lineage={} restored={}",
        store.save_lineage_id,
        snapshot is not None,
    )
    return _SERVICE


def _sim_now_ticks():
    try:
        import services

        now = services.time_service().sim_now
        absolute_ticks = getattr(now, "absolute_ticks", None)
        return absolute_ticks() if callable(absolute_ticks) else int(now)
    except Exception:
        return None


def _sim_now_minutes():
    try:
        import date_and_time

        ticks = _sim_now_ticks()
        if ticks is None:
            return 0.0
        return float(date_and_time.TimeSpan(int(ticks)).in_minutes())
    except Exception:
        return 0.0


def _betrayal_episode_context(event, payload):
    if getattr(event, "event_type", None) not in (
        EventType.CAUGHT_CHEATING,
        EventType.ROMANTIC_BOUNDARY_DISCOVERED,
    ):
        return {}
    observer_id = getattr(event, "observer_id", None)
    partner_id = getattr(event, "partner_id", None)
    rival_id = getattr(event, "rival_id", None)
    if observer_id is None or partner_id is None or rival_id is None:
        return {}
    evidence_keys = []
    for key in (
        "source_romance_event_ids",
        "eyewitness_source_event_ids",
    ):
        evidence_keys.extend(tuple(payload.get(key, ()) or ()))
    cause_id = payload.get("cause_id")
    if cause_id:
        evidence_keys.append(cause_id)
    observation = BETRAYAL_REACTION_EPISODES.observe(
        observer_id,
        partner_id,
        rival_id,
        getattr(event, "event_id", "unknown"),
        getattr(event, "event_type", "unknown"),
        _sim_now_minutes(),
        severity=payload.get("severity", 0),
        evidence_keys=evidence_keys,
        merge_window_minutes=(
            settings.BETRAYAL_REACTION_EPISODE_SIM_MINUTES
        ),
    )
    episode = observation.episode
    data = observation.to_data()
    if (
        observation.is_primary
        and observation.merge_reason == "post_resolution_reoffense"
    ):
        try:
            from fgeh_cheatingharder_breakup_adapter import (
                release_breakup_takeover_for_new_betrayal,
            )

            data["released_previous_breakup_takeover"] = (
                release_breakup_takeover_for_new_betrayal(
                    observer_id,
                    partner_id,
                    episode_id=episode.episode_id,
                )
            )
        except Exception:
            log_exception(
                "betrayal reoffense takeover release failed episode={}".format(
                    episode.episode_id
                )
            )
    log(
        "betrayal reaction episode observed episode={} primary={} reason={} "
        "event={} status={} selected={} sources={}",
        episode.episode_id,
        observation.is_primary,
        observation.merge_reason,
        getattr(event, "event_id", None),
        episode.status,
        episode.selected_intent,
        tuple(episode.source_event_ids),
    )
    return {
        "betrayal_episode": data,
        "betrayal_episode_primary": observation.is_primary,
        "betrayal_episode_reaction": dict(episode.reaction_details),
    }


def _bind_betrayal_episode_reaction(report, external_context=None):
    external_context = dict(external_context or {})
    interpretation = next((
        value
        for value in tuple(report.interpretations or ())
        if (
            dict(getattr(value, "details", {}) or {}).get("selected_intent")
            and dict(getattr(value, "details", {}) or {}).get(
                "betrayal_episode_primary",
                False,
            )
        )
    ), None)
    if interpretation is None:
        return
    details = dict(interpretation.details or {})
    episode_data = dict(external_context.get("betrayal_episode", {}) or {})
    episode_id = (
        details.get("betrayal_episode_id")
        or episode_data.get("episode_id")
    )
    if not episode_id:
        return
    episode = BETRAYAL_REACTION_EPISODES.bind_primary_reaction(
        episode_id,
        details.get("selected_intent"),
        details=details,
    )
    if episode is not None:
        log(
            "betrayal reaction episode selected episode={} intent={} event={}",
            episode.episode_id,
            episode.selected_intent,
            report.event.event_id,
        )


def _seed_directed_edges(directed_edges):
    try:
        import services
        from fgeh_cheatingharder_state import get_directed_state

        manager = services.sim_info_manager()
        for observer_id, partner_id in directed_edges:
            observer = manager.get(int(observer_id))
            partner = manager.get(int(partner_id))
            if observer is not None and partner is not None:
                get_directed_state(observer, partner)
    except Exception:
        log_exception("romantic memory directed edge bootstrap failed")


def _participants_from_legacy_event(event):
    participants = {}

    def add(role, value):
        if value is None:
            return
        participants.setdefault(role, []).append(int(value))

    add(ParticipantRole.ACTOR, getattr(event, "actor_id", None))
    add(ParticipantRole.TARGET, getattr(event, "target_id", None))
    add(ParticipantRole.OBSERVER, getattr(event, "observer_id", None))
    add(ParticipantRole.PARTNER, getattr(event, "partner_id", None))
    add(ParticipantRole.RIVAL, getattr(event, "rival_id", None))
    payload = dict(getattr(event, "payload", {}) or {})
    for sim_id in payload.get("witness_ids", ()):
        add(ParticipantRole.WITNESS, sim_id)
    for sim_id in payload.get("complicit_sim_ids", ()):
        add(ParticipantRole.COMPLICIT, sim_id)
    return participants


def _relationship_pairs_from_legacy_event(event, directed_edges):
    pairs = list(directed_edges)
    for first_name, second_name in (
        ("actor_id", "target_id"),
        ("observer_id", "partner_id"),
    ):
        first_id = getattr(event, first_name, None)
        second_id = getattr(event, second_name, None)
        if first_id is not None and second_id is not None:
            pairs.append((first_id, second_id))
    relationship_member_ids = tuple(
        dict(getattr(event, "payload", {}) or {}).get(
            "relationship_member_ids",
            (),
        )
    )
    if len(relationship_member_ids) == 2:
        pairs.append(relationship_member_ids)
    return tuple(pairs)


def _log_influence_shadows(report):
    for interpretation in tuple(report.interpretations or ()):
        details = dict(getattr(interpretation, "details", {}) or {})
        if details.get("episode_supplementary", False):
            continue
        shadow = dict(details.get("influence_shadow", {}) or {})
        if not shadow:
            continue
        comparison = dict(shadow.get("comparison", {}) or {})
        log(
            "relationship influence shadow event={} profile={} status={} authoritative={} legacy_selected={} shadow_selected={} attribution_max_delta={} state_delta_max_delta={} candidate_score_max_delta={}",
            report.event.event_id,
            shadow.get("profile_key"),
            shadow.get("status"),
            shadow.get("authoritative_model"),
            comparison.get("legacy_selected_intent"),
            comparison.get("shadow_selected_intent"),
            comparison.get("attribution_max_abs_delta"),
            comparison.get("state_delta_max_abs_delta"),
            comparison.get("candidate_score_max_abs_delta"),
        )
        matrix = dict(
            details.get("influence_shadow_matrix", {}) or {}
        )
        for profile_key in sorted(matrix):
            profile_result = dict(matrix[profile_key] or {})
            if profile_result.get("active_profile", False):
                continue
            profile_comparison = dict(
                profile_result.get("comparison", {}) or {}
            )
            log(
                "relationship influence shadow counterfactual event={} profile={} status={} legacy_selected={} shadow_selected={} attribution_max_delta={} state_delta_max_delta={} candidate_score_max_delta={}",
                report.event.event_id,
                profile_result.get("profile_key"),
                profile_result.get("status"),
                profile_comparison.get("legacy_selected_intent"),
                profile_comparison.get("shadow_selected_intent"),
                profile_comparison.get("attribution_max_abs_delta"),
                profile_comparison.get("state_delta_max_abs_delta"),
                profile_comparison.get("candidate_score_max_abs_delta"),
            )


def record_relationship_event(event, directed_edges=None):
    """Convert the old event-center envelope into the new immutable ledger."""
    directed_edges = tuple(
        (int(edge[0]), int(edge[1]))
        for edge in (directed_edges or ())
        if isinstance(edge, (tuple, list)) and len(edge) == 2
    )
    _seed_directed_edges(directed_edges)
    payload = dict(getattr(event, "payload", {}) or {})
    source = str(getattr(event, "source", "legacy_event_center"))
    source_event_id = str(getattr(event, "event_id", "unknown"))
    draft = EventDraft(
        getattr(event, "event_type", "unknown"),
        source,
        participants=_participants_from_legacy_event(event),
        source_event_id=source_event_id,
        source_fingerprint="{}:{}".format(source, source_event_id),
        cause_id=payload.get("cause_id") or source_event_id,
        occurred_at=payload.get("occurred_at", _sim_now_ticks()),
        severity=payload.get("severity", 0),
        payload=payload,
        contract_ids=payload.get("contract_ids", ()),
        relationship_pairs=_relationship_pairs_from_legacy_event(
            event,
            directed_edges,
        ),
    )
    external_context = {
        "directed_edges": directed_edges,
        "legacy_event_type": getattr(event, "event_type", None),
    }
    external_context.update(_betrayal_episode_context(event, payload))
    report = get_memory_service().pipeline.process(
        draft,
        external_context=external_context,
    )
    _bind_betrayal_episode_reaction(report, external_context)
    _log_influence_shadows(report)
    try:
        from fgeh_cheatingharder_relationship import (
            project_betrayal_rival_relationship_bit,
        )

        project_betrayal_rival_relationship_bit(report)
    except Exception:
        log_exception("romantic memory relationship-bit projection failed")
    log(
        "romantic memory processed source_event={} ledger_event={} duplicate={} claims={} beliefs={} interpretations={} state_deltas={} summaries={} opportunities={} errors={}",
        source_event_id,
        report.event.event_id,
        report.duplicate,
        len(report.claims),
        len(report.beliefs),
        len(report.interpretations),
        len(report.state_deltas),
        len(report.summary_edges),
        len(report.opportunities),
        tuple(report.errors),
    )
    return report


def get_memory_status():
    return get_memory_service().status()


def get_memory_summary(observer_id, partner_id):
    return get_memory_service().store.get_summary(observer_id, partner_id)

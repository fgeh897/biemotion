"""Bridge EA romantic-boundary cognition into the romantic memory system."""

from collections import deque

import services

try:
    from relationships.relationship_track import RelationshipTrack
    from relationships.satisfaction_tuning import SatisfactionTuning
except Exception:
    RelationshipTrack = None
    SatisfactionTuning = None

import fgeh_cheatingharder_injector as injector
import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_domain import EventType
from fgeh_cheatingharder_event_receipts import (
    EvidenceReceiptRegistry,
    EvidenceReceiptStatus,
)
from fgeh_cheatingharder_relationship import get_sim_info, has_claim, is_enabled
from fgeh_cheatingharder_romance_correlation import (
    RecentRomanceCorrelation,
    RomanceCorrelationMatch,
)


_INSTALLED = False
_RECENT_ROMANCE = RecentRomanceCorrelation(
    settings.EA_AWARENESS_CORRELATION_CAPACITY
)
_PENDING_SIGNALS = deque(
    maxlen=settings.EA_AWARENESS_PENDING_SIGNAL_CAPACITY
)
_BOUNDARY_BIT_NAME_MARKERS = (
    "romantic_boundary",
    "romance_boundary",
    "broken_boundary",
    "justcaughtcheating",
)
_PROJECT_BIT_NAME_PREFIX = "fgeh_cheatingharder_"
_RECENT_BOUNDARY_WARNINGS = {}
_AFFAIR_EVIDENCE_RECEIPTS = EvidenceReceiptRegistry(
    settings.EA_AWARENESS_EVIDENCE_RECEIPT_CAPACITY
)


def _sim_now_ticks():
    try:
        now = services.time_service().sim_now
        absolute_ticks = getattr(now, "absolute_ticks", None)
        return int(absolute_ticks() if callable(absolute_ticks) else now)
    except Exception:
        return None


def _correlation_window_ticks():
    try:
        import date_and_time

        return int(date_and_time.create_time_span(
            minutes=settings.EA_AWARENESS_CORRELATION_SIM_MINUTES
        ).in_ticks())
    except Exception:
        return int(settings.EA_AWARENESS_CORRELATION_SIM_MINUTES)


def _pending_signal_window_ticks():
    try:
        import date_and_time

        return int(date_and_time.create_time_span(
            minutes=settings.EA_AWARENESS_PENDING_SIGNAL_SIM_MINUTES
        ).in_ticks())
    except Exception:
        return int(settings.EA_AWARENESS_PENDING_SIGNAL_SIM_MINUTES)


def _breakup_warning_window_ticks():
    try:
        import date_and_time

        return int(date_and_time.create_time_span(
            minutes=settings.EA_AUTO_BREAKUP_WARNING_WINDOW_SIM_MINUTES
        ).in_ticks())
    except Exception:
        return int(settings.EA_AUTO_BREAKUP_WARNING_WINDOW_SIM_MINUTES)


def _guid64(value):
    try:
        return int(getattr(value, "guid64", None))
    except (TypeError, ValueError):
        return None


def _is_satisfaction_track(track):
    if SatisfactionTuning is None:
        return False
    stat_type = getattr(track, "stat_type", None)
    tuned_type = getattr(
        SatisfactionTuning,
        "RELATIONSHIP_SATISFACTION_TRACK",
        None,
    )
    if stat_type is tuned_type and tuned_type is not None:
        return True
    stat_id = _guid64(stat_type)
    tuned_id = _guid64(tuned_type)
    return stat_id is not None and stat_id == tuned_id


def _directional_pair(track):
    tracker = getattr(track, "tracker", None)
    if tracker is None:
        tracker = getattr(track, "_tracker", None)
    rel_data = getattr(tracker, "rel_data", None)
    try:
        observer_id = int(getattr(rel_data, "sim_id_a", None))
        partner_id = int(getattr(rel_data, "sim_id_b", None))
    except (TypeError, ValueError):
        return None
    if observer_id <= 0 or partner_id <= 0 or observer_id == partner_id:
        return None
    return observer_id, partner_id


def _is_loading(track, kwargs):
    if kwargs.get("from_load", False):
        return True
    tracker = getattr(track, "tracker", None)
    if tracker is None:
        tracker = getattr(track, "_tracker", None)
    return bool(
        getattr(tracker, "load_in_progress", False)
        or getattr(tracker, "suppress_callback_setup_during_load", False)
    )


def _has_directed_edge(observer, partner):
    if observer is None or partner is None:
        return False
    if has_claim(observer, partner):
        return True
    try:
        from fgeh_cheatingharder_state import has_initialized_directed_state

        if has_initialized_directed_state(observer, partner):
            return True
    except Exception:
        log_exception(
            "EA awareness directed state edge lookup failed observer={} partner={}".format(
                getattr(observer, "sim_id", None),
                getattr(partner, "sim_id", None),
            )
        )
    try:
        from fgeh_cheatingharder_devotion_runtime import get_devotion_bond

        bond = get_devotion_bond(observer.sim_id)
        return bond is not None and bond.beloved_id == partner.sim_id
    except Exception:
        log_exception(
            "EA awareness devotion edge lookup failed observer={} partner={}".format(
                getattr(observer, "sim_id", None),
                getattr(partner, "sim_id", None),
            )
        )
        return False


def _local_witness_edges(actor_info, target_info):
    results = []
    details = {}
    try:
        from fgeh_cheatingharder_route import evaluate_local_witness

        for candidate_sim in services.sim_info_manager().instanced_sims_gen():
            observer = get_sim_info(candidate_sim)
            observer_id = getattr(observer, "sim_id", None)
            if observer_id in (actor_info.sim_id, target_info.sim_id):
                continue
            for partner, rival in (
                (actor_info, target_info),
                (target_info, actor_info),
            ):
                if not _has_directed_edge(observer, partner):
                    continue
                witnessed, reason, distances = evaluate_local_witness(
                    observer,
                    partner,
                    rival,
                )
                edge = (observer_id, partner.sim_id, rival.sim_id)
                details["{}:{}:{}".format(*edge)] = {
                    "qualified": bool(witnessed),
                    "reason": reason,
                    "distance_squared": tuple(distances or ()),
                }
                if witnessed:
                    results.append(edge)
    except Exception:
        log_exception("recent romance local witness snapshot failed")
    return tuple(results), details


def record_recent_romance_event(
    actor_id,
    target_id,
    event_id,
    payload=None,
):
    now_ticks = _sim_now_ticks()
    if now_ticks is None:
        return None
    manager = services.sim_info_manager()
    actor = manager.get(int(actor_id))
    target = manager.get(int(target_id))
    if actor is None or target is None:
        return None
    local_edges, witness_details = _local_witness_edges(actor, target)
    cached_payload = dict(payload or {})
    cached_payload["local_witness_evidence"] = witness_details
    record = _RECENT_ROMANCE.record(
        event_id,
        actor.sim_id,
        target.sim_id,
        now_ticks,
        payload=cached_payload,
        local_witness_edges=local_edges,
    )
    log(
        "recent romance cached event={} actor={} target={} local_witness_edges={}",
        record.event_id,
        record.actor_id,
        record.target_id,
        record.local_witness_edges,
    )
    _flush_pending_awareness_signals(now_ticks)
    return record


def reset_ea_awareness_runtime():
    _RECENT_ROMANCE.clear()
    _PENDING_SIGNALS.clear()
    _RECENT_BOUNDARY_WARNINGS.clear()
    _AFFAIR_EVIDENCE_RECEIPTS.clear()
    try:
        from fgeh_cheatingharder_breakup_adapter import (
            reset_breakup_adapter_runtime,
        )

        reset_breakup_adapter_runtime()
    except Exception:
        log_exception("EA breakup transition runtime reset failed")
    log("EA romantic awareness runtime reset")


def _awareness_evidence_receipt(
    observer_id,
    partner_id,
    rival_id,
    acquisition_mode,
    signal,
    signal_payload,
    proposed_event_id,
):
    """Deduplicate one affair secret while allowing stronger later evidence."""
    secret_id = dict(signal_payload or {}).get("secret_id")
    if secret_id is None:
        return (
            EvidenceReceiptStatus.NEW,
            str(proposed_event_id),
            None,
        )
    canonical_event_id = "ea-affair-awareness:{}:{}:{}:{}".format(
        secret_id,
        observer_id,
        partner_id,
        rival_id,
    )
    status, receipt, previous_mode = _AFFAIR_EVIDENCE_RECEIPTS.observe(
        (
            "affair_secret",
            str(secret_id),
            int(observer_id),
            int(partner_id),
            int(rival_id),
        ),
        canonical_event_id,
        acquisition_mode,
        source_signal=signal,
    )
    return status, receipt.canonical_event_id, previous_mode


def _publish_awareness_evidence_upgrade(
    observer_id,
    partner_id,
    rival_id,
    canonical_event_id,
    previous_mode,
    acquisition_mode,
    signal,
    payload,
    actor_id=None,
    target_id=None,
):
    """Record stronger knowledge without reducing relationship state again."""
    try:
        from fgeh_cheatingharder_event_center import publish

        upgrade_payload = dict(payload or {})
        upgrade_payload.update({
            "canonical_awareness_event_id": canonical_event_id,
            "previous_acquisition_mode": previous_mode,
            "acquisition_mode": acquisition_mode,
            "awareness_signal": str(signal),
            "knowledge_evidence_only": True,
        })
        publish(
            EventType.ROMANTIC_KNOWLEDGE_EVIDENCE_UPDATED,
            source="ea_romantic_boundary_awareness",
            event_id="{}:evidence:{}".format(
                canonical_event_id,
                acquisition_mode,
            ),
            actor_id=actor_id,
            target_id=target_id,
            observer_id=observer_id,
            partner_id=partner_id,
            rival_id=rival_id,
            payload=upgrade_payload,
        )
        log(
            "EA awareness evidence upgraded observer={} partner={} rival={} old={} new={} canonical={}",
            observer_id,
            partner_id,
            rival_id,
            previous_mode,
            acquisition_mode,
            canonical_event_id,
        )
        return True
    except Exception:
        log_exception("EA romantic awareness evidence upgrade failed")
        return False


def _publish_awareness(
    observer_id,
    partner_id,
    match,
    signal,
    signal_payload=None,
):
    rival_id = match.rival_id
    records = tuple(sorted(
        match.records,
        key=lambda value: value.occurred_ticks,
    ))
    if not records or rival_id is None:
        return False
    eyewitness_records = tuple(
        record
        for record in records
        if record.was_local_witness(observer_id, partner_id, rival_id)
    )
    acquisition_mode = (
        "eyewitness" if eyewitness_records else "ea_confirmed"
    )
    event_type = (
        EventType.CAUGHT_CHEATING
        if eyewitness_records
        else EventType.ROMANTIC_BOUNDARY_DISCOVERED
    )
    latest = records[-1]
    payload = dict(latest.payload)
    payload.update(dict(signal_payload or {}))
    payload.update({
        "cause_id": latest.event_id,
        "source_romance_event_ids": tuple(
            record.event_id for record in records
        ),
        "eyewitness_source_event_ids": tuple(
            record.event_id for record in eyewitness_records
        ),
        "local_witness_snapshots": {
            record.event_id: record.payload.get(
                "local_witness_evidence",
                {},
            )
            for record in records
        },
        "awareness_signal": str(signal),
        "acquisition_mode": acquisition_mode,
        "severity": 100 if eyewitness_records else 85,
    })
    if eyewitness_records:
        payload["witness_ids"] = (observer_id,)
    proposed_event_id = "ea-awareness:{}:{}:{}:{}".format(
        observer_id,
        partner_id,
        rival_id,
        latest.event_id,
    )
    receipt_status, canonical_event_id, previous_mode = (
        _awareness_evidence_receipt(
            observer_id,
            partner_id,
            rival_id,
            acquisition_mode,
            signal,
            signal_payload,
            proposed_event_id,
        )
    )
    if receipt_status == EvidenceReceiptStatus.DUPLICATE:
        _RECENT_ROMANCE.mark_consumed(observer_id, records)
        log(
            "EA awareness evidence deduplicated observer={} partner={} rival={} acquisition={} canonical={}",
            observer_id,
            partner_id,
            rival_id,
            acquisition_mode,
            canonical_event_id,
        )
        return False
    if receipt_status == EvidenceReceiptStatus.UPGRADED:
        _RECENT_ROMANCE.mark_consumed(observer_id, records)
        return _publish_awareness_evidence_upgrade(
            observer_id,
            partner_id,
            rival_id,
            canonical_event_id,
            previous_mode,
            acquisition_mode,
            signal,
            payload,
            actor_id=latest.actor_id,
            target_id=latest.target_id,
        )
    try:
        from fgeh_cheatingharder_betrayal_reactions import BetrayalProfileKey
        from fgeh_cheatingharder_event_center import publish

        payload["reaction_profile_key"] = (
            BetrayalProfileKey.RIVAL_BLAMING
            if is_enabled(services.sim_info_manager().get(observer_id))
            else BetrayalProfileKey.BALANCED
        )
        publish(
            event_type,
            source="ea_romantic_boundary_awareness",
            event_id=canonical_event_id,
            actor_id=latest.actor_id,
            target_id=latest.target_id,
            observer_id=observer_id,
            partner_id=partner_id,
            rival_id=rival_id,
            payload=payload,
        )
        _RECENT_ROMANCE.mark_consumed(observer_id, records)
        log(
            "EA awareness published type={} observer={} partner={} rival={} acquisition={} source_events={}",
            event_type,
            observer_id,
            partner_id,
            rival_id,
            acquisition_mode,
            payload["source_romance_event_ids"],
        )
        return True
    except Exception:
        log_exception("EA romantic awareness publish failed")
        return False


def confirm_ea_romantic_awareness(
    observer_id,
    partner_id,
    signal,
    signal_payload=None,
    queue_if_missing=True,
    allowed_rival_ids=None,
    fallback_to_confirmed_known_rival=False,
):
    manager = services.sim_info_manager()
    observer = manager.get(int(observer_id))
    partner = manager.get(int(partner_id))
    if not _has_directed_edge(observer, partner):
        return False
    now_ticks = _sim_now_ticks()
    if now_ticks is None:
        return False
    match = _RECENT_ROMANCE.match(
        observer_id,
        partner_id,
        now_ticks,
        _correlation_window_ticks(),
        allowed_rival_ids=allowed_rival_ids,
    )
    if match.status == RomanceCorrelationMatch.AMBIGUOUS:
        log(
            "EA awareness correlation ambiguous observer={} partner={} rivals={} signal={}",
            observer_id,
            partner_id,
            match.rival_ids,
            signal,
        )
        return False
    if not match.matched:
        log(
            "EA awareness correlation missing observer={} partner={} signal={}",
            observer_id,
            partner_id,
            signal,
        )
        known_rivals = tuple(sorted({
            int(value)
            for value in (allowed_rival_ids or ())
            if value is not None
        }))
        if fallback_to_confirmed_known_rival and len(known_rivals) == 1:
            return _publish_known_rival_awareness(
                observer_id,
                partner_id,
                known_rivals[0],
                signal,
                signal_payload=signal_payload,
            )
        if queue_if_missing:
            _queue_pending_awareness_signal(
                observer_id,
                partner_id,
                signal,
                signal_payload,
                now_ticks,
            )
        return False
    log(
        "EA awareness correlation matched observer={} partner={} rival={} source_events={} signal={}",
        observer_id,
        partner_id,
        match.rival_id,
        tuple(record.event_id for record in match.records),
        signal,
    )
    return _publish_awareness(
        observer_id,
        partner_id,
        match,
        signal,
        signal_payload=signal_payload,
    )


def _publish_known_rival_awareness(
    observer_id,
    partner_id,
    rival_id,
    signal,
    signal_payload=None,
):
    """Publish EA-confirmed knowledge when the source names one rival.

    Without an objective interaction cache this deliberately cannot claim
    eyewitness acquisition, even if all Sims happen to be instantiated now.
    """
    payload = dict(signal_payload or {})
    source_event_id = (
        payload.get("secret_id")
        or payload.get("relationship_bit_id")
        or _sim_now_ticks()
        or "unknown"
    )
    payload.update({
        "cause_id": "ea-confirmed:{}".format(source_event_id),
        "source_romance_event_ids": (),
        "eyewitness_source_event_ids": (),
        "local_witness_snapshots": {},
        "awareness_signal": str(signal),
        "acquisition_mode": "ea_confirmed",
        "severity": 85,
    })
    proposed_event_id = "ea-confirmed-awareness:{}:{}:{}:{}".format(
        observer_id,
        partner_id,
        rival_id,
        source_event_id,
    )
    receipt_status, canonical_event_id, previous_mode = (
        _awareness_evidence_receipt(
            observer_id,
            partner_id,
            rival_id,
            "ea_confirmed",
            signal,
            signal_payload,
            proposed_event_id,
        )
    )
    if receipt_status == EvidenceReceiptStatus.DUPLICATE:
        log(
            "EA known-rival awareness deduplicated observer={} partner={} rival={} canonical={}",
            observer_id,
            partner_id,
            rival_id,
            canonical_event_id,
        )
        return False
    if receipt_status == EvidenceReceiptStatus.UPGRADED:
        return _publish_awareness_evidence_upgrade(
            observer_id,
            partner_id,
            rival_id,
            canonical_event_id,
            previous_mode,
            "ea_confirmed",
            signal,
            payload,
        )
    try:
        from fgeh_cheatingharder_betrayal_reactions import BetrayalProfileKey
        from fgeh_cheatingharder_event_center import publish

        payload["reaction_profile_key"] = (
            BetrayalProfileKey.RIVAL_BLAMING
            if is_enabled(services.sim_info_manager().get(observer_id))
            else BetrayalProfileKey.BALANCED
        )
        publish(
            EventType.ROMANTIC_BOUNDARY_DISCOVERED,
            source="ea_romantic_boundary_awareness",
            event_id=canonical_event_id,
            observer_id=observer_id,
            partner_id=partner_id,
            rival_id=rival_id,
            payload=payload,
        )
        log(
            "EA known-rival awareness published observer={} partner={} rival={} signal={}",
            observer_id,
            partner_id,
            rival_id,
            signal,
        )
        return True
    except Exception:
        log_exception("EA known-rival awareness publish failed")
        return False


def observe_affair_secret_discovery(
    discoverer_id,
    complicit_sim_ids,
    secret_id,
):
    """Translate EA's authoritative secret discovery into directed knowledge."""
    manager = services.sim_info_manager()
    discoverer = manager.get(int(discoverer_id))
    complicit_ids = tuple(sorted({
        int(value)
        for value in (complicit_sim_ids or ())
        if value is not None
    }))
    if discoverer is None or len(complicit_ids) < 2:
        return False
    published = False
    for partner_id in complicit_ids:
        partner = manager.get(partner_id)
        if not _has_directed_edge(discoverer, partner):
            continue
        rival_ids = tuple(
            value for value in complicit_ids if value != partner_id
        )
        published = (
            confirm_ea_romantic_awareness(
                discoverer.sim_id,
                partner_id,
                signal="affair_secret_discovered",
                signal_payload={
                    "secret_id": secret_id,
                    "complicit_sim_ids": complicit_ids,
                },
                queue_if_missing=False,
                allowed_rival_ids=rival_ids,
                fallback_to_confirmed_known_rival=True,
            )
            or published
        )
    return published


def _queue_pending_awareness_signal(
    observer_id,
    partner_id,
    signal,
    signal_payload,
    occurred_ticks,
):
    key = (int(observer_id), int(partner_id), str(signal))
    for pending in _PENDING_SIGNALS:
        if pending["key"] == key:
            pending["payload"].update(dict(signal_payload or {}))
            pending["occurred_ticks"] = int(occurred_ticks)
            return
    _PENDING_SIGNALS.append({
        "key": key,
        "observer_id": int(observer_id),
        "partner_id": int(partner_id),
        "signal": str(signal),
        "payload": dict(signal_payload or {}),
        "occurred_ticks": int(occurred_ticks),
    })
    log(
        "EA awareness signal pending observer={} partner={} signal={}",
        observer_id,
        partner_id,
        signal,
    )


def _flush_pending_awareness_signals(now_ticks=None):
    if not _PENDING_SIGNALS:
        return
    if now_ticks is None:
        now_ticks = _sim_now_ticks()
    if now_ticks is None:
        return
    max_age_ticks = _pending_signal_window_ticks()
    pending_values = tuple(_PENDING_SIGNALS)
    _PENDING_SIGNALS.clear()
    for pending in pending_values:
        age = int(now_ticks) - pending["occurred_ticks"]
        if age < 0 or age > max_age_ticks:
            log(
                "EA awareness pending signal expired observer={} partner={} signal={}",
                pending["observer_id"],
                pending["partner_id"],
                pending["signal"],
            )
            continue
        if confirm_ea_romantic_awareness(
            pending["observer_id"],
            pending["partner_id"],
            pending["signal"],
            signal_payload=pending["payload"],
            queue_if_missing=False,
        ):
            log(
                "EA awareness pending signal resolved observer={} partner={} signal={}",
                pending["observer_id"],
                pending["partner_id"],
                pending["signal"],
            )
            continue
        _PENDING_SIGNALS.append(pending)


def observe_relationship_bit_awareness(sim_info, target_id, bit):
    """Use known EA markers and log unknown relevant bits for live discovery."""
    owner = get_sim_info(sim_info)
    target = services.sim_info_manager().get(int(target_id))
    if owner is None or target is None:
        return False
    bit_id = _guid64(bit)
    bit_name = "{} {}".format(
        getattr(bit, "__name__", ""),
        getattr(bit, "name", ""),
    ).lower()
    if bit_name.strip().startswith(_PROJECT_BIT_NAME_PREFIX):
        return False
    if "shorttermbits_autoinitromance_warning" in bit_name:
        # This EA-authored warning is authoritative evidence that the pair
        # received romance-boundary awareness.  It must not depend on an
        # existing project claim/five-D edge: the first witnessed betrayal is
        # often the event that initializes that subjective direction.
        log(
            "EA relevant relationship bit owner={} target={} bit_id={} bit_name={}",
            owner.sim_id,
            target.sim_id,
            bit_id,
            bit_name,
        )
        now_ticks = _sim_now_ticks()
        if now_ticks is None:
            return False
        match = _RECENT_ROMANCE.match_relationship_signal(
            owner.sim_id,
            target.sim_id,
            now_ticks,
            _correlation_window_ticks(),
        )
        if match.status == RomanceCorrelationMatch.AMBIGUOUS:
            log(
                "EA auto-romance warning correlation ambiguous owner={} target={} rivals={}",
                owner.sim_id,
                target.sim_id,
                match.rival_ids,
            )
            return False
        if not match.matched:
            log(
                "EA auto-romance warning correlation missing owner={} target={}",
                owner.sim_id,
                target.sim_id,
            )
            return False
        _RECENT_BOUNDARY_WARNINGS[(
            match.observer_id,
            match.partner_id,
        )] = (now_ticks, bit_name)
        confirmed = _publish_awareness(
            match.observer_id,
            match.partner_id,
            match,
            signal="autoinit_romance_warning",
            signal_payload={
                "relationship_bit_id": bit_id,
                "relationship_bit_name": bit_name,
            },
        )
        log(
            "EA auto-romance warning awareness owner={} target={} observer={} partner={} rival={} confirmed={}",
            owner.sim_id,
            target.sim_id,
            match.observer_id,
            match.partner_id,
            match.rival_id,
            confirmed,
        )
        return confirmed
    if bit_id == settings.EA_REL_BIT_CHEATER_CAUGHT_BY_SIM:
        observer, partner = target, owner
    elif bit_id == settings.EA_REL_BIT_SIM_CAUGHT_CHEATER:
        observer, partner = owner, target
    elif _has_directed_edge(owner, target):
        observer, partner = owner, target
    elif _has_directed_edge(target, owner):
        observer, partner = target, owner
    else:
        return False
    log(
        "EA relevant relationship bit owner={} target={} bit_id={} bit_name={}",
        owner.sim_id,
        target.sim_id,
        bit_id,
        bit_name,
    )
    is_marker = bit_id in (
        settings.EA_REL_BIT_CHEATER_CAUGHT_BY_SIM,
        settings.EA_REL_BIT_SIM_CAUGHT_CHEATER,
    ) or any(marker in bit_name for marker in _BOUNDARY_BIT_NAME_MARKERS)
    if not is_marker:
        return False
    return confirm_ea_romantic_awareness(
        observer.sim_id,
        partner.sim_id,
        signal="relationship_bit_added",
        signal_payload={
            "relationship_bit_id": bit_id,
            "relationship_bit_name": bit_name,
        },
    )


def observe_ea_breakup_bit(sim_info, target_id, bit):
    bit_id = _guid64(bit)
    bit_name = "{} {}".format(
        getattr(bit, "__name__", ""),
        getattr(bit, "name", ""),
    ).lower()
    if (
        bit_id != settings.EA_REL_BIT_ROMANTIC_BROKEN_UP
        and "romantic-broken_up" not in bit_name
    ):
        return False
    owner = get_sim_info(sim_info)
    target = services.sim_info_manager().get(int(target_id))
    if owner is None or target is None:
        return False
    now_ticks = _sim_now_ticks()
    warning_name = None
    warning_ticks = None
    for observer, partner in ((owner, target), (target, owner)):
        warning = _RECENT_BOUNDARY_WARNINGS.get(
            (observer.sim_id, partner.sim_id)
        )
        if warning is not None:
            candidate_ticks, candidate_name = warning
            age = (
                None
                if now_ticks is None or candidate_ticks is None
                else now_ticks - candidate_ticks
            )
            if (
                age is not None
                and 0 <= age <= _breakup_warning_window_ticks()
            ):
                if warning_ticks is None or candidate_ticks > warning_ticks:
                    warning_ticks = candidate_ticks
                    warning_name = candidate_name
            else:
                _RECENT_BOUNDARY_WARNINGS.pop(
                    (observer.sim_id, partner.sim_id),
                    None,
                )
    for observer, partner in ((owner, target), (target, owner)):
        _RECENT_BOUNDARY_WARNINGS.pop(
            (observer.sim_id, partner.sim_id),
            None,
        )
    breakup_cause = (
        "repeated_romantic_boundary_violation"
        if warning_name is not None
        else "unknown_ea_breakup"
    )
    try:
        from fgeh_cheatingharder_breakup_adapter import complete_ea_breakup

        return complete_ea_breakup(
            owner,
            target,
            bit=bit,
            breakup_cause=breakup_cause,
            boundary_warning_name=warning_name,
        )
    except Exception:
        log_exception(
            "EA breakup completion bridge failed pair={}:{}".format(
                owner.sim_id,
                target.sim_id,
            )
        )
        return False


def install_ea_awareness_adapter():
    global _INSTALLED
    if _INSTALLED:
        return True
    if RelationshipTrack is None:
        log("EA romantic awareness adapter unavailable")
        return False
    try:
        @injector.inject(RelationshipTrack, "set_value", safe=True)
        def _observe_satisfaction_change(
            original,
            track,
            value,
            *args,
            **kwargs
        ):
            should_observe = (
                not _is_loading(track, kwargs)
                and _is_satisfaction_track(track)
            )
            before = None
            if should_observe:
                try:
                    before = float(track.get_value())
                except Exception:
                    before = None
            result = original(track, value, *args, **kwargs)
            if should_observe and before is not None:
                try:
                    after = float(track.get_value())
                    decrease = before - after
                    pair = _directional_pair(track)
                    if (
                        pair is not None
                        and decrease
                        >= settings.EA_AWARENESS_MIN_SATISFACTION_DROP
                    ):
                        log(
                            "EA satisfaction signal observer={} partner={} old={} new={} drop={}",
                            pair[0],
                            pair[1],
                            before,
                            after,
                            decrease,
                        )
                        confirm_ea_romantic_awareness(
                            pair[0],
                            pair[1],
                            signal="relationship_satisfaction_decreased",
                            signal_payload={
                                "satisfaction_before": before,
                                "satisfaction_after": after,
                                "satisfaction_drop": decrease,
                            },
                        )
                except Exception:
                    log_exception(
                        "EA relationship satisfaction observation failed"
                    )
            return result

        _INSTALLED = True
        log(
            "EA romantic awareness adapter installed satisfaction_tuning_found={}",
            getattr(
                SatisfactionTuning,
                "RELATIONSHIP_SATISFACTION_TRACK",
                None,
            ) is not None,
        )
        return True
    except Exception:
        log_exception("EA romantic awareness adapter install failed")
        return False

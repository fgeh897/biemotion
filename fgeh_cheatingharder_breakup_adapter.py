"""Capture directed breakup declarations before EA makes them bidirectional."""

import services

try:
    from interactions.context import InteractionSource
    from relationships.relationship_bit_change import (
        RelationshipBitChange,
        RelationshipBitOperationType,
    )
    from relationships.relationship_service import RelationshipService
except Exception:
    InteractionSource = None
    RelationshipBitChange = None
    RelationshipBitOperationType = None
    RelationshipService = None

try:
    from interactions.utils.loot import LootActions
except Exception:
    LootActions = None

try:
    from interactions.utils.loot_ops import DialogLootOp
except Exception:
    DialogLootOp = None

try:
    from interactions.utils.notification import NotificationElement
except Exception:
    NotificationElement = None

import fgeh_cheatingharder_injector as injector
import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_breakup_policy import (
    evaluate_external_breakup_request,
    is_breakup_bit_addition,
)
from fgeh_cheatingharder_breakup_authorization import (
    classify_breakup_request,
)
from fgeh_cheatingharder_domain import EventType
from fgeh_cheatingharder_ea_effect_gate import (
    EA_AUTO_BREAKUP_WARNING_RELATIONSHIP_BIT_IDS,
    EAEffectFamily,
    EAEffectGate,
    EAEffectKind,
    EA_RELATIONSHIP_EFFECTS,
    is_auto_breakup_transition_relationship_bit,
    is_auto_breakup_warning_relationship_bit,
)
from fgeh_cheatingharder_event_receipts import (
    BreakupExecutionRegistry,
    BreakupTransitionRegistry,
)
from fgeh_cheatingharder_relationship import get_sim_info, has_claim
from fgeh_cheatingharder_takeover import (
    RelationshipTakeoverRegistry,
    TakeoverFamily,
    TakeoverStatus,
)


_INSTALLED = False
_RESOLVER_CONTEXT_STACK = []
_LOOT_APPLY_RESOLVER_STACK = []
_AUTO_BREAKUP_WARNING_BIT_CACHE = {}
_TRANSITIONS = BreakupTransitionRegistry(
    settings.EA_BREAKUP_TRANSITION_CAPACITY
)
_EA_EFFECT_GATE = EAEffectGate(settings.EA_EFFECT_GATE_CAPACITY)
_TAKEOVERS = RelationshipTakeoverRegistry(
    settings.EA_RELATIONSHIP_TAKEOVER_CAPACITY
)
_FINAL_BREAKUP_AUTHORIZATIONS = {}
_MODEL_BREAKUP_EXECUTIONS = BreakupExecutionRegistry(
    settings.EA_BREAKUP_TRANSITION_CAPACITY
)


def _sim_now_ticks():
    try:
        now = services.time_service().sim_now
        absolute_ticks = getattr(now, "absolute_ticks", None)
        return int(absolute_ticks() if callable(absolute_ticks) else now)
    except Exception:
        return None


def _declaration_window_ticks():
    try:
        import date_and_time

        return int(date_and_time.create_time_span(
            minutes=settings.EA_BREAKUP_DECLARATION_WINDOW_SIM_MINUTES
        ).in_ticks())
    except Exception:
        return int(settings.EA_BREAKUP_DECLARATION_WINDOW_SIM_MINUTES)


def _policy_decision_window_ticks():
    try:
        import date_and_time

        return int(date_and_time.create_time_span(
            minutes=settings.EA_BREAKUP_POLICY_DECISION_MAX_AGE_SIM_MINUTES
        ).in_ticks())
    except Exception:
        return int(settings.EA_BREAKUP_POLICY_DECISION_MAX_AGE_SIM_MINUTES)


def _effect_gate_window_ticks():
    try:
        import date_and_time

        return int(date_and_time.create_time_span(
            minutes=settings.EA_EFFECT_GATE_WINDOW_SIM_MINUTES
        ).in_ticks())
    except Exception:
        return int(settings.EA_EFFECT_GATE_WINDOW_SIM_MINUTES)


def _takeover_window_ticks():
    try:
        import date_and_time

        return int(date_and_time.create_time_span(
            minutes=settings.EA_BREAKUP_TAKEOVER_COOLDOWN_SIM_MINUTES
        ).in_ticks())
    except Exception:
        return int(settings.EA_BREAKUP_TAKEOVER_COOLDOWN_SIM_MINUTES)


def _final_authorization_window_ticks():
    try:
        import date_and_time

        return int(date_and_time.create_time_span(
            minutes=settings.BREAKUP_FINAL_AUTHORIZATION_SIM_MINUTES
        ).in_ticks())
    except Exception:
        return int(settings.BREAKUP_FINAL_AUTHORIZATION_SIM_MINUTES)


def _pending_execution_window_ticks():
    try:
        import date_and_time

        return int(date_and_time.create_time_span(
            minutes=settings.BREAKUP_PENDING_EXECUTION_SIM_MINUTES
        ).in_ticks())
    except Exception:
        return int(settings.BREAKUP_PENDING_EXECUTION_SIM_MINUTES)


def _pair_key(first_sim_id, second_sim_id):
    return tuple(sorted((int(first_sim_id), int(second_sim_id))))


def _grant_final_breakup_authorization(
    initiator_id,
    recipient_id,
    transaction_id,
):
    now_ticks = _sim_now_ticks()
    expires_at = (
        None
        if now_ticks is None
        else int(now_ticks) + _final_authorization_window_ticks()
    )
    record = {
        "initiator_id": int(initiator_id),
        "recipient_id": int(recipient_id),
        "transaction_id": str(transaction_id),
        "expires_at": expires_at,
    }
    _FINAL_BREAKUP_AUTHORIZATIONS[
        _pair_key(initiator_id, recipient_id)
    ] = record
    log(
        "final breakup authorization granted transaction={} initiator={} recipient={} expires_at={}",
        transaction_id,
        initiator_id,
        recipient_id,
        expires_at,
    )
    return record


def _active_final_breakup_authorization(first_sim_id, second_sim_id):
    key = _pair_key(first_sim_id, second_sim_id)
    record = _FINAL_BREAKUP_AUTHORIZATIONS.get(key)
    if record is None:
        return None
    now_ticks = _sim_now_ticks()
    expires_at = record.get("expires_at")
    if (
        now_ticks is not None
        and expires_at is not None
        and int(now_ticks) >= int(expires_at)
    ):
        _FINAL_BREAKUP_AUTHORIZATIONS.pop(key, None)
        return None
    return record


def _clear_final_breakup_authorization(first_sim_id, second_sim_id):
    return _FINAL_BREAKUP_AUTHORIZATIONS.pop(
        _pair_key(first_sim_id, second_sim_id),
        None,
    )


def grant_model_breakup_authorization(
    initiator_id,
    recipient_id,
    transaction_id,
):
    """Authorize one exact model proposal, not any breakup on this pair."""
    authorization = _grant_final_breakup_authorization(
        initiator_id,
        recipient_id,
        transaction_id,
    )
    now_ticks = _sim_now_ticks()
    expires_at = (
        None
        if now_ticks is None
        else int(now_ticks) + _pending_execution_window_ticks()
    )
    _MODEL_BREAKUP_EXECUTIONS.authorize(
        initiator_id,
        recipient_id,
        transaction_id,
        expires_at=expires_at,
        expected_affordance_ids=(
            settings.EA_MANUAL_BREAKUP_AFFORDANCE_IDS
        ),
    )
    log(
        "model breakup execution authorized transaction={} initiator={} recipient={} expires_at={}",
        transaction_id,
        initiator_id,
        recipient_id,
        expires_at,
    )
    return authorization


def grant_direct_model_breakup_authorization(
    initiator_id,
    recipient_id,
    transaction_id,
):
    """Authorize resolved breakup loot without claiming an EA interaction."""
    _MODEL_BREAKUP_EXECUTIONS.clear_pair(initiator_id, recipient_id)
    released_takeovers, released_effect = _release_breakup_denials(
        initiator_id,
        recipient_id,
    )
    authorization = _grant_final_breakup_authorization(
        initiator_id,
        recipient_id,
        transaction_id,
    )
    log(
        "direct model breakup authorized transaction={} initiator={} "
        "recipient={} released_takeovers={} released_effect={}",
        transaction_id,
        initiator_id,
        recipient_id,
        len(released_takeovers),
        released_effect is not None,
    )
    return authorization


def bind_model_breakup_interaction(
    initiator_id,
    recipient_id,
    interaction_id,
):
    """Bind the transaction to the concrete EA interaction after queueing."""
    receipt = _MODEL_BREAKUP_EXECUTIONS.bind_interaction(
        initiator_id,
        recipient_id,
        interaction_id,
        occurred_ticks=_sim_now_ticks(),
    )
    if receipt is not None:
        log(
            "model breakup execution queued transaction={} initiator={} recipient={} interaction_id={}",
            receipt.transaction_id,
            initiator_id,
            recipient_id,
            interaction_id,
        )
    return receipt


def clear_model_breakup_authorization(initiator_id, recipient_id):
    """Remove a receipt when the authorized EA interaction cannot be queued."""
    authorization = _clear_final_breakup_authorization(
        initiator_id,
        recipient_id,
    )
    _MODEL_BREAKUP_EXECUTIONS.clear_pair(
        initiator_id,
        recipient_id,
    )
    return authorization


def _guid64(value):
    try:
        return int(getattr(value, "guid64", None))
    except (TypeError, ValueError):
        return None


def _operation_name(bit_operation):
    operation = getattr(bit_operation, "operation", None)
    if RelationshipBitOperationType is not None:
        try:
            if operation == RelationshipBitOperationType.ADD:
                return "add"
            if operation == RelationshipBitOperationType.REMOVE:
                return "remove"
        except Exception:
            pass
    try:
        numeric = int(operation)
    except (TypeError, ValueError):
        return str(operation or "").strip().lower()
    if numeric == 1:
        return "add"
    if numeric == 2:
        return "remove"
    return str(numeric)


def _is_breakup_addition(bit_operation):
    bit = getattr(bit_operation, "bit", None)
    bit_name = "{} {}".format(
        getattr(bit, "__name__", ""),
        getattr(bit, "name", ""),
    )
    return is_breakup_bit_addition(
        _operation_name(bit_operation),
        bit_id=_guid64(bit),
        bit_name=bit_name,
    )


def _is_primary_breakup_bit(bit):
    bit_name = "{} {}".format(
        getattr(bit, "__name__", ""),
        getattr(bit, "name", ""),
    )
    return is_breakup_bit_addition(
        "add",
        bit_id=_guid64(bit),
        bit_name=bit_name,
    )


def _bit_effect_family(bit):
    bit_name = "{} {}".format(
        getattr(bit, "__name__", ""),
        getattr(bit, "name", ""),
    )
    return EA_RELATIONSHIP_EFFECTS.family_for(
        EAEffectKind.RELATIONSHIP_BIT,
        resource_id=_guid64(bit),
        resource_name=bit_name,
    )


def _blocked_effect_receipt(first_sim_id, second_sim_id, bit):
    family = _bit_effect_family(bit)
    if family is None:
        return None, None
    receipt = _EA_EFFECT_GATE.blocked_receipt(
        family,
        first_sim_id,
        second_sim_id,
        occurred_ticks=_sim_now_ticks(),
        max_age_ticks=_effect_gate_window_ticks(),
    )
    return family, receipt


def _is_auto_breakup_warning_bit(bit):
    bit_name = "{} {}".format(
        getattr(bit, "__name__", ""),
        getattr(bit, "name", ""),
    )
    return is_auto_breakup_warning_relationship_bit(
        _guid64(bit),
        bit_name,
    )


def _is_auto_breakup_transition_bit(bit):
    bit_name = "{} {}".format(
        getattr(bit, "__name__", ""),
        getattr(bit, "name", ""),
    )
    return is_auto_breakup_transition_relationship_bit(
        _guid64(bit),
        bit_name,
    )


def _is_ea_jealousy_breakup_evidence(evidence):
    evidence = dict(evidence or {})
    if str(evidence.get("origin")) != "ea_scripted":
        return False
    affordance_name = str(
        evidence.get("affordance_name") or ""
    ).strip().lower()
    return (
        "reaction_jealousyloveinterest" in affordance_name
        or "reaction_jealousy_kiss_lovedone" in affordance_name
        or "reaction_mixer_jealousy_lovedone" in affordance_name
    )


def _is_ea_breakup_notification_context(evidence):
    """Classify only the confirmed EA jealousy breakup notification path."""
    evidence = dict(evidence or {})
    if str(evidence.get("origin")) != "ea_scripted":
        return False
    affordance_name = str(
        evidence.get("affordance_name") or ""
    ).strip().lower()
    return (
        affordance_name == "reaction_jealousyneutral"
        or _is_ea_jealousy_breakup_evidence(evidence)
    )


def _should_suppress_ea_breakup_notification(resolver):
    """Hide EA's breakup notice for every relationship managed by our model.

    EA can show this notification from an on-add loot before the breakup
    transition reaches our policy guard.  Requiring an already-created
    takeover receipt therefore races the presentation layer.  The context
    classifier above is intentionally narrow, and the project-edge check
    keeps unrelated EA relationships untouched; the model publishes the one
    authoritative result after its own transaction completes.
    """
    evidence = _resolver_evidence(resolver)
    if not _is_ea_breakup_notification_context(evidence):
        return False, evidence, None, None, None
    initiator_id = evidence.get("interaction_actor_id")
    recipient_id = evidence.get("interaction_target_id")
    if initiator_id is None or recipient_id is None:
        return False, evidence, None, None, None
    initiator = get_sim_info(initiator_id)
    recipient = get_sim_info(recipient_id)
    if (
        initiator is None
        or recipient is None
        or not _has_project_edge(initiator, recipient)
    ):
        return False, evidence, initiator_id, recipient_id, None
    now_ticks = _sim_now_ticks()
    takeover = _TAKEOVERS.active(
        TakeoverFamily.BREAKUP,
        initiator_id,
        recipient_id,
        occurred_ticks=now_ticks,
    )
    execution = _MODEL_BREAKUP_EXECUTIONS.active(
        initiator_id,
        recipient_id,
        occurred_ticks=now_ticks,
    )
    final_authorization = _active_final_breakup_authorization(
        initiator_id,
        recipient_id,
    )
    owner = (
        takeover
        if takeover is not None
        else execution
        if execution is not None
        else final_authorization
    )
    return True, evidence, initiator_id, recipient_id, owner


def _active_breakup_takeover_for_pair(first_sim_id, second_sim_id):
    now_ticks = _sim_now_ticks()
    for initiator_id, recipient_id in (
        (first_sim_id, second_sim_id),
        (second_sim_id, first_sim_id),
    ):
        receipt = _TAKEOVERS.active(
            TakeoverFamily.BREAKUP,
            initiator_id,
            recipient_id,
            occurred_ticks=now_ticks,
        )
        if receipt is not None:
            return receipt
    return None


def _auto_breakup_warning_bit_tuning(instance_id):
    instance_id = int(instance_id)
    if instance_id in _AUTO_BREAKUP_WARNING_BIT_CACHE:
        return _AUTO_BREAKUP_WARNING_BIT_CACHE[instance_id]
    bit = None
    try:
        import sims4.resources

        resource_type = sims4.resources.Types.RELATIONSHIP_BIT
        key = sims4.resources.get_resource_key(
            instance_id,
            resource_type,
        )
        manager = services.get_instance_manager(resource_type)
        bit = None if manager is None else manager.get(key)
    except Exception:
        log_exception(
            "EA auto-breakup warning tuning lookup failed bit_id={}".format(
                instance_id
            )
        )
    _AUTO_BREAKUP_WARNING_BIT_CACHE[instance_id] = bit
    return bit


def _clear_existing_auto_breakup_warnings(first, second):
    first_info = get_sim_info(first)
    second_info = get_sim_info(second)
    if first_info is None or second_info is None:
        return ()
    removed = []
    for owner, target in (
        (first_info, second_info),
        (second_info, first_info),
    ):
        tracker = getattr(owner, "relationship_tracker", None)
        if tracker is None:
            continue
        for bit_id in EA_AUTO_BREAKUP_WARNING_RELATIONSHIP_BIT_IDS:
            bit = _auto_breakup_warning_bit_tuning(bit_id)
            if bit is None:
                continue
            try:
                if not tracker.has_bit(target.sim_id, bit):
                    continue
                tracker.remove_relationship_bit(
                    target.sim_id,
                    bit,
                    send_rel_change_event=False,
                )
                removed.append((owner.sim_id, target.sim_id, bit_id))
            except Exception:
                log_exception(
                    "EA auto-breakup warning cleanup failed owner={} target={} bit_id={}".format(
                        owner.sim_id,
                        target.sim_id,
                        bit_id,
                    )
                )
    if removed:
        log(
            "EA auto-breakup warning state cleared pair={}:{} removed={}",
            first_info.sim_id,
            second_info.sim_id,
            tuple(removed),
        )
    return tuple(removed)


def _release_breakup_denials(first_sim_id, second_sim_id):
    released_takeovers = _TAKEOVERS.release_pair(
        TakeoverFamily.BREAKUP,
        first_sim_id,
        second_sim_id,
    )
    released_effect = _EA_EFFECT_GATE.release(
        EAEffectFamily.BREAKUP,
        first_sim_id,
        second_sim_id,
    )
    return released_takeovers, released_effect


def release_breakup_takeover_for_new_betrayal(
    observer_id,
    partner_id,
    episode_id=None,
):
    """Release the previous incident's decision for one distinct reoffense.

    This is deliberately narrower than resetting the breakup subsystem.  A
    new objective incident may be scored again, while duplicate callbacks for
    the old incident continue to reuse their existing takeover receipt.
    """
    released_takeovers, released_effect = _release_breakup_denials(
        observer_id,
        partner_id,
    )
    log(
        "breakup takeover released for betrayal reoffense episode={} "
        "observer={} partner={} takeovers={} effect_receipt={}",
        episode_id,
        observer_id,
        partner_id,
        len(released_takeovers),
        released_effect is not None,
    )
    return {
        "released_takeovers": len(released_takeovers),
        "released_effect_receipt": released_effect is not None,
    }


def _permanently_devoted_to(owner, beloved):
    owner_info = get_sim_info(owner)
    beloved_info = get_sim_info(beloved)
    if owner_info is None or beloved_info is None:
        return False
    try:
        from fgeh_cheatingharder_devotion_runtime import get_devotion_bond

        bond = get_devotion_bond(owner_info.sim_id)
        return (
            bond is not None
            and bond.beloved_id == beloved_info.sim_id
        )
    except Exception:
        log_exception(
            "EA effect gate devotion lookup failed owner={} beloved={}".format(
                getattr(owner_info, "sim_id", None),
                getattr(beloved_info, "sim_id", None),
            )
        )
        return False


def _guard_root_breakup_addition(actor_sim_id, target_sim_id, bit):
    """Require model authorization when EA bypasses resolver-owned loots."""
    actor = get_sim_info(actor_sim_id)
    target = get_sim_info(target_sim_id)
    if actor is None or target is None:
        return None
    now_ticks = _sim_now_ticks()
    authorized_declaration = _TRANSITIONS.declaration_for_pair(
        actor.sim_id,
        target.sim_id,
        occurred_ticks=now_ticks,
        max_age_ticks=_declaration_window_ticks(),
    )
    if authorized_declaration is not None:
        log(
            "EA root breakup effect allowed by recent directed declaration pair={}:{} initiator={} recipient={} event={}",
            actor.sim_id,
            target.sim_id,
            authorized_declaration.initiator_id,
            authorized_declaration.recipient_id,
            authorized_declaration.declaration_event_id,
        )
        return True
    evidence = (
        dict(_RESOLVER_CONTEXT_STACK[-1])
        if _RESOLVER_CONTEXT_STACK
        else {
            "origin": "ea_relationship_service",
            "intentional": None,
        }
    )
    evidence["guard_stage"] = "relationship_service_root"
    evidence["relationship_bit_id"] = _guid64(bit)
    evidence["relationship_bit_name"] = getattr(
        bit,
        "__name__",
        bit.__class__.__name__,
    )
    # A bidirectional bit may reach the service in either orientation.  Check
    # each actual permanent-devotion edge without pretending EA supplied an
    # initiator when this low-level path has already lost that direction.
    for initiator, recipient in ((actor, target), (target, actor)):
        if not _permanently_devoted_to(initiator, recipient):
            continue
        guard_result = _guard_breakup_request(
            initiator,
            recipient,
            bit,
            evidence,
        )
        if guard_result is False:
            log(
                "EA root breakup effect blocked before official relationship change owner={} beloved={} bit_id={} origin={}",
                initiator.sim_id,
                recipient.sim_id,
                _guid64(bit),
                evidence.get("origin"),
            )
            return False
        if guard_result is True:
            return True
    return None


def _has_project_edge(first, second):
    if first is None or second is None:
        return False
    if has_claim(first, second) or has_claim(second, first):
        return True
    try:
        from fgeh_cheatingharder_state import has_initialized_relationship_pair

        if has_initialized_relationship_pair(first, second):
            return True
    except Exception:
        log_exception(
            "breakup adapter directed state edge lookup failed pair={}:{}".format(
                getattr(first, "sim_id", None),
                getattr(second, "sim_id", None),
            )
        )
    try:
        from fgeh_cheatingharder_devotion_runtime import get_devotion_bond

        for owner, beloved in ((first, second), (second, first)):
            bond = get_devotion_bond(owner.sim_id)
            if bond is not None and bond.beloved_id == beloved.sim_id:
                return True
    except Exception:
        log_exception(
            "breakup adapter devotion edge lookup failed pair={}:{}".format(
                getattr(first, "sim_id", None),
                getattr(second, "sim_id", None),
            )
        )
    return False


def _resolver_evidence(resolver):
    interaction = getattr(resolver, "interaction", None)
    if interaction is None:
        interaction = getattr(resolver, "_interaction", None)
    if interaction is None:
        interaction = getattr(resolver, "super_interaction", None)
    context = getattr(resolver, "context", None)
    if context is None and interaction is not None:
        context = getattr(interaction, "context", None)
    source = getattr(context, "source", None)
    affordance = getattr(resolver, "affordance", None)
    if affordance is None and interaction is not None:
        affordance = getattr(interaction, "affordance", None)
    affordance_id = getattr(affordance, "guid64", None)
    classification = classify_breakup_request(
        source,
        affordance_id=affordance_id,
        pie_menu_source=(
            None
            if InteractionSource is None
            else InteractionSource.PIE_MENU
        ),
        autonomy_source=(
            None
            if InteractionSource is None
            else InteractionSource.AUTONOMY
        ),
        manual_breakup_affordance_ids=(
            settings.EA_MANUAL_BREAKUP_AFFORDANCE_IDS
        ),
    )
    interaction_actor = get_sim_info(
        getattr(interaction, "sim", None)
    )
    interaction_target = get_sim_info(
        getattr(interaction, "target", None)
    )
    return {
        "origin": classification.origin,
        "intentional": classification.intentional,
        "manual_breakup_authorized": (
            classification.manual_breakup_authorized
        ),
        "interaction_id": getattr(interaction, "id", None),
        "affordance_id": affordance_id,
        "affordance_name": getattr(affordance, "__name__", None),
        "interaction_source": (
            None if source is None else str(source)
        ),
        "interaction_actor_id": getattr(
            interaction_actor,
            "sim_id",
            None,
        ),
        "interaction_target_id": getattr(
            interaction_target,
            "sim_id",
            None,
        ),
    }


def _current_relationship_effect_evidence():
    if _RESOLVER_CONTEXT_STACK:
        return dict(_RESOLVER_CONTEXT_STACK[-1])
    if _LOOT_APPLY_RESOLVER_STACK:
        return _resolver_evidence(_LOOT_APPLY_RESOLVER_STACK[-1])
    return {
        "origin": "ea_relationship_service",
        "intentional": None,
    }


def _active_jealousy_reaction_evidence(first_sim_id, second_sim_id):
    """Recover reaction direction when EA writes a bit without a resolver."""
    pair_key = _pair_key(first_sim_id, second_sim_id)
    if pair_key is None:
        return None
    for possible_actor_id in pair_key:
        possible_actor = get_sim_info(possible_actor_id)
        actor_sim = (
            None
            if possible_actor is None
            else possible_actor.get_sim_instance()
        )
        if actor_sim is None:
            continue
        try:
            interactions = tuple(actor_sim.si_state.sis_actor_gen())
        except Exception:
            interactions = ()
        for interaction in interactions:
            affordance = getattr(interaction, "affordance", None)
            affordance_name = getattr(affordance, "__name__", None)
            evidence = {
                "origin": "ea_scripted",
                "intentional": None,
                "manual_breakup_authorized": False,
                "interaction_id": getattr(interaction, "id", None),
                "affordance_id": _guid64(affordance),
                "affordance_name": affordance_name,
                "interaction_source": str(
                    getattr(
                        getattr(interaction, "context", None),
                        "source",
                        "",
                    )
                ),
            }
            if not _is_ea_jealousy_breakup_evidence(evidence):
                continue
            interaction_actor = get_sim_info(
                getattr(interaction, "sim", None)
            )
            interaction_target = get_sim_info(
                getattr(interaction, "target", None)
            )
            actor_id = getattr(interaction_actor, "sim_id", None)
            target_id = getattr(interaction_target, "sim_id", None)
            if _pair_key(actor_id, target_id) != pair_key:
                continue
            evidence.update({
                "interaction_actor_id": actor_id,
                "interaction_target_id": target_id,
                "recovered_from_active_si_state": True,
            })
            return evidence
    return None


def _guard_direct_jealousy_transition(
    actor_sim_id,
    target_sim_id,
    bit_to_add,
):
    """Gate EA's pre-breakup relationship presentation before it is added."""
    evidence = _current_relationship_effect_evidence()
    if not _is_ea_jealousy_breakup_evidence(evidence):
        evidence = _active_jealousy_reaction_evidence(
            actor_sim_id,
            target_sim_id,
        )
        if evidence is None:
            log(
                "EA direct breakup transition had no jealousy context owner={} target={} bit_id={} bit_name={}",
                actor_sim_id,
                target_sim_id,
                _guid64(bit_to_add),
                getattr(
                    bit_to_add,
                    "__name__",
                    bit_to_add.__class__.__name__,
                ),
            )
            return None
    initiator_id = evidence.get("interaction_actor_id")
    recipient_id = evidence.get("interaction_target_id")
    if (
        initiator_id is None
        or recipient_id is None
        or _pair_key(initiator_id, recipient_id)
        != _pair_key(actor_sim_id, target_sim_id)
    ):
        log(
            "EA jealousy transition direction unavailable owner={} target={} interaction_actor={} interaction_target={} bit_id={}",
            actor_sim_id,
            target_sim_id,
            initiator_id,
            recipient_id,
            _guid64(bit_to_add),
        )
        return None
    initiator = get_sim_info(initiator_id)
    recipient = get_sim_info(recipient_id)
    evidence = dict(evidence)
    evidence["guard_stage"] = (
        "relationship_service_jealousy_transition"
    )
    return _guard_breakup_request(
        initiator,
        recipient,
        bit_to_add,
        evidence,
    )


def _resolver_participants(resolver, participant_type):
    if resolver is None or participant_type is None:
        return ()
    try:
        return tuple(resolver.get_participants(participant_type))
    except Exception:
        return ()


def _breakup_requests_from_bit_operations(bit_operations, resolver):
    requests = []
    for bit_operation in tuple(bit_operations or ()):
        if not _is_breakup_addition(bit_operation):
            continue
        recipients = _resolver_participants(
            resolver,
            getattr(bit_operation, "recipients", None),
        )
        targets = _resolver_participants(
            resolver,
            getattr(bit_operation, "targets", None),
        )
        bit = getattr(bit_operation, "bit", None)
        for recipient in recipients:
            for target in targets:
                if recipient is target:
                    continue
                requests.append((recipient, target, bit))
    return tuple(requests)


def _direct_breakup_requests(operation, resolver):
    """Return directed breakup additions owned by this exact EA loot package."""
    requests = []
    for action in tuple(getattr(operation, "loot_actions", ()) or ()):
        bit_operations = getattr(action, "_bit_operations", None)
        if not bit_operations:
            continue
        requests.extend(
            _breakup_requests_from_bit_operations(
                bit_operations,
                resolver,
            )
        )
    return tuple(requests)


def _relationship_change_breakup_requests(operation, resolver):
    return _breakup_requests_from_bit_operations(
        getattr(operation, "_bit_operations", ()),
        resolver,
    )


def _take_over_breakup_request(
    initiator,
    breakup_recipient,
    bit,
    evidence,
    policy_details,
    now_ticks,
):
    """Own one denied or deferred request and suppress EA retry spam."""
    _EA_EFFECT_GATE.deny(
        EAEffectFamily.BREAKUP,
        initiator.sim_id,
        breakup_recipient.sim_id,
        occurred_ticks=now_ticks,
        reason=policy_details.get(
            "reason",
            "relationship_policy_denied",
        ),
        evidence=evidence,
    )
    takeover, takeover_status = _TAKEOVERS.begin(
        TakeoverFamily.BREAKUP,
        initiator.sim_id,
        breakup_recipient.sim_id,
        occurred_ticks=now_ticks,
        duration_ticks=_takeover_window_ticks(),
        reason=policy_details.get(
            "reason",
            "relationship_policy_denied",
        ),
        selected_intent=policy_details.get("selected_intent"),
        decision_reference=policy_details.get("decision_reference"),
        context=policy_details.get("reaction_context"),
    )
    policy_details["takeover"] = (
        None if takeover is None else takeover.as_dict()
    )
    _clear_existing_auto_breakup_warnings(
        initiator,
        breakup_recipient,
    )
    if takeover_status == TakeoverStatus.STARTED:
        _publish_breakup_pressure(
            initiator,
            breakup_recipient,
            bit,
            evidence,
            policy_details,
        )
        try:
            if policy_details.get("suppress_takeover_expression", False):
                log(
                    "EA breakup takeover expression deferred initiator={} recipient={} reason={}",
                    initiator.sim_id,
                    breakup_recipient.sim_id,
                    policy_details.get("reason"),
                )
                return False
            from fgeh_cheatingharder_reaction_runtime import (
                apply_breakup_takeover_expression,
            )

            expression = apply_breakup_takeover_expression(
                initiator,
                breakup_recipient,
                policy_details,
            )
            log(
                "EA breakup request taken over initiator={} recipient={} selected={} expression={} cooldown_minutes={}",
                initiator.sim_id,
                breakup_recipient.sim_id,
                policy_details.get("selected_intent"),
                expression,
                settings.EA_BREAKUP_TAKEOVER_COOLDOWN_SIM_MINUTES,
            )
        except Exception:
            log_exception(
                "breakup takeover reaction failed initiator={} recipient={}".format(
                    initiator.sim_id,
                    breakup_recipient.sim_id,
                )
            )
    return False


def _guard_breakup_request(
    initiator,
    breakup_recipient,
    bit,
    evidence,
    resume_callback=None,
):
    if (
        initiator is None
        or breakup_recipient is None
        or not _has_project_edge(
            initiator,
            breakup_recipient,
        )
    ):
        return None
    now_ticks = _sim_now_ticks()
    player_proposal = (
        evidence.get("origin") == "player_interaction"
        and bool(evidence.get("manual_breakup_authorized", False))
    )
    pending_execution = _MODEL_BREAKUP_EXECUTIONS.active(
        initiator.sim_id,
        breakup_recipient.sim_id,
        occurred_ticks=now_ticks,
    )
    pending_request_matches = (
        pending_execution is not None
        and pending_execution.matches_request(
            initiator.sim_id,
            breakup_recipient.sim_id,
            affordance_id=evidence.get("affordance_id"),
            interaction_id=evidence.get("interaction_id"),
        )
    )
    if pending_execution is not None and player_proposal:
        # A deliberate new player request supersedes an older autonomous
        # queue receipt.  The old queued interaction will no longer inherit
        # broad pair authorization when it eventually reaches its loot.
        _MODEL_BREAKUP_EXECUTIONS.clear_pair(
            initiator.sim_id,
            breakup_recipient.sim_id,
        )
        _clear_final_breakup_authorization(
            initiator.sim_id,
            breakup_recipient.sim_id,
        )
        pending_execution = None
        pending_request_matches = False
        log(
            "pending model breakup superseded by player proposal initiator={} recipient={}",
            initiator.sim_id,
            breakup_recipient.sim_id,
        )
    elif pending_execution is not None and not pending_request_matches:
        _clear_existing_auto_breakup_warnings(
            initiator,
            breakup_recipient,
        )
        log(
            "parallel breakup request suppressed by pending model transaction={} status={} initiator={} recipient={} origin={} interaction_id={} affordance_id={}",
            pending_execution.transaction_id,
            pending_execution.status,
            initiator.sim_id,
            breakup_recipient.sim_id,
            evidence.get("origin"),
            evidence.get("interaction_id"),
            evidence.get("affordance_id"),
        )
        return False
    final_authorization = _active_final_breakup_authorization(
        initiator.sim_id,
        breakup_recipient.sim_id,
    )
    active_takeover = _TAKEOVERS.active(
        TakeoverFamily.BREAKUP,
        initiator.sim_id,
        breakup_recipient.sim_id,
        occurred_ticks=now_ticks,
    )
    explicit_authorization = (
        pending_request_matches
        or final_authorization is not None
        or bool(evidence.get("upper_layer_authorized", False))
    )
    if pending_request_matches:
        evidence = dict(evidence)
        evidence.update({
            "upper_layer_authorized": True,
            "negotiation_transaction_id": (
                pending_execution.transaction_id
            ),
            "model_execution_receipt": True,
        })
    elif final_authorization is not None:
        evidence = dict(evidence)
        evidence.update({
            "upper_layer_authorized": True,
            "negotiation_transaction_id": final_authorization.get(
                "transaction_id"
            ),
            "final_authorization_receipt": True,
        })
    if active_takeover is not None and (
        explicit_authorization or player_proposal
    ):
        released_takeovers, released_effect = _release_breakup_denials(
            initiator.sim_id,
            breakup_recipient.sim_id,
        )
        log(
            "EA breakup takeover released by explicit authorization initiator={} recipient={} origin={} takeovers={} effect_receipt={}",
            initiator.sim_id,
            breakup_recipient.sim_id,
            evidence.get("origin"),
            len(released_takeovers),
            released_effect is not None,
        )
        active_takeover = None
    if active_takeover is not None:
        active_takeover.note_suppressed_attempt(now_ticks)
        _clear_existing_auto_breakup_warnings(
            initiator,
            breakup_recipient,
        )
        _EA_EFFECT_GATE.deny(
            EAEffectFamily.BREAKUP,
            initiator.sim_id,
            breakup_recipient.sim_id,
            occurred_ticks=now_ticks,
            reason=active_takeover.reason,
            evidence=evidence,
        )
        attempts = active_takeover.suppressed_attempts
        if attempts in (1, 5, 10) or attempts % 25 == 0:
            log(
                "EA breakup retry short-circuited by active takeover initiator={} recipient={} selected={} suppressed_attempts={} expires_at={}",
                initiator.sim_id,
                breakup_recipient.sim_id,
                active_takeover.selected_intent,
                attempts,
                active_takeover.expires_at,
            )
        return False
    policy_decision, policy_details = _evaluate_breakup_request(
        initiator,
        breakup_recipient,
        evidence,
    )
    if not policy_decision.allowed:
        return _take_over_breakup_request(
            initiator,
            breakup_recipient,
            bit,
            evidence,
            policy_details,
            now_ticks,
        )
    if player_proposal and not explicit_authorization:
        if resume_callback is None:
            policy_details["reason"] = (
                "player_breakup_waiting_for_root_negotiation"
            )
            policy_details["selected_intent"] = "wait"
            policy_details["suppress_takeover_expression"] = True
            return _take_over_breakup_request(
                initiator,
                breakup_recipient,
                bit,
                evidence,
                policy_details,
                now_ticks,
            )
        try:
            from fgeh_cheatingharder_breakup_negotiation_runtime import (
                begin_player_breakup_negotiation,
            )

            negotiation, pending = begin_player_breakup_negotiation(
                initiator,
                breakup_recipient,
                evidence,
                policy_details,
                occurred_ticks=now_ticks,
                on_authorized=resume_callback,
            )
        except Exception:
            negotiation = None
            pending = False
            log_exception(
                "player breakup negotiation adapter failed initiator={} recipient={}".format(
                    initiator.sim_id,
                    breakup_recipient.sim_id,
                )
            )
        if pending:
            policy_details["reason"] = "player_breakup_negotiation_pending"
            policy_details["selected_intent"] = "await_player_decision"
            policy_details["suppress_takeover_expression"] = True
            return _take_over_breakup_request(
                initiator,
                breakup_recipient,
                bit,
                evidence,
                policy_details,
                now_ticks,
            )
        if negotiation is None:
            policy_details["reason"] = (
                "player_breakup_negotiation_unavailable"
            )
            policy_details["selected_intent"] = "wait"
            policy_details["suppress_takeover_expression"] = True
            return _take_over_breakup_request(
                initiator,
                breakup_recipient,
                bit,
                evidence,
                policy_details,
                now_ticks,
            )
        policy_details["negotiation"] = negotiation.as_dict()
        if not negotiation.official_breakup_authorized:
            policy_details["reason"] = "negotiation_{}".format(
                negotiation.proposer_decision
            )
            policy_details["selected_intent"] = (
                negotiation.proposer_decision
            )
            return _take_over_breakup_request(
                initiator,
                breakup_recipient,
                bit,
                evidence,
                policy_details,
                now_ticks,
            )
        final_authorization = _grant_final_breakup_authorization(
            initiator.sim_id,
            breakup_recipient.sim_id,
            negotiation.transaction_id,
        )
        evidence = dict(evidence)
        evidence.update({
            "upper_layer_authorized": True,
            "negotiation_transaction_id": negotiation.transaction_id,
            "negotiation_response": negotiation.response,
            "negotiation_final_decision": (
                negotiation.proposer_decision
            ),
        })
        explicit_authorization = True
    elif not explicit_authorization:
        try:
            from fgeh_cheatingharder_breakup_negotiation_runtime import (
                evaluate_ea_breakup_negotiation,
            )

            negotiation = evaluate_ea_breakup_negotiation(
                initiator,
                breakup_recipient,
                evidence,
                policy_details,
                occurred_ticks=now_ticks,
            )
        except Exception:
            negotiation = None
            log_exception(
                "breakup negotiation adapter failed initiator={} recipient={}".format(
                    initiator.sim_id,
                    breakup_recipient.sim_id,
                )
            )
        if negotiation is None:
            policy_details["reason"] = "breakup_negotiation_unavailable"
            policy_details["selected_intent"] = "wait"
            return _take_over_breakup_request(
                initiator,
                breakup_recipient,
                bit,
                evidence,
                policy_details,
                now_ticks,
            )
        policy_details["negotiation"] = negotiation.as_dict()
        if not negotiation.official_breakup_authorized:
            policy_details["reason"] = "negotiation_{}".format(
                negotiation.proposer_decision
            )
            policy_details["selected_intent"] = (
                negotiation.proposer_decision
            )
            return _take_over_breakup_request(
                initiator,
                breakup_recipient,
                bit,
                evidence,
                policy_details,
                now_ticks,
            )
        evidence = dict(evidence)
        evidence.update({
            "upper_layer_authorized": True,
            "negotiation_transaction_id": negotiation.transaction_id,
            "negotiation_response": negotiation.response,
            "negotiation_final_decision": (
                negotiation.proposer_decision
            ),
        })
        log(
            "EA breakup authorized after negotiation transaction={} initiator={} recipient={} response={} final={} outcome={}",
            negotiation.transaction_id,
            initiator.sim_id,
            breakup_recipient.sim_id,
            negotiation.response,
            negotiation.proposer_decision,
            negotiation.outcome,
        )
    _release_breakup_denials(
        initiator.sim_id,
        breakup_recipient.sim_id,
    )
    record_ea_breakup_declaration(
        initiator,
        breakup_recipient,
        bit=bit,
        evidence=evidence,
    )
    return True


def reset_breakup_adapter_runtime():
    _TRANSITIONS.clear()
    _EA_EFFECT_GATE.clear()
    _TAKEOVERS.clear()
    _AUTO_BREAKUP_WARNING_BIT_CACHE.clear()
    _FINAL_BREAKUP_AUTHORIZATIONS.clear()
    _MODEL_BREAKUP_EXECUTIONS.clear()
    _RESOLVER_CONTEXT_STACK.clear()
    _LOOT_APPLY_RESOLVER_STACK.clear()
    try:
        from fgeh_cheatingharder_breakup_negotiation_runtime import (
            reset_breakup_negotiation_runtime,
        )

        reset_breakup_negotiation_runtime()
    except Exception:
        log_exception("breakup negotiation runtime reset failed")
    try:
        from fgeh_cheatingharder_reaction_runtime import (
            reset_relationship_reaction_runtime,
        )

        reset_relationship_reaction_runtime()
    except Exception:
        log_exception("relationship reaction runtime reset failed")
    log("EA breakup transition runtime reset")


def get_breakup_takeover_status(initiator_id, recipient_id):
    receipt = _TAKEOVERS.active(
        TakeoverFamily.BREAKUP,
        initiator_id,
        recipient_id,
        occurred_ticks=_sim_now_ticks(),
    )
    return None if receipt is None else receipt.as_dict()


def _latest_breakup_behavior_decision(initiator_id, recipient_id, now_ticks):
    try:
        from fgeh_cheatingharder_betrayal_memory_rules import (
            INTERPRETATION_BETRAYAL_ATTRIBUTION,
        )
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        store = get_memory_service().store
        bond = store.get_devotion_bond(initiator_id)
        permanently_devoted = (
            bond is not None and bond.beloved_id == recipient_id
        )
        for interpretation in reversed(
            store.interpretations_for_knower(initiator_id)
        ):
            if (
                not interpretation.active
                or interpretation.interpretation_type
                != INTERPRETATION_BETRAYAL_ATTRIBUTION
            ):
                continue
            details = dict(interpretation.details or {})
            try:
                partner_id = int(details.get("partner_id"))
            except (TypeError, ValueError):
                continue
            if partner_id != int(recipient_id):
                continue
            occurred_ticks = interpretation.created_at
            age_ticks = None
            try:
                if now_ticks is not None and occurred_ticks is not None:
                    age_ticks = int(now_ticks) - int(occurred_ticks)
            except (TypeError, ValueError):
                age_ticks = None
            if (
                age_ticks is None
                or age_ticks < 0
                or age_ticks > _policy_decision_window_ticks()
            ):
                return (
                    permanently_devoted,
                    None,
                    None,
                    interpretation.interpretation_id,
                    age_ticks,
                    None,
                )
            breakup_candidate = None
            for candidate in details.get("candidates", ()):
                candidate = dict(candidate or {})
                if candidate.get("intent") == "break_up":
                    breakup_candidate = candidate
                    break
            return (
                permanently_devoted,
                details.get("selected_intent"),
                breakup_candidate,
                interpretation.interpretation_id,
                age_ticks,
                {
                    "attribution": dict(
                        details.get("attribution", {}) or {}
                    ),
                    "rival_id": details.get("rival_id"),
                    "profile_key": details.get("profile_key"),
                    "event_tags": tuple(
                        details.get("event_tags", ()) or ()
                    ),
                    "severity": details.get("severity", 100.0),
                    "selected_intent": details.get(
                        "selected_intent"
                    ),
                },
            )
        return permanently_devoted, None, None, None, None, None
    except Exception:
        log_exception(
            "breakup upper-layer decision lookup failed initiator={} recipient={}".format(
                initiator_id,
                recipient_id,
            )
        )
        return False, None, None, None, None, None


def _evaluate_breakup_request(initiator, recipient, evidence):
    evidence = dict(evidence or {})
    origin = evidence.get("origin", "ea_relationship_loot")
    now_ticks = _sim_now_ticks()
    (
        permanently_devoted,
        selected_intent,
        breakup_candidate,
        decision_reference,
        decision_age_ticks,
        reaction_context,
    ) = _latest_breakup_behavior_decision(
        initiator.sim_id,
        recipient.sim_id,
        now_ticks,
    )
    decision = evaluate_external_breakup_request(
        origin,
        managed_by_project=True,
        permanently_devoted=permanently_devoted,
        selected_intent=selected_intent,
        breakup_candidate=breakup_candidate,
        decision_reference=decision_reference,
        upper_layer_authorized=bool(
            evidence.get("upper_layer_authorized", False)
        ),
    )
    details = decision.as_dict()
    details["decision_age_ticks"] = decision_age_ticks
    details["occurred_at"] = now_ticks
    details["reaction_context"] = dict(reaction_context or {})
    log(
        "breakup policy decision initiator={} recipient={} origin={} source={} affordance_id={} affordance_name={} manual_authorized={} allowed={} reason={} selected={} candidate={} reference={} age_ticks={}",
        initiator.sim_id,
        recipient.sim_id,
        origin,
        evidence.get("interaction_source"),
        evidence.get("affordance_id"),
        evidence.get("affordance_name"),
        evidence.get("manual_breakup_authorized", False),
        decision.allowed,
        decision.reason,
        decision.selected_intent,
        decision.breakup_candidate,
        decision.decision_reference,
        decision_age_ticks,
    )
    return decision, details


def _publish_breakup_pressure(
    initiator,
    recipient,
    bit,
    evidence,
    policy_details,
):
    now_ticks = _sim_now_ticks()
    try:
        from fgeh_cheatingharder_event_center import publish

        payload = dict(evidence or {})
        payload.update({
            "initiator_id": initiator.sim_id,
            "recipient_id": recipient.sim_id,
            "relationship_member_ids": tuple(sorted((
                initiator.sim_id,
                recipient.sim_id,
            ))),
            "relationship_bit_id": _guid64(bit),
            "official_relationship_ended": False,
            "policy": dict(policy_details or {}),
        })
        publish(
            EventType.BREAKUP_PRESSURE,
            source="external_breakup_policy",
            event_id="ea-breakup-pressure:{}:{}:{}".format(
                initiator.sim_id,
                recipient.sim_id,
                "unknown" if now_ticks is None else now_ticks,
            ),
            actor_id=initiator.sim_id,
            target_id=recipient.sim_id,
            observer_id=initiator.sim_id,
            partner_id=recipient.sim_id,
            payload=payload,
        )
        log(
            "EA breakup request blocked initiator={} recipient={} origin={} reason={} official_relationship_ended=False",
            initiator.sim_id,
            recipient.sim_id,
            evidence.get("origin", "unknown"),
            policy_details.get("reason", "unknown"),
        )
        return True
    except Exception:
        log_exception(
            "EA breakup pressure publish failed initiator={} recipient={}".format(
                initiator.sim_id,
                recipient.sim_id,
            )
        )
        return False


def record_ea_breakup_declaration(
    initiator_sim_or_info,
    recipient_sim_or_info,
    bit=None,
    evidence=None,
):
    """Record Actor -> Target before EA adds its bidirectional breakup bit."""
    initiator = get_sim_info(initiator_sim_or_info)
    recipient = get_sim_info(recipient_sim_or_info)
    if (
        initiator is None
        or recipient is None
        or not _has_project_edge(initiator, recipient)
    ):
        return False
    now_ticks = _sim_now_ticks()
    evidence = dict(evidence or {})
    origin = evidence.pop("origin", "ea_relationship_loot")
    intentional = evidence.pop("intentional", None)
    declaration_event_id = "ea-breakup-declared:{}:{}:{}".format(
        initiator.sim_id,
        recipient.sim_id,
        "unknown" if now_ticks is None else now_ticks,
    )
    receipt, created = _TRANSITIONS.declare(
        initiator.sim_id,
        recipient.sim_id,
        declaration_event_id,
        occurred_ticks=now_ticks,
        origin=origin,
        intentional=intentional,
        evidence=evidence,
    )
    if receipt is None or not created:
        return False
    try:
        from fgeh_cheatingharder_event_center import publish

        payload = dict(receipt.evidence)
        payload.update({
            "initiator_id": receipt.initiator_id,
            "recipient_id": receipt.recipient_id,
            "initiator_known": True,
            "origin": receipt.origin,
            "intentional": receipt.intentional,
            "relationship_bit_id": _guid64(bit),
        })
        publish(
            EventType.BREAKUP_DECLARED,
            source="ea_relationship_bit_change",
            event_id=receipt.declaration_event_id,
            actor_id=receipt.initiator_id,
            target_id=receipt.recipient_id,
            payload=payload,
        )
        log(
            "EA breakup declared initiator={} recipient={} origin={} intentional={} event={}",
            receipt.initiator_id,
            receipt.recipient_id,
            receipt.origin,
            receipt.intentional,
            receipt.declaration_event_id,
        )
        return True
    except Exception:
        log_exception(
            "EA breakup declaration publish failed initiator={} recipient={}".format(
                initiator.sim_id,
                recipient.sim_id,
            )
        )
        return False


def complete_ea_breakup(
    first_sim_or_info,
    second_sim_or_info,
    bit=None,
    breakup_cause="unknown_ea_breakup",
    boundary_warning_name=None,
):
    """Publish one completion after EA confirms the official relationship ended."""
    first = get_sim_info(first_sim_or_info)
    second = get_sim_info(second_sim_or_info)
    if (
        first is None
        or second is None
        or not _has_project_edge(first, second)
    ):
        return False
    now_ticks = _sim_now_ticks()
    model_execution = _MODEL_BREAKUP_EXECUTIONS.active(
        first.sim_id,
        second.sim_id,
        occurred_ticks=now_ticks,
    )
    completion, created = _TRANSITIONS.complete(
        first.sim_id,
        second.sim_id,
        occurred_ticks=now_ticks,
        max_declaration_age_ticks=_declaration_window_ticks(),
    )
    if completion is None or not created:
        return False
    declaration = completion.declaration
    initiator_id = completion.initiator_id
    recipient_id = completion.recipient_id
    bit_name = "{} {}".format(
        getattr(bit, "__name__", ""),
        getattr(bit, "name", ""),
    ).lower()
    payload = {
        "breakup_cause": str(breakup_cause),
        "relationship_member_ids": tuple(completion.pair_key),
        "initiator_id": initiator_id,
        "recipient_id": recipient_id,
        "initiator_known": declaration is not None,
        "origin": (
            "unknown" if declaration is None else declaration.origin
        ),
        "intentional": (
            None if declaration is None else declaration.intentional
        ),
        "declaration_event_id": (
            None
            if declaration is None
            else declaration.declaration_event_id
        ),
        "relationship_bit_id": _guid64(bit),
        "relationship_bit_name": bit_name,
        "boundary_warning_name": boundary_warning_name,
        "model_execution_transaction_id": (
            None
            if model_execution is None
            else model_execution.transaction_id
        ),
        "proposal_execution_status": "completed",
    }
    if declaration is not None:
        payload["declaration_evidence"] = dict(declaration.evidence)
    try:
        from fgeh_cheatingharder_event_center import publish
        from fgeh_cheatingharder_memory_models import DevotionBondStatus
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        publish(
            EventType.BREAKUP_COMPLETED,
            source="ea_relationship_bit",
            event_id=completion.completion_event_id,
            actor_id=initiator_id,
            target_id=recipient_id,
            payload=payload,
        )
        initiator_info = (
            first if first.sim_id == initiator_id else second
        )
        recipient_info = (
            second if initiator_info is first else first
        )
        try:
            from fgeh_cheatingharder_notification import (
                show_breakup_completed_notification,
            )

            show_breakup_completed_notification(
                initiator_info,
                recipient_info,
            )
        except Exception:
            log_exception(
                "breakup completed notification dispatch failed pair={}:{}".format(
                    first.sim_id,
                    second.sim_id,
                )
            )
        store = get_memory_service().store
        preserved_owners = []
        for owner, beloved in ((first, second), (second, first)):
            bond = store.get_devotion_bond(owner.sim_id)
            if bond is None or bond.beloved_id != beloved.sim_id:
                continue
            store.set_devotion_status(
                owner.sim_id,
                DevotionBondStatus.SEPARATED,
            )
            preserved_owners.append(owner.sim_id)
        _TAKEOVERS.release_pair(
            TakeoverFamily.BREAKUP,
            first.sim_id,
            second.sim_id,
        )
        _clear_final_breakup_authorization(
            first.sim_id,
            second.sim_id,
        )
        completed_execution = _MODEL_BREAKUP_EXECUTIONS.complete(
            first.sim_id,
            second.sim_id,
            occurred_ticks=now_ticks,
        )
        log(
            "EA breakup completed pair={}:{} initiator={} recipient={} origin={} cause={} model_transaction={} model_status={} devotion_preserved_owners={}",
            first.sim_id,
            second.sim_id,
            initiator_id,
            recipient_id,
            payload["origin"],
            breakup_cause,
            (
                None
                if completed_execution is None
                else completed_execution.transaction_id
            ),
            (
                None
                if completed_execution is None
                else completed_execution.status
            ),
            tuple(preserved_owners),
        )
        return True
    except Exception:
        log_exception(
            "EA breakup completion publish failed pair={}:{}".format(
                first.sim_id,
                second.sim_id,
            )
        )
        return False


def install_breakup_adapter():
    global _INSTALLED
    if _INSTALLED:
        return True
    if RelationshipBitChange is None:
        log("EA breakup direction adapter unavailable")
        return False
    try:
        if DialogLootOp is not None:
            @injector.inject(
                DialogLootOp,
                "_apply_to_subject_and_target",
                safe=True,
            )
            def _suppress_managed_breakup_dialog_loot(
                original,
                operation,
                subject,
                target,
                resolver,
                *args,
                **kwargs
            ):
                try:
                    suppress, evidence, initiator_id, recipient_id, owner = (
                        _should_suppress_ea_breakup_notification(resolver)
                    )
                    if suppress:
                        log(
                            "EA breakup dialog loot notification suppressed initiator={} recipient={} affordance_id={} interaction_id={} owner_type={}",
                            initiator_id,
                            recipient_id,
                            evidence.get("affordance_id"),
                            evidence.get("interaction_id"),
                            owner.__class__.__name__,
                        )
                        return None
                except Exception:
                    log_exception(
                        "EA breakup dialog loot notification guard failed"
                    )
                return original(
                    operation,
                    subject,
                    target,
                    resolver,
                    *args,
                    **kwargs
                )

            log("EA managed-breakup dialog loot notification guard installed")

        if NotificationElement is not None:
            @injector.inject(
                NotificationElement,
                "show_notification",
                safe=True,
            )
            def _suppress_managed_breakup_notification_element(
                original,
                element,
                *args,
                **kwargs
            ):
                try:
                    interaction = getattr(element, "interaction", None)
                    resolver = (
                        None
                        if interaction is None
                        else interaction.get_resolver()
                    )
                    suppress, evidence, initiator_id, recipient_id, owner = (
                        _should_suppress_ea_breakup_notification(resolver)
                    )
                    if suppress:
                        log(
                            "EA breakup notification element suppressed initiator={} recipient={} affordance_id={} interaction_id={} owner_type={}",
                            initiator_id,
                            recipient_id,
                            evidence.get("affordance_id"),
                            evidence.get("interaction_id"),
                            owner.__class__.__name__,
                        )
                        return None
                except Exception:
                    log_exception(
                        "EA breakup notification element guard failed"
                    )
                return original(element, *args, **kwargs)

            log("EA managed-breakup notification element guard installed")

        if RelationshipService is not None:
            @injector.inject(
                RelationshipService,
                "add_relationship_bit",
                safe=True,
            )
            def _gate_ea_relationship_bit_effect(
                original,
                relationship_service,
                actor_sim_id,
                target_sim_id,
                bit_to_add,
                *args,
                **kwargs
            ):
                if _is_auto_breakup_transition_bit(bit_to_add):
                    takeover = _active_breakup_takeover_for_pair(
                        actor_sim_id,
                        target_sim_id,
                    )
                    if takeover is not None:
                        takeover.note_suppressed_attempt(_sim_now_ticks())
                        log(
                            "EA auto-breakup relationship transition blocked "
                            "by active takeover owner={} target={} bit_id={} "
                            "bit_name={} selected={} reason={}",
                            actor_sim_id,
                            target_sim_id,
                            _guid64(bit_to_add),
                            getattr(
                                bit_to_add,
                                "__name__",
                                bit_to_add.__class__.__name__,
                            ),
                            takeover.selected_intent,
                            takeover.reason,
                        )
                        return None
                    transition_guard = _guard_direct_jealousy_transition(
                        actor_sim_id,
                        target_sim_id,
                        bit_to_add,
                    )
                    if transition_guard is False:
                        log(
                            "EA direct jealousy relationship transition "
                            "blocked before presentation change owner={} "
                            "target={} bit_id={} bit_name={}",
                            actor_sim_id,
                            target_sim_id,
                            _guid64(bit_to_add),
                            getattr(
                                bit_to_add,
                                "__name__",
                                bit_to_add.__class__.__name__,
                            ),
                        )
                        return None
                if _is_auto_breakup_warning_bit(bit_to_add):
                    takeover = _active_breakup_takeover_for_pair(
                        actor_sim_id,
                        target_sim_id,
                    )
                    if takeover is not None:
                        takeover.note_suppressed_attempt(
                            _sim_now_ticks()
                        )
                        log(
                            "EA auto-breakup warning blocked by active takeover owner={} target={} bit_id={} bit_name={} selected={} reason={} suppressed_attempts={}",
                            actor_sim_id,
                            target_sim_id,
                            _guid64(bit_to_add),
                            getattr(
                                bit_to_add,
                                "__name__",
                                bit_to_add.__class__.__name__,
                            ),
                            takeover.selected_intent,
                            takeover.reason,
                            takeover.suppressed_attempts,
                        )
                        return None
                family, receipt = _blocked_effect_receipt(
                    actor_sim_id,
                    target_sim_id,
                    bit_to_add,
                )
                if receipt is not None:
                    log(
                        "EA relationship effect blocked family={} kind={} owner={} target={} bit_id={} bit_name={} reason={}",
                        family,
                        EAEffectKind.RELATIONSHIP_BIT,
                        actor_sim_id,
                        target_sim_id,
                        _guid64(bit_to_add),
                        getattr(
                            bit_to_add,
                            "__name__",
                            bit_to_add.__class__.__name__,
                        ),
                        receipt.reason,
                    )
                    return None
                if (
                    family == EAEffectFamily.BREAKUP
                    and _is_primary_breakup_bit(bit_to_add)
                ):
                    root_guard_result = _guard_root_breakup_addition(
                        actor_sim_id,
                        target_sim_id,
                        bit_to_add,
                    )
                    if root_guard_result is False:
                        return None
                return original(
                    relationship_service,
                    actor_sim_id,
                    target_sim_id,
                    bit_to_add,
                    *args,
                    **kwargs
                )

            log("EA relationship effect gate installed")
        else:
            log("EA relationship effect gate unavailable")

        if LootActions is not None:
            @injector.inject(
                LootActions,
                "apply_to_resolver",
                safe=True,
            )
            def _capture_breakup_loot_apply_context(
                original,
                operation,
                resolver,
                *args,
                **kwargs
            ):
                _LOOT_APPLY_RESOLVER_STACK.append(resolver)
                try:
                    return original(
                        operation,
                        resolver,
                        *args,
                        **kwargs
                    )
                finally:
                    _LOOT_APPLY_RESOLVER_STACK.pop()

            @injector.inject(
                LootActions,
                "apply_to_resolver_and_get_display_texts",
                safe=True,
            )
            def _capture_breakup_loot_display_apply_context(
                original,
                operation,
                resolver,
                *args,
                **kwargs
            ):
                _LOOT_APPLY_RESOLVER_STACK.append(resolver)
                try:
                    return original(
                        operation,
                        resolver,
                        *args,
                        **kwargs
                    )
                finally:
                    _LOOT_APPLY_RESOLVER_STACK.pop()

            @injector.inject(
                LootActions,
                "get_loot_ops_gen",
                safe=True,
            )
            def _filter_complete_breakup_loot(
                original,
                operation,
                resolver=None,
                *args,
                **kwargs
            ):
                generated = original(
                    operation,
                    resolver=resolver,
                    *args,
                    **kwargs
                )
                if (
                    resolver is None
                    or not _LOOT_APPLY_RESOLVER_STACK
                    or not any(
                        active_resolver is resolver
                        for active_resolver
                        in _LOOT_APPLY_RESOLVER_STACK
                    )
                ):
                    return generated
                generated_actions = None
                try:
                    requests = _direct_breakup_requests(
                        operation,
                        resolver,
                    )
                    if not requests:
                        return generated
                    generated_actions = tuple(generated)
                    if not generated_actions:
                        return iter(())
                    for recipient, target, bit in requests:
                        initiator = get_sim_info(recipient)
                        breakup_recipient = get_sim_info(target)
                        if (
                            initiator is None
                            or breakup_recipient is None
                            or not _has_project_edge(
                                initiator,
                                breakup_recipient,
                            )
                        ):
                            continue
                        evidence = _resolver_evidence(resolver)
                        evidence.update({
                            "guard_stage": (
                                "whole_breakup_loot_generator"
                            ),
                            "breakup_loot_id": _guid64(operation),
                            "breakup_loot_name": getattr(
                                operation,
                                "__name__",
                                operation.__class__.__name__,
                            ),
                        })

                        def _resume_authorized_breakup(
                            negotiation,
                            _operation=operation,
                            _resolver=resolver,
                            _initiator=initiator,
                            _recipient=breakup_recipient,
                        ):
                            _grant_final_breakup_authorization(
                                _initiator.sim_id,
                                _recipient.sim_id,
                                negotiation.transaction_id,
                            )
                            log(
                                "resuming player-authorized EA breakup transaction={} initiator={} recipient={}",
                                negotiation.transaction_id,
                                _initiator.sim_id,
                                _recipient.sim_id,
                            )
                            _operation.apply_to_resolver(_resolver)

                        guard_result = _guard_breakup_request(
                            initiator,
                            breakup_recipient,
                            bit,
                            evidence,
                            resume_callback=_resume_authorized_breakup,
                        )
                        if guard_result is False:
                            log(
                                "EA breakup loot generator blocked before all side effects loot_id={} loot_name={} initiator={} recipient={} generated_actions={}",
                                evidence.get("breakup_loot_id"),
                                evidence.get("breakup_loot_name"),
                                initiator.sim_id,
                                breakup_recipient.sim_id,
                                len(generated_actions),
                            )
                            return iter(())
                        if guard_result is True:
                            break
                    return iter(generated_actions)
                except Exception:
                    log_exception(
                        "EA complete breakup loot generator guard failed"
                    )
                    if generated_actions is None:
                        return generated
                    return iter(generated_actions)

            log("EA breakup whole-loot generator guard installed")
        else:
            log("EA complete breakup loot guard unavailable")

        @injector.inject(
            RelationshipBitChange,
            "apply_to_resolver",
            safe=True,
        )
        def _capture_breakup_resolver_context(
            original,
            operation,
            resolver,
            *args,
            **kwargs
        ):
            evidence = _resolver_evidence(resolver)
            try:
                requests = _relationship_change_breakup_requests(
                    operation,
                    resolver,
                )
                for recipient, target, bit in requests:
                    initiator = get_sim_info(recipient)
                    breakup_recipient = get_sim_info(target)
                    group_evidence = dict(evidence)
                    group_evidence["guard_stage"] = (
                        "relationship_bit_change_group"
                    )
                    guard_result = _guard_breakup_request(
                        initiator,
                        breakup_recipient,
                        bit,
                        group_evidence,
                    )
                    if guard_result is False:
                        log(
                            "EA breakup relationship-bit group blocked before partner removal initiator={} recipient={} operations={}",
                            getattr(initiator, "sim_id", None),
                            getattr(
                                breakup_recipient,
                                "sim_id",
                                None,
                            ),
                            len(tuple(
                                getattr(
                                    operation,
                                    "_bit_operations",
                                    (),
                                )
                            )),
                        )
                        return (False, None)
                    if guard_result is True:
                        break
            except Exception:
                log_exception(
                    "EA breakup relationship-bit group guard failed"
                )
            _RESOLVER_CONTEXT_STACK.append(evidence)
            try:
                return original(operation, resolver, *args, **kwargs)
            finally:
                _RESOLVER_CONTEXT_STACK.pop()

        @injector.inject(
            RelationshipBitChange,
            "_perform_bit_operation",
            safe=True,
        )
        def _capture_breakup_direction(
            original,
            operation,
            recipient,
            target,
            bit_operation,
            *args,
            **kwargs
        ):
            try:
                bit = getattr(bit_operation, "bit", None)
                evidence = (
                    dict(_RESOLVER_CONTEXT_STACK[-1])
                    if _RESOLVER_CONTEXT_STACK
                    else {
                        "origin": "ea_relationship_loot",
                        "intentional": None,
                    }
                )
                if (
                    _is_auto_breakup_transition_bit(bit)
                    and _is_ea_jealousy_breakup_evidence(evidence)
                ):
                    initiator = get_sim_info(recipient)
                    breakup_recipient = get_sim_info(target)
                    evidence["guard_stage"] = (
                        "ea_jealousy_relationship_transition"
                    )
                    guard_result = _guard_breakup_request(
                        initiator,
                        breakup_recipient,
                        bit,
                        evidence,
                    )
                    if guard_result is False:
                        log(
                            "EA jealousy pre-breakup relationship transition "
                            "blocked initiator={} recipient={} bit_id={} "
                            "bit_name={}",
                            getattr(initiator, "sim_id", None),
                            getattr(breakup_recipient, "sim_id", None),
                            _guid64(bit),
                            getattr(
                                bit,
                                "__name__",
                                bit.__class__.__name__,
                            ),
                        )
                        return None
                if _is_breakup_addition(bit_operation):
                    initiator = get_sim_info(recipient)
                    breakup_recipient = get_sim_info(target)
                    guard_result = _guard_breakup_request(
                        initiator,
                        breakup_recipient,
                        bit,
                        evidence,
                    )
                    if guard_result is False:
                        return None
                    if guard_result is None:
                        record_ea_breakup_declaration(
                            recipient,
                            target,
                            bit=bit,
                            evidence=evidence,
                        )
            except Exception:
                log_exception("EA breakup direction capture failed")
            return original(
                operation,
                recipient,
                target,
                bit_operation,
                *args,
                **kwargs
            )

        _INSTALLED = True
        log("EA breakup direction adapter installed")
        return True
    except Exception:
        log_exception("EA breakup direction adapter install failed")
        return False

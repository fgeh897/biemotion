"""Thin adapters from reliable EA events into the relationship event center."""

import services

try:
    try:
        from tag import GameTag
    except ImportError:
        from tag import Tag as GameTag
except Exception:
    GameTag = None

try:
    from event_testing.test_events import TestEvent
    from interactions.base.interaction import Interaction
    from interactions.utils.outcome_enums import OutcomeResult
    import fgeh_cheatingharder_injector as injector
except Exception:
    TestEvent = None
    Interaction = None
    OutcomeResult = None
    injector = None

import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_domain import EventType
from fgeh_cheatingharder_interaction_semantics import (
    is_ea_jealousy_awareness_reaction_name,
    outside_romance_journal_overrides,
)
from fgeh_cheatingharder_relationship import (
    get_sim_info,
    has_claim,
    has_multiple_romantic_relationships,
    is_enabled,
    request_claim,
)


_ROMANCE_TAGS = set()
_INTERACTION_OBSERVER_INSTALLED = False
_RELATIONSHIP_EVENT_OBSERVER_INSTALLED = False
_SECRET_OBSERVER_INSTALLED = False
_OBSERVED_SUCCESSFUL_INTERACTIONS = set()
_OBSERVED_REPAIR_INTERACTIONS = set()
_RELATIONSHIP_EVENT_HANDLER = None
if GameTag is not None:
    for _tag_name in ("SOCIAL_FLIRTY", "SOCIAL_FLIRTY_EMOTIONAL", "SOCIAL_FLIRTY_PHYSICAL"):
        _tag_value = getattr(GameTag, _tag_name, None)
        if _tag_value is not None:
            _ROMANCE_TAGS.add(_tag_value)


def reset_event_adapter_runtime():
    """Clear source-instance dedupe when a different save becomes active."""
    _OBSERVED_SUCCESSFUL_INTERACTIONS.clear()
    _OBSERVED_REPAIR_INTERACTIONS.clear()
    try:
        from fgeh_cheatingharder_ea_awareness import (
            reset_ea_awareness_runtime,
        )

        reset_ea_awareness_runtime()
    except Exception:
        log_exception("EA romantic awareness runtime reset failed")
    log("relationship event adapter runtime reset")


def _get_target_sim_info(interaction):
    target = getattr(interaction, "target", None)
    target_info = get_sim_info(target)
    if target_info is not None and hasattr(target_info, "sim_id"):
        return target_info
    return None


def _interaction_name(interaction):
    affordance = getattr(interaction, "affordance", None)
    return "{} {}".format(
        getattr(affordance, "__name__", ""),
        getattr(interaction, "__class__", type(interaction)).__name__,
    ).lower()


def _interaction_payload(interaction):
    affordance = getattr(interaction, "affordance", None)
    return {
        "interaction_id": getattr(interaction, "id", None),
        "interaction_name": _interaction_name(interaction),
        "affordance_id": getattr(affordance, "guid64", None),
        "affordance_name": getattr(affordance, "__name__", None),
    }


def _interaction_token(interaction):
    interaction_id = getattr(interaction, "id", None)
    if interaction_id is None:
        interaction_id = id(interaction)
    ticks = None
    try:
        now = services.time_service().sim_now
        absolute_ticks = getattr(now, "absolute_ticks", None)
        ticks = absolute_ticks() if callable(absolute_ticks) else int(now)
    except Exception:
        pass
    return (int(interaction_id), ticks)


def _interaction_event_id(interaction, actor_info, target_info):
    interaction_id, ticks = _interaction_token(interaction)
    return "interaction-success:{}:{}:{}:{}".format(
        actor_info.sim_id,
        target_info.sim_id,
        interaction_id,
        "unknown-time" if ticks is None else ticks,
    )


def _is_romantic_interaction(interaction):
    try:
        if _ROMANCE_TAGS:
            tags = set(interaction.get_category_tags())
            if tags.intersection(_ROMANCE_TAGS):
                return True
    except Exception:
        pass
    return any(
        word in _interaction_name(interaction)
        for word in ("kiss", "flirt", "romance", "woohoo", "sex")
    )


def _is_breakup_interaction(interaction):
    return any(
        word in _interaction_name(interaction)
        for word in ("breakup", "break_up", "break up")
    )


def _is_meaningful_social(interaction):
    affordance = getattr(interaction, "affordance", None)
    if not getattr(affordance, "is_social", False):
        return False
    name = _interaction_name(interaction)
    return not any(
        marker in name
        for marker in (
            "argue",
            "breakup",
            "break_up",
            "divorce",
            "fight",
            "insult",
            "mean",
            "mock",
            "shout",
            "yell",
        )
    )


def _elapsed_since_summary_timestamp(summary, key):
    if summary is None:
        return None
    previous = summary.timestamps.get(key)
    if previous is None:
        return None
    try:
        now = services.time_service().sim_now
        import date_and_time

        return date_and_time.TimeSpan(
            int(now.absolute_ticks()) - int(previous)
        ).in_minutes()
    except Exception:
        return None


def _publish_devotion_contact(interaction, actor_info, target_info, event_token):
    if not _is_meaningful_social(interaction):
        return
    try:
        from fgeh_cheatingharder_devotion_runtime import get_devotion_bond
        from fgeh_cheatingharder_memory_runtime import get_memory_summary

        matching_edges = []
        for owner, beloved in (
            (actor_info, target_info),
            (target_info, actor_info),
        ):
            bond = get_devotion_bond(owner.sim_id)
            if bond is None or bond.beloved_id != beloved.sim_id:
                continue
            summary = get_memory_summary(owner.sim_id, beloved.sim_id)
            elapsed = _elapsed_since_summary_timestamp(
                summary,
                "last_meaningful_devotion_contact_at",
            )
            if (
                elapsed is not None
                and elapsed
                < settings.DEVOTION_CONTACT_EVENT_MIN_INTERVAL_SIM_MINUTES
            ):
                continue
            matching_edges.append((owner.sim_id, beloved.sim_id))
        if not matching_edges:
            return

        from fgeh_cheatingharder_event_center import publish

        for owner_id, beloved_id in matching_edges:
            payload = _interaction_payload(interaction)
            publish(
                EventType.DEVOTION_CONTACT_COMPLETED,
                source="ea_interaction_outcome",
                event_id="{}:devotion-contact:{}:{}".format(
                    event_token,
                    owner_id,
                    beloved_id,
                ),
                actor_id=actor_info.sim_id,
                target_id=target_info.sim_id,
                observer_id=owner_id,
                partner_id=beloved_id,
                payload=payload,
            )
    except Exception:
        log_exception("devotion meaningful contact observation failed")


def observe_completed_interaction(interaction):
    """Publish only successful outcomes; callers deduplicate by interaction."""
    if interaction is None:
        return
    actor_info = get_sim_info(getattr(interaction, "sim", None))
    target_info = _get_target_sim_info(interaction)
    if actor_info is None or target_info is None:
        return
    event_token = _interaction_event_id(
        interaction,
        actor_info,
        target_info,
    )
    if _is_breakup_interaction(interaction):
        # RelationshipBitChange captures Actor -> Target before EA adds the
        # bidirectional broken-up bit.  A successful animation is not itself
        # proof that the official relationship state changed.
        log(
            "successful breakup interaction observed actor={} target={} event={}",
            actor_info.sim_id,
            target_info.sim_id,
            event_token,
        )
        try:
            from fgeh_cheatingharder_route import handle_breakup_interaction

            handle_breakup_interaction(actor_info, target_info)
        except Exception:
            log_exception("breakup route observation failed")
        return
    interaction_name = _interaction_name(interaction)
    if is_ea_jealousy_awareness_reaction_name(interaction_name):
        # EA's caught-cheating relationship bits and affair-secret discovery
        # are often one-shot signals.  A later jealousy reaction is fresh,
        # character-local proof that this observer recognized a recent
        # partner/rival incident.  Correlation still requires a recent romance
        # record and a real directed relationship edge, so proximity alone
        # cannot manufacture knowledge.
        try:
            from fgeh_cheatingharder_ea_awareness import (
                confirm_ea_romantic_awareness,
            )

            confirmed = confirm_ea_romantic_awareness(
                actor_info.sim_id,
                target_info.sim_id,
                signal="jealousy_reaction_completed",
                signal_payload=_interaction_payload(interaction),
                queue_if_missing=False,
            )
            log(
                "EA jealousy reaction awareness observed observer={} "
                "partner={} interaction={} confirmed={}",
                actor_info.sim_id,
                target_info.sim_id,
                interaction_name,
                confirmed,
            )
        except Exception:
            log_exception("EA jealousy reaction awareness observation failed")
        # A jealousy reaction is a response to romance, not a new romantic act.
        # Do not cache it as partner/rival evidence.
        return
    _publish_devotion_contact(
        interaction,
        actor_info,
        target_info,
        event_token,
    )
    if not _is_romantic_interaction(interaction):
        return
    log(
        "successful romantic interaction actor={} target={} affordance={}",
        actor_info.sim_id,
        target_info.sim_id,
        getattr(getattr(interaction, "affordance", None), "__name__", "unknown"),
    )
    from fgeh_cheatingharder_event_center import publish

    payload = _interaction_payload(interaction)
    actor_has_other_romance = has_multiple_romantic_relationships(
        actor_info,
        target_info,
    )
    target_has_other_romance = has_multiple_romantic_relationships(
        target_info,
        actor_info,
    )
    journal_overrides = outside_romance_journal_overrides(
        actor_has_other_romance,
        target_has_other_romance,
    )
    if journal_overrides:
        payload.update(journal_overrides)
        payload["outside_romance_participant_ids"] = tuple(
            sim_info.sim_id
            for sim_info, has_other_romance in (
                (actor_info, actor_has_other_romance),
                (target_info, target_has_other_romance),
            )
            if has_other_romance
        )
        log(
            "outside romance promoted to journal timeline actor={} target={} "
            "actor_has_other={} target_has_other={}",
            actor_info.sim_id,
            target_info.sim_id,
            actor_has_other_romance,
            target_has_other_romance,
        )
    publish(
        EventType.ROMANCE_COMPLETED,
        source="ea_interaction_outcome",
        event_id=event_token,
        actor_id=actor_info.sim_id,
        target_id=target_info.sim_id,
        payload=payload,
    )
    try:
        from fgeh_cheatingharder_ea_awareness import (
            record_recent_romance_event,
        )

        record_recent_romance_event(
            actor_info.sim_id,
            target_info.sim_id,
            event_token,
            payload=payload,
        )
    except Exception:
        log_exception("recent romantic interaction cache failed")
    # This is a local witness check only.  It does not arm incoming claims and
    # therefore cannot grant absent Sims omniscient knowledge.
    try:
        from fgeh_cheatingharder_route import on_romantic_interaction

        on_romantic_interaction(
            actor_info,
            target_info,
            cause_id=event_token,
        )
    except Exception:
        log_exception("local caught interaction observation failed")
    if is_enabled(actor_info):
        request_claim(actor_info, target_info)
    elif is_enabled(target_info):
        # EA social mixers may report the player-directed Sim as the target.
        # Keep the one-way claim prompt aligned with the enabled participant,
        # not with an unreliable actor/target orientation.
        log(
            "claim request orientation reversed enabled_sim={} other_sim={}",
            target_info.sim_id,
            actor_info.sim_id,
        )
        request_claim(target_info, actor_info)


def _observe_repair_outcome(interaction, outcome_result):
    """Adapt exact EA repair affordances, including their failure outcomes."""
    try:
        from fgeh_cheatingharder_repair_ea import (
            is_ea_apology_interaction,
            observe_ea_apology_outcome,
        )

        if not is_ea_apology_interaction(interaction):
            return False
        interaction_token = _interaction_token(interaction)[0]
        if interaction_token in _OBSERVED_REPAIR_INTERACTIONS:
            return True
        _OBSERVED_REPAIR_INTERACTIONS.add(interaction_token)
        if len(_OBSERVED_REPAIR_INTERACTIONS) > 512:
            _OBSERVED_REPAIR_INTERACTIONS.clear()
            _OBSERVED_REPAIR_INTERACTIONS.add(interaction_token)
        actor_info = get_sim_info(getattr(interaction, "sim", None))
        target_info = _get_target_sim_info(interaction)
        if actor_info is None or target_info is None:
            return False
        return observe_ea_apology_outcome(
            interaction,
            outcome_result == OutcomeResult.SUCCESS,
            event_id="{}:repair:apology".format(
                _interaction_event_id(
                    interaction,
                    actor_info,
                    target_info,
                )
            ),
        )
    except Exception:
        log_exception("EA repair interaction outcome observation failed")
        return False


def install_interaction_observer():
    global _INTERACTION_OBSERVER_INSTALLED
    if _INTERACTION_OBSERVER_INSTALLED:
        return True
    if Interaction is None or OutcomeResult is None or injector is None:
        log("interaction outcome observer unavailable")
        return False

    @injector.inject(Interaction, "store_result_for_outcome", safe=True)
    def _observe_outcome(original, interaction, *args, **kwargs):
        result = original(interaction, *args, **kwargs)
        try:
            outcome_result = args[1] if len(args) > 1 else kwargs.get("result")
            try:
                from fgeh_cheatingharder_autonomous_behavior_runtime import (
                    observe_autonomous_interaction_outcome,
                )

                observe_autonomous_interaction_outcome(
                    interaction,
                    outcome_result == OutcomeResult.SUCCESS,
                )
            except Exception:
                log_exception(
                    "autonomous interaction outcome observation failed"
                )
            _observe_repair_outcome(interaction, outcome_result)
            interaction_token = _interaction_token(interaction)[0]
            if (
                outcome_result == OutcomeResult.SUCCESS
                and interaction_token not in _OBSERVED_SUCCESSFUL_INTERACTIONS
            ):
                _OBSERVED_SUCCESSFUL_INTERACTIONS.add(interaction_token)
                if len(_OBSERVED_SUCCESSFUL_INTERACTIONS) > 512:
                    _OBSERVED_SUCCESSFUL_INTERACTIONS.clear()
                    _OBSERVED_SUCCESSFUL_INTERACTIONS.add(interaction_token)
                observe_completed_interaction(interaction)
        except Exception:
            log_exception("successful interaction outcome observation failed")
        return result

    _INTERACTION_OBSERVER_INSTALLED = True
    log("successful interaction outcome observer installed")
    return True


class _RelationshipBitEventHandler:

    def handle_event(self, sim_info, event, resolver):
        try:
            bit = resolver.event_kwargs.get("relationship_bit")
            bit_id = getattr(bit, "guid64", None)
            target_id = resolver.event_kwargs.get("target_sim_id")
            if sim_info is None or target_id is None:
                return
            from fgeh_cheatingharder_event_center import publish

            if bit_id == settings.CLAIM_RELATIONSHIP_BIT_INSTANCE_ID:
                publish(
                    EventType.CLAIM_ESTABLISHED,
                    source="ea_add_relationship_bit",
                    event_id="claim:{}:{}".format(sim_info.sim_id, target_id),
                    observer_id=sim_info.sim_id,
                    partner_id=target_id,
                )
                return
            from fgeh_cheatingharder_ea_awareness import (
                observe_ea_breakup_bit,
                observe_relationship_bit_awareness,
            )

            observe_ea_breakup_bit(sim_info, target_id, bit)
            observe_relationship_bit_awareness(sim_info, target_id, bit)
        except Exception:
            log_exception("relationship bit event adapter failed")


def install_relationship_event_observer():
    global _RELATIONSHIP_EVENT_OBSERVER_INSTALLED, _RELATIONSHIP_EVENT_HANDLER
    if TestEvent is None:
        return False
    try:
        event_manager = services.get_event_manager()
        if event_manager is None:
            return False
        if _RELATIONSHIP_EVENT_HANDLER is None:
            _RELATIONSHIP_EVENT_HANDLER = _RelationshipBitEventHandler()
        # EventManagerService clears its callback map on every zone unload.
        # The underlying map stores handlers in a set, so registering the same
        # handler again is idempotent within a zone and required after travel.
        event_manager.register_single_event(
            _RELATIONSHIP_EVENT_HANDLER,
            TestEvent.AddRelationshipBit,
        )
        _RELATIONSHIP_EVENT_OBSERVER_INSTALLED = True
        log("relationship bit event observer installed")
        return True
    except Exception:
        log_exception("relationship bit event observer install failed")
        return False


def install_secret_observer():
    global _SECRET_OBSERVER_INSTALLED
    if _SECRET_OBSERVER_INSTALLED or injector is None:
        return _SECRET_OBSERVER_INSTALLED
    try:
        from sims.secrets.sim_secret_enums import RelationshipSecretStatus
        from sims.secrets.sim_secrets_service import SimSecretsService

        @injector.inject(SimSecretsService, "add_secret_for_sims", safe=True)
        def _observe_secret_creation(original, service, *args, **kwargs):
            secret = original(service, *args, **kwargs)
            try:
                if secret is not None and secret.guid64 == settings.EA_AFFAIR_SECRET_INSTANCE_ID:
                    from fgeh_cheatingharder_event_center import publish

                    publish(
                        EventType.AFFAIR_SECRET_CREATED,
                        source="ea_secret_service",
                        event_id="affair-created:{}".format(secret.secret_id),
                        payload={"complicit_sim_ids": tuple(secret.complicit_sims)},
                    )
            except Exception:
                log_exception("affair secret creation adapter failed")
            return secret

        @injector.inject(
            SimSecretsService,
            "update_relationship_secret_status",
            safe=True,
        )
        def _observe_secret_discovery(original, service, *args, **kwargs):
            secret_id = args[0] if len(args) > 0 else kwargs.get("secret_id")
            source_sim_id = args[1] if len(args) > 1 else kwargs.get("source_sim_id")
            target_sim_id = args[2] if len(args) > 2 else kwargs.get("target_sim_id")
            relationship_status = (
                args[3] if len(args) > 3 else kwargs.get("relationship_secret_status")
            )
            result = original(service, *args, **kwargs)
            try:
                secret = service._secrets.get(secret_id)
                if (
                    result
                    and secret is not None
                    and secret.guid64 == settings.EA_AFFAIR_SECRET_INSTANCE_ID
                    and relationship_status == RelationshipSecretStatus.DISCOVERED
                ):
                    discoverer_id = None
                    if source_sim_id not in secret.complicit_sims:
                        discoverer_id = source_sim_id
                    elif target_sim_id not in secret.complicit_sims:
                        discoverer_id = target_sim_id
                    discoverer = services.sim_info_manager().get(discoverer_id)
                    if discoverer is not None:
                        from fgeh_cheatingharder_event_center import publish
                        from fgeh_cheatingharder_ea_awareness import (
                            observe_affair_secret_discovery,
                        )

                        for partner_id in tuple(secret.complicit_sims):
                            partner = services.sim_info_manager().get(partner_id)
                            if partner is None or not has_claim(discoverer, partner):
                                continue
                            publish(
                                EventType.AFFAIR_SECRET_DISCOVERED,
                                source="ea_secret_service",
                                event_id="affair-discovered:{}:{}:{}".format(
                                    secret.secret_id,
                                    discoverer_id,
                                    partner_id,
                                ),
                                observer_id=discoverer_id,
                                partner_id=partner_id,
                                payload={
                                    "secret_id": secret.secret_id,
                                    "complicit_sim_ids": tuple(
                                        secret.complicit_sims
                                    ),
                                    "knowledge_signal_only": True,
                                },
                            )
                        observe_affair_secret_discovery(
                            discoverer_id,
                            tuple(secret.complicit_sims),
                            secret.secret_id,
                        )
            except Exception:
                log_exception("affair secret discovery adapter failed")
            return result

        _SECRET_OBSERVER_INSTALLED = True
        log("original affair secret observers installed")
        return True
    except Exception:
        log("original affair secret observers unavailable (EP21 may not be installed)")
        return False


def install_game_event_observers():
    install_interaction_observer()
    install_relationship_event_observer()
    install_secret_observer()
    return True


def is_interaction_observer_installed():
    return _INTERACTION_OBSERVER_INSTALLED

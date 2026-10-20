"""Sims 4 adapter for permanent one-way devotion and romance guarding."""

from event_testing.results import TestResult
from interactions.aop import AffordanceObjectPair
from interactions.interaction_queue import InteractionQueue
from sims4.localization import LocalizationHelperTuning

import fgeh_cheatingharder_injector as injector
import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_devotion import (
    evaluate_mean_pair,
    evaluate_romantic_pair,
    mean_interaction_metadata_reason,
    romantic_interaction_metadata_reason,
)
from fgeh_cheatingharder_domain import EventType


_GUARD_INSTALLED = False
_REJECTION_EVENT_IDS = set()
_AOP_BLOCK_LOG_KEYS = set()
_ROMANCE_TAGS = set()

try:
    try:
        from tag import GameTag
    except ImportError:
        from tag import Tag as GameTag

    for _tag_name in (
        "SOCIAL_FLIRTY",
        "SOCIAL_FLIRTY_EMOTIONAL",
        "SOCIAL_FLIRTY_PHYSICAL",
        "SOCIAL_ROMANTIC",
        "SOCIAL_WOOHOO",
        "WOOHOO",
    ):
        _tag = getattr(GameTag, _tag_name, None)
        if _tag is not None:
            _ROMANCE_TAGS.add(_tag)
except Exception:
    pass


_ROMANCE_PRIORITY_NAME_MARKERS = (
    # WW's conversation is sexual/romantic gameplay even though some tuning
    # names begin with the otherwise informational "talk_about" prefix.
    "sex_fantas",
    "talkaboutfantas",
    "talk_about_fantas",
)

_ROMANCE_NAME_MARKERS = (
    "flirt",
    "kiss",
    "makeout",
    "make_out",
    "make out",
    "woohoo",
    "try_for_baby",
    "try for baby",
    "romance",
    "romantic",
    "propose",
    "boyfriend",
    "girlfriend",
    "askforsex",
    "startsex",
    "start_sex",
    "joinsex",
    "join_sex",
    "sex_partner",
    "sex_interaction",
)
_NON_ROMANCE_NAME_MARKERS = (
    "breakup",
    "break_up",
    "break up",
    "divorce",
    "preference",
    "orientation",
    "romance_advice",
    "romantic_advice",
    "relationshipadvice",
    "romanticeducation",
    "askaboutlovelife",
    "askaboutwoohoo",
    "woohoointerest",
    "talk_about",
    "discuss",
    "reaction",
    "jealousy_reaction",
    "settings",
    "debug",
)


def _sim_info(value):
    if value is None:
        return None
    value = getattr(value, "sim_info", value)
    return value if getattr(value, "sim_id", None) else None


def _sim_now_ticks():
    try:
        import services

        now = services.time_service().sim_now
        absolute_ticks = getattr(now, "absolute_ticks", None)
        return absolute_ticks() if callable(absolute_ticks) else int(now)
    except Exception:
        return None


def get_devotion_bond(owner_or_id):
    owner_id = getattr(_sim_info(owner_or_id), "sim_id", owner_or_id)
    try:
        owner_id = int(owner_id)
    except (TypeError, ValueError):
        return None
    try:
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        return get_memory_service().store.get_devotion_bond(owner_id)
    except Exception:
        log_exception(
            "devotion bond lookup failed owner={}".format(owner_id)
        )
        return None


def can_choose_beloved(owner_or_id, beloved_or_id):
    owner = _sim_info(owner_or_id)
    beloved = _sim_info(beloved_or_id)
    if owner is None or beloved is None or owner.sim_id == beloved.sim_id:
        return False
    bond = get_devotion_bond(owner.sim_id)
    return bond is None or bond.beloved_id == beloved.sim_id


def establish_devotion(
    owner_or_info,
    beloved_or_info,
    source="player_choice",
):
    """Bind one owner permanently and publish the objective creation event."""
    owner = _sim_info(owner_or_info)
    beloved = _sim_info(beloved_or_info)
    if owner is None or beloved is None or owner.sim_id == beloved.sim_id:
        return None
    try:
        from fgeh_cheatingharder_relationship import is_devotion_enabled

        if not bool(getattr(owner, "is_selectable", False)):
            log(
                "devotion binding rejected: owner is not player-controlled owner={}",
                owner.sim_id,
            )
            return None
        if not is_devotion_enabled(owner):
            log(
                "devotion binding rejected: owner lacks devotion trait owner={}",
                owner.sim_id,
            )
            return None
    except Exception:
        log_exception(
            "devotion binding eligibility check failed owner={}".format(
                owner.sim_id
            )
        )
        return None
    existing = get_devotion_bond(owner.sim_id)
    if existing is not None:
        if existing.beloved_id != beloved.sim_id:
            log(
                "devotion conflict owner={} existing_beloved={} requested={}",
                owner.sim_id,
                existing.beloved_id,
                beloved.sim_id,
            )
            return None
        try:
            from fgeh_cheatingharder_relationship import (
                ensure_devotion_relationship_bit,
            )

            ensure_devotion_relationship_bit(owner, beloved)
        except Exception:
            log_exception(
                "existing devotion relationship bit reconcile failed owner={} beloved={}".format(
                    owner.sim_id,
                    beloved.sim_id,
                )
            )
        return existing

    event_id = "devotion:{}:{}".format(owner.sim_id, beloved.sim_id)
    try:
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        bond, created = get_memory_service().store.bind_devotion(
            owner.sim_id,
            beloved.sim_id,
            event_id,
            established_at=_sim_now_ticks(),
            source=source,
        )
        if not created:
            try:
                from fgeh_cheatingharder_relationship import (
                    ensure_devotion_relationship_bit,
                )

                ensure_devotion_relationship_bit(owner, beloved)
            except Exception:
                log_exception(
                    "restored devotion relationship bit reconcile failed owner={} beloved={}".format(
                        owner.sim_id,
                        beloved.sim_id,
                    )
                )
            return bond
        try:
            from fgeh_cheatingharder_relationship import (
                ensure_devotion_relationship_bit,
            )

            ensure_devotion_relationship_bit(owner, beloved)
        except Exception:
            # The bond is the authority.  A missing tuning resource must not
            # roll it back or weaken the romance guards.
            log_exception(
                "new devotion relationship bit projection failed owner={} beloved={}".format(
                    owner.sim_id,
                    beloved.sim_id,
                )
            )
        from fgeh_cheatingharder_event_center import publish

        publish(
            EventType.DEVOTION_BOND_CREATED,
            source="devotion_runtime",
            event_id=event_id,
            observer_id=owner.sim_id,
            partner_id=beloved.sim_id,
            payload={
                "devotion_source": source,
                "permanent": True,
                "exclusive": True,
            },
        )
        try:
            from fgeh_cheatingharder_longing_runtime import (
                schedule_longing_check,
            )

            schedule_longing_check(
                owner.sim_id,
                beloved.sim_id,
                minutes=settings.DEVOTION_LONGING_FIRST_CHECK_SIM_MINUTES,
            )
        except Exception:
            log_exception(
                "devotion longing cycle arm failed owner={} beloved={}".format(
                    owner.sim_id,
                    beloved.sim_id,
                )
            )
        log(
            "permanent devotion established owner={} beloved={} source={}",
            owner.sim_id,
            beloved.sim_id,
            source,
        )
        return bond
    except Exception:
        log_exception(
            "permanent devotion establishment failed owner={} beloved={}".format(
                owner.sim_id,
                beloved.sim_id,
            )
        )
        return None


def _affordance_name(affordance_or_interaction):
    affordance = getattr(
        affordance_or_interaction,
        "affordance",
        affordance_or_interaction,
    )
    return "{} {}".format(
        getattr(affordance, "__name__", ""),
        getattr(affordance, "tuning_manager", ""),
    ).lower()


def _affordance(affordance_or_interaction):
    return getattr(
        affordance_or_interaction,
        "affordance",
        affordance_or_interaction,
    )


def _category_tags(affordance_or_interaction):
    affordance = _affordance(affordance_or_interaction)
    tags = set(getattr(affordance, "interaction_category_tags", ()) or ())
    getter = getattr(affordance_or_interaction, "get_category_tags", None)
    if callable(getter):
        try:
            tags.update(getter())
        except Exception:
            pass
    return tags


def _queue_icon_instance(affordance_or_interaction):
    icon_factory = getattr(
        _affordance(affordance_or_interaction),
        "_icon",
        None,
    )
    resource_key = getattr(icon_factory, "key", None)
    try:
        return int(getattr(resource_key, "instance", None))
    except (TypeError, ValueError):
        return None


def _broadcaster_ids(affordance_or_interaction):
    ids = set()
    basic_extras = getattr(
        _affordance(affordance_or_interaction),
        "basic_extras",
        (),
    ) or ()
    for extra in basic_extras:
        broadcaster_types = getattr(extra, "broadcaster_types", None)
        get_all = getattr(broadcaster_types, "get_all", None)
        if not callable(get_all):
            continue
        try:
            for broadcaster_type in get_all():
                broadcaster_id = getattr(
                    broadcaster_type,
                    "guid64",
                    None,
                )
                if broadcaster_id is not None:
                    ids.add(int(broadcaster_id))
        except Exception:
            continue
    return ids


def romantic_interaction_classification(affordance_or_interaction):
    name = _affordance_name(affordance_or_interaction)
    if any(marker in name for marker in _ROMANCE_PRIORITY_NAME_MARKERS):
        return "priority_name"
    metadata_reason = romantic_interaction_metadata_reason(
        _queue_icon_instance(affordance_or_interaction),
        _broadcaster_ids(affordance_or_interaction),
    )
    if metadata_reason is not None:
        return metadata_reason
    if any(marker in name for marker in _NON_ROMANCE_NAME_MARKERS):
        return None
    try:
        category_tags = _category_tags(affordance_or_interaction)
        if _ROMANCE_TAGS.intersection(category_tags):
            return "category_tag"
        tag_names = " ".join(str(value).lower() for value in category_tags)
        if any(
            marker in tag_names
            for marker in ("flirty", "romance", "romantic", "woohoo")
        ):
            return "category_tag_name"
    except Exception:
        pass
    if any(marker in name for marker in _ROMANCE_NAME_MARKERS):
        return "name"
    return None


def is_guarded_romantic_interaction(affordance_or_interaction):
    return romantic_interaction_classification(
        affordance_or_interaction
    ) is not None


def mean_interaction_classification(affordance_or_interaction):
    return mean_interaction_metadata_reason(
        _category_tags(affordance_or_interaction)
    )


def is_guarded_mean_interaction(affordance_or_interaction):
    return mean_interaction_classification(
        affordance_or_interaction
    ) is not None


def evaluate_interaction_permission(actor_or_info, target_or_info):
    actor = _sim_info(actor_or_info)
    target = _sim_info(target_or_info)
    if actor is None or target is None:
        return None
    try:
        return evaluate_romantic_pair(
            actor.sim_id,
            target.sim_id,
            get_devotion_bond,
        )
    except Exception:
        log_exception(
            "devotion romantic pair evaluation failed actor={} target={}".format(
                actor.sim_id,
                target.sim_id,
            )
        )
        return None


def evaluate_mean_interaction_permission(actor_or_info, target_or_info):
    actor = _sim_info(actor_or_info)
    target = _sim_info(target_or_info)
    if actor is None or target is None:
        return None
    try:
        return evaluate_mean_pair(
            actor.sim_id,
            target.sim_id,
            get_devotion_bond,
        )
    except Exception:
        log_exception(
            "devotion mean pair evaluation failed actor={} target={}".format(
                actor.sim_id,
                target.sim_id,
            )
        )
        return None


def _blocked_test_result():
    tooltip = LocalizationHelperTuning.get_raw_text(
        "对方心中已有此生唯一的挚爱，不会接受这段浪漫关系。"
    )
    return TestResult(
        False,
        "Blocked by FGEH permanent devotion.",
        tooltip=lambda *args, **kwargs: tooltip,
    )


def _blocked_mean_test_result():
    tooltip = LocalizationHelperTuning.get_raw_text(
        "至死不渝的小人不会对自己认定的一生挚爱使用刻薄互动。"
    )
    return TestResult(
        False,
        "Blocked mean interaction toward FGEH permanent beloved.",
        tooltip=lambda *args, **kwargs: tooltip,
    )


def _publish_rejection(interaction, actor, target, permission):
    interaction_id = getattr(interaction, "id", id(interaction))
    if interaction_id in _REJECTION_EVENT_IDS:
        return
    _REJECTION_EVENT_IDS.add(interaction_id)
    if len(_REJECTION_EVENT_IDS) > 512:
        _REJECTION_EVENT_IDS.clear()
        _REJECTION_EVENT_IDS.add(interaction_id)
    try:
        from fgeh_cheatingharder_event_center import publish

        publish(
            EventType.OUTSIDE_ROMANCE_REJECTED,
            source="interaction_queue_guard",
            event_id="devotion-rejection:{}:{}:{}".format(
                actor.sim_id,
                target.sim_id,
                interaction_id,
            ),
            actor_id=actor.sim_id,
            target_id=target.sim_id,
            observer_id=permission.devoted_owner_id,
            partner_id=permission.beloved_id,
            payload={
                "interaction_name": _affordance_name(interaction),
                "block_reason": permission.reason,
                "interaction_id": interaction_id,
            },
        )
    except Exception:
        log_exception("devotion rejection event publish failed")


def install_devotion_guard():
    global _GUARD_INSTALLED
    if _GUARD_INSTALLED:
        return True
    try:
        @injector.inject(AffordanceObjectPair, "test", safe=True)
        def _test_romantic_permission(
            original,
            aop,
            context,
            *args,
            **kwargs
        ):
            original_result = original(aop, context, *args, **kwargs)
            try:
                if not original_result:
                    return original_result
                if is_guarded_mean_interaction(aop.affordance):
                    permission = evaluate_mean_interaction_permission(
                        getattr(context, "sim", None),
                        aop.target,
                    )
                    if permission is not None and not permission.allowed:
                        log(
                            "devotion mean AOP blocked actor={} target={} owner={} beloved={} classification={} affordance={}",
                            permission.actor_id,
                            permission.target_id,
                            permission.devoted_owner_id,
                            permission.beloved_id,
                            mean_interaction_classification(
                                aop.affordance
                            ),
                            _affordance_name(aop.affordance),
                        )
                        return _blocked_mean_test_result()
                if not is_guarded_romantic_interaction(aop.affordance):
                    return original_result
                permission = evaluate_interaction_permission(
                    getattr(context, "sim", None),
                    aop.target,
                )
                if permission is not None and not permission.allowed:
                    actor_id = getattr(
                        _sim_info(getattr(context, "sim", None)),
                        "sim_id",
                        None,
                    )
                    target_id = getattr(
                        _sim_info(aop.target),
                        "sim_id",
                        None,
                    )
                    affordance_name = _affordance_name(aop.affordance)
                    classification = romantic_interaction_classification(
                        aop.affordance
                    )
                    log_key = (
                        actor_id,
                        target_id,
                        affordance_name,
                    )
                    if log_key not in _AOP_BLOCK_LOG_KEYS:
                        _AOP_BLOCK_LOG_KEYS.add(log_key)
                        if len(_AOP_BLOCK_LOG_KEYS) > 512:
                            _AOP_BLOCK_LOG_KEYS.clear()
                            _AOP_BLOCK_LOG_KEYS.add(log_key)
                        log(
                            "devotion AOP blocked actor={} target={} owner={} beloved={} reason={} classification={} affordance={}",
                            actor_id,
                            target_id,
                            permission.devoted_owner_id,
                            permission.beloved_id,
                            permission.reason,
                            classification,
                            affordance_name,
                        )
                    return _blocked_test_result()
            except Exception:
                # A guard failure must never take the interaction system down.
                log_exception("devotion AOP guard failed open")
            return original_result

        @injector.inject(InteractionQueue, "append", safe=True)
        def _guard_romantic_queue(original, queue, interaction, *args, **kwargs):
            try:
                if is_guarded_mean_interaction(interaction):
                    actor = _sim_info(getattr(interaction, "sim", None))
                    target = _sim_info(getattr(interaction, "target", None))
                    permission = evaluate_mean_interaction_permission(
                        actor,
                        target,
                    )
                    if permission is not None and not permission.allowed:
                        log(
                            "devotion mean queue blocked actor={} target={} owner={} beloved={} classification={} interaction={}",
                            permission.actor_id,
                            permission.target_id,
                            permission.devoted_owner_id,
                            permission.beloved_id,
                            mean_interaction_classification(interaction),
                            _affordance_name(interaction),
                        )
                        return TestResult(
                            False,
                            "Blocked mean interaction toward permanent beloved.",
                        )
                if is_guarded_romantic_interaction(interaction):
                    actor = _sim_info(getattr(interaction, "sim", None))
                    target = _sim_info(getattr(interaction, "target", None))
                    permission = evaluate_interaction_permission(actor, target)
                    if permission is not None and not permission.allowed:
                        log(
                            "devotion queue blocked actor={} target={} owner={} beloved={} reason={} classification={} interaction={}",
                            actor.sim_id,
                            target.sim_id,
                            permission.devoted_owner_id,
                            permission.beloved_id,
                            permission.reason,
                            romantic_interaction_classification(
                                interaction
                            ),
                            _affordance_name(interaction),
                        )
                        _publish_rejection(
                            interaction,
                            actor,
                            target,
                            permission,
                        )
                        return TestResult(
                            False,
                            "Blocked by FGEH permanent devotion queue guard.",
                        )
            except Exception:
                log_exception("devotion queue guard failed open")
            return original(queue, interaction, *args, **kwargs)

        _GUARD_INSTALLED = True
        log(
            "permanent devotion romance/mean guard installed romance_tags={}",
            len(_ROMANCE_TAGS),
        )
        return True
    except Exception:
        log_exception("permanent devotion romance guard install failed")
        return False

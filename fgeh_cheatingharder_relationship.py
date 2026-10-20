import services
import sims4.resources
import date_and_time

from sims4.resources import Types

import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception


_TRAIT_CACHE = None
_DEVOTION_TRAIT_CACHE = None
_CLAIM_BIT_CACHE = None
_CHECK_IN_COOLDOWN_BIT_CACHE = None
_DEVOTION_RELATIONSHIP_BIT_CACHE = None
_BETRAYAL_RIVAL_RELATIONSHIP_BIT_CACHE = None
_DECLINED_CLAIMS = {}


def _get_tuning(resource_type, instance_id):
    try:
        key = sims4.resources.get_resource_key(instance_id, resource_type)
        manager = services.get_instance_manager(resource_type)
        return manager.get(key)
    except Exception:
        log_exception("tuning lookup failed type={} instance={}".format(resource_type, instance_id))
        return None


def get_possessive_trait():
    global _TRAIT_CACHE
    if _TRAIT_CACHE is None:
        _TRAIT_CACHE = _get_tuning(Types.TRAIT, settings.TRAIT_INSTANCE_ID)
        log("possessive trait lookup found={}", _TRAIT_CACHE is not None)
    return _TRAIT_CACHE


def get_devotion_trait():
    global _DEVOTION_TRAIT_CACHE
    if _DEVOTION_TRAIT_CACHE is None:
        _DEVOTION_TRAIT_CACHE = _get_tuning(
            Types.TRAIT,
            settings.DEVOTION_TRAIT_INSTANCE_ID,
        )
        log(
            "permanent devotion trait lookup found={}",
            _DEVOTION_TRAIT_CACHE is not None,
        )
    return _DEVOTION_TRAIT_CACHE


def get_claim_relationship_bit():
    global _CLAIM_BIT_CACHE
    if _CLAIM_BIT_CACHE is None:
        _CLAIM_BIT_CACHE = _get_tuning(
            Types.RELATIONSHIP_BIT,
            settings.CLAIM_RELATIONSHIP_BIT_INSTANCE_ID,
        )
        log("claim relationship bit lookup found={}", _CLAIM_BIT_CACHE is not None)
    return _CLAIM_BIT_CACHE


def get_check_in_cooldown_bit():
    global _CHECK_IN_COOLDOWN_BIT_CACHE
    if _CHECK_IN_COOLDOWN_BIT_CACHE is None:
        _CHECK_IN_COOLDOWN_BIT_CACHE = _get_tuning(
            Types.RELATIONSHIP_BIT,
            settings.CHECK_IN_COOLDOWN_BIT_INSTANCE_ID,
        )
        log(
            "check-in cooldown relationship bit lookup found={}",
            _CHECK_IN_COOLDOWN_BIT_CACHE is not None,
        )
    return _CHECK_IN_COOLDOWN_BIT_CACHE


def get_devotion_relationship_bit():
    """Return the visible owner -> beloved UI projection tuning."""
    global _DEVOTION_RELATIONSHIP_BIT_CACHE
    if _DEVOTION_RELATIONSHIP_BIT_CACHE is None:
        _DEVOTION_RELATIONSHIP_BIT_CACHE = _get_tuning(
            Types.RELATIONSHIP_BIT,
            settings.DEVOTION_RELATIONSHIP_BIT_INSTANCE_ID,
        )
        log(
            "devotion relationship bit lookup found={}",
            _DEVOTION_RELATIONSHIP_BIT_CACHE is not None,
        )
    return _DEVOTION_RELATIONSHIP_BIT_CACHE


def get_betrayal_rival_relationship_bit():
    """Return the visible observer -> known rival projection tuning."""
    global _BETRAYAL_RIVAL_RELATIONSHIP_BIT_CACHE
    if _BETRAYAL_RIVAL_RELATIONSHIP_BIT_CACHE is None:
        _BETRAYAL_RIVAL_RELATIONSHIP_BIT_CACHE = _get_tuning(
            Types.RELATIONSHIP_BIT,
            settings.BETRAYAL_RIVAL_RELATIONSHIP_BIT_INSTANCE_ID,
        )
        log(
            "betrayal rival relationship bit lookup found={}",
            _BETRAYAL_RIVAL_RELATIONSHIP_BIT_CACHE is not None,
        )
    return _BETRAYAL_RIVAL_RELATIONSHIP_BIT_CACHE


def get_sim_info(sim_or_info):
    if sim_or_info is None:
        return None
    sim_info = getattr(sim_or_info, "sim_info", sim_or_info)
    if hasattr(sim_info, "sim_id"):
        return sim_info
    if isinstance(sim_info, int):
        try:
            manager = services.sim_info_manager()
            if manager is not None:
                return manager.get(sim_info)
        except Exception:
            log_exception(
                "SimInfo id lookup failed sim_id={}".format(sim_info)
            )
        return None
    return sim_info


def is_enabled(sim_or_info):
    sim_info = get_sim_info(sim_or_info)
    trait = get_possessive_trait()
    if sim_info is None or trait is None:
        log(
            "trait test unavailable sim={} trait_found={}",
            getattr(sim_info, "sim_id", None),
            trait is not None,
        )
        return False
    try:
        return bool(sim_info.has_trait(trait))
    except Exception:
        try:
            return bool(sim_info.trait_tracker.has_trait(trait))
        except Exception:
            log_exception("trait test failed")
            return False


def is_devotion_enabled(sim_or_info):
    sim_info = get_sim_info(sim_or_info)
    trait = get_devotion_trait()
    if sim_info is None or trait is None:
        return False
    try:
        return bool(sim_info.has_trait(trait))
    except Exception:
        try:
            return bool(sim_info.trait_tracker.has_trait(trait))
        except Exception:
            log_exception("permanent devotion trait test failed")
            return False


def has_claim(observer_sim_or_info, target_sim_or_info):
    observer = get_sim_info(observer_sim_or_info)
    target = get_sim_info(target_sim_or_info)
    bit = get_claim_relationship_bit()
    if observer is None or target is None or bit is None:
        return False
    try:
        return bool(observer.relationship_tracker.has_bit(target.sim_id, bit))
    except Exception:
        log_exception("claim test failed observer={} target={}".format(observer, target))
        return False


def has_check_in_cooldown(observer_sim_or_info, target_sim_or_info):
    observer = get_sim_info(observer_sim_or_info)
    target = get_sim_info(target_sim_or_info)
    bit = get_check_in_cooldown_bit()
    if observer is None or target is None or bit is None:
        return False
    try:
        return bool(observer.relationship_tracker.has_bit(target.sim_id, bit))
    except Exception:
        log_exception("check-in cooldown test failed")
        return False


def has_devotion_relationship_bit(owner_sim_or_info, beloved_sim_or_info):
    owner = get_sim_info(owner_sim_or_info)
    beloved = get_sim_info(beloved_sim_or_info)
    bit = get_devotion_relationship_bit()
    if owner is None or beloved is None or bit is None:
        return False
    try:
        return bool(owner.relationship_tracker.has_bit(beloved.sim_id, bit))
    except Exception:
        log_exception(
            "devotion relationship bit test failed owner={} beloved={}".format(
                getattr(owner, "sim_id", None),
                getattr(beloved, "sim_id", None),
            )
        )
        return False


def ensure_devotion_relationship_bit(owner_sim_or_info, beloved_sim_or_info):
    """Reconcile one visible bit from the authoritative devotion bond."""
    owner = get_sim_info(owner_sim_or_info)
    beloved = get_sim_info(beloved_sim_or_info)
    bit = get_devotion_relationship_bit()
    if owner is None or beloved is None or bit is None:
        return False
    try:
        already_present = has_devotion_relationship_bit(owner, beloved)
        if not already_present:
            owner.relationship_tracker.add_relationship_bit(
                beloved.sim_id,
                bit,
                force_add=True,
                allow_readdition=True,
            )
            log(
                "devotion relationship bit added owner={} beloved={}",
                owner.sim_id,
                beloved.sim_id,
            )
        # Saved unidirectional bits can already exist before the client has
        # received the actor-facing relationship proto.  Re-send this exact
        # edge after reconciliation so Sim Profile does not depend on a fresh
        # add/remove event.
        owner.relationship_tracker.send_relationship_info(
            target_sim_id=beloved.sim_id
        )
        log(
            "devotion relationship info resent owner={} beloved={} existing={}",
            owner.sim_id,
            beloved.sim_id,
            already_present,
        )
        return True
    except Exception:
        log_exception(
            "devotion relationship bit add failed owner={} beloved={}".format(
                owner.sim_id,
                beloved.sim_id,
            )
        )
        return False


def reconcile_devotion_relationship_bits():
    """Restore missing UI projections after the memory snapshot is loaded."""
    try:
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        manager = services.sim_info_manager()
        restored = 0
        missing_sims = 0
        for bond in get_memory_service().store.devotion_bonds():
            owner = manager.get(int(bond.owner_id))
            beloved = manager.get(int(bond.beloved_id))
            if owner is None or beloved is None:
                missing_sims += 1
                continue
            if ensure_devotion_relationship_bit(owner, beloved):
                restored += 1
        log(
            "devotion relationship bit reconciliation complete bonds={} available={} missing_sims={}",
            len(get_memory_service().store.devotion_bonds()),
            restored,
            missing_sims,
        )
        return restored
    except Exception:
        log_exception("devotion relationship bit reconciliation failed")
        return 0


def has_betrayal_rival_relationship_bit(observer_sim_or_info, rival_sim_or_info):
    observer = get_sim_info(observer_sim_or_info)
    rival = get_sim_info(rival_sim_or_info)
    bit = get_betrayal_rival_relationship_bit()
    if observer is None or rival is None or bit is None:
        return False
    try:
        return bool(observer.relationship_tracker.has_bit(rival.sim_id, bit))
    except Exception:
        log_exception(
            "betrayal rival bit test failed observer={} rival={}".format(
                getattr(observer, "sim_id", None),
                getattr(rival, "sim_id", None),
            )
        )
        return False


def ensure_betrayal_rival_relationship_bit(
    observer_sim_or_info,
    rival_sim_or_info,
):
    """Project confirmed observer knowledge as one visible directed bit."""
    observer = get_sim_info(observer_sim_or_info)
    rival = get_sim_info(rival_sim_or_info)
    bit = get_betrayal_rival_relationship_bit()
    if (
        observer is None
        or rival is None
        or bit is None
        or observer.sim_id == rival.sim_id
    ):
        return False
    try:
        already_present = has_betrayal_rival_relationship_bit(observer, rival)
        if not already_present:
            observer.relationship_tracker.add_relationship_bit(
                rival.sim_id,
                bit,
                force_add=True,
                allow_readdition=True,
            )
            log(
                "betrayal rival relationship bit added observer={} rival={}",
                observer.sim_id,
                rival.sim_id,
            )
        observer.relationship_tracker.send_relationship_info(
            target_sim_id=rival.sim_id
        )
        return True
    except Exception:
        log_exception(
            "betrayal rival relationship bit add failed observer={} rival={}".format(
                observer.sim_id,
                rival.sim_id,
            )
        )
        return False


def project_betrayal_rival_relationship_bit(report):
    """Mirror a newly confirmed betrayal report into the EA relationship UI."""
    try:
        from fgeh_cheatingharder_betrayal_memory_rules import (
            betrayal_rival_marker_edge,
        )

        edge = betrayal_rival_marker_edge(report.event, report.beliefs)
        if edge is None:
            return False
        return ensure_betrayal_rival_relationship_bit(edge[0], edge[1])
    except Exception:
        log_exception("betrayal rival relationship bit projection failed")
        return False


def reconcile_betrayal_rival_relationship_bits():
    """Backfill visible rival markers from persisted confirmed knowledge."""
    try:
        from fgeh_cheatingharder_betrayal_memory_rules import (
            betrayal_rival_marker_edge,
        )
        from fgeh_cheatingharder_domain import EventType
        from fgeh_cheatingharder_memory_runtime import get_memory_service

        store = get_memory_service().store
        manager = services.sim_info_manager()
        restored = 0
        missing_sims = 0
        projected_edges = set()
        for event_type in (
            EventType.CAUGHT_CHEATING,
            EventType.ROMANTIC_BOUNDARY_DISCOVERED,
        ):
            for event in store.events_for_type(event_type):
                beliefs = []
                for claim in store.claims_for_event(event.event_id):
                    beliefs.extend(store.beliefs_for_claim(claim.claim_id))
                edge = betrayal_rival_marker_edge(event, beliefs)
                if edge is None or edge in projected_edges:
                    continue
                projected_edges.add(edge)
                observer = manager.get(int(edge[0]))
                rival = manager.get(int(edge[1]))
                if observer is None or rival is None:
                    missing_sims += 1
                    continue
                if ensure_betrayal_rival_relationship_bit(observer, rival):
                    restored += 1
        log(
            "betrayal rival bit reconciliation complete restored={} missing_sims={}",
            restored,
            missing_sims,
        )
        return restored
    except Exception:
        log_exception("betrayal rival relationship bit reconciliation failed")
        return 0


def start_check_in_cooldown(observer_sim_or_info, target_sim_or_info):
    observer = get_sim_info(observer_sim_or_info)
    target = get_sim_info(target_sim_or_info)
    bit = get_check_in_cooldown_bit()
    if observer is None or target is None or bit is None:
        return False
    try:
        observer.relationship_tracker.add_relationship_bit(
            target.sim_id,
            bit,
            allow_readdition=True,
        )
        log(
            "persistent check-in cooldown started observer={} target={} minutes={}",
            observer.sim_id,
            target.sim_id,
            settings.CHECK_IN_COOLDOWN_SIM_MINUTES,
        )
        return True
    except Exception:
        log_exception("check-in cooldown add failed")
        return False


def get_claim_observers_for_target(target_sim_or_info):
    """Return traited Sims that have a directed claim on the target."""
    target = get_sim_info(target_sim_or_info)
    if target is None:
        return ()
    try:
        observers = []
        for observer in services.sim_info_manager().get_all():
            if observer.sim_id == target.sim_id or not is_enabled(observer):
                continue
            if has_claim(observer, target):
                observers.append(observer)
        return tuple(observers)
    except Exception:
        log_exception("claim observer lookup failed target={}".format(getattr(target, "sim_id", None)))
        return ()


def has_multiple_romantic_relationships(observer_sim_or_info, exclude_sim_or_info=None):
    """Return True when the Sim has positive romance with another Sim."""
    observer = get_sim_info(observer_sim_or_info)
    excluded = get_sim_info(exclude_sim_or_info)
    if observer is None:
        return False
    try:
        from relationships.relationship_track import RelationshipTrack

        relationships = services.relationship_service().get_all_sim_relationships(
            observer.sim_id,
        )
        for relationship in relationships:
            other_sim_id = relationship.get_other_sim_id(observer.sim_id)
            if excluded is not None and other_sim_id == excluded.sim_id:
                continue
            try:
                romance_score = relationship.get_track_score(
                    observer.sim_id,
                    RelationshipTrack.ROMANCE_TRACK,
                )
            except Exception:
                romance_score = 0
            if romance_score > 0:
                return True
    except Exception:
        log_exception(
            "multiple romance lookup failed observer={}".format(
                getattr(observer, "sim_id", None),
            )
        )
    return False


def _declined_claim_key(observer, target):
    return (getattr(observer, "sim_id", None), getattr(target, "sim_id", None))


def _claim_was_declined_recently(observer, target):
    key = _declined_claim_key(observer, target)
    expiry = _DECLINED_CLAIMS.get(key)
    if expiry is None:
        return False
    try:
        now = services.time_service().sim_now
        if now < expiry:
            return True
    except Exception:
        log_exception("claim decline cooldown lookup failed")
    _DECLINED_CLAIMS.pop(key, None)
    return False


def _remember_declined_claim(observer, target):
    try:
        expiry = services.time_service().sim_now + date_and_time.create_time_span(
            minutes=settings.CLAIM_CONFIRMATION_COOLDOWN_SIM_MINUTES,
        )
        _DECLINED_CLAIMS[_declined_claim_key(observer, target)] = expiry
        log(
            "claim decline remembered observer={} target={} cooldown_minutes={}",
            observer.sim_id,
            target.sim_id,
            settings.CLAIM_CONFIRMATION_COOLDOWN_SIM_MINUTES,
        )
    except Exception:
        log_exception("claim decline memory failed")


def request_claim(observer_sim_or_info, target_sim_or_info):
    """Create a claim, asking first when another romance already exists."""
    observer = get_sim_info(observer_sim_or_info)
    target = get_sim_info(target_sim_or_info)
    if observer is None or target is None:
        return False
    if has_claim(observer, target):
        log("claim skipped: already exists observer={} target={}", observer.sim_id, target.sim_id)
        return False
    if _claim_was_declined_recently(observer, target):
        log(
            "claim skipped: recent confirmation decline observer={} target={}",
            observer.sim_id,
            target.sim_id,
        )
        return False

    if has_multiple_romantic_relationships(observer, target):
        log(
            "multiple romance detected observer={} target={}",
            observer.sim_id,
            target.sim_id,
        )

        def _accept_claim():
            establish_claim(observer, target)

        def _decline_claim():
            _remember_declined_claim(observer, target)

        try:
            from fgeh_cheatingharder_confirmation import show_multiple_romance_confirmation

            if show_multiple_romance_confirmation(
                observer,
                target,
                _accept_claim,
                _decline_claim,
            ):
                return True
        except Exception:
            log_exception("claim confirmation import failed")

        # NPCs have no UI owner. Keep their autonomous route working instead of
        # silently blocking a claim that cannot be confirmed on screen.
        if observer.get_sim_instance() is None:
            log(
                "claim confirmation unavailable; accepting autonomous claim observer={} target={}",
                observer.sim_id,
                target.sim_id,
            )
            return establish_claim(observer, target)
        log(
            "claim confirmation unavailable; claim not created observer={} target={}",
            observer.sim_id,
            target.sim_id,
        )
        return False

    return establish_claim(observer, target)


def establish_claim(
    observer_sim_or_info,
    target_sim_or_info,
):
    observer = get_sim_info(observer_sim_or_info)
    target = get_sim_info(target_sim_or_info)
    bit = get_claim_relationship_bit()
    if observer is None or target is None or bit is None or observer.sim_id == target.sim_id:
        log(
            "claim skipped observer={} target={} bit_found={}",
            getattr(observer, "sim_id", None),
            getattr(target, "sim_id", None),
            bit is not None,
        )
        return False
    if has_claim(observer, target):
        log("claim skipped: already exists observer={} target={}", observer.sim_id, target.sim_id)
        return False
    try:
        observer.relationship_tracker.add_relationship_bit(
            target.sim_id,
            bit,
            allow_readdition=False,
        )
        log("claim established observer={} target={}", observer.sim_id, target.sim_id)
        try:
            from fgeh_cheatingharder_domain import EventType
            from fgeh_cheatingharder_event_center import publish

            publish(
                EventType.CLAIM_ESTABLISHED,
                source="claim_api",
                event_id="claim:{}:{}".format(observer.sim_id, target.sim_id),
                observer_id=observer.sim_id,
                partner_id=target.sim_id,
            )
        except Exception:
            log_exception("claim relationship event failed")
        try:
            from fgeh_cheatingharder_notification import show_claim_notification
            show_claim_notification(observer, target)
        except Exception:
            log_exception("claim notification import failed")
        return True
    except Exception:
        log_exception("claim add failed observer={} target={}".format(observer, target))
        return False


def remove_claim(observer_sim_or_info, target_sim_or_info):
    observer = get_sim_info(observer_sim_or_info)
    target = get_sim_info(target_sim_or_info)
    bit = get_claim_relationship_bit()
    if observer is None or target is None or bit is None:
        return False
    try:
        observer.relationship_tracker.remove_relationship_bit(target.sim_id, bit)
        log("claim removed observer={} target={}", observer.sim_id, target.sim_id)
        return True
    except Exception:
        log_exception("claim remove failed observer={} target={}".format(observer, target))
        return False


def get_claim_records():
    """Return the persisted one-way claims for all Sims with the trait."""
    try:
        manager = services.sim_info_manager()
        sim_infos = tuple(manager.get_all())
        records = []
        for observer in sim_infos:
            if not is_enabled(observer):
                continue
            for target in sim_infos:
                if observer.sim_id == target.sim_id:
                    continue
                if has_claim(observer, target):
                    records.append(
                        {
                            "observer_id": observer.sim_id,
                            "target_id": target.sim_id,
                            "observer": observer,
                            "target": target,
                        }
                    )
        return tuple(records)
    except Exception:
        log_exception("claim records lookup failed")
        return ()

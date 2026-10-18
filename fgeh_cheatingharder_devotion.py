"""Pure rules for extreme one-way devotion.

No Sims 4 imports belong here.  Game adapters provide ids and a bond lookup;
the policy returns an explainable decision that is unit-testable on desktop
Python.
"""


ATTACHMENT_FLOOR = 100.0
COMMITMENT_FLOOR = 100.0

# EA's queue sub-interaction heart icon:
# InGame/UI/Icons/InteractionQueueSubInteractions/
# icon_queuesubinteraction_romantic.png
ROMANTIC_QUEUE_ICON_INSTANCE = 0xD2DA0A0C5A0BC252

# EA jealousy broadcasters used by emotional, physical, kiss, WooHoo, legacy
# jealousy-trait, and witnessed-cheating romantic interactions.
JEALOUSY_BROADCASTER_IDS = frozenset(
    (
        0x12964,
        0x58843,
        0x1E93E,
        0x5BA88,
        0x12A92,
        0x1EA01,
        0x1F902,
    )
)

# EA applies this category tag to targeted insults, yelling, mocking, fights,
# and pack-specific mean socials.  Friendly disagreements do not carry it.
MEAN_INTERACTION_TAG_NAMES = frozenset(("interaction_mean",))


class DevotionConflictError(ValueError):
    pass


class RomanticPermission:

    ALLOW = "allow"
    BLOCK_ACTOR_DEVOTED_ELSEWHERE = "block_actor_devoted_elsewhere"
    BLOCK_TARGET_DEVOTED_ELSEWHERE = "block_target_devoted_elsewhere"
    BLOCK_ACTOR_MEAN_TO_BELOVED = "block_actor_mean_to_beloved"

    def __init__(
        self,
        allowed,
        reason=ALLOW,
        devoted_owner_id=None,
        beloved_id=None,
        actor_id=None,
        target_id=None,
    ):
        self.allowed = bool(allowed)
        self.reason = str(reason)
        self.devoted_owner_id = (
            None if devoted_owner_id is None else int(devoted_owner_id)
        )
        self.beloved_id = None if beloved_id is None else int(beloved_id)
        self.actor_id = None if actor_id is None else int(actor_id)
        self.target_id = None if target_id is None else int(target_id)

    def to_data(self):
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "devoted_owner_id": self.devoted_owner_id,
            "beloved_id": self.beloved_id,
            "actor_id": self.actor_id,
            "target_id": self.target_id,
        }


def romantic_interaction_metadata_reason(
    icon_instance=None,
    broadcaster_ids=(),
):
    """Return the strongest EA-native signal that marks romantic behavior."""
    try:
        if int(icon_instance) == ROMANTIC_QUEUE_ICON_INSTANCE:
            return "romantic_queue_icon"
    except (TypeError, ValueError):
        pass
    for broadcaster_id in broadcaster_ids:
        try:
            broadcaster_id = int(broadcaster_id)
        except (TypeError, ValueError):
            continue
        if broadcaster_id in JEALOUSY_BROADCASTER_IDS:
            return "ea_jealousy_broadcaster"
    return None


def mean_interaction_metadata_reason(tag_values=()):
    """Return EA's stable mean-social signal without inspecting display names."""
    normalized = set()
    for value in tag_values or ():
        name = getattr(value, "name", None)
        if name is None and isinstance(value, str):
            name = value
        if name:
            normalized.add(str(name).strip().lower())
    if normalized.intersection(MEAN_INTERACTION_TAG_NAMES):
        return "ea_mean_interaction_tag"
    return None


def evaluate_mean_pair(actor_id, target_id, bond_lookup):
    """Block only a devoted owner's mean action toward their own beloved."""
    actor_id = int(actor_id)
    target_id = int(target_id)
    if actor_id <= 0 or target_id <= 0 or actor_id == target_id:
        return RomanticPermission(
            True,
            actor_id=actor_id,
            target_id=target_id,
        )
    actor_bond = bond_lookup(actor_id)
    if actor_bond is not None and actor_bond.beloved_id == target_id:
        return RomanticPermission(
            False,
            RomanticPermission.BLOCK_ACTOR_MEAN_TO_BELOVED,
            devoted_owner_id=actor_id,
            beloved_id=target_id,
            actor_id=actor_id,
            target_id=target_id,
        )
    return RomanticPermission(
        True,
        actor_id=actor_id,
        target_id=target_id,
    )


def evaluate_romantic_pair(actor_id, target_id, bond_lookup):
    """Return whether a two-Sim romantic attempt respects both one-way bonds."""
    actor_id = int(actor_id)
    target_id = int(target_id)
    if actor_id <= 0 or target_id <= 0 or actor_id == target_id:
        return RomanticPermission(
            True,
            actor_id=actor_id,
            target_id=target_id,
        )

    actor_bond = bond_lookup(actor_id)
    if actor_bond is not None and actor_bond.beloved_id != target_id:
        return RomanticPermission(
            False,
            RomanticPermission.BLOCK_ACTOR_DEVOTED_ELSEWHERE,
            devoted_owner_id=actor_id,
            beloved_id=actor_bond.beloved_id,
            actor_id=actor_id,
            target_id=target_id,
        )

    target_bond = bond_lookup(target_id)
    if target_bond is not None and target_bond.beloved_id != actor_id:
        return RomanticPermission(
            False,
            RomanticPermission.BLOCK_TARGET_DEVOTED_ELSEWHERE,
            devoted_owner_id=target_id,
            beloved_id=target_bond.beloved_id,
            actor_id=actor_id,
            target_id=target_id,
        )

    return RomanticPermission(
        True,
        actor_id=actor_id,
        target_id=target_id,
    )


def evaluate_romance_value_change(
    sim_id_a,
    sim_id_b,
    current_value,
    requested_value,
    bond_lookup,
):
    """Guard only positive romance growth; decreases are always permitted.

    Relationship tracks are bidirectional, so the two ids describe a pair
    rather than a reliable initiator/target direction.  The pair policy checks
    both one-way devotion bonds and is therefore safe at this deepest layer.
    """
    try:
        current_value = float(current_value)
        requested_value = float(requested_value)
    except (TypeError, ValueError):
        return RomanticPermission(
            True,
            actor_id=sim_id_a,
            target_id=sim_id_b,
        )
    if requested_value <= current_value:
        return RomanticPermission(
            True,
            actor_id=sim_id_a,
            target_id=sim_id_b,
        )
    return evaluate_romantic_pair(
        sim_id_a,
        sim_id_b,
        bond_lookup,
    )


def evaluate_intimate_group(participant_ids, bond_lookup):
    """Reject a multi-Sim intimate group when any pair violates devotion."""
    unique_ids = []
    seen = set()
    for participant_id in participant_ids:
        try:
            participant_id = int(participant_id)
        except (TypeError, ValueError):
            continue
        if participant_id <= 0 or participant_id in seen:
            continue
        seen.add(participant_id)
        unique_ids.append(participant_id)

    for first_index, actor_id in enumerate(unique_ids):
        for target_id in unique_ids[first_index + 1:]:
            permission = evaluate_romantic_pair(
                actor_id,
                target_id,
                bond_lookup,
            )
            if not permission.allowed:
                return permission
    return RomanticPermission(True)


def build_devotion_floor_deltas(
    store,
    owner_id,
    beloved_id,
    event_id=None,
):
    """Build current-state constraints without directly mutating the store."""
    bond = store.get_devotion_bond(owner_id)
    if bond is None or bond.beloved_id != int(beloved_id):
        return ()
    state = store.get_directed_state(owner_id, beloved_id)
    from fgeh_cheatingharder_memory_models import (
        DirectedStateDelta,
        StateChangeMode,
    )

    changes = []
    for dimension, floor in (
        ("attachment", ATTACHMENT_FLOOR),
        ("commitment", COMMITMENT_FLOOR),
    ):
        if (
            state is not None
            and state.initialized.get(dimension, False)
            and state.get(dimension) >= floor
        ):
            continue
        changes.append(
            DirectedStateDelta(
                owner_id,
                beloved_id,
                dimension,
                floor,
                "permanent_only_beloved_floor",
                mode=StateChangeMode.SET,
                event_id=event_id,
            )
        )
    return tuple(changes)


def devotion_state_constraint(event, observer_id, partner_id, store):
    return build_devotion_floor_deltas(
        store,
        observer_id,
        partner_id,
        event_id=getattr(event, "event_id", None),
    )

"""Pure classification of lower-layer breakup requests.

An InteractionSource describes how an interaction entered the queue.  It is
not, by itself, proof that the player deliberately chose to end a
relationship.  In particular, third-party scripted reactions may use
SCRIPT_WITH_USER_INTENT.

Only a known breakup affordance selected from the pie menu is recognized as a
player-authored proposal.  It still enters the negotiation state machine; a
recipient acceptance or a second-stage player insistence grants the separate
final authority.  Autonomous and scripted requests remain model-supervised.
"""


class BreakupRequestOrigin:
    PLAYER_INTERACTION = "player_interaction"
    EA_AUTONOMY = "ea_autonomy"
    EA_SCRIPTED = "ea_scripted"
    EA_RELATIONSHIP_LOOT = "ea_relationship_loot"


class BreakupRequestClassification:

    def __init__(
        self,
        origin,
        intentional=None,
        manual_breakup_authorized=False,
    ):
        self.origin = str(origin)
        self.intentional = (
            None if intentional is None else bool(intentional)
        )
        self.manual_breakup_authorized = bool(
            manual_breakup_authorized
        )


def _same_source(first, second):
    if first is None or second is None:
        return False
    if first is second or first == second:
        return True
    try:
        return int(first) == int(second)
    except (TypeError, ValueError):
        return False


def _normalized_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def classify_breakup_request(
    source,
    affordance_id=None,
    pie_menu_source=None,
    autonomy_source=None,
    manual_breakup_affordance_ids=(),
):
    """Classify evidence without granting authority from a source hint alone."""
    normalized_affordance_id = _normalized_id(affordance_id)
    manual_ids = frozenset(
        normalized
        for normalized in (
            _normalized_id(value)
            for value in tuple(manual_breakup_affordance_ids or ())
        )
        if normalized is not None
    )
    is_explicit_player_breakup = (
        _same_source(source, pie_menu_source)
        and normalized_affordance_id in manual_ids
    )
    if is_explicit_player_breakup:
        return BreakupRequestClassification(
            BreakupRequestOrigin.PLAYER_INTERACTION,
            intentional=True,
            manual_breakup_authorized=True,
        )
    if _same_source(source, autonomy_source):
        return BreakupRequestClassification(
            BreakupRequestOrigin.EA_AUTONOMY,
            intentional=True,
        )
    if source is not None:
        return BreakupRequestClassification(
            BreakupRequestOrigin.EA_SCRIPTED,
            intentional=None,
        )
    return BreakupRequestClassification(
        BreakupRequestOrigin.EA_RELATIONSHIP_LOOT,
        intentional=None,
    )

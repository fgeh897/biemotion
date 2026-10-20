"""Pure authorization gate for EA-owned relationship consequences.

EA remains an event/signal source.  The relationship model decides whether a
semantic effect family may reach the game state.  Concrete EA resources are
registered in a catalog so adapters do not scatter resource ids through their
control flow.
"""

from collections import deque


class EAEffectFamily:
    BREAKUP = "breakup"


class EAEffectKind:
    RELATIONSHIP_BIT = "relationship_bit"
    BUFF = "buff"
    OFFICIAL_RELATIONSHIP = "official_relationship"


class EAEffectCatalog:
    """Map concrete EA resources to a semantic relationship-effect family."""

    def __init__(self):
        self._rules = []

    def register(
        self,
        family,
        kind,
        resource_ids=(),
        name_markers=(),
    ):
        rule = {
            "family": str(family),
            "kind": str(kind),
            "resource_ids": frozenset(
                int(value) for value in tuple(resource_ids or ())
            ),
            "name_markers": tuple(
                str(value).strip().lower()
                for value in tuple(name_markers or ())
                if str(value).strip()
            ),
        }
        self._rules.append(rule)
        return rule

    def family_for(self, kind, resource_id=None, resource_name=None):
        kind = str(kind)
        try:
            resource_id = int(resource_id)
        except (TypeError, ValueError):
            resource_id = None
        resource_name = str(resource_name or "").strip().lower()
        for rule in self._rules:
            if rule["kind"] != kind:
                continue
            if resource_id in rule["resource_ids"]:
                return rule["family"]
            if any(
                marker in resource_name
                for marker in rule["name_markers"]
            ):
                return rule["family"]
        return None


class EAEffectBlockReceipt:

    def __init__(
        self,
        family,
        first_sim_id,
        second_sim_id,
        occurred_ticks=None,
        reason="relationship_policy_denied",
        evidence=None,
    ):
        self.family = str(family)
        self.pair_key = tuple(sorted((
            int(first_sim_id),
            int(second_sim_id),
        )))
        self.occurred_ticks = (
            None if occurred_ticks is None else int(occurred_ticks)
        )
        self.reason = str(reason)
        self.evidence = dict(evidence or {})


class EAEffectGate:
    """Hold short-lived denials for one semantic relationship transaction."""

    def __init__(self, capacity=64):
        self.capacity = max(1, int(capacity))
        self._receipts = {}
        self._order = deque()

    @staticmethod
    def _key(family, first_sim_id, second_sim_id):
        try:
            first_sim_id = int(first_sim_id)
            second_sim_id = int(second_sim_id)
        except (TypeError, ValueError):
            return None
        if (
            first_sim_id <= 0
            or second_sim_id <= 0
            or first_sim_id == second_sim_id
        ):
            return None
        return (
            str(family),
            tuple(sorted((first_sim_id, second_sim_id))),
        )

    def clear(self):
        self._receipts.clear()
        self._order.clear()

    def release(self, family, first_sim_id, second_sim_id):
        """Remove one pair-specific denial after explicit authorization."""
        key = self._key(family, first_sim_id, second_sim_id)
        if key is None:
            return None
        receipt = self._receipts.pop(key, None)
        try:
            self._order.remove(key)
        except ValueError:
            pass
        return receipt

    def deny(
        self,
        family,
        first_sim_id,
        second_sim_id,
        occurred_ticks=None,
        reason="relationship_policy_denied",
        evidence=None,
    ):
        key = self._key(family, first_sim_id, second_sim_id)
        if key is None:
            return None
        receipt = EAEffectBlockReceipt(
            family,
            first_sim_id,
            second_sim_id,
            occurred_ticks=occurred_ticks,
            reason=reason,
            evidence=evidence,
        )
        self._receipts[key] = receipt
        try:
            self._order.remove(key)
        except ValueError:
            pass
        self._order.append(key)
        while len(self._order) > self.capacity:
            expired = self._order.popleft()
            self._receipts.pop(expired, None)
        return receipt

    def blocked_receipt(
        self,
        family,
        first_sim_id,
        second_sim_id,
        occurred_ticks=None,
        max_age_ticks=None,
    ):
        key = self._key(family, first_sim_id, second_sim_id)
        if key is None:
            return None
        receipt = self._receipts.get(key)
        if receipt is None:
            return None
        if (
            occurred_ticks is not None
            and receipt.occurred_ticks is not None
            and max_age_ticks is not None
        ):
            age = int(occurred_ticks) - receipt.occurred_ticks
            if age < 0 or age > int(max_age_ticks):
                self._receipts.pop(key, None)
                try:
                    self._order.remove(key)
                except ValueError:
                    pass
                return None
        return receipt


EA_RELATIONSHIP_EFFECTS = EAEffectCatalog()
EA_AUTO_BREAKUP_WARNING_RELATIONSHIP_BIT_IDS = frozenset((
    363150,  # EP21 auto-romance breakup warning stage 1
    363151,  # EP21 auto-romance breakup warning stage 2
))
EA_AUTO_BREAKUP_TRANSITION_RELATIONSHIP_BIT_IDS = frozenset((
    77634,  # romanticCombo_JustGoodFriends
    15836,  # romanticCombo_ItsVeryComplicated
))


def is_auto_breakup_warning_relationship_bit(
    resource_id=None,
    resource_name=None,
):
    try:
        resource_id = int(resource_id)
    except (TypeError, ValueError):
        resource_id = None
    resource_name = str(resource_name or "").strip().lower()
    return (
        resource_id in EA_AUTO_BREAKUP_WARNING_RELATIONSHIP_BIT_IDS
        or "shorttermbits_autoinitromance_warning" in resource_name
    )


def is_auto_breakup_transition_relationship_bit(
    resource_id=None,
    resource_name=None,
):
    """Classify only the relationship-status bits observed in EA auto breakup."""
    try:
        resource_id = int(resource_id)
    except (TypeError, ValueError):
        resource_id = None
    resource_name = str(resource_name or "").strip().lower()
    return (
        resource_id in EA_AUTO_BREAKUP_TRANSITION_RELATIONSHIP_BIT_IDS
        or "romanticcombo_justgoodfriends" in resource_name
        or "romanticcombo_itsverycomplicated" in resource_name
    )


EA_RELATIONSHIP_EFFECTS.register(
    EAEffectFamily.BREAKUP,
    EAEffectKind.RELATIONSHIP_BIT,
    resource_ids=(
        15811,   # romantic-Broken_Up
        15812,   # reverse/directed romantic-Broken_Up
        97332,   # shortterm_JustBrokeUpOrDivorced
        246538,  # short-term breakup bitterness marker
        *EA_AUTO_BREAKUP_WARNING_RELATIONSHIP_BIT_IDS,
        *EA_AUTO_BREAKUP_TRANSITION_RELATIONSHIP_BIT_IDS,
        412859,  # grief target
        422961,  # grief trigger: breakup
    ),
    name_markers=(
        "romantic-broken_up",
        "justbrokeupordivorced",
        "st_breakup",
        "shorttermbits_autoinitromance_warning",
        "romanticcombo_justgoodfriends",
        "romanticcombo_itsverycomplicated",
        "grieftrigger_breakup",
    ),
)

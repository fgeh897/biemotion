"""Pure upper-layer policy for external breakup requests.

EA and third-party systems may request an official breakup.  This policy does
not inspect game objects; it decides whether that lower-layer request is
authorized by the character's already-computed relationship behavior.
"""


class BreakupPolicyReason:
    PLAYER_OVERRIDE = "player_override"
    UPPER_LAYER_AUTHORIZED = "upper_layer_authorized"
    NO_PROTECTIVE_POLICY = "no_protective_policy"
    BREAKUP_INTENT_SELECTED = "breakup_intent_selected"
    BREAKUP_GATE_BLOCKED = "breakup_gate_blocked"
    DIFFERENT_INTENT_SELECTED = "different_intent_selected"
    NO_RECENT_DECISION = "no_recent_upper_layer_decision"


EA_BROKEN_UP_RELATIONSHIP_BIT_IDS = frozenset((15811, 15812))


class BreakupPolicyDecision:

    def __init__(
        self,
        allowed,
        reason,
        origin,
        permanently_devoted=False,
        selected_intent=None,
        breakup_candidate=None,
        decision_reference=None,
    ):
        self.allowed = bool(allowed)
        self.reason = str(reason)
        self.origin = str(origin or "unknown")
        self.permanently_devoted = bool(permanently_devoted)
        self.selected_intent = (
            None if selected_intent is None else str(selected_intent)
        )
        self.breakup_candidate = dict(breakup_candidate or {})
        self.decision_reference = (
            None
            if decision_reference is None
            else str(decision_reference)
        )

    def as_dict(self):
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "origin": self.origin,
            "permanently_devoted": self.permanently_devoted,
            "selected_intent": self.selected_intent,
            "breakup_candidate": dict(self.breakup_candidate),
            "decision_reference": self.decision_reference,
        }


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def is_breakup_bit_addition(operation, bit_id=None, bit_name=None):
    """Return whether one normalized relationship-bit operation starts a breakup."""
    operation_name = str(operation or "").strip().lower()
    is_add = operation_name in ("1", "add")
    try:
        normalized_bit_id = int(bit_id)
    except (TypeError, ValueError):
        normalized_bit_id = None
    normalized_bit_name = str(bit_name or "").strip().lower()
    return is_add and (
        normalized_bit_id in EA_BROKEN_UP_RELATIONSHIP_BIT_IDS
        or "romantic-broken_up" in normalized_bit_name
    )


def evaluate_external_breakup_request(
    origin,
    managed_by_project=False,
    permanently_devoted=False,
    selected_intent=None,
    breakup_candidate=None,
    decision_reference=None,
    upper_layer_authorized=False,
):
    """Return whether an external request may end the official relationship."""
    origin = str(origin or "unknown")
    candidate = dict(breakup_candidate or {})
    if origin == "player_interaction":
        return BreakupPolicyDecision(
            True,
            BreakupPolicyReason.PLAYER_OVERRIDE,
            origin,
            permanently_devoted=permanently_devoted,
            selected_intent=selected_intent,
            breakup_candidate=candidate,
            decision_reference=decision_reference,
        )
    if upper_layer_authorized:
        return BreakupPolicyDecision(
            True,
            BreakupPolicyReason.UPPER_LAYER_AUTHORIZED,
            origin,
            permanently_devoted=permanently_devoted,
            selected_intent=selected_intent,
            breakup_candidate=candidate,
            decision_reference=decision_reference,
        )
    if not managed_by_project:
        return BreakupPolicyDecision(
            True,
            BreakupPolicyReason.NO_PROTECTIVE_POLICY,
            origin,
            permanently_devoted=False,
            selected_intent=selected_intent,
            breakup_candidate=candidate,
            decision_reference=decision_reference,
        )
    if not candidate:
        return BreakupPolicyDecision(
            False,
            BreakupPolicyReason.NO_RECENT_DECISION,
            origin,
            permanently_devoted=permanently_devoted,
            selected_intent=selected_intent,
            decision_reference=decision_reference,
        )
    if (
        not bool(candidate.get("eligible", False))
        or _number(candidate.get("score", 0.0)) <= 0.0
    ):
        return BreakupPolicyDecision(
            False,
            BreakupPolicyReason.BREAKUP_GATE_BLOCKED,
            origin,
            permanently_devoted=permanently_devoted,
            selected_intent=selected_intent,
            breakup_candidate=candidate,
            decision_reference=decision_reference,
        )
    if str(selected_intent) != "break_up":
        return BreakupPolicyDecision(
            False,
            BreakupPolicyReason.DIFFERENT_INTENT_SELECTED,
            origin,
            permanently_devoted=permanently_devoted,
            selected_intent=selected_intent,
            breakup_candidate=candidate,
            decision_reference=decision_reference,
        )
    return BreakupPolicyDecision(
        True,
        BreakupPolicyReason.BREAKUP_INTENT_SELECTED,
        origin,
        permanently_devoted=permanently_devoted,
        selected_intent=selected_intent,
        breakup_candidate=candidate,
        decision_reference=decision_reference,
    )

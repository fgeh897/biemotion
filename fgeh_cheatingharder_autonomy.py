"""Pure admission policy for memory-driven autonomous actions.

The romantic-memory pipeline may propose many kinds of behavior.  This module
keeps the boundary explicit: a remembered opportunity is only a proposal, and
only a separately registered, enabled action may reach the Sims runtime.
"""


class AutonomousAdmissionStatus:
    ADMITTED = "admitted"
    EXECUTION_DISABLED = "execution_disabled"
    INTENT_MISSING = "intent_missing"
    ACTION_UNREGISTERED = "action_unregistered"
    COOLDOWN_ACTIVE = "cooldown_active"
    TARGET_PROVENANCE_INVALID = "target_provenance_invalid"


class AutonomousAdmission:

    def __init__(
        self,
        admitted,
        status,
        opportunity_type,
        intent,
        observer_id,
        partner_id,
        event_id=None,
    ):
        self.admitted = bool(admitted)
        self.status = str(status)
        self.opportunity_type = str(opportunity_type)
        self.intent = None if intent is None else str(intent)
        self.observer_id = int(observer_id)
        self.partner_id = int(partner_id)
        self.event_id = None if event_id is None else str(event_id)

    @property
    def action_key(self):
        if self.intent is None:
            return None
        return (self.opportunity_type, self.intent)

    def to_data(self):
        return {
            "admitted": self.admitted,
            "status": self.status,
            "opportunity_type": self.opportunity_type,
            "intent": self.intent,
            "observer_id": self.observer_id,
            "partner_id": self.partner_id,
            "event_id": self.event_id,
        }


def admit_memory_opportunity(
    opportunity,
    registered_action_keys,
    cooldown_active=False,
    target_provenance_valid=True,
):
    """Return an explainable admission decision without importing game APIs."""
    context = dict(getattr(opportunity, "context", {}) or {})
    opportunity_type = str(getattr(opportunity, "opportunity_type", ""))
    selected_intent = context.get("selected_intent")
    common = {
        "opportunity_type": opportunity_type,
        "intent": selected_intent,
        "observer_id": getattr(opportunity, "observer_id"),
        "partner_id": getattr(opportunity, "partner_id"),
        "event_id": getattr(opportunity, "event_id", None),
    }
    if not bool(context.get("execution_enabled", False)):
        return AutonomousAdmission(
            False,
            AutonomousAdmissionStatus.EXECUTION_DISABLED,
            **common
        )
    if not selected_intent:
        return AutonomousAdmission(
            False,
            AutonomousAdmissionStatus.INTENT_MISSING,
            **common
        )
    action_key = (opportunity_type, str(selected_intent))
    if action_key not in set(registered_action_keys):
        return AutonomousAdmission(
            False,
            AutonomousAdmissionStatus.ACTION_UNREGISTERED,
            **common
        )
    if not target_provenance_valid:
        return AutonomousAdmission(
            False,
            AutonomousAdmissionStatus.TARGET_PROVENANCE_INVALID,
            **common
        )
    if cooldown_active:
        return AutonomousAdmission(
            False,
            AutonomousAdmissionStatus.COOLDOWN_ACTIVE,
            **common
        )
    return AutonomousAdmission(
        True,
        AutonomousAdmissionStatus.ADMITTED,
        **common
    )

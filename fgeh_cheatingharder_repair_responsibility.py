"""Pure, registered responsibility resolution for relationship repair."""

from fgeh_cheatingharder_domain import EventType
from fgeh_cheatingharder_memory_models import ParticipantRole


class RepairResponsibilityDecision:

    def __init__(
        self,
        reconciliation_proposer_id,
        repair_requester_id,
        accountable_id,
        harmed_id,
        basis,
        confidence=0.0,
        confirmed=False,
        source_event_id=None,
    ):
        self.reconciliation_proposer_id = int(
            reconciliation_proposer_id
        )
        self.repair_requester_id = int(repair_requester_id)
        self.accountable_id = int(accountable_id)
        self.harmed_id = int(harmed_id)
        self.basis = str(basis)
        self.confidence = max(0.0, min(1.0, float(confidence)))
        self.confirmed = bool(confirmed)
        self.source_event_id = (
            None if source_event_id is None else str(source_event_id)
        )

    @property
    def requester_may_demand_repair(self):
        """Whether this decision can justify a blame-bearing repair demand.

        The current minimal requirement is a sincere apology.  It must never
        be assigned from the zero-confidence fallback merely because one Sim
        happened to request reconciliation.  Unknown responsibility can still
        lead to refusal or to future neutral rebuilding requirements, but not
        to an admission of fault.
        """
        return (
            self.confirmed
            and self.confidence > 0.0
            and self.repair_requester_id == self.harmed_id
        )

    def to_data(self):
        return {
            "reconciliation_proposer_id": self.reconciliation_proposer_id,
            "repair_requester_id": self.repair_requester_id,
            "accountable_id": self.accountable_id,
            "harmed_id": self.harmed_id,
            "basis": self.basis,
            "confidence": self.confidence,
            "confirmed": self.confirmed,
            "source_event_id": self.source_event_id,
            "requester_may_demand_repair": (
                self.requester_may_demand_repair
            ),
        }


class RepairResponsibilityRule:

    def __init__(self, key, evaluator, priority=0):
        self.key = str(key)
        self.evaluator = evaluator
        self.priority = int(priority)

    def evaluate(self, events, proposer_id, recipient_id):
        return self.evaluator(events, proposer_id, recipient_id)


class RepairResponsibilityRegistry:

    def __init__(self):
        self._rules = {}

    def register(self, rule):
        if not isinstance(rule, RepairResponsibilityRule):
            raise TypeError("rule must be RepairResponsibilityRule")
        if rule.key in self._rules:
            raise ValueError(
                "Repair responsibility rule already registered: {}".format(
                    rule.key
                )
            )
        self._rules[rule.key] = rule
        return rule

    def rules(self):
        return tuple(
            sorted(
                self._rules.values(),
                key=lambda value: (-value.priority, value.key),
            )
        )

    def resolve(self, events, proposer_id, recipient_id):
        events = tuple(events or ())
        for rule in self.rules():
            decision = rule.evaluate(events, proposer_id, recipient_id)
            if decision is not None:
                return decision
        return RepairResponsibilityDecision(
            proposer_id,
            recipient_id,
            proposer_id,
            recipient_id,
            basis="reconciliation_proposer_provisional",
            confidence=0.0,
            confirmed=False,
        )


def _single(event, role):
    values = event.participants_for(role)
    return values[0] if values else None


def _latest_witnessed_betrayal(events, proposer_id, recipient_id):
    pair = {int(proposer_id), int(recipient_id)}
    for event in sorted(
        tuple(events or ()),
        key=lambda value: value.sequence,
        reverse=True,
    ):
        if (
            event.event_type == EventType.RECONCILIATION_RESOLVED
            and event.payload.get("official_partnership_restored")
        ):
            break
        if event.event_type != EventType.CAUGHT_CHEATING:
            continue
        harmed_id = _single(event, ParticipantRole.OBSERVER)
        accountable_id = _single(event, ParticipantRole.PARTNER)
        if (
            harmed_id is None
            or accountable_id is None
            or {harmed_id, accountable_id} != pair
        ):
            continue
        return RepairResponsibilityDecision(
            proposer_id,
            recipient_id,
            accountable_id,
            harmed_id,
            basis="latest_witnessed_betrayal",
            confidence=1.0,
            confirmed=True,
            source_event_id=event.event_id,
        )
    return None


REPAIR_RESPONSIBILITY_RULES = RepairResponsibilityRegistry()
REPAIR_RESPONSIBILITY_RULES.register(
    RepairResponsibilityRule(
        "core.repair_responsibility.latest_witnessed_betrayal.v1",
        _latest_witnessed_betrayal,
        priority=100,
    )
)


def resolve_repair_responsibility(events, proposer_id, recipient_id):
    return REPAIR_RESPONSIBILITY_RULES.resolve(
        events,
        proposer_id,
        recipient_id,
    )

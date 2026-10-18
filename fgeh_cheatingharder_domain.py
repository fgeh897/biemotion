"""Pure domain objects for directed relationship behavior.

This module deliberately has no Sims 4 imports.  It is the stable boundary
between game adapters and the decision pipeline, and can be tested on the
developer's normal Python runtime.
"""

from collections import deque


class EventType:
    CLAIM_ESTABLISHED = "claim_established"
    DEVOTION_BOND_CREATED = "devotion_bond_created"
    DEVOTION_LONGING_STARTED = "devotion_longing_started"
    DEVOTION_CONTACT_SOUGHT = "devotion_contact_sought"
    DEVOTION_CONTACT_COMPLETED = "devotion_contact_completed"
    OUTSIDE_ROMANCE_REJECTED = "outside_romance_rejected"
    ROMANCE_COMPLETED = "romance_completed"
    BREAKUP_PRESSURE = "breakup_pressure"
    BREAKUP_PROPOSED = "breakup_proposed"
    BREAKUP_RESPONSE = "breakup_response"
    BREAKUP_NEGOTIATION_RESOLVED = "breakup_negotiation_resolved"
    BREAKUP_DECLARED = "breakup_declared"
    BREAKUP_COMPLETED = "breakup_completed"
    RECONCILIATION_PROPOSED = "reconciliation_proposed"
    RECONCILIATION_RESPONSE = "reconciliation_response"
    RECONCILIATION_RESOLVED = "reconciliation_resolved"
    REPAIR_ACTION_RESOLVED = "repair_action_resolved"
    REACTION_EXPRESSION_SELECTED = "reaction_expression_selected"
    AFFAIR_SECRET_CREATED = "affair_secret_created"
    AFFAIR_SECRET_DISCOVERED = "affair_secret_discovered"
    CAUGHT_CHEATING = "caught_cheating"
    ROMANTIC_BOUNDARY_DISCOVERED = "romantic_boundary_discovered"
    ROMANTIC_KNOWLEDGE_EVIDENCE_UPDATED = (
        "romantic_knowledge_evidence_updated"
    )
    AUTONOMOUS_ACTION_RESOLVED = "autonomous_action_resolved"
    RELATIONSHIP_REEVALUATION = "relationship_reevaluation"
    BEHAVIOR_EXECUTED = "behavior_executed"
    VISIT_ARRIVED = "visit_arrived"
    VISIT_FINISHED = "visit_finished"


class OpportunityType:
    RELATIONSHIP_RESPONSE = "relationship_response"
    DEVOTION_LONGING = "devotion_longing"


class IntentType:
    WAIT = "wait"
    REPAIR_RELATIONSHIP = "repair_relationship"
    BREAK_UP = "break_up"
    VISIT_UNANNOUNCED = "visit_unannounced"
    LONGING_WAIT = "longing_wait"
    SEEK_BELOVED = "seek_beloved"
    CRISIS_SEEK_REASSURANCE = "crisis_seek_reassurance"
    CRISIS_GIVE_SPACE = "crisis_give_space"
    CRISIS_REPEAT_BREAKUP = "crisis_repeat_breakup"


class RelationshipEvent:

    def __init__(
        self,
        event_type,
        event_id,
        source,
        actor_id=None,
        target_id=None,
        observer_id=None,
        partner_id=None,
        rival_id=None,
        payload=None,
    ):
        self.event_type = event_type
        self.event_id = str(event_id)
        self.source = str(source)
        self.actor_id = actor_id
        self.target_id = target_id
        self.observer_id = observer_id
        self.partner_id = partner_id
        self.rival_id = rival_id
        self.payload = dict(payload or {})

    @property
    def directed_edge(self):
        if self.observer_id is None or self.partner_id is None:
            return None
        return (self.observer_id, self.partner_id)

    def __repr__(self):
        return (
            "RelationshipEvent(type={!r}, id={!r}, source={!r}, edge={!r})"
        ).format(self.event_type, self.event_id, self.source, self.directed_edge)


class DirectedState:
    DIMENSIONS = (
        "attachment",
        "trust",
        "exclusivity",
        "commitment",
        "boundary",
    )

    def __init__(self, observer_id, partner_id, values=None, persisted=None):
        values = dict(values or {})
        persisted = dict(persisted or {})
        self.observer_id = observer_id
        self.partner_id = partner_id
        self.values = {
            dimension: float(values.get(dimension, 0.0))
            for dimension in self.DIMENSIONS
        }
        self.persisted = {
            dimension: bool(persisted.get(dimension, False))
            for dimension in self.DIMENSIONS
        }

    def get(self, dimension, default=0.0):
        return float(self.values.get(dimension, default))

    def as_dict(self):
        return dict(self.values)


class StateChange:

    ADD = "add"
    SET_IF_MISSING = "set_if_missing"

    def __init__(self, dimension, value, reason, mode=ADD):
        self.dimension = str(dimension)
        self.value = float(value)
        self.reason = str(reason)
        self.mode = str(mode)


class BehaviorOpportunity:

    def __init__(
        self,
        observer_id,
        partner_id,
        reason,
        urgency=0.0,
        opportunity_type=OpportunityType.RELATIONSHIP_RESPONSE,
        context=None,
    ):
        self.observer_id = observer_id
        self.partner_id = partner_id
        self.reason = str(reason)
        self.urgency = float(urgency)
        self.opportunity_type = opportunity_type
        self.context = dict(context or {})


class BehaviorCandidate:

    def __init__(self, intent_type, score, terms=None, eligible=True, blockers=None):
        self.intent_type = str(intent_type)
        self.score = max(0.0, float(score))
        self.terms = tuple(terms or ())
        self.eligible = bool(eligible)
        self.blockers = tuple(blockers or ())

    def as_dict(self):
        return {
            "intent": self.intent_type,
            "score": self.score,
            "terms": tuple(self.terms),
            "eligible": self.eligible,
            "blockers": tuple(self.blockers),
        }


class BehaviorIntent:

    def __init__(self, intent_type, observer_id, partner_id, reason, context=None):
        self.intent_type = str(intent_type)
        self.observer_id = observer_id
        self.partner_id = partner_id
        self.reason = str(reason)
        self.context = dict(context or {})


class ExecutionResult:

    def __init__(self, accepted, status, details=None):
        self.accepted = bool(accepted)
        self.status = str(status)
        self.details = dict(details or {})


class DecisionRecord:

    def __init__(
        self,
        observer_id,
        partner_id,
        reason,
        state,
        candidates,
        roll,
        total_score,
        selected_intent,
    ):
        self.observer_id = observer_id
        self.partner_id = partner_id
        self.reason = str(reason)
        self.state = dict(state)
        self.candidates = tuple(candidates)
        self.roll = float(roll)
        self.total_score = float(total_score)
        self.selected_intent = selected_intent

    def as_dict(self):
        return {
            "observer_id": self.observer_id,
            "partner_id": self.partner_id,
            "reason": self.reason,
            "state": dict(self.state),
            "candidates": tuple(candidate.as_dict() for candidate in self.candidates),
            "roll": self.roll,
            "total_score": self.total_score,
            "selected": self.selected_intent,
        }


class EventIdWindow:
    """Bounded idempotency window for noisy game event adapters."""

    def __init__(self, capacity=256):
        self.capacity = max(1, int(capacity))
        self._ids = set()
        self._order = deque()

    def add(self, event_id):
        event_id = str(event_id)
        if event_id in self._ids:
            return False
        self._ids.add(event_id)
        self._order.append(event_id)
        while len(self._order) > self.capacity:
            self._ids.discard(self._order.popleft())
        return True

    def clear(self):
        self._ids.clear()
        self._order.clear()

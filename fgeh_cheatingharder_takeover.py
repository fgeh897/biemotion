"""Pure runtime ownership receipts for EA relationship-effect takeovers.

EA may request the same semantic outcome repeatedly while its autonomy or
reaction state remains active.  A takeover receipt marks that the relationship
model already handled the first request.  Later requests can therefore be
short-circuited without creating duplicate ledger events, decisions, or
emotional expressions.
"""

from collections import deque


class TakeoverFamily:
    BREAKUP = "breakup"


class TakeoverStatus:
    STARTED = "started"
    ACTIVE = "active"


def _sim_id(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


class RelationshipTakeoverReceipt:

    def __init__(
        self,
        family,
        initiator_id,
        recipient_id,
        started_at=None,
        expires_at=None,
        reason="relationship_policy_denied",
        selected_intent=None,
        decision_reference=None,
        context=None,
    ):
        self.family = str(family)
        self.initiator_id = _sim_id(initiator_id)
        self.recipient_id = _sim_id(recipient_id)
        self.started_at = (
            None if started_at is None else int(started_at)
        )
        self.expires_at = (
            None if expires_at is None else int(expires_at)
        )
        self.reason = str(reason)
        self.selected_intent = (
            None if selected_intent is None else str(selected_intent)
        )
        self.decision_reference = (
            None
            if decision_reference is None
            else str(decision_reference)
        )
        self.context = dict(context or {})
        self.suppressed_attempts = 0
        self.last_attempt_at = self.started_at

    @property
    def key(self):
        return (
            self.family,
            self.initiator_id,
            self.recipient_id,
        )

    def is_active(self, occurred_ticks=None):
        if occurred_ticks is None or self.expires_at is None:
            return True
        try:
            return int(occurred_ticks) < self.expires_at
        except (TypeError, ValueError):
            return True

    def note_suppressed_attempt(self, occurred_ticks=None):
        self.suppressed_attempts += 1
        if occurred_ticks is not None:
            self.last_attempt_at = int(occurred_ticks)

    def as_dict(self):
        return {
            "family": self.family,
            "initiator_id": self.initiator_id,
            "recipient_id": self.recipient_id,
            "started_at": self.started_at,
            "expires_at": self.expires_at,
            "reason": self.reason,
            "selected_intent": self.selected_intent,
            "decision_reference": self.decision_reference,
            "suppressed_attempts": self.suppressed_attempts,
            "last_attempt_at": self.last_attempt_at,
            "context": dict(self.context),
        }


class RelationshipTakeoverRegistry:
    """Bounded, directed receipts for model-owned relationship outcomes."""

    def __init__(self, capacity=64):
        self.capacity = max(1, int(capacity))
        self._receipts = {}
        self._order = deque()

    @staticmethod
    def _key(family, initiator_id, recipient_id):
        initiator_id = _sim_id(initiator_id)
        recipient_id = _sim_id(recipient_id)
        if (
            initiator_id is None
            or recipient_id is None
            or initiator_id == recipient_id
        ):
            return None
        return (str(family), initiator_id, recipient_id)

    def clear(self):
        self._receipts.clear()
        self._order.clear()

    def _touch(self, key):
        try:
            self._order.remove(key)
        except ValueError:
            pass
        self._order.append(key)
        while len(self._order) > self.capacity:
            expired = self._order.popleft()
            self._receipts.pop(expired, None)

    def active(
        self,
        family,
        initiator_id,
        recipient_id,
        occurred_ticks=None,
    ):
        key = self._key(family, initiator_id, recipient_id)
        if key is None:
            return None
        receipt = self._receipts.get(key)
        if receipt is None:
            return None
        if not receipt.is_active(occurred_ticks):
            self._receipts.pop(key, None)
            try:
                self._order.remove(key)
            except ValueError:
                pass
            return None
        self._touch(key)
        return receipt

    def begin(
        self,
        family,
        initiator_id,
        recipient_id,
        occurred_ticks=None,
        duration_ticks=None,
        reason="relationship_policy_denied",
        selected_intent=None,
        decision_reference=None,
        context=None,
    ):
        key = self._key(family, initiator_id, recipient_id)
        if key is None:
            return None, None
        existing = self.active(
            family,
            initiator_id,
            recipient_id,
            occurred_ticks=occurred_ticks,
        )
        if existing is not None:
            existing.note_suppressed_attempt(occurred_ticks)
            return existing, TakeoverStatus.ACTIVE
        expires_at = None
        if occurred_ticks is not None and duration_ticks is not None:
            expires_at = int(occurred_ticks) + max(
                1,
                int(duration_ticks),
            )
        receipt = RelationshipTakeoverReceipt(
            family,
            initiator_id,
            recipient_id,
            started_at=occurred_ticks,
            expires_at=expires_at,
            reason=reason,
            selected_intent=selected_intent,
            decision_reference=decision_reference,
            context=context,
        )
        self._receipts[key] = receipt
        self._touch(key)
        return receipt, TakeoverStatus.STARTED

    def release(self, family, initiator_id, recipient_id):
        key = self._key(family, initiator_id, recipient_id)
        if key is None:
            return None
        receipt = self._receipts.pop(key, None)
        try:
            self._order.remove(key)
        except ValueError:
            pass
        return receipt

    def release_pair(self, family, first_id, second_id):
        released = []
        for initiator_id, recipient_id in (
            (first_id, second_id),
            (second_id, first_id),
        ):
            receipt = self.release(
                family,
                initiator_id,
                recipient_id,
            )
            if receipt is not None:
                released.append(receipt)
        return tuple(released)


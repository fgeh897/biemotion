"""Pure runtime receipts for noisy EA relationship callbacks.

The game may describe one relationship transition through several callbacks.
These small registries join those callbacks without importing Sims 4 objects or
turning the objective event ledger into mutable runtime state.
"""

from collections import deque


def _sim_id(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _pair_key(first_id, second_id):
    first_id = _sim_id(first_id)
    second_id = _sim_id(second_id)
    if first_id is None or second_id is None or first_id == second_id:
        return None
    return tuple(sorted((first_id, second_id)))


class BreakupDeclarationReceipt:

    def __init__(
        self,
        declaration_event_id,
        initiator_id,
        recipient_id,
        occurred_ticks=None,
        origin="ea_relationship_loot",
        intentional=None,
        evidence=None,
    ):
        self.declaration_event_id = str(declaration_event_id)
        self.initiator_id = _sim_id(initiator_id)
        self.recipient_id = _sim_id(recipient_id)
        self.occurred_ticks = (
            None if occurred_ticks is None else int(occurred_ticks)
        )
        self.origin = str(origin or "unknown")
        self.intentional = (
            None if intentional is None else bool(intentional)
        )
        self.evidence = dict(evidence or {})

    @property
    def pair_key(self):
        return _pair_key(self.initiator_id, self.recipient_id)

    def merge_evidence(self, origin=None, intentional=None, evidence=None):
        if origin and (
            self.origin in ("unknown", "ea_relationship_loot")
            or origin not in ("unknown", "ea_relationship_loot")
        ):
            self.origin = str(origin)
        if intentional is not None:
            self.intentional = bool(intentional)
        self.evidence.update(dict(evidence or {}))


class BreakupCompletionReceipt:

    def __init__(
        self,
        completion_event_id,
        pair_key,
        occurred_ticks=None,
        declaration=None,
    ):
        self.completion_event_id = str(completion_event_id)
        self.pair_key = tuple(pair_key)
        self.occurred_ticks = (
            None if occurred_ticks is None else int(occurred_ticks)
        )
        self.declaration = declaration

    @property
    def initiator_id(self):
        if self.declaration is None:
            return None
        return self.declaration.initiator_id

    @property
    def recipient_id(self):
        if self.declaration is None:
            return None
        return self.declaration.recipient_id


class BreakupTransitionRegistry:
    """Join a directed breakup declaration to a bidirectional EA bit."""

    def __init__(self, capacity=32):
        self.capacity = max(1, int(capacity))
        self._declarations = {}
        self._completions = {}
        self._pair_order = deque()

    def clear(self):
        self._declarations.clear()
        self._completions.clear()
        self._pair_order.clear()

    def _touch(self, pair_key):
        try:
            self._pair_order.remove(pair_key)
        except ValueError:
            pass
        self._pair_order.append(pair_key)
        while len(self._pair_order) > self.capacity:
            expired = self._pair_order.popleft()
            self._declarations.pop(expired, None)
            self._completions.pop(expired, None)

    def declare(
        self,
        initiator_id,
        recipient_id,
        declaration_event_id,
        occurred_ticks=None,
        origin="ea_relationship_loot",
        intentional=None,
        evidence=None,
    ):
        pair_key = _pair_key(initiator_id, recipient_id)
        if pair_key is None:
            return None, False
        existing = self._declarations.get(pair_key)
        completion = self._completions.get(pair_key)
        if (
            existing is not None
            and completion is not None
            and existing.declaration_event_id
            == str(declaration_event_id)
            and existing.initiator_id == _sim_id(initiator_id)
            and existing.recipient_id == _sim_id(recipient_id)
        ):
            existing.merge_evidence(
                origin=origin,
                intentional=intentional,
                evidence=evidence,
            )
            self._touch(pair_key)
            return existing, False
        if (
            existing is not None
            and completion is None
            and existing.initiator_id == _sim_id(initiator_id)
            and existing.recipient_id == _sim_id(recipient_id)
        ):
            existing.merge_evidence(
                origin=origin,
                intentional=intentional,
                evidence=evidence,
            )
            self._touch(pair_key)
            return existing, False
        declaration = BreakupDeclarationReceipt(
            declaration_event_id,
            initiator_id,
            recipient_id,
            occurred_ticks=occurred_ticks,
            origin=origin,
            intentional=intentional,
            evidence=evidence,
        )
        self._declarations[pair_key] = declaration
        self._completions.pop(pair_key, None)
        self._touch(pair_key)
        return declaration, True

    def declaration_for_pair(
        self,
        first_id,
        second_id,
        occurred_ticks=None,
        max_age_ticks=None,
    ):
        """Return the recent directed declaration for one unordered pair."""
        pair_key = _pair_key(first_id, second_id)
        if pair_key is None:
            return None
        declaration = self._declarations.get(pair_key)
        if declaration is None:
            return None
        if (
            max_age_ticks is not None
            and occurred_ticks is not None
            and declaration.occurred_ticks is not None
        ):
            age = int(occurred_ticks) - declaration.occurred_ticks
            if age < 0 or age > int(max_age_ticks):
                return None
        self._touch(pair_key)
        return declaration

    def complete(
        self,
        first_id,
        second_id,
        occurred_ticks=None,
        max_declaration_age_ticks=None,
    ):
        pair_key = _pair_key(first_id, second_id)
        if pair_key is None:
            return None, False
        existing = self._completions.get(pair_key)
        if existing is not None:
            self._touch(pair_key)
            return existing, False
        declaration = self._declarations.get(pair_key)
        if (
            declaration is not None
            and max_declaration_age_ticks is not None
            and occurred_ticks is not None
            and declaration.occurred_ticks is not None
        ):
            age = int(occurred_ticks) - declaration.occurred_ticks
            if age < 0 or age > int(max_declaration_age_ticks):
                declaration = None
        if declaration is None:
            completion_event_id = "ea-breakup-completed:{}:{}:{}".format(
                pair_key[0],
                pair_key[1],
                "unknown" if occurred_ticks is None else int(occurred_ticks),
            )
        else:
            completion_event_id = "ea-breakup-completed:{}".format(
                declaration.declaration_event_id
            )
        completion = BreakupCompletionReceipt(
            completion_event_id,
            pair_key,
            occurred_ticks=occurred_ticks,
            declaration=declaration,
        )
        self._completions[pair_key] = completion
        self._touch(pair_key)
        return completion, True


class BreakupExecutionStatus:
    AUTHORIZED = "authorized"
    QUEUED = "queued"
    COMPLETED = "completed"


class BreakupExecutionReceipt:
    """One model-authorized breakup waiting for its exact EA interaction."""

    def __init__(
        self,
        initiator_id,
        recipient_id,
        transaction_id,
        expires_at=None,
        expected_affordance_ids=(),
    ):
        self.initiator_id = _sim_id(initiator_id)
        self.recipient_id = _sim_id(recipient_id)
        self.transaction_id = str(transaction_id)
        self.expires_at = (
            None if expires_at is None else int(expires_at)
        )
        self.expected_affordance_ids = frozenset(
            int(value)
            for value in tuple(expected_affordance_ids or ())
        )
        self.interaction_id = None
        self.status = BreakupExecutionStatus.AUTHORIZED

    @property
    def pair_key(self):
        return _pair_key(self.initiator_id, self.recipient_id)

    def bind_interaction(self, interaction_id):
        if interaction_id is not None:
            self.interaction_id = int(interaction_id)
        self.status = BreakupExecutionStatus.QUEUED

    def matches_request(
        self,
        initiator_id,
        recipient_id,
        affordance_id=None,
        interaction_id=None,
    ):
        if self.status == BreakupExecutionStatus.COMPLETED:
            return False
        if (
            self.initiator_id != _sim_id(initiator_id)
            or self.recipient_id != _sim_id(recipient_id)
        ):
            return False
        if self.expected_affordance_ids:
            try:
                affordance_id = int(affordance_id)
            except (TypeError, ValueError):
                return False
            if affordance_id not in self.expected_affordance_ids:
                return False
        if self.interaction_id is not None:
            try:
                interaction_id = int(interaction_id)
            except (TypeError, ValueError):
                return False
            if interaction_id != self.interaction_id:
                return False
        return True

class BreakupExecutionRegistry:
    """Pair-level transaction lock for queued model-authorized breakups."""

    def __init__(self, capacity=32):
        self.capacity = max(1, int(capacity))
        self._receipts = {}
        self._order = deque()

    def clear(self):
        self._receipts.clear()
        self._order.clear()

    def _touch(self, pair_key):
        try:
            self._order.remove(pair_key)
        except ValueError:
            pass
        self._order.append(pair_key)
        while len(self._order) > self.capacity:
            expired = self._order.popleft()
            self._receipts.pop(expired, None)

    def authorize(
        self,
        initiator_id,
        recipient_id,
        transaction_id,
        expires_at=None,
        expected_affordance_ids=(),
    ):
        receipt = BreakupExecutionReceipt(
            initiator_id,
            recipient_id,
            transaction_id,
            expires_at=expires_at,
            expected_affordance_ids=expected_affordance_ids,
        )
        pair_key = receipt.pair_key
        if pair_key is None:
            return None
        self._receipts[pair_key] = receipt
        self._touch(pair_key)
        return receipt

    def active(self, first_id, second_id, occurred_ticks=None):
        pair_key = _pair_key(first_id, second_id)
        if pair_key is None:
            return None
        receipt = self._receipts.get(pair_key)
        if receipt is None:
            return None
        if (
            occurred_ticks is not None
            and receipt.expires_at is not None
            and int(occurred_ticks) >= receipt.expires_at
        ):
            self._receipts.pop(pair_key, None)
            try:
                self._order.remove(pair_key)
            except ValueError:
                pass
            return None
        self._touch(pair_key)
        return receipt

    def bind_interaction(
        self,
        first_id,
        second_id,
        interaction_id,
        occurred_ticks=None,
    ):
        receipt = self.active(
            first_id,
            second_id,
            occurred_ticks=occurred_ticks,
        )
        if receipt is None:
            return None
        receipt.bind_interaction(interaction_id)
        return receipt

    def complete(self, first_id, second_id, occurred_ticks=None):
        receipt = self.active(
            first_id,
            second_id,
            occurred_ticks=occurred_ticks,
        )
        if receipt is None:
            return None
        receipt.status = BreakupExecutionStatus.COMPLETED
        return receipt

    def clear_pair(self, first_id, second_id):
        pair_key = _pair_key(first_id, second_id)
        if pair_key is None:
            return None
        receipt = self._receipts.pop(pair_key, None)
        try:
            self._order.remove(pair_key)
        except ValueError:
            pass
        return receipt


class EvidenceReceiptStatus:
    NEW = "new"
    UPGRADED = "upgraded"
    DUPLICATE = "duplicate"


class EvidenceReceipt:

    def __init__(
        self,
        key,
        canonical_event_id,
        acquisition_mode,
        rank,
        source_signal=None,
    ):
        self.key = tuple(key)
        self.canonical_event_id = str(canonical_event_id)
        self.acquisition_mode = str(acquisition_mode)
        self.rank = int(rank)
        self.source_signals = []
        self.add_signal(source_signal)

    def add_signal(self, source_signal):
        if source_signal is None:
            return
        source_signal = str(source_signal)
        if source_signal not in self.source_signals:
            self.source_signals.append(source_signal)


class EvidenceReceiptRegistry:
    """Allow one canonical reaction while retaining stronger later evidence."""

    DEFAULT_RANKS = {
        "inferred": 1,
        "told": 2,
        "ea_confirmed": 3,
        "eyewitness": 4,
    }

    def __init__(self, capacity=128, ranks=None):
        self.capacity = max(1, int(capacity))
        self.ranks = dict(self.DEFAULT_RANKS)
        self.ranks.update(dict(ranks or {}))
        self._receipts = {}
        self._order = deque()

    def clear(self):
        self._receipts.clear()
        self._order.clear()

    def observe(
        self,
        key,
        canonical_event_id,
        acquisition_mode,
        source_signal=None,
    ):
        key = tuple(key)
        acquisition_mode = str(acquisition_mode)
        rank = int(self.ranks.get(acquisition_mode, 0))
        existing = self._receipts.get(key)
        if existing is None:
            receipt = EvidenceReceipt(
                key,
                canonical_event_id,
                acquisition_mode,
                rank,
                source_signal=source_signal,
            )
            self._receipts[key] = receipt
            self._order.append(key)
            while len(self._order) > self.capacity:
                expired = self._order.popleft()
                self._receipts.pop(expired, None)
            return EvidenceReceiptStatus.NEW, receipt, None
        previous_mode = existing.acquisition_mode
        existing.add_signal(source_signal)
        if rank > existing.rank:
            existing.rank = rank
            existing.acquisition_mode = acquisition_mode
            return EvidenceReceiptStatus.UPGRADED, existing, previous_mode
        return EvidenceReceiptStatus.DUPLICATE, existing, previous_mode

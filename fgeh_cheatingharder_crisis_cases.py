"""Pure, save-safe records for an unresolved relationship crisis.

A crisis is not an EA relationship bit and it is not a temporary Buff.  It is
the persistent reason why the relationship director should keep considering
follow-up behavior after a breakup proposal was delayed.
"""

from fgeh_cheatingharder_memory_models import copy_primitive


class RelationshipCrisisStatus:
    ACTIVE = "active"
    RESOLVED = "resolved"
    RELATIONSHIP_ENDED = "relationship_ended"
    SUPERSEDED = "superseded"


class RelationshipCrisisStage:
    BREAKUP_DELAYED = "breakup_delayed"


class RelationshipCrisisAction:
    SEEK_REASSURANCE = "seek_reassurance"
    GIVE_SPACE = "give_space"
    REPEAT_BREAKUP = "repeat_breakup"


class RelationshipCrisisCaseRecord:
    """One durable crisis shared by a pair, with asymmetric actor roles."""

    def __init__(
        self,
        case_id,
        relationship_pair,
        proposer_id,
        recipient_id,
        cause_type=RelationshipCrisisStage.BREAKUP_DELAYED,
        source_transaction_ids=(),
        created_at=None,
        updated_at=None,
        severity=50.0,
        status=RelationshipCrisisStatus.ACTIVE,
        stage=RelationshipCrisisStage.BREAKUP_DELAYED,
        proposal_count=1,
        round_index=0,
        action_history=(),
        revision=0,
    ):
        pair = tuple(sorted(int(value) for value in relationship_pair))
        if len(pair) != 2 or pair[0] <= 0 or pair[0] == pair[1]:
            raise ValueError("relationship_pair must contain two Sim ids")
        proposer_id = int(proposer_id)
        recipient_id = int(recipient_id)
        if tuple(sorted((proposer_id, recipient_id))) != pair:
            raise ValueError("proposer and recipient must belong to the pair")
        self.case_id = str(case_id)
        self.relationship_pair = pair
        self.proposer_id = proposer_id
        self.recipient_id = recipient_id
        self.cause_type = str(cause_type)
        self.source_transaction_ids = tuple(dict.fromkeys(
            str(value) for value in tuple(source_transaction_ids or ())
            if value is not None
        ))
        self.created_at = copy_primitive(created_at)
        self.updated_at = copy_primitive(
            created_at if updated_at is None else updated_at
        )
        self.severity = max(0.0, min(100.0, float(severity)))
        self.status = str(status)
        self.stage = str(stage)
        self.proposal_count = max(1, int(proposal_count))
        self.round_index = max(0, int(round_index))
        self.action_history = tuple(
            copy_primitive(value) for value in tuple(action_history or ())
        )
        self.revision = max(0, int(revision))

    @property
    def is_active(self):
        return self.status == RelationshipCrisisStatus.ACTIVE

    def role_for(self, sim_id):
        sim_id = int(sim_id)
        if sim_id == self.proposer_id:
            return "proposer"
        if sim_id == self.recipient_id:
            return "recipient"
        return None

    def observe_delayed_breakup(
        self,
        proposer_id,
        recipient_id,
        source_transaction_id,
        occurred_at=None,
        severity=None,
    ):
        """Merge one later proposal without duplicating the same transaction."""
        source_transaction_id = str(source_transaction_id)
        if source_transaction_id in self.source_transaction_ids:
            return False
        proposer_id = int(proposer_id)
        recipient_id = int(recipient_id)
        if tuple(sorted((proposer_id, recipient_id))) != self.relationship_pair:
            return False
        self.proposer_id = proposer_id
        self.recipient_id = recipient_id
        self.source_transaction_ids = (
            self.source_transaction_ids + (source_transaction_id,)
        )
        self.proposal_count += 1
        self.round_index += 1
        self.updated_at = copy_primitive(occurred_at)
        if severity is not None:
            self.severity = max(
                self.severity,
                max(0.0, min(100.0, float(severity))),
            )
        self.status = RelationshipCrisisStatus.ACTIVE
        self.stage = RelationshipCrisisStage.BREAKUP_DELAYED
        self.revision += 1
        return True

    def record_action(
        self,
        action_type,
        actor_id,
        target_id,
        outcome,
        occurred_at=None,
        source_event_id=None,
        details=None,
        action_id=None,
    ):
        if not self.is_active:
            return False
        actor_id = int(actor_id)
        target_id = int(target_id)
        if tuple(sorted((actor_id, target_id))) != self.relationship_pair:
            return False
        if action_id is not None:
            action_id = str(action_id)
            if any(
                str(value.get("action_id")) == action_id
                for value in self.action_history
                if isinstance(value, dict) and value.get("action_id") is not None
            ):
                return False
        self.action_history = self.action_history + ({
            "action_id": None if action_id is None else str(action_id),
            "action_type": str(action_type),
            "actor_id": actor_id,
            "target_id": target_id,
            "outcome": str(outcome),
            "occurred_at": copy_primitive(occurred_at),
            "source_event_id": (
                None if source_event_id is None else str(source_event_id)
            ),
            "details": copy_primitive(dict(details or {})),
        },)
        self.updated_at = copy_primitive(occurred_at)
        self.round_index += 1
        self.revision += 1
        return True

    def close(self, status, occurred_at=None, details=None):
        if not self.is_active:
            return False
        self.status = str(status)
        self.updated_at = copy_primitive(occurred_at)
        if details:
            self.action_history = self.action_history + ({
                "action_type": "crisis_closed",
                "actor_id": None,
                "target_id": None,
                "outcome": self.status,
                "occurred_at": copy_primitive(occurred_at),
                "details": copy_primitive(dict(details or {})),
            },)
        self.revision += 1
        return True

    def to_data(self):
        return {
            "case_id": self.case_id,
            "relationship_pair": list(self.relationship_pair),
            "proposer_id": self.proposer_id,
            "recipient_id": self.recipient_id,
            "cause_type": self.cause_type,
            "source_transaction_ids": list(self.source_transaction_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "severity": self.severity,
            "status": self.status,
            "stage": self.stage,
            "proposal_count": self.proposal_count,
            "round_index": self.round_index,
            "action_history": copy_primitive(self.action_history),
            "revision": self.revision,
        }

    @classmethod
    def from_data(cls, data):
        return cls(**dict(data or {}))

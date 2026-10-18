"""Pure, save-safe relationship-repair requirements and case records."""

from fgeh_cheatingharder_memory_models import copy_primitive


class RepairCaseStatus:
    OPEN = "open"
    SATISFIED = "satisfied"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    SUPERSEDED = "superseded"


class RepairRequirementDefinition:

    def __init__(self, key, accepted_action_types=(), description=""):
        self.key = str(key)
        self.accepted_action_types = tuple(
            str(value) for value in accepted_action_types
        )
        self.description = str(description)

    def matches(self, action_type, accepted):
        return bool(accepted) and str(action_type) in self.accepted_action_types


class RepairRequirementRegistry:

    def __init__(self):
        self._definitions = {}

    def register(self, definition):
        if not isinstance(definition, RepairRequirementDefinition):
            raise TypeError("definition must be RepairRequirementDefinition")
        if definition.key in self._definitions:
            raise ValueError(
                "Repair requirement already registered: {}".format(
                    definition.key
                )
            )
        self._definitions[definition.key] = definition
        return definition

    def get(self, key, default=None):
        return self._definitions.get(str(key), default)

    def definitions(self):
        return tuple(
            self._definitions[key] for key in sorted(self._definitions)
        )


REPAIR_REQUIREMENTS = RepairRequirementRegistry()
SINCERE_APOLOGY_REQUIREMENT = REPAIR_REQUIREMENTS.register(
    RepairRequirementDefinition(
        "sincere_apology",
        accepted_action_types=("apology",),
        description=(
            "The accountable Sim offers an apology and the harmed Sim "
            "accepts it."
        ),
    )
)


class RepairCaseRecord:
    """One directed request to repair before official reconciliation."""

    def __init__(
        self,
        case_id,
        relationship_pair,
        accountable_id,
        harmed_id,
        requirement_keys,
        source_transaction_id=None,
        reconciliation_proposer_id=None,
        repair_requester_id=None,
        responsibility_basis="legacy_reconciliation_proposer",
        responsibility_confidence=0.0,
        responsibility_confirmed=False,
        responsibility_source_event_id=None,
        status=RepairCaseStatus.OPEN,
        satisfied_requirement_keys=(),
        attempts=(),
        revision=0,
    ):
        pair = tuple(sorted(int(value) for value in relationship_pair))
        if len(pair) != 2 or pair[0] <= 0 or pair[0] == pair[1]:
            raise ValueError("relationship_pair must contain two Sim ids")
        self.case_id = str(case_id)
        self.relationship_pair = pair
        self.accountable_id = int(accountable_id)
        self.harmed_id = int(harmed_id)
        self.requirement_keys = tuple(
            dict.fromkeys(str(value) for value in requirement_keys)
        )
        self.source_transaction_id = (
            None
            if source_transaction_id is None
            else str(source_transaction_id)
        )
        self.reconciliation_proposer_id = int(
            reconciliation_proposer_id
            if reconciliation_proposer_id is not None
            else accountable_id
        )
        self.repair_requester_id = int(
            repair_requester_id
            if repair_requester_id is not None
            else harmed_id
        )
        self.responsibility_basis = str(responsibility_basis)
        self.responsibility_confidence = max(
            0.0,
            min(1.0, float(responsibility_confidence)),
        )
        self.responsibility_confirmed = bool(responsibility_confirmed)
        self.responsibility_source_event_id = (
            None
            if responsibility_source_event_id is None
            else str(responsibility_source_event_id)
        )
        self.status = str(status)
        self.satisfied_requirement_keys = tuple(
            dict.fromkeys(str(value) for value in satisfied_requirement_keys)
        )
        self.attempts = tuple(copy_primitive(value) for value in attempts)
        self.revision = int(revision)

    @property
    def is_satisfied(self):
        return self.status == RepairCaseStatus.SATISFIED

    @property
    def is_active(self):
        return self.status in (
            RepairCaseStatus.OPEN,
            RepairCaseStatus.SATISFIED,
        )

    def apply_action(
        self,
        action_type,
        accepted,
        actor_id,
        recipient_id,
        source_event_id=None,
    ):
        if (
            not self.is_active
            or int(actor_id) != self.accountable_id
            or int(recipient_id) != self.harmed_id
        ):
            return False
        satisfied = set(self.satisfied_requirement_keys)
        matched = []
        for key in self.requirement_keys:
            definition = REPAIR_REQUIREMENTS.get(key)
            if (
                definition is not None
                and definition.matches(action_type, accepted)
            ):
                satisfied.add(key)
                matched.append(key)
        self.attempts = self.attempts + ({
            "action_type": str(action_type),
            "accepted": bool(accepted),
            "actor_id": int(actor_id),
            "recipient_id": int(recipient_id),
            "source_event_id": (
                None if source_event_id is None else str(source_event_id)
            ),
            "matched_requirement_keys": tuple(matched),
        },)
        self.satisfied_requirement_keys = tuple(
            key for key in self.requirement_keys if key in satisfied
        )
        if set(self.requirement_keys).issubset(satisfied):
            self.status = RepairCaseStatus.SATISFIED
        self.revision += 1
        return True

    def to_data(self):
        return {
            "case_id": self.case_id,
            "relationship_pair": list(self.relationship_pair),
            "accountable_id": self.accountable_id,
            "harmed_id": self.harmed_id,
            "requirement_keys": list(self.requirement_keys),
            "source_transaction_id": self.source_transaction_id,
            "reconciliation_proposer_id": self.reconciliation_proposer_id,
            "repair_requester_id": self.repair_requester_id,
            "responsibility_basis": self.responsibility_basis,
            "responsibility_confidence": self.responsibility_confidence,
            "responsibility_confirmed": self.responsibility_confirmed,
            "responsibility_source_event_id": (
                self.responsibility_source_event_id
            ),
            "status": self.status,
            "satisfied_requirement_keys": list(
                self.satisfied_requirement_keys
            ),
            "attempts": copy_primitive(self.attempts),
            "revision": self.revision,
        }

    @classmethod
    def from_data(cls, data):
        return cls(**dict(data or {}))

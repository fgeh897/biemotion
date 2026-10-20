"""Pure records for the romantic event ledger and relationship cognition.

This module has no Sims 4 imports.  Records contain ids and primitive values
only; live Sim objects, tuning classes, resolvers, and callbacks never enter the
ledger.  That boundary keeps save migrations and normal Python unit tests
possible.
"""


SCHEMA_VERSION = 5


class ParticipantRole:
    ACTOR = "actor"
    TARGET = "target"
    OBSERVER = "observer"
    PARTNER = "partner"
    RIVAL = "rival"
    WITNESS = "witness"
    INFORMANT = "informant"
    COMPLICIT = "complicit"
    RELATIONSHIP_SUBJECT = "relationship_subject"


class ClaimTruthStatus:
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"
    PLAYER_ASSERTED = "player_asserted"


class BeliefStatus:
    SUSPECTED = "suspected"
    BELIEVED = "believed"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"
    DISPROVED = "disproved"


class AcquisitionMode:
    PARTICIPANT = "participant"
    EYEWITNESS = "eyewitness"
    EA_CONFIRMED = "ea_confirmed"
    TOLD = "told"
    INFERRED = "inferred"
    PLAYER_ASSERTED = "player_asserted"


class StateChangeMode:
    ADD = "add"
    SET = "set"
    SET_IF_MISSING = "set_if_missing"


class DevotionBondStatus:
    """Current world-facing state of a permanent one-way devotion bond."""

    DEVOTED = "devoted"
    SEPARATED = "separated"
    UNREQUITED = "unrequited"
    BELOVED_DEAD = "beloved_dead"
    BELOVED_MISSING = "beloved_missing"
    BELOVED_PURGED = "beloved_purged"


DIRECTED_DIMENSIONS = (
    "attachment",
    "trust",
    "exclusivity",
    "commitment",
    "boundary",
)


def clamp_percent(value):
    return max(0.0, min(100.0, float(value)))


def normalize_sim_ids(values):
    if values is None:
        return ()
    if isinstance(values, (int, str)):
        values = (values,)
    normalized = []
    seen = set()
    for value in values:
        try:
            sim_id = int(value)
        except (TypeError, ValueError):
            continue
        if sim_id <= 0 or sim_id in seen:
            continue
        seen.add(sim_id)
        normalized.append(sim_id)
    return tuple(normalized)


def normalize_participants(participants):
    result = {}
    for role, sim_ids in dict(participants or {}).items():
        normalized = normalize_sim_ids(sim_ids)
        if normalized:
            result[str(role)] = normalized
    return result


def normalize_relationship_pairs(values):
    result = []
    seen = set()
    for value in values or ():
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            continue
        normalized = normalize_sim_ids(value)
        if len(normalized) != 2:
            continue
        pair = tuple(sorted(normalized))
        if pair not in seen:
            seen.add(pair)
            result.append(pair)
    return tuple(result)


def copy_primitive(value):
    """Return a save-safe copy without retaining game objects."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {
            str(key): copy_primitive(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list, set, frozenset)):
        return [copy_primitive(item) for item in value]
    return str(value)


class EventDraft:

    def __init__(
        self,
        event_type,
        source,
        participants=None,
        source_event_id=None,
        source_fingerprint=None,
        cause_id=None,
        occurred_at=None,
        severity=0.0,
        payload=None,
        contract_ids=None,
        relationship_pairs=None,
    ):
        self.event_type = str(event_type)
        self.source = str(source)
        self.participants = normalize_participants(participants)
        self.source_event_id = (
            None if source_event_id is None else str(source_event_id)
        )
        self.source_fingerprint = (
            None if source_fingerprint is None else str(source_fingerprint)
        )
        self.cause_id = None if cause_id is None else str(cause_id)
        self.occurred_at = copy_primitive(occurred_at)
        self.severity = clamp_percent(severity)
        self.payload = copy_primitive(dict(payload or {}))
        self.contract_ids = tuple(str(value) for value in (contract_ids or ()))
        self.relationship_pairs = normalize_relationship_pairs(
            relationship_pairs
        )


class RomanticEventRecord:

    def __init__(
        self,
        event_id,
        sequence,
        event_type,
        source,
        participants=None,
        source_event_id=None,
        source_fingerprint=None,
        cause_id=None,
        occurred_at=None,
        severity=0.0,
        payload=None,
        contract_ids=None,
        relationship_pairs=None,
    ):
        self.event_id = str(event_id)
        self.sequence = int(sequence)
        self.event_type = str(event_type)
        self.source = str(source)
        self.participants = normalize_participants(participants)
        self.source_event_id = (
            None if source_event_id is None else str(source_event_id)
        )
        self.source_fingerprint = (
            None if source_fingerprint is None else str(source_fingerprint)
        )
        self.cause_id = None if cause_id is None else str(cause_id)
        self.occurred_at = copy_primitive(occurred_at)
        self.severity = clamp_percent(severity)
        self.payload = copy_primitive(dict(payload or {}))
        self.contract_ids = tuple(str(value) for value in (contract_ids or ()))
        self.relationship_pairs = normalize_relationship_pairs(
            relationship_pairs
        )

    def participants_for(self, role):
        return tuple(self.participants.get(str(role), ()))

    def all_participant_ids(self):
        result = []
        seen = set()
        for sim_ids in self.participants.values():
            for sim_id in sim_ids:
                if sim_id not in seen:
                    seen.add(sim_id)
                    result.append(sim_id)
        return tuple(result)

    def to_data(self):
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "source": self.source,
            "participants": copy_primitive(self.participants),
            "source_event_id": self.source_event_id,
            "source_fingerprint": self.source_fingerprint,
            "cause_id": self.cause_id,
            "occurred_at": self.occurred_at,
            "severity": self.severity,
            "payload": copy_primitive(self.payload),
            "contract_ids": list(self.contract_ids),
            "relationship_pairs": [
                list(value) for value in self.relationship_pairs
            ],
        }

    @classmethod
    def from_data(cls, data):
        return cls(**dict(data or {}))


class ClaimDraft:

    def __init__(
        self,
        claim_type,
        subject_ids=None,
        object_ids=None,
        value=None,
        truth_status=ClaimTruthStatus.UNKNOWN,
        asserted_by_id=None,
        supporting_event_ids=None,
        contradicting_event_ids=None,
        provenance="event_rule",
        stable_key=None,
    ):
        self.claim_type = str(claim_type)
        self.subject_ids = normalize_sim_ids(subject_ids)
        self.object_ids = normalize_sim_ids(object_ids)
        self.value = copy_primitive(value)
        self.truth_status = str(truth_status)
        self.asserted_by_id = (
            None if asserted_by_id is None else int(asserted_by_id)
        )
        self.supporting_event_ids = tuple(
            str(value) for value in (supporting_event_ids or ())
        )
        self.contradicting_event_ids = tuple(
            str(value) for value in (contradicting_event_ids or ())
        )
        self.provenance = str(provenance)
        self.stable_key = None if stable_key is None else str(stable_key)


class ClaimRecord:

    def __init__(
        self,
        claim_id,
        sequence,
        claim_type,
        subject_ids=None,
        object_ids=None,
        value=None,
        truth_status=ClaimTruthStatus.UNKNOWN,
        asserted_by_id=None,
        supporting_event_ids=None,
        contradicting_event_ids=None,
        provenance="event_rule",
        stable_key=None,
    ):
        self.claim_id = str(claim_id)
        self.sequence = int(sequence)
        self.claim_type = str(claim_type)
        self.subject_ids = normalize_sim_ids(subject_ids)
        self.object_ids = normalize_sim_ids(object_ids)
        self.value = copy_primitive(value)
        self.truth_status = str(truth_status)
        self.asserted_by_id = (
            None if asserted_by_id is None else int(asserted_by_id)
        )
        self.supporting_event_ids = tuple(
            str(value) for value in (supporting_event_ids or ())
        )
        self.contradicting_event_ids = tuple(
            str(value) for value in (contradicting_event_ids or ())
        )
        self.provenance = str(provenance)
        self.stable_key = None if stable_key is None else str(stable_key)

    def to_data(self):
        return {
            "claim_id": self.claim_id,
            "sequence": self.sequence,
            "claim_type": self.claim_type,
            "subject_ids": list(self.subject_ids),
            "object_ids": list(self.object_ids),
            "value": copy_primitive(self.value),
            "truth_status": self.truth_status,
            "asserted_by_id": self.asserted_by_id,
            "supporting_event_ids": list(self.supporting_event_ids),
            "contradicting_event_ids": list(self.contradicting_event_ids),
            "provenance": self.provenance,
            "stable_key": self.stable_key,
        }

    @classmethod
    def from_data(cls, data):
        return cls(**dict(data or {}))


class BeliefDraft:

    def __init__(
        self,
        knower_id,
        claim_id,
        acquisition_mode,
        status=BeliefStatus.BELIEVED,
        credibility=50.0,
        confidence=50.0,
        source_sim_id=None,
        acquisition_event_id=None,
        acquired_at=None,
        stable_key=None,
    ):
        self.knower_id = int(knower_id)
        self.claim_id = str(claim_id)
        self.acquisition_mode = str(acquisition_mode)
        self.status = str(status)
        self.credibility = clamp_percent(credibility)
        self.confidence = clamp_percent(confidence)
        self.source_sim_id = (
            None if source_sim_id is None else int(source_sim_id)
        )
        self.acquisition_event_id = (
            None if acquisition_event_id is None else str(acquisition_event_id)
        )
        self.acquired_at = copy_primitive(acquired_at)
        self.stable_key = None if stable_key is None else str(stable_key)


class BeliefRecord:

    def __init__(
        self,
        belief_id,
        sequence,
        knower_id,
        claim_id,
        acquisition_mode,
        status=BeliefStatus.BELIEVED,
        credibility=50.0,
        confidence=50.0,
        source_sim_id=None,
        acquisition_event_id=None,
        acquired_at=None,
        stable_key=None,
    ):
        self.belief_id = str(belief_id)
        self.sequence = int(sequence)
        self.knower_id = int(knower_id)
        self.claim_id = str(claim_id)
        self.acquisition_mode = str(acquisition_mode)
        self.status = str(status)
        self.credibility = clamp_percent(credibility)
        self.confidence = clamp_percent(confidence)
        self.source_sim_id = (
            None if source_sim_id is None else int(source_sim_id)
        )
        self.acquisition_event_id = (
            None if acquisition_event_id is None else str(acquisition_event_id)
        )
        self.acquired_at = copy_primitive(acquired_at)
        self.stable_key = None if stable_key is None else str(stable_key)

    def to_data(self):
        return {
            "belief_id": self.belief_id,
            "sequence": self.sequence,
            "knower_id": self.knower_id,
            "claim_id": self.claim_id,
            "acquisition_mode": self.acquisition_mode,
            "status": self.status,
            "credibility": self.credibility,
            "confidence": self.confidence,
            "source_sim_id": self.source_sim_id,
            "acquisition_event_id": self.acquisition_event_id,
            "acquired_at": self.acquired_at,
            "stable_key": self.stable_key,
        }

    @classmethod
    def from_data(cls, data):
        return cls(**dict(data or {}))


class InterpretationDraft:

    def __init__(
        self,
        knower_id,
        claim_id,
        interpretation_type,
        confidence=50.0,
        rule_id="unknown",
        source_belief_id=None,
        created_at=None,
        active=True,
        details=None,
        stable_key=None,
    ):
        self.knower_id = int(knower_id)
        self.claim_id = str(claim_id)
        self.interpretation_type = str(interpretation_type)
        self.confidence = clamp_percent(confidence)
        self.rule_id = str(rule_id)
        self.source_belief_id = (
            None if source_belief_id is None else str(source_belief_id)
        )
        self.created_at = copy_primitive(created_at)
        self.active = bool(active)
        self.details = copy_primitive(dict(details or {}))
        self.stable_key = None if stable_key is None else str(stable_key)


class InterpretationRecord:

    def __init__(
        self,
        interpretation_id,
        sequence,
        knower_id,
        claim_id,
        interpretation_type,
        confidence=50.0,
        rule_id="unknown",
        source_belief_id=None,
        created_at=None,
        active=True,
        details=None,
        stable_key=None,
    ):
        self.interpretation_id = str(interpretation_id)
        self.sequence = int(sequence)
        self.knower_id = int(knower_id)
        self.claim_id = str(claim_id)
        self.interpretation_type = str(interpretation_type)
        self.confidence = clamp_percent(confidence)
        self.rule_id = str(rule_id)
        self.source_belief_id = (
            None if source_belief_id is None else str(source_belief_id)
        )
        self.created_at = copy_primitive(created_at)
        self.active = bool(active)
        self.details = copy_primitive(dict(details or {}))
        self.stable_key = None if stable_key is None else str(stable_key)

    def to_data(self):
        return {
            "interpretation_id": self.interpretation_id,
            "sequence": self.sequence,
            "knower_id": self.knower_id,
            "claim_id": self.claim_id,
            "interpretation_type": self.interpretation_type,
            "confidence": self.confidence,
            "rule_id": self.rule_id,
            "source_belief_id": self.source_belief_id,
            "created_at": self.created_at,
            "active": self.active,
            "details": copy_primitive(self.details),
            "stable_key": self.stable_key,
        }

    @classmethod
    def from_data(cls, data):
        return cls(**dict(data or {}))


class DirectedStateDelta:

    def __init__(
        self,
        observer_id,
        partner_id,
        dimension,
        value,
        reason,
        mode=StateChangeMode.ADD,
        event_id=None,
        claim_id=None,
        belief_id=None,
        interpretation_id=None,
    ):
        self.observer_id = int(observer_id)
        self.partner_id = int(partner_id)
        self.dimension = str(dimension)
        self.value = float(value)
        self.reason = str(reason)
        self.mode = str(mode)
        self.event_id = None if event_id is None else str(event_id)
        self.claim_id = None if claim_id is None else str(claim_id)
        self.belief_id = None if belief_id is None else str(belief_id)
        self.interpretation_id = (
            None if interpretation_id is None else str(interpretation_id)
        )


class DirectedStateRecord:

    def __init__(self, observer_id, partner_id, values=None, initialized=None, revision=0):
        self.observer_id = int(observer_id)
        self.partner_id = int(partner_id)
        values = dict(values or {})
        initialized = dict(initialized or {})
        self.values = {
            dimension: clamp_percent(values.get(dimension, 0.0))
            for dimension in DIRECTED_DIMENSIONS
        }
        self.initialized = {
            dimension: bool(initialized.get(dimension, dimension in values))
            for dimension in DIRECTED_DIMENSIONS
        }
        self.revision = int(revision)

    def get(self, dimension, default=0.0):
        return float(self.values.get(dimension, default))

    def to_data(self):
        return {
            "observer_id": self.observer_id,
            "partner_id": self.partner_id,
            "values": dict(self.values),
            "initialized": dict(self.initialized),
            "revision": self.revision,
        }

    @classmethod
    def from_data(cls, data):
        return cls(**dict(data or {}))


class DevotionBondRecord:
    """One permanent beloved identity for one owner.

    This is categorical current state, not a sixth relationship percentage.
    The romantic ledger explains how it was created while this projection lets
    interaction tests answer the hot-path question without scanning history.
    """

    def __init__(
        self,
        owner_id,
        beloved_id,
        established_event_id,
        established_at=None,
        source="unknown",
        status=DevotionBondStatus.DEVOTED,
        revision=1,
    ):
        self.owner_id = int(owner_id)
        self.beloved_id = int(beloved_id)
        if self.owner_id <= 0 or self.beloved_id <= 0:
            raise ValueError("Devotion bond Sim ids must be positive")
        if self.owner_id == self.beloved_id:
            raise ValueError("A Sim cannot be their own only beloved")
        self.established_event_id = str(established_event_id)
        self.established_at = copy_primitive(established_at)
        self.source = str(source)
        self.status = str(status)
        self.revision = max(1, int(revision))

    def to_data(self):
        return {
            "owner_id": self.owner_id,
            "beloved_id": self.beloved_id,
            "established_event_id": self.established_event_id,
            "established_at": self.established_at,
            "source": self.source,
            "status": self.status,
            "revision": self.revision,
        }

    @classmethod
    def from_data(cls, data):
        return cls(**dict(data or {}))


class RelationshipHistorySummary:

    def __init__(
        self,
        observer_id,
        partner_id,
        counters=None,
        timestamps=None,
        flags=None,
        confidences=None,
        gauges=None,
        last_event_sequence=0,
        projection_version=1,
    ):
        self.observer_id = int(observer_id)
        self.partner_id = int(partner_id)
        self.counters = {
            str(key): int(value)
            for key, value in dict(counters or {}).items()
        }
        self.timestamps = copy_primitive(dict(timestamps or {}))
        self.flags = {
            str(key): bool(value)
            for key, value in dict(flags or {}).items()
        }
        self.confidences = {
            str(key): clamp_percent(value)
            for key, value in dict(confidences or {}).items()
        }
        self.gauges = {
            str(key): clamp_percent(value)
            for key, value in dict(gauges or {}).items()
        }
        self.last_event_sequence = int(last_event_sequence)
        self.projection_version = int(projection_version)

    def increment(self, key, amount=1):
        key = str(key)
        self.counters[key] = self.counters.get(key, 0) + int(amount)

    def set_timestamp(self, key, value):
        self.timestamps[str(key)] = copy_primitive(value)

    def set_flag(self, key, value=True):
        self.flags[str(key)] = bool(value)

    def set_confidence(self, key, value):
        self.confidences[str(key)] = clamp_percent(value)

    def set_gauge(self, key, value):
        self.gauges[str(key)] = clamp_percent(value)

    def to_data(self):
        return {
            "observer_id": self.observer_id,
            "partner_id": self.partner_id,
            "counters": dict(self.counters),
            "timestamps": copy_primitive(self.timestamps),
            "flags": dict(self.flags),
            "confidences": dict(self.confidences),
            "gauges": dict(self.gauges),
            "last_event_sequence": self.last_event_sequence,
            "projection_version": self.projection_version,
        }

    @classmethod
    def from_data(cls, data):
        return cls(**dict(data or {}))


class SummaryMutation:

    INCREMENT = "increment"
    SET_TIMESTAMP = "set_timestamp"
    SET_FLAG = "set_flag"
    SET_CONFIDENCE = "set_confidence"
    SET_GAUGE = "set_gauge"

    def __init__(
        self,
        observer_id,
        partner_id,
        operation,
        key,
        value,
        projection_version=1,
    ):
        self.observer_id = int(observer_id)
        self.partner_id = int(partner_id)
        self.operation = str(operation)
        self.key = str(key)
        self.value = copy_primitive(value)
        self.projection_version = int(projection_version)


class MemoryOpportunity:

    def __init__(
        self,
        opportunity_type,
        observer_id,
        partner_id,
        reason,
        urgency=0.0,
        event_id=None,
        context=None,
    ):
        self.opportunity_type = str(opportunity_type)
        self.observer_id = int(observer_id)
        self.partner_id = int(partner_id)
        self.reason = str(reason)
        self.urgency = float(urgency)
        self.event_id = None if event_id is None else str(event_id)
        self.context = copy_primitive(dict(context or {}))

    def to_data(self):
        return {
            "opportunity_type": self.opportunity_type,
            "observer_id": self.observer_id,
            "partner_id": self.partner_id,
            "reason": self.reason,
            "urgency": self.urgency,
            "event_id": self.event_id,
            "context": copy_primitive(self.context),
        }


class ProcessingReport:

    def __init__(self, event, duplicate=False):
        self.event = event
        self.duplicate = bool(duplicate)
        self.claims = []
        self.beliefs = []
        self.interpretations = []
        self.state_deltas = []
        self.summary_edges = set()
        self.opportunities = []
        self.errors = []

    def to_data(self):
        return {
            "event_id": getattr(self.event, "event_id", None),
            "event_type": getattr(self.event, "event_type", None),
            "duplicate": self.duplicate,
            "claim_ids": [record.claim_id for record in self.claims],
            "belief_ids": [record.belief_id for record in self.beliefs],
            "interpretation_ids": [
                record.interpretation_id for record in self.interpretations
            ],
            "state_delta_count": len(self.state_deltas),
            "summary_edges": sorted(self.summary_edges),
            "opportunities": [
                opportunity.to_data() for opportunity in self.opportunities
            ],
            "errors": list(self.errors),
        }

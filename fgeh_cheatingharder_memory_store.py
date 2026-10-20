"""Repositories and snapshots for romantic events, beliefs, and projections."""

import uuid

from fgeh_cheatingharder_memory_models import (
    BeliefRecord,
    ClaimRecord,
    DevotionBondRecord,
    DirectedStateRecord,
    DIRECTED_DIMENSIONS,
    InterpretationRecord,
    RelationshipHistorySummary,
    RomanticEventRecord,
    SCHEMA_VERSION,
    StateChangeMode,
    clamp_percent,
    copy_primitive,
)
from fgeh_cheatingharder_devotion import DevotionConflictError
from fgeh_cheatingharder_repair_cases import (
    RepairCaseRecord,
    RepairCaseStatus,
)
from fgeh_cheatingharder_crisis_cases import (
    RelationshipCrisisCaseRecord,
    RelationshipCrisisStatus,
)


class SnapshotVersionError(ValueError):
    pass


class RomanticMemoryStore:
    """Single save-lineage aggregate with rebuildable query indexes."""

    def __init__(self, save_lineage_id=None):
        self.save_lineage_id = str(save_lineage_id or uuid.uuid4().hex)
        self._next_sequence = 1
        self._events = {}
        self._claims = {}
        self._beliefs = {}
        self._interpretations = {}
        self._devotion_bonds = {}
        self._directed_states = {}
        self._summaries = {}
        self._repair_cases = {}
        self._relationship_crises = {}
        self._receipts = set()
        self._event_id_by_fingerprint = {}
        self._claim_id_by_stable_key = {}
        self._belief_id_by_stable_key = {}
        self._interpretation_id_by_stable_key = {}
        self._event_ids_by_type = {}
        self._event_ids_by_participant = {}
        self._event_ids_by_relationship = {}
        self._claim_ids_by_event = {}
        self._belief_ids_by_knower = {}
        self._belief_ids_by_claim = {}
        self._interpretation_ids_by_knower = {}
        self._interpretation_ids_by_claim = {}
        self._state_change_listener = None

    def _allocate_id(self, prefix):
        sequence = self._next_sequence
        self._next_sequence += 1
        record_id = "{}:{}:{:012d}".format(
            str(prefix),
            self.save_lineage_id,
            sequence,
        )
        return (record_id, sequence)

    def set_state_change_listener(self, callback):
        self._state_change_listener = callback

    def append_event(self, draft):
        fingerprint = draft.source_fingerprint
        if fingerprint:
            existing_id = self._event_id_by_fingerprint.get(fingerprint)
            if existing_id is not None:
                return (self._events[existing_id], False)
        event_id, sequence = self._allocate_id("evt")
        event = RomanticEventRecord(
            event_id=event_id,
            sequence=sequence,
            event_type=draft.event_type,
            source=draft.source,
            participants=draft.participants,
            source_event_id=draft.source_event_id,
            source_fingerprint=fingerprint,
            cause_id=draft.cause_id,
            occurred_at=draft.occurred_at,
            severity=draft.severity,
            payload=draft.payload,
            contract_ids=draft.contract_ids,
            relationship_pairs=draft.relationship_pairs,
        )
        self._events[event.event_id] = event
        if fingerprint:
            self._event_id_by_fingerprint[fingerprint] = event.event_id
        self._index_event(event)
        return (event, True)

    def _index_event(self, event):
        self._event_ids_by_type.setdefault(event.event_type, []).append(event.event_id)
        for sim_id in event.all_participant_ids():
            self._event_ids_by_participant.setdefault(sim_id, []).append(event.event_id)
        for pair in event.relationship_pairs:
            self._event_ids_by_relationship.setdefault(pair, []).append(
                event.event_id
            )

    def append_claim(self, draft):
        stable_key = draft.stable_key
        if stable_key:
            existing_id = self._claim_id_by_stable_key.get(stable_key)
            if existing_id is not None:
                return (self._claims[existing_id], False)
        claim_id, sequence = self._allocate_id("clm")
        claim = ClaimRecord(
            claim_id=claim_id,
            sequence=sequence,
            claim_type=draft.claim_type,
            subject_ids=draft.subject_ids,
            object_ids=draft.object_ids,
            value=draft.value,
            truth_status=draft.truth_status,
            asserted_by_id=draft.asserted_by_id,
            supporting_event_ids=draft.supporting_event_ids,
            contradicting_event_ids=draft.contradicting_event_ids,
            provenance=draft.provenance,
            stable_key=stable_key,
        )
        self._claims[claim.claim_id] = claim
        if stable_key:
            self._claim_id_by_stable_key[stable_key] = claim.claim_id
        self._index_claim(claim)
        return (claim, True)

    def _index_claim(self, claim):
        for event_id in claim.supporting_event_ids + claim.contradicting_event_ids:
            self._claim_ids_by_event.setdefault(event_id, []).append(claim.claim_id)

    def append_belief(self, draft):
        stable_key = draft.stable_key
        if stable_key:
            existing_id = self._belief_id_by_stable_key.get(stable_key)
            if existing_id is not None:
                return (self._beliefs[existing_id], False)
        belief_id, sequence = self._allocate_id("blf")
        belief = BeliefRecord(
            belief_id=belief_id,
            sequence=sequence,
            knower_id=draft.knower_id,
            claim_id=draft.claim_id,
            acquisition_mode=draft.acquisition_mode,
            status=draft.status,
            credibility=draft.credibility,
            confidence=draft.confidence,
            source_sim_id=draft.source_sim_id,
            acquisition_event_id=draft.acquisition_event_id,
            acquired_at=draft.acquired_at,
            stable_key=stable_key,
        )
        self._beliefs[belief.belief_id] = belief
        if stable_key:
            self._belief_id_by_stable_key[stable_key] = belief.belief_id
        self._index_belief(belief)
        return (belief, True)

    def _index_belief(self, belief):
        self._belief_ids_by_knower.setdefault(belief.knower_id, []).append(
            belief.belief_id
        )
        self._belief_ids_by_claim.setdefault(belief.claim_id, []).append(
            belief.belief_id
        )

    def append_interpretation(self, draft):
        stable_key = draft.stable_key
        if stable_key:
            existing_id = self._interpretation_id_by_stable_key.get(stable_key)
            if existing_id is not None:
                return (self._interpretations[existing_id], False)
        interpretation_id, sequence = self._allocate_id("int")
        interpretation = InterpretationRecord(
            interpretation_id=interpretation_id,
            sequence=sequence,
            knower_id=draft.knower_id,
            claim_id=draft.claim_id,
            interpretation_type=draft.interpretation_type,
            confidence=draft.confidence,
            rule_id=draft.rule_id,
            source_belief_id=draft.source_belief_id,
            created_at=draft.created_at,
            active=draft.active,
            details=draft.details,
            stable_key=stable_key,
        )
        self._interpretations[interpretation.interpretation_id] = interpretation
        if stable_key:
            self._interpretation_id_by_stable_key[stable_key] = (
                interpretation.interpretation_id
            )
        self._index_interpretation(interpretation)
        return (interpretation, True)

    def _index_interpretation(self, interpretation):
        self._interpretation_ids_by_knower.setdefault(
            interpretation.knower_id,
            [],
        ).append(interpretation.interpretation_id)
        self._interpretation_ids_by_claim.setdefault(
            interpretation.claim_id,
            [],
        ).append(interpretation.interpretation_id)

    def get_event(self, event_id):
        return self._events.get(str(event_id))

    def get_claim(self, claim_id):
        return self._claims.get(str(claim_id))

    def get_belief(self, belief_id):
        return self._beliefs.get(str(belief_id))

    def get_interpretation(self, interpretation_id):
        return self._interpretations.get(str(interpretation_id))

    def events(self):
        return tuple(sorted(self._events.values(), key=lambda value: value.sequence))

    def claims(self):
        return tuple(sorted(self._claims.values(), key=lambda value: value.sequence))

    def beliefs(self):
        return tuple(sorted(self._beliefs.values(), key=lambda value: value.sequence))

    def interpretations(self):
        return tuple(
            sorted(self._interpretations.values(), key=lambda value: value.sequence)
        )

    def events_for_type(self, event_type):
        return tuple(
            self._events[event_id]
            for event_id in self._event_ids_by_type.get(str(event_type), ())
        )

    def events_for_participant(self, sim_id):
        return tuple(
            self._events[event_id]
            for event_id in self._event_ids_by_participant.get(int(sim_id), ())
        )

    def events_for_relationship(self, sim_a_id, sim_b_id):
        pair = tuple(sorted((int(sim_a_id), int(sim_b_id))))
        if pair[0] <= 0 or pair[0] == pair[1]:
            return ()
        return tuple(
            self._events[event_id]
            for event_id in self._event_ids_by_relationship.get(pair, ())
        )

    def claims_for_event(self, event_id):
        return tuple(
            self._claims[claim_id]
            for claim_id in self._claim_ids_by_event.get(str(event_id), ())
        )

    def beliefs_for_knower(self, sim_id):
        return tuple(
            self._beliefs[belief_id]
            for belief_id in self._belief_ids_by_knower.get(int(sim_id), ())
        )

    def beliefs_for_claim(self, claim_id):
        return tuple(
            self._beliefs[belief_id]
            for belief_id in self._belief_ids_by_claim.get(str(claim_id), ())
        )

    def interpretations_for_knower(self, sim_id):
        return tuple(
            self._interpretations[interpretation_id]
            for interpretation_id in self._interpretation_ids_by_knower.get(
                int(sim_id),
                (),
            )
        )

    def bind_devotion(
        self,
        owner_id,
        beloved_id,
        established_event_id,
        established_at=None,
        source="unknown",
    ):
        """Create the owner's only beloved projection, idempotently."""
        owner_id = int(owner_id)
        beloved_id = int(beloved_id)
        existing = self._devotion_bonds.get(owner_id)
        if existing is not None:
            if existing.beloved_id != beloved_id:
                raise DevotionConflictError(
                    "Sim {} is already devoted to Sim {}".format(
                        owner_id,
                        existing.beloved_id,
                    )
                )
            return (existing, False)
        record = DevotionBondRecord(
            owner_id,
            beloved_id,
            established_event_id,
            established_at=established_at,
            source=source,
        )
        self._devotion_bonds[owner_id] = record
        return (record, True)

    def get_devotion_bond(self, owner_id):
        return self._devotion_bonds.get(int(owner_id))

    def set_devotion_status(self, owner_id, status):
        """Update relationship context without changing the only beloved."""
        record = self.get_devotion_bond(owner_id)
        if record is None:
            return None
        requested = str(status)
        if record.status == requested:
            return record
        record.status = requested
        record.revision += 1
        return record

    def devotion_bonds(self):
        return tuple(
            self._devotion_bonds[key]
            for key in sorted(self._devotion_bonds)
        )

    def get_directed_state(self, observer_id, partner_id, create=False):
        key = (int(observer_id), int(partner_id))
        state = self._directed_states.get(key)
        if state is None and create:
            state = DirectedStateRecord(key[0], key[1])
            self._directed_states[key] = state
        return state

    def seed_directed_state(self, observer_id, partner_id, values, initialized=None):
        key = (int(observer_id), int(partner_id))
        state = self._directed_states.get(key)
        if state is not None:
            return state
        state = DirectedStateRecord(
            key[0],
            key[1],
            values=values,
            initialized=initialized,
        )
        self._directed_states[key] = state
        return state

    def apply_state_delta(self, delta):
        if delta.dimension not in DIRECTED_DIMENSIONS:
            raise ValueError("Unknown directed dimension: {}".format(delta.dimension))
        state = self.get_directed_state(
            delta.observer_id,
            delta.partner_id,
            create=True,
        )
        old_value = state.get(delta.dimension)
        was_initialized = state.initialized.get(delta.dimension, False)
        if delta.mode == StateChangeMode.SET_IF_MISSING and was_initialized:
            return (state, old_value, old_value, False)
        if delta.mode == StateChangeMode.ADD:
            new_value = clamp_percent(old_value + delta.value)
        elif delta.mode in (StateChangeMode.SET, StateChangeMode.SET_IF_MISSING):
            new_value = clamp_percent(delta.value)
        else:
            raise ValueError("Unknown state change mode: {}".format(delta.mode))
        changed = (not was_initialized) or old_value != new_value
        state.values[delta.dimension] = new_value
        state.initialized[delta.dimension] = True
        if changed:
            state.revision += 1
            callback = self._state_change_listener
            if callback is not None:
                callback(delta, old_value, new_value, state)
        return (state, old_value, new_value, changed)

    def directed_states(self):
        return tuple(
            self._directed_states[key]
            for key in sorted(self._directed_states)
        )

    def get_summary(self, observer_id, partner_id, create=False):
        key = (int(observer_id), int(partner_id))
        summary = self._summaries.get(key)
        if summary is None and create:
            summary = RelationshipHistorySummary(key[0], key[1])
            self._summaries[key] = summary
        return summary

    def summaries(self):
        return tuple(self._summaries[key] for key in sorted(self._summaries))

    def has_receipt(self, consumer_id, subject_id, event_id, rule_version):
        return (
            str(consumer_id),
            int(subject_id or 0),
            str(event_id),
            int(rule_version),
        ) in self._receipts

    def add_receipt(self, consumer_id, subject_id, event_id, rule_version):
        receipt = (
            str(consumer_id),
            int(subject_id or 0),
            str(event_id),
            int(rule_version),
        )
        if receipt in self._receipts:
            return False
        self._receipts.add(receipt)
        return True

    def open_repair_case(
        self,
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
    ):
        accountable_id = int(accountable_id)
        harmed_id = int(harmed_id)
        existing = self.find_active_repair_case_for_pair(
            accountable_id,
            harmed_id,
        )
        if existing is not None and not existing.is_satisfied:
            return existing, False
        case_id, _sequence = self._allocate_id("repair")
        record = RepairCaseRecord(
            case_id,
            (accountable_id, harmed_id),
            accountable_id,
            harmed_id,
            requirement_keys,
            source_transaction_id=source_transaction_id,
            reconciliation_proposer_id=reconciliation_proposer_id,
            repair_requester_id=repair_requester_id,
            responsibility_basis=responsibility_basis,
            responsibility_confidence=responsibility_confidence,
            responsibility_confirmed=responsibility_confirmed,
            responsibility_source_event_id=responsibility_source_event_id,
        )
        self._repair_cases[case_id] = record
        return record, True

    def repair_cases(self):
        return tuple(
            self._repair_cases[key] for key in sorted(self._repair_cases)
        )

    def get_repair_case(self, case_id):
        return self._repair_cases.get(str(case_id))

    def find_active_repair_case(self, accountable_id, harmed_id):
        accountable_id = int(accountable_id)
        harmed_id = int(harmed_id)
        matches = [
            record
            for record in self._repair_cases.values()
            if (
                record.accountable_id == accountable_id
                and record.harmed_id == harmed_id
                and record.is_active
            )
        ]
        if not matches:
            return None
        return sorted(matches, key=lambda value: value.case_id)[-1]

    def find_active_repair_case_for_pair(self, sim_a_id, sim_b_id):
        pair = tuple(sorted((int(sim_a_id), int(sim_b_id))))
        matches = [
            record
            for record in self._repair_cases.values()
            if record.relationship_pair == pair and record.is_active
        ]
        if not matches:
            return None
        return sorted(matches, key=lambda value: value.case_id)[-1]

    def apply_repair_action_to_case(
        self,
        actor_id,
        recipient_id,
        action_type,
        accepted,
        source_event_id=None,
    ):
        record = self.find_active_repair_case(actor_id, recipient_id)
        if record is None:
            return None
        record.apply_action(
            action_type,
            accepted,
            actor_id,
            recipient_id,
            source_event_id=source_event_id,
        )
        return record

    def close_satisfied_repair_cases(self, sim_a_id, sim_b_id):
        pair = tuple(sorted((int(sim_a_id), int(sim_b_id))))
        changed = 0
        for record in self._repair_cases.values():
            if record.relationship_pair != pair or not record.is_satisfied:
                continue
            record.status = RepairCaseStatus.COMPLETED
            record.revision += 1
            changed += 1
        return changed

    def open_relationship_crisis(
        self,
        proposer_id,
        recipient_id,
        source_transaction_id,
        occurred_at=None,
        severity=50.0,
        cause_type="breakup_delayed",
    ):
        proposer_id = int(proposer_id)
        recipient_id = int(recipient_id)
        existing = self.find_active_relationship_crisis(
            proposer_id,
            recipient_id,
        )
        if existing is not None:
            existing.observe_delayed_breakup(
                proposer_id,
                recipient_id,
                source_transaction_id,
                occurred_at=occurred_at,
                severity=severity,
            )
            return existing, False
        case_id, _sequence = self._allocate_id("crisis")
        record = RelationshipCrisisCaseRecord(
            case_id,
            (proposer_id, recipient_id),
            proposer_id,
            recipient_id,
            cause_type=cause_type,
            source_transaction_ids=(source_transaction_id,),
            created_at=occurred_at,
            updated_at=occurred_at,
            severity=severity,
        )
        self._relationship_crises[case_id] = record
        return record, True

    def relationship_crises(self):
        return tuple(
            self._relationship_crises[key]
            for key in sorted(self._relationship_crises)
        )

    def get_relationship_crisis(self, case_id):
        return self._relationship_crises.get(str(case_id))

    def find_active_relationship_crisis(self, sim_a_id, sim_b_id):
        pair = tuple(sorted((int(sim_a_id), int(sim_b_id))))
        matches = [
            record
            for record in self._relationship_crises.values()
            if record.relationship_pair == pair and record.is_active
        ]
        if not matches:
            return None
        return sorted(matches, key=lambda value: value.case_id)[-1]

    def record_relationship_crisis_action(
        self,
        case_id,
        action_type,
        actor_id,
        target_id,
        outcome,
        occurred_at=None,
        source_event_id=None,
        details=None,
        action_id=None,
    ):
        record = self.get_relationship_crisis(case_id)
        if record is None:
            return None
        record.record_action(
            action_type,
            actor_id,
            target_id,
            outcome,
            occurred_at=occurred_at,
            source_event_id=source_event_id,
            details=details,
            action_id=action_id,
        )
        return record

    def close_relationship_crises_for_pair(
        self,
        sim_a_id,
        sim_b_id,
        status=RelationshipCrisisStatus.RESOLVED,
        occurred_at=None,
        details=None,
    ):
        pair = tuple(sorted((int(sim_a_id), int(sim_b_id))))
        changed = 0
        for record in self._relationship_crises.values():
            if record.relationship_pair != pair or not record.is_active:
                continue
            if record.close(status, occurred_at=occurred_at, details=details):
                changed += 1
        return changed

    def to_snapshot(self):
        return {
            "schema_version": SCHEMA_VERSION,
            "save_lineage_id": self.save_lineage_id,
            "next_sequence": self._next_sequence,
            "events": [record.to_data() for record in self.events()],
            "claims": [record.to_data() for record in self.claims()],
            "beliefs": [record.to_data() for record in self.beliefs()],
            "interpretations": [
                record.to_data() for record in self.interpretations()
            ],
            "devotion_bonds": [
                record.to_data() for record in self.devotion_bonds()
            ],
            "directed_states": [
                record.to_data() for record in self.directed_states()
            ],
            "summaries": [record.to_data() for record in self.summaries()],
            "repair_cases": [
                record.to_data() for record in self.repair_cases()
            ],
            "relationship_crises": [
                record.to_data() for record in self.relationship_crises()
            ],
            "receipts": [list(value) for value in sorted(self._receipts)],
        }

    @classmethod
    def from_snapshot(cls, snapshot):
        data = copy_primitive(dict(snapshot or {}))
        version = int(data.get("schema_version", 0))
        if version not in (1, 2, 3, 4, SCHEMA_VERSION):
            raise SnapshotVersionError(
                "Unsupported romantic memory schema {} (supported: 1-{})".format(
                    version,
                    SCHEMA_VERSION,
                )
            )
        store = cls(save_lineage_id=data.get("save_lineage_id"))
        store._events = {
            record.event_id: record
            for record in (
                RomanticEventRecord.from_data(value)
                for value in data.get("events", ())
            )
        }
        store._claims = {
            record.claim_id: record
            for record in (
                ClaimRecord.from_data(value)
                for value in data.get("claims", ())
            )
        }
        store._beliefs = {
            record.belief_id: record
            for record in (
                BeliefRecord.from_data(value)
                for value in data.get("beliefs", ())
            )
        }
        store._interpretations = {
            record.interpretation_id: record
            for record in (
                InterpretationRecord.from_data(value)
                for value in data.get("interpretations", ())
            )
        }
        store._devotion_bonds = {
            record.owner_id: record
            for record in (
                DevotionBondRecord.from_data(value)
                for value in data.get("devotion_bonds", ())
            )
        }
        store._directed_states = {
            (record.observer_id, record.partner_id): record
            for record in (
                DirectedStateRecord.from_data(value)
                for value in data.get("directed_states", ())
            )
        }
        store._summaries = {
            (record.observer_id, record.partner_id): record
            for record in (
                RelationshipHistorySummary.from_data(value)
                for value in data.get("summaries", ())
            )
        }
        store._repair_cases = {
            record.case_id: record
            for record in (
                RepairCaseRecord.from_data(value)
                for value in data.get("repair_cases", ())
            )
        }
        store._relationship_crises = {
            record.case_id: record
            for record in (
                RelationshipCrisisCaseRecord.from_data(value)
                for value in data.get("relationship_crises", ())
            )
        }
        store._receipts = {
            (str(value[0]), int(value[1]), str(value[2]), int(value[3]))
            for value in data.get("receipts", ())
            if len(value) == 4
        }
        highest_sequence = 0
        for collection in (
            store._events.values(),
            store._claims.values(),
            store._beliefs.values(),
            store._interpretations.values(),
        ):
            for record in collection:
                highest_sequence = max(highest_sequence, record.sequence)
        store._next_sequence = max(
            int(data.get("next_sequence", 1)),
            highest_sequence + 1,
        )
        store._rebuild_indexes()
        return store

    def _rebuild_indexes(self):
        self._event_id_by_fingerprint.clear()
        self._claim_id_by_stable_key.clear()
        self._belief_id_by_stable_key.clear()
        self._interpretation_id_by_stable_key.clear()
        self._event_ids_by_type.clear()
        self._event_ids_by_participant.clear()
        self._event_ids_by_relationship.clear()
        self._claim_ids_by_event.clear()
        self._belief_ids_by_knower.clear()
        self._belief_ids_by_claim.clear()
        self._interpretation_ids_by_knower.clear()
        self._interpretation_ids_by_claim.clear()
        for event in self.events():
            if event.source_fingerprint:
                self._event_id_by_fingerprint[event.source_fingerprint] = event.event_id
            self._index_event(event)
        for claim in self.claims():
            if claim.stable_key:
                self._claim_id_by_stable_key[claim.stable_key] = claim.claim_id
            self._index_claim(claim)
        for belief in self.beliefs():
            if belief.stable_key:
                self._belief_id_by_stable_key[belief.stable_key] = belief.belief_id
            self._index_belief(belief)
        for interpretation in self.interpretations():
            if interpretation.stable_key:
                self._interpretation_id_by_stable_key[
                    interpretation.stable_key
                ] = interpretation.interpretation_id
            self._index_interpretation(interpretation)

    def counts(self):
        return {
            "events": len(self._events),
            "claims": len(self._claims),
            "beliefs": len(self._beliefs),
            "interpretations": len(self._interpretations),
            "devotion_bonds": len(self._devotion_bonds),
            "directed_states": len(self._directed_states),
            "summaries": len(self._summaries),
            "repair_cases": len(self._repair_cases),
            "relationship_crises": len(self._relationship_crises),
            "receipts": len(self._receipts),
        }

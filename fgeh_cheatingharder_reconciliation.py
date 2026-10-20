"""Pure, asymmetric reconciliation negotiation for former partners.

The proposer and recipient never share one relationship score.  A player
clicking the interaction explicitly supplies the proposer's decision to ask;
an autonomous caller must first win the proposer utility competition.  The
recipient always answers from recipient -> proposer state and history.

Only mutual willingness authorizes the lower EA relationship transaction.
This module deliberately has no Sims 4 imports.
"""

import random

from fgeh_cheatingharder_utility_model import (
    RELATIONSHIP_UTILITY_MODELS,
    UtilityCandidateDefinition,
    UtilityFactor,
    UtilityGate,
)


DIRECTED_STATE_DEFAULTS = {
    "attachment": 68.0,
    "trust": 65.0,
    "exclusivity": 88.0,
    "commitment": 68.0,
    "boundary": 50.0,
}


class ReconciliationProposal:
    PROPOSE = "propose_reconciliation"
    HOLD_BACK = "hold_back_reconciliation"


class ReconciliationResponse:
    ACCEPT = "accept_reconciliation"
    REPAIR_FIRST = "request_repair_before_reconciliation"
    DEFER = "defer_reconciliation"
    REFUSE = "refuse_reconciliation"


class ReconciliationOutcome:
    OFFICIAL_RECONCILIATION_AUTHORIZED = (
        "official_reconciliation_authorized"
    )
    REPAIR_REQUIRED = "repair_required"
    RECONCILIATION_DEFERRED = "reconciliation_deferred"
    RECONCILIATION_REFUSED = "reconciliation_refused"
    PROPOSAL_WITHHELD = "proposal_withheld"


def _clamp(value, minimum, maximum):
    return max(float(minimum), min(float(maximum), float(value)))


def normalize_directed_state(values):
    values = dict(values or {})
    return {
        dimension: _clamp(values.get(dimension, default), 0.0, 100.0)
        for dimension, default in DIRECTED_STATE_DEFAULTS.items()
    }


class ReconciliationInfluence:
    """Registered personality contribution without branching core logic."""

    def __init__(
        self,
        key,
        proposal_modifiers=None,
        response_modifiers=None,
        description="",
    ):
        self.key = str(key)
        self.proposal_modifiers = {
            str(choice): _clamp(value, -40.0, 40.0)
            for choice, value in dict(proposal_modifiers or {}).items()
        }
        self.response_modifiers = {
            str(choice): _clamp(value, -40.0, 40.0)
            for choice, value in dict(response_modifiers or {}).items()
        }
        self.description = str(description)

    def proposal_modifier(self, choice):
        return self.proposal_modifiers.get(str(choice), 0.0)

    def response_modifier(self, choice):
        return self.response_modifiers.get(str(choice), 0.0)


class ReconciliationInfluenceRegistry:

    def __init__(self):
        self._definitions = {}

    def register(self, definition):
        if not isinstance(definition, ReconciliationInfluence):
            raise TypeError("definition must be ReconciliationInfluence")
        if definition.key in self._definitions:
            raise ValueError(
                "Reconciliation influence already registered: {}".format(
                    definition.key
                )
            )
        self._definitions[definition.key] = definition
        return definition

    def get(self, key, default=None):
        return self._definitions.get(str(key), default)

    def keys(self):
        return tuple(sorted(self._definitions))


RECONCILIATION_INFLUENCES = ReconciliationInfluenceRegistry()
PERMANENT_DEVOTION_INFLUENCE = RECONCILIATION_INFLUENCES.register(
    ReconciliationInfluence(
        "permanent_devotion",
        proposal_modifiers={
            ReconciliationProposal.PROPOSE: 38.0,
            ReconciliationProposal.HOLD_BACK: -35.0,
        },
        response_modifiers={
            ReconciliationResponse.ACCEPT: 28.0,
            ReconciliationResponse.REPAIR_FIRST: 18.0,
            ReconciliationResponse.DEFER: -10.0,
            ReconciliationResponse.REFUSE: -30.0,
        },
        description=(
            "Strongly favors returning to the only beloved, but does not "
            "force the other Sim to accept."
        ),
    )
)


PROPOSER_PROPOSE_MODEL_KEY = (
    "core.relationship.reconciliation.proposal.propose.v1"
)
PROPOSER_HOLD_MODEL_KEY = (
    "core.relationship.reconciliation.proposal.hold_back.v1"
)
RECIPIENT_ACCEPT_MODEL_KEY = (
    "core.relationship.reconciliation.response.accept.v1"
)
RECIPIENT_REPAIR_MODEL_KEY = (
    "core.relationship.reconciliation.response.repair_first.v1"
)
RECIPIENT_DEFER_MODEL_KEY = (
    "core.relationship.reconciliation.response.defer.v1"
)
RECIPIENT_REFUSE_MODEL_KEY = (
    "core.relationship.reconciliation.response.refuse.v1"
)


PROPOSER_PROPOSE_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        PROPOSER_PROPOSE_MODEL_KEY,
        base=8.0,
        factors=(
            UtilityFactor("attachment", "state.attachment", 0.32),
            UtilityFactor("trust", "state.trust", 0.12),
            UtilityFactor("exclusivity", "state.exclusivity", 0.08),
            UtilityFactor("commitment", "state.commitment", 0.30),
            UtilityFactor(
                "low_boundary",
                "state.boundary",
                0.10,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "past_refusals",
                "history.reconciliation_refusals_received",
                -8.0,
                maximum=3.0,
            ),
        ),
    )
)

PROPOSER_HOLD_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        PROPOSER_HOLD_MODEL_KEY,
        base=10.0,
        factors=(
            UtilityFactor(
                "low_attachment",
                "state.attachment",
                0.30,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "distrust",
                "state.trust",
                0.18,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "low_commitment",
                "state.commitment",
                0.28,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor("boundary", "state.boundary", 0.16),
            UtilityFactor(
                "past_refusals",
                "history.reconciliation_refusals_received",
                8.0,
                maximum=3.0,
            ),
        ),
    )
)

RECIPIENT_ACCEPT_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        RECIPIENT_ACCEPT_MODEL_KEY,
        base=8.0,
        factors=(
            UtilityFactor("attachment", "state.attachment", 0.28),
            UtilityFactor("trust", "state.trust", 0.20),
            UtilityFactor("exclusivity", "state.exclusivity", 0.08),
            UtilityFactor("commitment", "state.commitment", 0.26),
            UtilityFactor(
                "low_boundary",
                "state.boundary",
                0.08,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "known_betrayals",
                "history.known_betrayal_count",
                -5.0,
                maximum=3.0,
            ),
            UtilityFactor(
                "broken_promises",
                "history.known_broken_promise_count",
                -6.0,
                maximum=3.0,
            ),
            UtilityFactor(
                "completed_requested_repair",
                "context.repair_case_satisfied",
                30.0,
                maximum=1.0,
            ),
            UtilityFactor(
                "recent_breakup_caution",
                "context.recipient_recently_confirmed_breakup",
                -70.0,
                maximum=1.0,
            ),
        ),
    )
)

RECIPIENT_REPAIR_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        RECIPIENT_REPAIR_MODEL_KEY,
        base=10.0,
        factors=(
            UtilityFactor("attachment", "state.attachment", 0.18),
            UtilityFactor("commitment", "state.commitment", 0.14),
            UtilityFactor(
                "distrust",
                "state.trust",
                0.22,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor("boundary", "state.boundary", 0.18),
            UtilityFactor(
                "known_betrayals",
                "history.known_betrayal_count",
                7.0,
                maximum=3.0,
            ),
            UtilityFactor(
                "broken_promises",
                "history.known_broken_promise_count",
                8.0,
                maximum=3.0,
            ),
        ),
        gates=(
            UtilityGate(
                "repair_requester_is_confirmed_accountable_party",
                "context.repair_request_valid",
                requirement=UtilityGate.REQUIRE_TRUE,
            ),
            UtilityGate(
                "requested_repair_already_satisfied",
                "context.repair_case_satisfied",
                requirement=UtilityGate.REQUIRE_FALSE,
            ),
        ),
    )
)

RECIPIENT_DEFER_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        RECIPIENT_DEFER_MODEL_KEY,
        base=4.0,
        factors=(
            UtilityFactor(
                "recent_breakup_caution",
                "context.recipient_recently_confirmed_breakup",
                48.0,
                maximum=1.0,
            ),
            UtilityFactor("attachment", "state.attachment", 0.10),
            UtilityFactor(
                "distrust",
                "state.trust",
                0.12,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor("boundary", "state.boundary", 0.12),
            UtilityFactor(
                "past_proposals",
                "history.reconciliation_proposals_received",
                3.0,
                maximum=3.0,
            ),
        ),
        gates=(
            UtilityGate(
                "no_recent_confirmed_breakup_to_cool_down_from",
                "context.recipient_recently_confirmed_breakup",
                requirement=UtilityGate.REQUIRE_TRUE,
            ),
        ),
    )
)

RECIPIENT_REFUSE_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        RECIPIENT_REFUSE_MODEL_KEY,
        base=8.0,
        factors=(
            UtilityFactor(
                "low_attachment",
                "state.attachment",
                0.30,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "low_commitment",
                "state.commitment",
                0.24,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "distrust",
                "state.trust",
                0.20,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor("boundary", "state.boundary", 0.20),
            UtilityFactor(
                "past_proposals",
                "history.reconciliation_proposals_received",
                3.0,
                maximum=3.0,
            ),
        ),
    )
)


class ReconciliationChoiceCandidate:

    def __init__(self, choice, utility):
        self.choice = str(choice)
        self.score = utility.score
        self.terms = utility.terms
        self.eligible = utility.eligible
        self.blockers = utility.blockers

    def as_dict(self):
        return {
            "choice": self.choice,
            "score": self.score,
            "terms": tuple(self.terms),
            "eligible": self.eligible,
            "blockers": tuple(self.blockers),
        }


class ReconciliationChoiceDecision:

    def __init__(self, selected, candidates, roll, total_score, forced=False):
        self.selected = str(selected)
        self.candidates = tuple(candidates)
        self.roll = float(roll)
        self.total_score = float(total_score)
        self.forced = bool(forced)

    def as_dict(self):
        return {
            "selected": self.selected,
            "roll": self.roll,
            "total_score": self.total_score,
            "forced": self.forced,
            "candidates": tuple(
                candidate.as_dict() for candidate in self.candidates
            ),
        }


class ReconciliationResult:

    def __init__(
        self,
        transaction_id,
        proposer_id,
        recipient_id,
        proposal_decision,
        response_decision,
        outcome,
        official_reconciliation_authorized,
    ):
        self.transaction_id = str(transaction_id)
        self.proposer_id = int(proposer_id)
        self.recipient_id = int(recipient_id)
        self.proposal_decision = proposal_decision
        self.response_decision = response_decision
        self.outcome = str(outcome)
        self.official_reconciliation_authorized = bool(
            official_reconciliation_authorized
        )

    @property
    def proposal(self):
        return self.proposal_decision.selected

    @property
    def response(self):
        if self.response_decision is None:
            return None
        return self.response_decision.selected

    @property
    def proposer_intent(self):
        if self.proposal == ReconciliationProposal.PROPOSE:
            return "restore_relationship"
        return "remain_apart"

    @property
    def recipient_intent(self):
        if self.response == ReconciliationResponse.ACCEPT:
            return "restore_relationship"
        if self.response == ReconciliationResponse.REPAIR_FIRST:
            return "repair_before_commitment"
        if self.response == ReconciliationResponse.DEFER:
            return "need_time_before_reconciliation"
        return "remain_apart"

    def as_dict(self):
        return {
            "transaction_id": self.transaction_id,
            "proposer_id": self.proposer_id,
            "recipient_id": self.recipient_id,
            "proposal": self.proposal,
            "proposal_decision": self.proposal_decision.as_dict(),
            "response": self.response,
            "response_decision": (
                None
                if self.response_decision is None
                else self.response_decision.as_dict()
            ),
            "outcome": self.outcome,
            "official_reconciliation_authorized": (
                self.official_reconciliation_authorized
            ),
            "proposer_intent": self.proposer_intent,
            "recipient_intent": self.recipient_intent,
        }


def _influence_terms(influences, choice, proposal=False):
    modifiers = []
    for influence in tuple(influences or ()):
        modifier = (
            influence.proposal_modifier(choice)
            if proposal
            else influence.response_modifier(choice)
        )
        if modifier:
            modifiers.append(modifier)
    return ((
        "personality_modifier",
        _clamp(sum(modifiers), -40.0, 40.0),
    ),)


def _candidate(choice, model, values, influences, proposal=False):
    return ReconciliationChoiceCandidate(
        choice,
        model.evaluate(
            values,
            extra_terms=_influence_terms(
                influences,
                choice,
                proposal=proposal,
            ),
        ),
    )


def _select(candidates, roll=None):
    eligible = tuple(
        candidate
        for candidate in candidates
        if candidate.eligible and candidate.score > 0.0
    )
    if not eligible:
        raise ValueError(
            "Reconciliation choice has no eligible positive candidate"
        )
    total = sum(candidate.score for candidate in eligible)
    normalized_roll = (
        random.random()
        if roll is None
        else _clamp(roll, 0.0, 0.999999)
    )
    cursor = normalized_roll * total
    selected = eligible[-1]
    running = 0.0
    for candidate in eligible:
        running += candidate.score
        if cursor < running:
            selected = candidate
            break
    return ReconciliationChoiceDecision(
        selected.choice,
        candidates,
        normalized_roll,
        total,
    )


def _force_proposal(decision):
    return ReconciliationChoiceDecision(
        ReconciliationProposal.PROPOSE,
        decision.candidates,
        decision.roll,
        decision.total_score,
        forced=True,
    )


def evaluate_reconciliation(
    transaction_id,
    proposer_id,
    recipient_id,
    proposer_state,
    recipient_state,
    proposer_history=None,
    recipient_history=None,
    proposer_influences=(),
    recipient_influences=(),
    recipient_context=None,
    proposal_roll=None,
    response_roll=None,
    force_proposal=False,
):
    """Evaluate a proposal and asymmetric response without touching EA."""
    proposer_values = {
        "state": normalize_directed_state(proposer_state),
        "history": dict(proposer_history or {}),
        "context": {},
    }
    proposal_candidates = (
        _candidate(
            ReconciliationProposal.PROPOSE,
            PROPOSER_PROPOSE_MODEL,
            proposer_values,
            proposer_influences,
            proposal=True,
        ),
        _candidate(
            ReconciliationProposal.HOLD_BACK,
            PROPOSER_HOLD_MODEL,
            proposer_values,
            proposer_influences,
            proposal=True,
        ),
    )
    proposal_decision = _select(
        proposal_candidates,
        roll=proposal_roll,
    )
    if force_proposal:
        proposal_decision = _force_proposal(proposal_decision)
    if proposal_decision.selected != ReconciliationProposal.PROPOSE:
        return ReconciliationResult(
            transaction_id,
            proposer_id,
            recipient_id,
            proposal_decision,
            None,
            ReconciliationOutcome.PROPOSAL_WITHHELD,
            False,
        )

    normalized_recipient_context = {
        "repair_request_valid": True,
        "recipient_recently_confirmed_breakup": False,
    }
    normalized_recipient_context.update(dict(recipient_context or {}))
    recipient_values = {
        "state": normalize_directed_state(recipient_state),
        "history": dict(recipient_history or {}),
        "context": normalized_recipient_context,
    }
    response_candidates = (
        _candidate(
            ReconciliationResponse.ACCEPT,
            RECIPIENT_ACCEPT_MODEL,
            recipient_values,
            recipient_influences,
        ),
        _candidate(
            ReconciliationResponse.REPAIR_FIRST,
            RECIPIENT_REPAIR_MODEL,
            recipient_values,
            recipient_influences,
        ),
        _candidate(
            ReconciliationResponse.DEFER,
            RECIPIENT_DEFER_MODEL,
            recipient_values,
            recipient_influences,
        ),
        _candidate(
            ReconciliationResponse.REFUSE,
            RECIPIENT_REFUSE_MODEL,
            recipient_values,
            recipient_influences,
        ),
    )
    response_decision = _select(
        response_candidates,
        roll=response_roll,
    )
    if response_decision.selected == ReconciliationResponse.ACCEPT:
        outcome = (
            ReconciliationOutcome.OFFICIAL_RECONCILIATION_AUTHORIZED
        )
        authorized = True
    elif response_decision.selected == ReconciliationResponse.REPAIR_FIRST:
        outcome = ReconciliationOutcome.REPAIR_REQUIRED
        authorized = False
    elif response_decision.selected == ReconciliationResponse.DEFER:
        outcome = ReconciliationOutcome.RECONCILIATION_DEFERRED
        authorized = False
    else:
        outcome = ReconciliationOutcome.RECONCILIATION_REFUSED
        authorized = False
    return ReconciliationResult(
        transaction_id,
        proposer_id,
        recipient_id,
        proposal_decision,
        response_decision,
        outcome,
        authorized,
    )

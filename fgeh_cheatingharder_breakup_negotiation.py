"""Pure, synchronous breakup negotiation for managed relationship edges.

The lower EA layer asks to end an official relationship.  This module does
not touch Sims, relationship bits, buffs, or UI.  It answers two directed
questions before that irreversible commit:

1. Does the recipient accept the proposal or ask the proposer to stay?
2. If asked to stay, does the proposer withdraw, delay, or insist?

The five relationship dimensions remain the stable input.  A negotiation is
a short-lived transaction and its outcome belongs in the event ledger, not in
a sixth relationship track.
"""

import random

from fgeh_cheatingharder_utility_model import (
    RELATIONSHIP_UTILITY_MODELS,
    UtilityCandidateDefinition,
    UtilityFactor,
)


DIRECTED_STATE_DEFAULTS = {
    "attachment": 68.0,
    "trust": 65.0,
    "exclusivity": 88.0,
    "commitment": 68.0,
    "boundary": 50.0,
}


class BreakupMotive:
    BETRAYAL_REACTION = "betrayal_reaction"
    FINAL_DECISION = "final_decision"
    EMOTIONAL_OUTBURST = "emotional_outburst"
    EXTERNAL_PRESSURE = "external_pressure"


class BreakupResponse:
    ACCEPT = "accept_breakup"
    REFUSE = "refuse_breakup"
    PLEAD = "plead_to_stay"


class BreakupFinalDecision:
    NOT_REQUIRED = "not_required"
    WITHDRAW = "withdraw_breakup"
    DELAY = "delay_breakup"
    INSIST = "confirm_breakup"


class BreakupNegotiationOutcome:
    OFFICIAL_BREAKUP_AUTHORIZED = "official_breakup_authorized"
    RELATIONSHIP_RETAINED = "relationship_retained"
    RELATIONSHIP_DELAYED = "relationship_delayed"


def _clamp(value, minimum, maximum):
    return max(float(minimum), min(float(maximum), float(value)))


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def normalize_directed_state(values):
    values = dict(values or {})
    return {
        dimension: _clamp(
            values.get(dimension, default),
            0.0,
            100.0,
        )
        for dimension, default in DIRECTED_STATE_DEFAULTS.items()
    }


class BreakupNegotiationInfluence:
    """Registered data-only modifiers for one personality bottom."""

    def __init__(
        self,
        key,
        response_modifiers=None,
        final_decision_modifiers=None,
        description="",
    ):
        self.key = str(key)
        self.response_modifiers = {
            str(choice): _clamp(value, -40.0, 40.0)
            for choice, value in dict(response_modifiers or {}).items()
        }
        self.final_decision_modifiers = {
            str(choice): _clamp(value, -40.0, 40.0)
            for choice, value in dict(
                final_decision_modifiers or {}
            ).items()
        }
        self.description = str(description)

    def response_modifier(self, choice):
        return self.response_modifiers.get(str(choice), 0.0)

    def final_modifier(self, choice):
        return self.final_decision_modifiers.get(str(choice), 0.0)


class BreakupNegotiationInfluenceRegistry:

    def __init__(self):
        self._definitions = {}

    def register(self, definition):
        if not isinstance(definition, BreakupNegotiationInfluence):
            raise TypeError(
                "definition must be BreakupNegotiationInfluence"
            )
        if definition.key in self._definitions:
            raise ValueError(
                "Breakup influence already registered: {}".format(
                    definition.key
                )
            )
        self._definitions[definition.key] = definition
        return definition

    def get(self, key, default=None):
        return self._definitions.get(str(key), default)

    def keys(self):
        return tuple(sorted(self._definitions))


BREAKUP_NEGOTIATION_INFLUENCES = (
    BreakupNegotiationInfluenceRegistry()
)
PERMANENT_DEVOTION_INFLUENCE = (
    BREAKUP_NEGOTIATION_INFLUENCES.register(
        BreakupNegotiationInfluence(
            "permanent_devotion",
            response_modifiers={
                BreakupResponse.ACCEPT: -35.0,
                BreakupResponse.REFUSE: 18.0,
                BreakupResponse.PLEAD: 35.0,
            },
            final_decision_modifiers={
                BreakupFinalDecision.WITHDRAW: 20.0,
                BreakupFinalDecision.DELAY: 10.0,
                BreakupFinalDecision.INSIST: -30.0,
            },
            description=(
                "Strongly resists losing the beloved without granting an "
                "infinite veto over the other Sim's final decision."
            ),
        )
    )
)


class BreakupMotiveDefinition:

    def __init__(
        self,
        key,
        response_modifiers=None,
        final_decision_modifiers=None,
    ):
        self.key = str(key)
        self.response_modifiers = {
            str(choice): _number(value)
            for choice, value in dict(response_modifiers or {}).items()
        }
        self.final_decision_modifiers = {
            str(choice): _number(value)
            for choice, value in dict(
                final_decision_modifiers or {}
            ).items()
        }

    def response_modifier(self, choice):
        return self.response_modifiers.get(str(choice), 0.0)

    def final_modifier(self, choice):
        return self.final_decision_modifiers.get(str(choice), 0.0)


class BreakupMotiveRegistry:

    def __init__(self):
        self._definitions = {}

    def register(self, definition):
        if definition.key in self._definitions:
            raise ValueError(
                "Breakup motive already registered: {}".format(
                    definition.key
                )
            )
        self._definitions[definition.key] = definition
        return definition

    def get(self, key):
        return self._definitions.get(
            str(key),
            self._definitions[BreakupMotive.EXTERNAL_PRESSURE],
        )


BREAKUP_MOTIVES = BreakupMotiveRegistry()
for _motive in (
    BreakupMotiveDefinition(
        BreakupMotive.BETRAYAL_REACTION,
        response_modifiers={BreakupResponse.ACCEPT: 4.0},
        final_decision_modifiers={
            BreakupFinalDecision.DELAY: 12.0,
            BreakupFinalDecision.INSIST: 8.0,
        },
    ),
    BreakupMotiveDefinition(
        BreakupMotive.FINAL_DECISION,
        response_modifiers={BreakupResponse.ACCEPT: 8.0},
        final_decision_modifiers={
            BreakupFinalDecision.WITHDRAW: -15.0,
            BreakupFinalDecision.DELAY: -10.0,
            BreakupFinalDecision.INSIST: 25.0,
        },
    ),
    BreakupMotiveDefinition(
        BreakupMotive.EMOTIONAL_OUTBURST,
        response_modifiers={BreakupResponse.PLEAD: 5.0},
        final_decision_modifiers={
            BreakupFinalDecision.WITHDRAW: 10.0,
            BreakupFinalDecision.DELAY: 15.0,
            BreakupFinalDecision.INSIST: -5.0,
        },
    ),
    BreakupMotiveDefinition(BreakupMotive.EXTERNAL_PRESSURE),
):
    BREAKUP_MOTIVES.register(_motive)


RECIPIENT_ACCEPT_MODEL_KEY = (
    "core.relationship.breakup_response.accept.v1"
)
RECIPIENT_REFUSE_MODEL_KEY = (
    "core.relationship.breakup_response.refuse.v1"
)
RECIPIENT_PLEAD_MODEL_KEY = (
    "core.relationship.breakup_response.plead.v1"
)
PROPOSER_WITHDRAW_MODEL_KEY = (
    "core.relationship.breakup_final.withdraw.v1"
)
PROPOSER_DELAY_MODEL_KEY = "core.relationship.breakup_final.delay.v1"
PROPOSER_INSIST_MODEL_KEY = "core.relationship.breakup_final.insist.v1"


RECIPIENT_ACCEPT_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        RECIPIENT_ACCEPT_MODEL_KEY,
        base=12.0,
        factors=(
            UtilityFactor("boundary", "state.boundary", 0.28),
            UtilityFactor(
                "distrust",
                "state.trust",
                0.16,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "low_attachment",
                "state.attachment",
                0.25,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "low_commitment",
                "state.commitment",
                0.22,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "past_proposals_received",
                "history.breakup_proposals_received",
                4.0,
                maximum=5.0,
            ),
        ),
    )
)

RECIPIENT_REFUSE_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        RECIPIENT_REFUSE_MODEL_KEY,
        base=8.0,
        factors=(
            UtilityFactor("commitment", "state.commitment", 0.24),
            UtilityFactor("exclusivity", "state.exclusivity", 0.16),
            UtilityFactor("boundary", "state.boundary", 0.12),
            UtilityFactor("attachment", "state.attachment", 0.12),
            UtilityFactor(
                "past_proposals_received",
                "history.breakup_proposals_received",
                2.0,
                maximum=5.0,
            ),
        ),
    )
)

RECIPIENT_PLEAD_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        RECIPIENT_PLEAD_MODEL_KEY,
        base=8.0,
        factors=(
            UtilityFactor("attachment", "state.attachment", 0.34),
            UtilityFactor("commitment", "state.commitment", 0.25),
            UtilityFactor("exclusivity", "state.exclusivity", 0.12),
            UtilityFactor("remaining_trust", "state.trust", 0.08),
            UtilityFactor(
                "low_boundary",
                "state.boundary",
                0.18,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
        ),
    )
)

PROPOSER_WITHDRAW_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        PROPOSER_WITHDRAW_MODEL_KEY,
        base=8.0,
        factors=(
            UtilityFactor("attachment", "state.attachment", 0.28),
            UtilityFactor("commitment", "state.commitment", 0.22),
            UtilityFactor("remaining_trust", "state.trust", 0.08),
            UtilityFactor(
                "plea_strength",
                "context.plea_strength",
                0.20,
            ),
        ),
    )
)

PROPOSER_DELAY_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        PROPOSER_DELAY_MODEL_KEY,
        base=10.0,
        factors=(
            UtilityFactor("attachment", "state.attachment", 0.15),
            UtilityFactor("commitment", "state.commitment", 0.12),
            UtilityFactor(
                "distrust",
                "state.trust",
                0.08,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor("boundary", "state.boundary", 0.08),
            UtilityFactor(
                "plea_strength",
                "context.plea_strength",
                0.18,
            ),
        ),
    )
)

PROPOSER_INSIST_MODEL = RELATIONSHIP_UTILITY_MODELS.register(
    UtilityCandidateDefinition(
        PROPOSER_INSIST_MODEL_KEY,
        base=8.0,
        factors=(
            UtilityFactor("boundary", "state.boundary", 0.26),
            UtilityFactor(
                "distrust",
                "state.trust",
                0.20,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "low_attachment",
                "state.attachment",
                0.22,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "low_commitment",
                "state.commitment",
                0.18,
                transform=UtilityFactor.INVERSE_PERCENT,
            ),
            UtilityFactor(
                "known_betrayals",
                "history.known_betrayal_count",
                8.0,
                maximum=3.0,
            ),
            UtilityFactor(
                "broken_promises",
                "history.known_broken_promise_count",
                10.0,
                maximum=3.0,
            ),
        ),
    )
)


class BreakupChoiceCandidate:

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


class BreakupChoiceDecision:

    def __init__(self, selected, candidates, roll, total_score):
        self.selected = str(selected)
        self.candidates = tuple(candidates)
        self.roll = float(roll)
        self.total_score = float(total_score)

    @property
    def selected_score(self):
        for candidate in self.candidates:
            if candidate.choice == self.selected:
                return candidate.score
        return 0.0

    def as_dict(self):
        return {
            "selected": self.selected,
            "roll": self.roll,
            "total_score": self.total_score,
            "candidates": tuple(
                candidate.as_dict() for candidate in self.candidates
            ),
        }


class BreakupNegotiationResult:

    def __init__(
        self,
        transaction_id,
        proposer_id,
        recipient_id,
        motive,
        response_decision,
        final_decision,
        outcome,
        official_breakup_authorized,
    ):
        self.transaction_id = str(transaction_id)
        self.proposer_id = int(proposer_id)
        self.recipient_id = int(recipient_id)
        self.motive = str(motive)
        self.response_decision = response_decision
        self.final_decision = final_decision
        self.outcome = str(outcome)
        self.official_breakup_authorized = bool(
            official_breakup_authorized
        )

    @property
    def response(self):
        return self.response_decision.selected

    @property
    def proposer_decision(self):
        if self.final_decision is None:
            return BreakupFinalDecision.NOT_REQUIRED
        return self.final_decision.selected

    @property
    def proposer_intent(self):
        if self.official_breakup_authorized:
            return "leave"
        if self.outcome == BreakupNegotiationOutcome.RELATIONSHIP_DELAYED:
            return "uncertain"
        return "repair"

    @property
    def recipient_intent(self):
        if self.response == BreakupResponse.ACCEPT:
            return "accept_end"
        if self.official_breakup_authorized:
            return "deny_breakup"
        if self.response == BreakupResponse.REFUSE:
            return "reject_end"
        return "repair"

    def as_dict(self):
        return {
            "transaction_id": self.transaction_id,
            "proposer_id": self.proposer_id,
            "recipient_id": self.recipient_id,
            "motive": self.motive,
            "response": self.response,
            "response_decision": self.response_decision.as_dict(),
            "proposer_decision": self.proposer_decision,
            "final_decision": (
                None
                if self.final_decision is None
                else self.final_decision.as_dict()
            ),
            "outcome": self.outcome,
            "official_breakup_authorized": (
                self.official_breakup_authorized
            ),
            "proposer_intent": self.proposer_intent,
            "recipient_intent": self.recipient_intent,
        }


def _influence_term(influences, choice, final=False):
    values = []
    for influence in tuple(influences or ()):
        modifier = (
            influence.final_modifier(choice)
            if final
            else influence.response_modifier(choice)
        )
        if modifier:
            values.append(modifier)
    total = _clamp(
        sum(values),
        -40.0,
        40.0,
    )
    return (("personality_modifier", total),)


def _candidate(
    choice,
    model,
    values,
    motive,
    influences,
    final=False,
):
    motive_definition = BREAKUP_MOTIVES.get(motive)
    motive_modifier = (
        motive_definition.final_modifier(choice)
        if final
        else motive_definition.response_modifier(choice)
    )
    extra_terms = (("motive:{}".format(motive), motive_modifier),)
    extra_terms += _influence_term(
        influences,
        choice,
        final=final,
    )
    return BreakupChoiceCandidate(
        choice,
        model.evaluate(values, extra_terms=extra_terms),
    )


def _select(candidates, roll=None):
    eligible = tuple(
        candidate
        for candidate in candidates
        if candidate.eligible and candidate.score > 0.0
    )
    if not eligible:
        raise ValueError("Breakup choice has no eligible positive candidate")
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
    return BreakupChoiceDecision(
        selected.choice,
        candidates,
        normalized_roll,
        total,
    )


def evaluate_breakup_negotiation(
    transaction_id,
    proposer_id,
    recipient_id,
    proposer_state,
    recipient_state,
    motive=BreakupMotive.EXTERNAL_PRESSURE,
    proposer_history=None,
    recipient_history=None,
    proposer_influences=(),
    recipient_influences=(),
    response_roll=None,
    final_roll=None,
    forced_response=None,
):
    """Resolve one complete proposal without touching the lower EA layer."""
    proposer_state = normalize_directed_state(proposer_state)
    recipient_state = normalize_directed_state(recipient_state)
    response_values = {
        "state": recipient_state,
        "history": dict(recipient_history or {}),
        "context": {},
    }
    response_candidates = (
        _candidate(
            BreakupResponse.ACCEPT,
            RECIPIENT_ACCEPT_MODEL,
            response_values,
            motive,
            recipient_influences,
        ),
        _candidate(
            BreakupResponse.REFUSE,
            RECIPIENT_REFUSE_MODEL,
            response_values,
            motive,
            recipient_influences,
        ),
        _candidate(
            BreakupResponse.PLEAD,
            RECIPIENT_PLEAD_MODEL,
            response_values,
            motive,
            recipient_influences,
        ),
    )
    if forced_response in (
        BreakupResponse.ACCEPT,
        BreakupResponse.REFUSE,
        BreakupResponse.PLEAD,
    ):
        response_decision = BreakupChoiceDecision(
            forced_response,
            response_candidates,
            -1.0,
            sum(
                max(0.0, candidate.score)
                for candidate in response_candidates
                if candidate.eligible
            ),
        )
    else:
        response_decision = _select(response_candidates, roll=response_roll)
    if response_decision.selected == BreakupResponse.ACCEPT:
        return BreakupNegotiationResult(
            transaction_id,
            proposer_id,
            recipient_id,
            motive,
            response_decision,
            None,
            BreakupNegotiationOutcome.OFFICIAL_BREAKUP_AUTHORIZED,
            True,
        )

    plea_strength = _clamp(
        response_decision.selected_score
        * 100.0
        / max(1.0, response_decision.total_score),
        0.0,
        100.0,
    )
    final_values = {
        "state": proposer_state,
        "history": dict(proposer_history or {}),
        "context": {"plea_strength": plea_strength},
    }
    final_candidates = (
        _candidate(
            BreakupFinalDecision.WITHDRAW,
            PROPOSER_WITHDRAW_MODEL,
            final_values,
            motive,
            proposer_influences,
            final=True,
        ),
        _candidate(
            BreakupFinalDecision.DELAY,
            PROPOSER_DELAY_MODEL,
            final_values,
            motive,
            proposer_influences,
            final=True,
        ),
        _candidate(
            BreakupFinalDecision.INSIST,
            PROPOSER_INSIST_MODEL,
            final_values,
            motive,
            proposer_influences,
            final=True,
        ),
    )
    final_decision = _select(final_candidates, roll=final_roll)
    if final_decision.selected == BreakupFinalDecision.INSIST:
        outcome = (
            BreakupNegotiationOutcome.OFFICIAL_BREAKUP_AUTHORIZED
        )
        authorized = True
    elif final_decision.selected == BreakupFinalDecision.DELAY:
        outcome = BreakupNegotiationOutcome.RELATIONSHIP_DELAYED
        authorized = False
    else:
        outcome = BreakupNegotiationOutcome.RELATIONSHIP_RETAINED
        authorized = False
    return BreakupNegotiationResult(
        transaction_id,
        proposer_id,
        recipient_id,
        motive,
        response_decision,
        final_decision,
        outcome,
        authorized,
    )


def force_breakup_final_decision(result, final_choice):
    """Resolve a player's second-stage choice without rerolling the response.

    The recipient's first reaction remains model-owned.  This helper changes
    only the proposer's final decision after a refusal or plea, preserving the
    scored candidates for ledger/debug explanations.
    """
    if result.response == BreakupResponse.ACCEPT:
        return result
    if result.final_decision is None:
        raise ValueError("Breakup result has no final-decision candidates")
    final_choice = str(final_choice)
    if final_choice not in (
        BreakupFinalDecision.WITHDRAW,
        BreakupFinalDecision.DELAY,
        BreakupFinalDecision.INSIST,
    ):
        raise ValueError("Unsupported breakup final choice: {}".format(
            final_choice
        ))
    final_decision = BreakupChoiceDecision(
        final_choice,
        result.final_decision.candidates,
        result.final_decision.roll,
        result.final_decision.total_score,
    )
    if final_choice == BreakupFinalDecision.INSIST:
        outcome = BreakupNegotiationOutcome.OFFICIAL_BREAKUP_AUTHORIZED
        authorized = True
    elif final_choice == BreakupFinalDecision.DELAY:
        outcome = BreakupNegotiationOutcome.RELATIONSHIP_DELAYED
        authorized = False
    else:
        outcome = BreakupNegotiationOutcome.RELATIONSHIP_RETAINED
        authorized = False
    return BreakupNegotiationResult(
        result.transaction_id,
        result.proposer_id,
        result.recipient_id,
        result.motive,
        result.response_decision,
        final_decision,
        outcome,
        authorized,
    )

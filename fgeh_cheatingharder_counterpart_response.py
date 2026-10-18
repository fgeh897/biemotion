"""Pure counterpart responses to a betrayal-driven relationship action.

The injured Sim decides what to do first.  This model answers the separate
question of how the partner responds once reassurance, confrontation, or
closeness actually reaches them.  It contains no Sims 4 imports so the scores
and directed consequences can be tested outside the game.
"""

import random


class CounterpartResponse:

    GAVE_REASSURANCE = "gave_reassurance"
    EVADED_REASSURANCE = "evaded_reassurance"
    REFUSED_REASSURANCE = "refused_reassurance"

    APOLOGIZED = "apologized"
    DEFLECTED = "deflected"
    COUNTERATTACKED = "counterattacked"
    WITHDREW = "withdrew"

    RECIPROCATED_CLOSENESS = "reciprocated_closeness"
    ACCEPTED_CAUTIOUSLY = "accepted_cautiously"
    PULLED_AWAY = "pulled_away"


_RESPONSE_EFFECTS = {
    CounterpartResponse.GAVE_REASSURANCE: (
        {"trust": 6, "attachment": 2},
        {"commitment": 1},
    ),
    CounterpartResponse.EVADED_REASSURANCE: (
        {"trust": -3, "boundary": 2},
        {"boundary": 1},
    ),
    CounterpartResponse.REFUSED_REASSURANCE: (
        {"trust": -5, "attachment": -2, "boundary": 4},
        {"attachment": -1, "commitment": -1, "boundary": 2},
    ),
    CounterpartResponse.APOLOGIZED: (
        {"trust": 3, "attachment": 1, "boundary": -1},
        {"commitment": 2},
    ),
    CounterpartResponse.DEFLECTED: (
        {"trust": -4, "boundary": 3},
        {"boundary": 1},
    ),
    CounterpartResponse.COUNTERATTACKED: (
        {"trust": -6, "attachment": -3, "boundary": 5},
        {"trust": -2, "attachment": -2, "boundary": 3},
    ),
    CounterpartResponse.WITHDREW: (
        {"trust": -3, "attachment": -2, "boundary": 3},
        {"attachment": -2, "commitment": -2, "boundary": 2},
    ),
    CounterpartResponse.RECIPROCATED_CLOSENESS: (
        {"trust": 2, "attachment": 4},
        {"attachment": 2, "commitment": 1},
    ),
    CounterpartResponse.ACCEPTED_CAUTIOUSLY: (
        {"attachment": 1},
        {"attachment": 1},
    ),
    CounterpartResponse.PULLED_AWAY: (
        {"trust": -2, "attachment": -4, "boundary": 3},
        {"attachment": -2, "commitment": -1, "boundary": 2},
    ),
}


def _clamp_percent(value, default=50.0):
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return float(default)


def _state_value(state, key):
    try:
        return _clamp_percent(state.get(key, 50.0))
    except Exception:
        return 50.0


def _known_betrayals(history):
    try:
        value = dict(history or {}).get("known_betrayal_count", 0)
        return max(0.0, min(5.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


class CounterpartResponseCandidate:

    def __init__(self, response, score, terms=None):
        self.response = str(response)
        self.score = max(0.1, float(score))
        self.terms = tuple(terms or ())

    def as_dict(self):
        return {
            "response": self.response,
            "score": self.score,
            "terms": tuple(self.terms),
        }


class CounterpartResponseEvaluation:

    def __init__(self, intent, candidates, roll, selected_response):
        self.intent = str(intent)
        self.candidates = tuple(candidates or ())
        self.roll = float(roll)
        self.selected_response = str(selected_response)

    @property
    def selected_candidate(self):
        return next(
            (
                candidate
                for candidate in self.candidates
                if candidate.response == self.selected_response
            ),
            None,
        )

    def as_dict(self):
        injured, responder = _RESPONSE_EFFECTS.get(
            self.selected_response,
            ({}, {}),
        )
        return {
            "intent": self.intent,
            "selected_response": self.selected_response,
            "roll": self.roll,
            "candidates": tuple(
                candidate.as_dict() for candidate in self.candidates
            ),
            "injured_state_deltas": dict(injured),
            "responder_state_deltas": dict(responder),
        }


def _candidate(response, base, terms):
    return CounterpartResponseCandidate(
        response,
        float(base) + sum(float(value) for _name, value in terms),
        terms=(("base", float(base)),) + tuple(terms),
    )


def build_counterpart_response_candidates(
    intent,
    responder_state,
    injured_history=None,
):
    """Build response utilities from the responder's directed relationship."""
    intent = str(intent)
    attachment = _state_value(responder_state, "attachment")
    trust = _state_value(responder_state, "trust")
    commitment = _state_value(responder_state, "commitment")
    boundary = _state_value(responder_state, "boundary")
    betrayals = _known_betrayals(injured_history)
    if intent == "seek_reassurance":
        return (
            _candidate(CounterpartResponse.GAVE_REASSURANCE, 12, (
                ("attachment", attachment * 0.22),
                ("commitment", commitment * 0.24),
                ("trust", trust * 0.08),
                ("repeat_betrayal", betrayals * -4.0),
            )),
            _candidate(CounterpartResponse.EVADED_REASSURANCE, 10, (
                ("boundary", boundary * 0.12),
                ("distrust", (100.0 - trust) * 0.08),
                ("repeat_betrayal", betrayals * 3.0),
            )),
            _candidate(CounterpartResponse.REFUSED_REASSURANCE, 4, (
                ("boundary", boundary * 0.18),
                ("low_attachment", (100.0 - attachment) * 0.10),
                ("repeat_betrayal", betrayals * 4.0),
            )),
        )
    if intent == "confront_partner":
        return (
            _candidate(CounterpartResponse.APOLOGIZED, 10, (
                ("attachment", attachment * 0.18),
                ("commitment", commitment * 0.18),
                ("trust", trust * 0.08),
                ("repeat_betrayal", betrayals * -4.0),
            )),
            _candidate(CounterpartResponse.DEFLECTED, 12, (
                ("boundary", boundary * 0.10),
                ("distrust", (100.0 - trust) * 0.06),
                ("repeat_betrayal", betrayals * 3.0),
            )),
            _candidate(CounterpartResponse.COUNTERATTACKED, 4, (
                ("boundary", boundary * 0.15),
                ("low_attachment", (100.0 - attachment) * 0.08),
                ("repeat_betrayal", betrayals * 2.0),
            )),
            _candidate(CounterpartResponse.WITHDREW, 6, (
                ("low_commitment", (100.0 - commitment) * 0.12),
                ("boundary", boundary * 0.10),
                ("repeat_betrayal", betrayals * 2.0),
            )),
        )
    if intent == "cling_to_partner":
        return (
            _candidate(CounterpartResponse.RECIPROCATED_CLOSENESS, 12, (
                ("attachment", attachment * 0.26),
                ("commitment", commitment * 0.18),
                ("soft_boundary", (100.0 - boundary) * 0.08),
                ("repeat_betrayal", betrayals * -3.0),
            )),
            _candidate(CounterpartResponse.ACCEPTED_CAUTIOUSLY, 14, (
                ("trust", trust * 0.08),
                ("boundary", boundary * 0.10),
                ("repeat_betrayal", betrayals * 2.0),
            )),
            _candidate(CounterpartResponse.PULLED_AWAY, 4, (
                ("low_attachment", (100.0 - attachment) * 0.18),
                ("boundary", boundary * 0.18),
                ("repeat_betrayal", betrayals * 4.0),
            )),
        )
    return ()


def evaluate_counterpart_response(
    intent,
    responder_state,
    injured_history=None,
    rng=None,
):
    candidates = build_counterpart_response_candidates(
        intent,
        responder_state,
        injured_history=injured_history,
    )
    if not candidates:
        return None
    random_source = rng or random.random
    roll = max(0.0, min(0.999999999, float(random_source())))
    total = sum(candidate.score for candidate in candidates)
    cursor = roll * total
    selected = candidates[-1]
    for candidate in candidates:
        cursor -= candidate.score
        if cursor < 0.0:
            selected = candidate
            break
    return CounterpartResponseEvaluation(
        intent,
        candidates,
        roll,
        selected.response,
    )

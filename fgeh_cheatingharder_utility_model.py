"""Reusable, declarative utility scoring for relationship behavior candidates.

Event adapters provide facts.  Interpretation rules provide subjective values.
This module only turns already-derived state, history, interpretation, and
context values into an auditable score plus eligibility blockers.
"""


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _resolve(values, path, default=0.0):
    current = values
    for part in str(path).split("."):
        current = _mapping(current).get(part)
        if current is None:
            return default
    return current


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


class UtilityFactor:

    IDENTITY = "identity"
    INVERSE_PERCENT = "inverse_percent"

    def __init__(
        self,
        key,
        value_path,
        weight,
        transform=IDENTITY,
        minimum=None,
        maximum=None,
    ):
        self.key = str(key)
        self.value_path = str(value_path)
        self.weight = float(weight)
        self.transform = str(transform)
        self.minimum = minimum
        self.maximum = maximum

    def contribution(self, values):
        value = _number(_resolve(values, self.value_path, 0.0))
        if self.minimum is not None:
            value = max(float(self.minimum), value)
        if self.maximum is not None:
            value = min(float(self.maximum), value)
        if self.transform == self.INVERSE_PERCENT:
            value = 100.0 - value
        elif self.transform != self.IDENTITY:
            raise ValueError(
                "Unknown utility transform: {}".format(self.transform)
            )
        return value * self.weight


class UtilityGate:

    REQUIRE_TRUE = "require_true"
    REQUIRE_FALSE = "require_false"

    def __init__(self, key, value_path, requirement=REQUIRE_TRUE):
        self.key = str(key)
        self.value_path = str(value_path)
        self.requirement = str(requirement)

    def blocker(self, values):
        value = bool(_resolve(values, self.value_path, False))
        if self.requirement == self.REQUIRE_TRUE:
            passed = value
        elif self.requirement == self.REQUIRE_FALSE:
            passed = not value
        else:
            raise ValueError(
                "Unknown utility gate requirement: {}".format(
                    self.requirement
                )
            )
        return None if passed else self.key


class UtilityScore:

    def __init__(self, score, terms, eligible, blockers):
        self.score = max(0.0, float(score))
        self.terms = tuple(terms or ())
        self.eligible = bool(eligible)
        self.blockers = tuple(str(value) for value in (blockers or ()))

    def as_dict(self):
        return {
            "score": self.score,
            "terms": tuple(self.terms),
            "eligible": self.eligible,
            "blockers": tuple(self.blockers),
        }


class UtilityCandidateDefinition:

    def __init__(self, key, base=0.0, factors=None, gates=None):
        self.key = str(key)
        self.base = float(base)
        self.factors = tuple(factors or ())
        self.gates = tuple(gates or ())

    def evaluate(self, values, extra_terms=None):
        blockers = tuple(
            blocker
            for blocker in (
                gate.blocker(values) for gate in self.gates
            )
            if blocker is not None
        )
        terms = [("base", self.base)]
        terms.extend(
            (factor.key, factor.contribution(values))
            for factor in self.factors
        )
        terms.extend(tuple(extra_terms or ()))
        eligible = not blockers
        return UtilityScore(
            sum(value for _key, value in terms) if eligible else 0.0,
            terms,
            eligible,
            blockers,
        )


class UtilityModelRegistry:

    def __init__(self):
        self._definitions = {}

    def register(self, definition):
        key = str(definition.key)
        if key in self._definitions:
            raise ValueError(
                "Utility candidate definition already registered: {}".format(
                    key
                )
            )
        self._definitions[key] = definition
        return definition

    def get(self, key, default=None):
        return self._definitions.get(str(key), default)

    def require(self, key):
        definition = self.get(key)
        if definition is None:
            raise KeyError(
                "Unknown utility candidate definition: {}".format(key)
            )
        return definition

    def keys(self):
        return tuple(sorted(self._definitions))


RELATIONSHIP_UTILITY_MODELS = UtilityModelRegistry()

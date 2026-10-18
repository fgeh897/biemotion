"""Pure definitions for memory-driven autonomous relationship behaviors.

The registry deliberately contains no Sims 4 imports.  It describes why an
action is allowed to reach a particular executor while the runtime owns EA
objects, alarms, queues, and interaction outcomes.
"""


class BehaviorExecutionStrategy:
    PROFILED_SOCIAL = "profiled_social"
    CUSTOM_HANDLER = "custom_handler"

    ALL = (PROFILED_SOCIAL, CUSTOM_HANDLER)


class AffordanceSelectionProfile:

    def __init__(
        self,
        key,
        weights,
        exclusions=(),
        require_social=True,
        minimum_score=1.0,
        fallback_mixer_ids=(),
    ):
        self.key = str(key)
        self.weights = tuple(
            (str(marker).lower(), float(weight))
            for marker, weight in tuple(weights or ())
        )
        self.exclusions = tuple(
            str(marker).lower()
            for marker in tuple(exclusions or ())
        )
        self.require_social = bool(require_social)
        self.minimum_score = float(minimum_score)
        self.fallback_mixer_ids = tuple(
            int(value) for value in tuple(fallback_mixer_ids or ())
        )
        if not self.key:
            raise ValueError("Affordance profile key cannot be empty.")
        if not self.weights:
            raise ValueError(
                "Affordance profile requires at least one weighted marker."
            )

    def score_name(self, affordance_name):
        normalized = str(affordance_name or "").lower()
        if any(marker in normalized for marker in self.exclusions):
            return None
        score = 0.0
        for marker, weight in self.weights:
            if marker in normalized:
                score = max(score, weight)
        return score if score >= self.minimum_score else None

    def to_data(self):
        return {
            "key": self.key,
            "weights": self.weights,
            "exclusions": self.exclusions,
            "require_social": self.require_social,
            "minimum_score": self.minimum_score,
            "fallback_mixer_ids": self.fallback_mixer_ids,
        }


class AutonomousBehaviorDefinition:

    def __init__(
        self,
        opportunity_type,
        intent,
        execution_strategy,
        affordance_profile=None,
        cooldown_minutes=0.0,
        cooldown_timestamp_key=None,
        retryable_statuses=(
            "pair_not_together",
            "observer_unavailable",
        ),
        no_candidate_status=None,
    ):
        self.opportunity_type = str(opportunity_type)
        self.intent = str(intent)
        self.execution_strategy = str(execution_strategy)
        self.affordance_profile = affordance_profile
        self.cooldown_minutes = max(0.0, float(cooldown_minutes))
        self.cooldown_timestamp_key = (
            None
            if cooldown_timestamp_key is None
            else str(cooldown_timestamp_key)
        )
        self.retryable_statuses = tuple(
            str(value) for value in tuple(retryable_statuses or ())
        )
        self.no_candidate_status = str(
            no_candidate_status
            or "no_safe_{}_affordance".format(self.intent)
        )
        if not self.opportunity_type or not self.intent:
            raise ValueError(
                "Behavior opportunity type and intent cannot be empty."
            )
        if self.execution_strategy not in BehaviorExecutionStrategy.ALL:
            raise ValueError(
                "Unknown behavior execution strategy: {}".format(
                    self.execution_strategy
                )
            )
        if (
            self.execution_strategy
            == BehaviorExecutionStrategy.PROFILED_SOCIAL
            and not isinstance(
                self.affordance_profile,
                AffordanceSelectionProfile,
            )
        ):
            raise ValueError(
                "Profiled social behavior requires an affordance profile."
            )

    @property
    def key(self):
        return (self.opportunity_type, self.intent)

    def to_data(self):
        return {
            "opportunity_type": self.opportunity_type,
            "intent": self.intent,
            "execution_strategy": self.execution_strategy,
            "affordance_profile": (
                None
                if self.affordance_profile is None
                else self.affordance_profile.key
            ),
            "cooldown_minutes": self.cooldown_minutes,
            "cooldown_timestamp_key": self.cooldown_timestamp_key,
            "retryable_statuses": self.retryable_statuses,
            "no_candidate_status": self.no_candidate_status,
        }


class AutonomousBehaviorRegistry:

    def __init__(self):
        self._definitions = {}

    def register(self, definition):
        if not isinstance(definition, AutonomousBehaviorDefinition):
            raise TypeError(
                "Expected AutonomousBehaviorDefinition, got {!r}".format(
                    type(definition)
                )
            )
        current = self._definitions.get(definition.key)
        if current is not None and current is not definition:
            raise ValueError(
                "Autonomous behavior already registered: {}".format(
                    definition.key
                )
            )
        self._definitions[definition.key] = definition
        return definition

    def get(self, opportunity_type, intent):
        return self._definitions.get((
            str(opportunity_type),
            str(intent),
        ))

    def require(self, opportunity_type, intent):
        definition = self.get(opportunity_type, intent)
        if definition is None:
            raise KeyError(
                "Unknown autonomous behavior: {}".format((
                    str(opportunity_type),
                    str(intent),
                ))
            )
        return definition

    def keys(self):
        return tuple(sorted(self._definitions))

    def definitions(self):
        return tuple(
            self._definitions[key]
            for key in sorted(self._definitions)
        )

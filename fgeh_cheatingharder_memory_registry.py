"""Explicit extension points for the romantic memory processing pipeline."""


class DuplicateRegistrationError(ValueError):
    pass


class EventDefinition:

    def __init__(
        self,
        event_type,
        description="",
        version=1,
        semantic_tags=(),
        default_severity=0,
    ):
        self.event_type = str(event_type)
        self.description = str(description)
        self.version = int(version)
        self.semantic_tags = tuple(dict.fromkeys(
            str(value) for value in tuple(semantic_tags or ())
        ))
        try:
            default_severity = float(default_severity)
        except (TypeError, ValueError):
            default_severity = 0.0
        self.default_severity = max(0.0, min(100.0, default_severity))


class RuleRegistration:

    def __init__(
        self,
        stage,
        key,
        callback,
        event_types=None,
        priority=0,
        version=1,
    ):
        self.stage = str(stage)
        self.key = str(key)
        self.callback = callback
        self.event_types = (
            None
            if event_types is None
            else frozenset(str(value) for value in event_types)
        )
        self.priority = int(priority)
        self.version = int(version)

    @property
    def consumer_id(self):
        return "{}:{}".format(self.stage, self.key)

    def accepts(self, event_type):
        return self.event_types is None or str(event_type) in self.event_types


class RomanticMemoryRegistry:
    """Registry owned by one runtime; importing a module does not mutate it."""

    CLAIM_STAGE = "claim"
    KNOWLEDGE_STAGE = "knowledge"
    INTERPRETATION_STAGE = "interpretation"
    STATE_STAGE = "state"
    SUMMARY_STAGE = "summary"
    OPPORTUNITY_STAGE = "opportunity"

    STAGES = (
        CLAIM_STAGE,
        KNOWLEDGE_STAGE,
        INTERPRETATION_STAGE,
        STATE_STAGE,
        SUMMARY_STAGE,
        OPPORTUNITY_STAGE,
    )

    def __init__(self):
        self._event_definitions = {}
        self._rules = {stage: [] for stage in self.STAGES}
        self._rule_keys = set()

    def register_event_definition(self, definition):
        if not isinstance(definition, EventDefinition):
            raise TypeError("definition must be EventDefinition")
        if definition.event_type in self._event_definitions:
            raise DuplicateRegistrationError(
                "Event definition already registered: {}".format(
                    definition.event_type
                )
            )
        self._event_definitions[definition.event_type] = definition
        return definition

    def event_definition(self, event_type):
        return self._event_definitions.get(str(event_type))

    def register_rule(
        self,
        stage,
        key,
        callback,
        event_types=None,
        priority=0,
        version=1,
    ):
        stage = str(stage)
        if stage not in self._rules:
            raise ValueError("Unknown memory pipeline stage: {}".format(stage))
        unique_key = (stage, str(key))
        if unique_key in self._rule_keys:
            raise DuplicateRegistrationError(
                "Rule already registered: {}:{}".format(stage, key)
            )
        if not callable(callback):
            raise TypeError("callback must be callable")
        registration = RuleRegistration(
            stage,
            key,
            callback,
            event_types=event_types,
            priority=priority,
            version=version,
        )
        self._rule_keys.add(unique_key)
        self._rules[stage].append(registration)
        self._rules[stage].sort(
            key=lambda value: (-value.priority, value.key)
        )
        return registration

    def rules_for(self, stage, event_type):
        return tuple(
            registration
            for registration in self._rules.get(str(stage), ())
            if registration.accepts(event_type)
        )

    def describe(self):
        return {
            "event_types": tuple(sorted(self._event_definitions)),
            "event_definitions": tuple(
                {
                    "event_type": definition.event_type,
                    "version": definition.version,
                    "semantic_tags": tuple(definition.semantic_tags),
                    "default_severity": definition.default_severity,
                }
                for definition in (
                    self._event_definitions[key]
                    for key in sorted(self._event_definitions)
                )
            ),
            "rules": {
                stage: tuple(
                    {
                        "key": registration.key,
                        "priority": registration.priority,
                        "version": registration.version,
                        "event_types": (
                            None
                            if registration.event_types is None
                            else tuple(sorted(registration.event_types))
                        ),
                    }
                    for registration in self._rules[stage]
                )
                for stage in self.STAGES
            },
        }

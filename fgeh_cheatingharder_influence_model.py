"""Pure, tag-driven relationship influence model.

This module is the reusable layer between interpreted romantic events and
behavior utility models.  It deliberately has no Sims 4 imports.

Events declare semantic tags and base directed-state deltas.  Personality
profiles register four independent kinds of influence:

* attribution multipliers: how the Sim assigns responsibility;
* state multipliers: how strongly tagged events change the five dimensions;
* behavior modifiers: which tagged responses become more attractive;
* hard rules: explicit constraints resolved by priority.

Numeric influences are order-independent and bounded.  Priority is reserved
for hard-rule conflicts so ordinary trait stacking cannot become "last trait
wins" logic.
"""


class RelationshipDimension:
    ATTACHMENT = "attachment"
    TRUST = "trust"
    EXCLUSIVITY = "exclusivity"
    COMMITMENT = "commitment"
    BOUNDARY = "boundary"

    ALL = (
        ATTACHMENT,
        TRUST,
        EXCLUSIVITY,
        COMMITMENT,
        BOUNDARY,
    )


class RelationshipEventTag:
    AFFECTION = "affection"
    ROMANCE = "romance"
    COMMITMENT = "commitment"
    COMMITMENT_BREACH = "commitment_breach"
    BETRAYAL = "betrayal"
    DECEPTION = "deception"
    NEGLECT = "neglect"
    REJECTION = "rejection"
    BOUNDARY_BREAK = "boundary_break"
    SEPARATION = "separation"


class AttributionTarget:
    PARTNER = "partner"
    RIVAL = "rival"
    SELF = "self"
    CIRCUMSTANCE = "circumstance"

    ALL = (PARTNER, RIVAL, SELF, CIRCUMSTANCE)


class InfluenceConflictError(ValueError):
    pass


def _clamp(value, minimum, maximum):
    return max(float(minimum), min(float(maximum), float(value)))


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _normalized_tags(values):
    return frozenset(
        str(value).strip().lower()
        for value in tuple(values or ())
        if str(value).strip()
    )


def _normalized_state(values, default=0.0):
    values = dict(values or {})
    return {
        dimension: _clamp(values.get(dimension, default), 0.0, 100.0)
        for dimension in RelationshipDimension.ALL
    }


def _normalized_attribution(values):
    raw = {
        target: max(0.0, _number(dict(values or {}).get(target), 0.0))
        for target in AttributionTarget.ALL
    }
    total = sum(raw.values())
    if total <= 0.0:
        return {
            target: 25.0
            for target in AttributionTarget.ALL
        }
    return {
        target: raw[target] * 100.0 / total
        for target in AttributionTarget.ALL
    }


def _nested_numeric_mapping(values):
    result = {}
    for context_tag, entries in dict(values or {}).items():
        normalized_tag = str(context_tag).strip().lower()
        if not normalized_tag:
            continue
        result[normalized_tag] = {
            str(key).strip().lower(): _number(value)
            for key, value in dict(entries or {}).items()
            if str(key).strip()
        }
    return result


def _matching_context_tags(mapping, event_tags):
    tags = set(event_tags)
    tags.add("*")
    return tuple(
        tag
        for tag in sorted(tags)
        if tag in mapping
    )


class RelationshipEventStimulus:

    def __init__(
        self,
        event_type,
        tags=(),
        severity=100.0,
        confidence=100.0,
        partner_responsibility=100.0,
        context=None,
    ):
        self.event_type = str(event_type)
        self.tags = _normalized_tags(tags)
        self.severity = _clamp(severity, 0.0, 100.0)
        self.confidence = _clamp(confidence, 0.0, 100.0)
        self.partner_responsibility = _clamp(
            partner_responsibility,
            0.0,
            100.0,
        )
        self.context = dict(context or {})


class EventImpactDefinition:
    """Registered base effect for one interpreted relationship event."""

    def __init__(
        self,
        key,
        tags=(),
        base_state_deltas=None,
        responsibility_sensitive_dimensions=(),
        description="",
    ):
        self.key = str(key)
        self.tags = _normalized_tags(tags)
        raw_deltas = dict(base_state_deltas or {})
        unknown_dimensions = set(raw_deltas).difference(
            RelationshipDimension.ALL
        )
        if unknown_dimensions:
            raise ValueError(
                "Unknown relationship dimensions: {}".format(
                    tuple(sorted(unknown_dimensions))
                )
            )
        self.base_state_deltas = {
            dimension: _number(raw_deltas.get(dimension), 0.0)
            for dimension in RelationshipDimension.ALL
        }
        sensitive = _normalized_tags(
            responsibility_sensitive_dimensions
        )
        unknown_sensitive = sensitive.difference(
            RelationshipDimension.ALL
        )
        if unknown_sensitive:
            raise ValueError(
                "Unknown responsibility-sensitive dimensions: {}".format(
                    tuple(sorted(unknown_sensitive))
                )
            )
        self.responsibility_sensitive_dimensions = sensitive
        self.description = str(description)


class TraitInfluenceDefinition:
    """Registered, data-only personality influence."""

    def __init__(
        self,
        key,
        priority=0,
        initial_state_contributions=None,
        attribution_tag_multipliers=None,
        state_tag_multipliers=None,
        behavior_tag_modifiers=None,
        hard_rules=None,
        description="",
    ):
        self.key = str(key)
        self.priority = int(priority)
        self.initial_state_contributions = {
            str(dimension): _number(value)
            for dimension, value in dict(
                initial_state_contributions or {}
            ).items()
        }
        unknown_dimensions = set(
            self.initial_state_contributions
        ).difference(RelationshipDimension.ALL)
        if unknown_dimensions:
            raise ValueError(
                "Unknown initial-state dimensions: {}".format(
                    tuple(sorted(unknown_dimensions))
                )
            )
        self.attribution_tag_multipliers = _nested_numeric_mapping(
            attribution_tag_multipliers
        )
        self.state_tag_multipliers = _nested_numeric_mapping(
            state_tag_multipliers
        )
        for entries in self.state_tag_multipliers.values():
            unknown = set(entries).difference(RelationshipDimension.ALL)
            if unknown:
                raise ValueError(
                    "Unknown state multiplier dimensions: {}".format(
                        tuple(sorted(unknown))
                    )
                )
        for entries in self.attribution_tag_multipliers.values():
            unknown = set(entries).difference(AttributionTarget.ALL)
            if unknown:
                raise ValueError(
                    "Unknown attribution targets: {}".format(
                        tuple(sorted(unknown))
                    )
                )
        self.behavior_tag_modifiers = _nested_numeric_mapping(
            behavior_tag_modifiers
        )
        self.hard_rules = {
            str(rule_key): value
            for rule_key, value in dict(hard_rules or {}).items()
        }
        self.description = str(description)


class InfluenceRegistry:

    def __init__(self):
        self._events = {}
        self._traits = {}

    @staticmethod
    def _register(collection, definition, kind):
        if definition.key in collection:
            raise ValueError(
                "{} already registered: {}".format(kind, definition.key)
            )
        collection[definition.key] = definition
        return definition

    def register_event(self, definition):
        if not isinstance(definition, EventImpactDefinition):
            raise TypeError("definition must be EventImpactDefinition")
        return self._register(
            self._events,
            definition,
            "Event impact",
        )

    def register_trait(self, definition):
        if not isinstance(definition, TraitInfluenceDefinition):
            raise TypeError("definition must be TraitInfluenceDefinition")
        return self._register(
            self._traits,
            definition,
            "Trait influence",
        )

    def event(self, key):
        return self._events.get(str(key))

    def trait(self, key):
        return self._traits.get(str(key))

    def event_keys(self):
        return tuple(sorted(self._events))

    def trait_keys(self):
        return tuple(sorted(self._traits))


class EventImpactResult:

    def __init__(
        self,
        event_key,
        event_tags,
        state_before,
        state_deltas,
        state_after,
        multiplier_traces,
    ):
        self.event_key = str(event_key)
        self.event_tags = tuple(sorted(event_tags))
        self.state_before = dict(state_before)
        self.state_deltas = dict(state_deltas)
        self.state_after = dict(state_after)
        self.multiplier_traces = {
            dimension: tuple(values)
            for dimension, values in dict(multiplier_traces).items()
        }

    def as_dict(self):
        return {
            "event_key": self.event_key,
            "event_tags": self.event_tags,
            "state_before": dict(self.state_before),
            "state_deltas": dict(self.state_deltas),
            "state_after": dict(self.state_after),
            "multiplier_traces": dict(self.multiplier_traces),
        }


def resolve_initial_state(base_state, influences=()):
    state = _normalized_state(base_state)
    for influence in tuple(influences or ()):
        for dimension, contribution in (
            influence.initial_state_contributions.items()
        ):
            state[dimension] += contribution
    return {
        dimension: _clamp(value, 0.0, 100.0)
        for dimension, value in state.items()
    }


def resolve_attribution(
    base_attribution,
    event_tags,
    influences=(),
):
    event_tags = _normalized_tags(event_tags)
    values = _normalized_attribution(base_attribution)
    for influence in tuple(influences or ()):
        mapping = influence.attribution_tag_multipliers
        for context_tag in _matching_context_tags(mapping, event_tags):
            for target, multiplier in mapping[context_tag].items():
                values[target] *= _clamp(multiplier, 0.05, 4.0)
    return _normalized_attribution(values)


def _state_multiplier(dimension, event_tags, influences):
    multiplier = 1.0
    trace = []
    for influence in sorted(
        tuple(influences or ()),
        key=lambda item: item.key,
    ):
        mapping = influence.state_tag_multipliers
        for context_tag in _matching_context_tags(mapping, event_tags):
            if dimension not in mapping[context_tag]:
                continue
            value = _clamp(
                mapping[context_tag][dimension],
                0.05,
                4.0,
            )
            multiplier *= value
            trace.append((influence.key, context_tag, value))
    bounded = _clamp(multiplier, 0.25, 2.50)
    return bounded, tuple(trace)


def evaluate_event_impact(
    definition,
    stimulus,
    state_before,
    influences=(),
):
    if not isinstance(definition, EventImpactDefinition):
        raise TypeError("definition must be EventImpactDefinition")
    if not isinstance(stimulus, RelationshipEventStimulus):
        raise TypeError("stimulus must be RelationshipEventStimulus")
    state_before = _normalized_state(state_before)
    event_tags = frozenset(definition.tags.union(stimulus.tags))
    severity_factor = stimulus.severity / 100.0
    confidence_factor = stimulus.confidence / 100.0
    responsibility_factor = stimulus.partner_responsibility / 100.0
    deltas = {}
    traces = {}
    for dimension in RelationshipDimension.ALL:
        multiplier, trait_trace = _state_multiplier(
            dimension,
            event_tags,
            influences,
        )
        responsibility_scale = (
            responsibility_factor
            if dimension
            in definition.responsibility_sensitive_dimensions
            else 1.0
        )
        delta = (
            definition.base_state_deltas[dimension]
            * severity_factor
            * confidence_factor
            * responsibility_scale
            * multiplier
        )
        deltas[dimension] = delta
        traces[dimension] = (
            ("severity", severity_factor),
            ("confidence", confidence_factor),
            ("responsibility", responsibility_scale),
            ("trait_multiplier", multiplier),
        ) + trait_trace
    state_after = {
        dimension: _clamp(
            state_before[dimension] + deltas[dimension],
            0.0,
            100.0,
        )
        for dimension in RelationshipDimension.ALL
    }
    return EventImpactResult(
        definition.key,
        event_tags,
        state_before,
        deltas,
        state_after,
        traces,
    )


def resolve_behavior_modifier(
    behavior_tags,
    event_tags,
    influences=(),
):
    behavior_tags = _normalized_tags(behavior_tags)
    event_tags = _normalized_tags(event_tags)
    score = 0.0
    trace = []
    for influence in sorted(
        tuple(influences or ()),
        key=lambda item: item.key,
    ):
        mapping = influence.behavior_tag_modifiers
        for context_tag in _matching_context_tags(mapping, event_tags):
            entries = mapping[context_tag]
            for behavior_tag in sorted(behavior_tags):
                if behavior_tag not in entries:
                    continue
                value = _clamp(
                    entries[behavior_tag],
                    -40.0,
                    40.0,
                )
                score += value
                trace.append((
                    influence.key,
                    context_tag,
                    behavior_tag,
                    value,
                ))
    return _clamp(score, -40.0, 40.0), tuple(trace)


def resolve_hard_rules(influences=()):
    candidates = {}
    for influence in tuple(influences or ()):
        for rule_key, value in influence.hard_rules.items():
            candidates.setdefault(rule_key, []).append((
                influence.priority,
                influence.key,
                value,
            ))
    resolved = {}
    for rule_key, entries in candidates.items():
        highest_priority = max(entry[0] for entry in entries)
        winners = tuple(
            entry
            for entry in entries
            if entry[0] == highest_priority
        )
        winner_values = {
            repr(entry[2])
            for entry in winners
        }
        if len(winner_values) > 1:
            raise InfluenceConflictError(
                "Conflicting hard rule '{}' at priority {}: {}".format(
                    rule_key,
                    highest_priority,
                    tuple(sorted(entry[1] for entry in winners)),
                )
            )
        resolved[rule_key] = {
            "value": winners[0][2],
            "priority": highest_priority,
            "sources": tuple(sorted(entry[1] for entry in winners)),
        }
    return resolved

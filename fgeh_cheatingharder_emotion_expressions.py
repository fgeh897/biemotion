"""Pure, registered emotional-expression selection for directed state.

Relationship state remains the cause.  These definitions only decide how a
state may be expressed to the player right now, including expressing nothing.
"""

import random


class ExpressionPhase:
    LONGING = "longing"
    REUNION = "reunion"
    BETRAYAL = "betrayal"
    REPAIR_RESPONSE = "repair_response"


class ExpressionType:
    NONE = "none"
    GENTLE_LONGING = "gentle_longing"
    ANXIOUS_LONGING = "anxious_longing"
    REUNION_RELIEF = "reunion_relief"
    BETRAYAL_PRESSURE = "betrayal_pressure"
    BETRAYAL_HURT = "betrayal_hurt"
    BETRAYAL_ANGER = "betrayal_anger"
    REPAIR_REOPENING = "repair_reopening"
    REPAIR_WARY = "repair_wary"
    REPAIR_INSUFFICIENT = "repair_insufficient"


class ExpressionCandidate:

    def __init__(
        self,
        expression_type,
        phase,
        score,
        duration_minutes,
        terms=(),
        eligible=True,
        blockers=(),
    ):
        self.expression_type = str(expression_type)
        self.phase = str(phase)
        self.score = max(0.0, float(score))
        self.duration_minutes = max(1.0, float(duration_minutes))
        self.terms = tuple(terms or ())
        self.eligible = bool(eligible)
        self.blockers = tuple(blockers or ())

    def as_dict(self):
        return {
            "expression_type": self.expression_type,
            "phase": self.phase,
            "score": self.score,
            "duration_minutes": self.duration_minutes,
            "terms": tuple(self.terms),
            "eligible": self.eligible,
            "blockers": tuple(self.blockers),
        }


class ExpressionDefinition:

    def __init__(self, expression_type, phase, candidate_builder):
        self.expression_type = str(expression_type)
        self.phase = str(phase)
        self.candidate_builder = candidate_builder

    def build(self, state, context):
        candidate = self.candidate_builder(state, context)
        if not isinstance(candidate, ExpressionCandidate):
            raise TypeError(
                "Expression builder {} did not return ExpressionCandidate".format(
                    self.expression_type
                )
            )
        modifiers = dict(
            context.get("expression_score_modifiers", {}) or {}
        )
        try:
            modifier = float(modifiers.get(self.expression_type, 0.0))
        except (TypeError, ValueError):
            modifier = 0.0
        if modifier:
            candidate = ExpressionCandidate(
                candidate.expression_type,
                candidate.phase,
                (
                    candidate.score + modifier
                    if candidate.eligible
                    else 0.0
                ),
                candidate.duration_minutes,
                terms=candidate.terms + (
                    ("registered_expression_modifier", modifier),
                ),
                eligible=candidate.eligible,
                blockers=candidate.blockers,
            )
        return candidate


class ExpressionRegistry:

    def __init__(self):
        self._definitions = {}
        self._phase_order = {}

    def register(self, definition):
        if not isinstance(definition, ExpressionDefinition):
            raise TypeError("definition must be ExpressionDefinition")
        key = (definition.phase, definition.expression_type)
        if key in self._definitions:
            raise ValueError(
                "Expression is already registered: {}:{}".format(*key)
            )
        self._definitions[key] = definition
        self._phase_order.setdefault(definition.phase, []).append(key)
        return definition

    def definitions_for(self, phase):
        return tuple(
            self._definitions[key]
            for key in self._phase_order.get(str(phase), ())
        )

    def build_candidates(self, phase, state, context):
        return tuple(
            definition.build(state, context)
            for definition in self.definitions_for(phase)
        )


EMOTIONAL_EXPRESSIONS = ExpressionRegistry()


def _value(state, key):
    try:
        return max(0.0, min(100.0, float(state.get(key))))
    except Exception:
        return 0.0


def _intensity(context):
    try:
        return max(
            0.0,
            min(100.0, float(context.get("longing_intensity", 0.0))),
        )
    except Exception:
        return 0.0


def _context_percent(context, key, default=0.0):
    try:
        return max(
            0.0,
            min(100.0, float(context.get(key, default))),
        )
    except Exception:
        return max(0.0, min(100.0, float(default)))


def _attribution(context, target):
    values = dict(context.get("attribution", {}) or {})
    try:
        return max(
            0.0,
            min(100.0, float(values.get(target, 0.0))),
        )
    except Exception:
        return 0.0


def _selected_intent(context):
    return str(context.get("selected_intent", "") or "")


def _accepted(context):
    return bool(context.get("accepted", False))


def _action_tag(context, tag):
    return str(tag) in tuple(context.get("action_tags", ()) or ())


def _longing_none(state, context):
    attachment = _value(state, "attachment")
    intensity = _intensity(context)
    terms = (
        ("base", 32.0),
        ("low_attachment", (100.0 - attachment) * 0.20),
        ("low_intensity", (100.0 - intensity) * 0.18),
    )
    duration = 60.0 + (100.0 - intensity) * 0.45
    return ExpressionCandidate(
        ExpressionType.NONE,
        ExpressionPhase.LONGING,
        sum(value for _, value in terms),
        duration,
        terms=terms,
    )


def _gentle_longing(state, context):
    attachment = _value(state, "attachment")
    trust = _value(state, "trust")
    commitment = _value(state, "commitment")
    intensity = _intensity(context)
    terms = (
        ("base", 18.0),
        ("attachment", attachment * 0.24),
        ("trust", trust * 0.22),
        ("longing_intensity", intensity * 0.32),
        ("commitment", commitment * 0.08),
        (
            "positive_romance",
            10.0 if context.get("has_positive_romance", False) else 0.0,
        ),
    )
    duration = 60.0 + intensity * 0.90 + commitment * 0.30
    return ExpressionCandidate(
        ExpressionType.GENTLE_LONGING,
        ExpressionPhase.LONGING,
        sum(value for _, value in terms),
        duration,
        terms=terms,
    )


def _anxious_longing(state, context):
    attachment = _value(state, "attachment")
    trust = _value(state, "trust")
    exclusivity = _value(state, "exclusivity")
    intensity = _intensity(context)
    blockers = []
    # Personality bottom: a deeply trusting Sim does not randomly turn anxious
    # merely because the random roll happened to land on this expression.
    if trust >= 85.0 and not context.get("recent_rejection", False):
        blockers.append("trust_too_high_for_anxiety")
    terms = (
        ("base", 4.0),
        ("attachment", attachment * 0.16),
        ("distrust", (100.0 - trust) * 0.48),
        ("longing_intensity", intensity * 0.28),
        ("exclusivity", exclusivity * 0.10),
    )
    duration = 120.0 + intensity * 0.90 + attachment * 0.30
    return ExpressionCandidate(
        ExpressionType.ANXIOUS_LONGING,
        ExpressionPhase.LONGING,
        0.0 if blockers else sum(value for _, value in terms),
        duration,
        terms=terms,
        eligible=not blockers,
        blockers=blockers,
    )


def _reunion_none(state, context):
    attachment = _value(state, "attachment")
    terms = (
        ("base", 30.0),
        ("low_attachment", (100.0 - attachment) * 0.22),
    )
    return ExpressionCandidate(
        ExpressionType.NONE,
        ExpressionPhase.REUNION,
        sum(value for _, value in terms),
        60.0,
        terms=terms,
    )


def _reunion_relief(state, context):
    attachment = _value(state, "attachment")
    trust = _value(state, "trust")
    intensity = _intensity(context)
    blockers = []
    if not context.get("was_longing", False):
        blockers.append("no_longing_to_relieve")
    terms = (
        ("base", 12.0),
        ("attachment", attachment * 0.28),
        ("trust", trust * 0.12),
        ("previous_longing_intensity", intensity * 0.34),
    )
    duration = 90.0 + intensity * 0.75 + attachment * 0.25
    return ExpressionCandidate(
        ExpressionType.REUNION_RELIEF,
        ExpressionPhase.REUNION,
        0.0 if blockers else sum(value for _, value in terms),
        duration,
        terms=terms,
        eligible=not blockers,
        blockers=blockers,
    )


def _betrayal_none(state, context):
    severity = _context_percent(context, "severity", 100.0)
    trust = _value(state, "trust")
    circumstance = _attribution(context, "circumstance")
    terms = (
        ("base", 8.0),
        ("low_severity", (100.0 - severity) * 0.30),
        ("remaining_trust", trust * 0.08),
        ("circumstance_attribution", circumstance * 0.20),
    )
    return ExpressionCandidate(
        ExpressionType.NONE,
        ExpressionPhase.BETRAYAL,
        sum(value for _, value in terms),
        60.0,
        terms=terms,
    )


def _betrayal_pressure(state, context):
    severity = _context_percent(context, "severity", 100.0)
    trust = _value(state, "trust")
    attachment = _value(state, "attachment")
    exclusivity = _value(state, "exclusivity")
    intent = _selected_intent(context)
    terms = (
        ("base", 10.0),
        ("severity", severity * 0.14),
        ("distrust", (100.0 - trust) * 0.24),
        ("attachment", attachment * 0.10),
        ("exclusivity", exclusivity * 0.10),
        (
            "selected_reassurance_or_endurance",
            20.0
            if intent in ("seek_reassurance", "endure_silently")
            else 0.0,
        ),
    )
    duration = 120.0 + severity * 0.90 + attachment * 0.30
    return ExpressionCandidate(
        ExpressionType.BETRAYAL_PRESSURE,
        ExpressionPhase.BETRAYAL,
        sum(value for _, value in terms),
        duration,
        terms=terms,
    )


def _betrayal_hurt(state, context):
    severity = _context_percent(context, "severity", 100.0)
    attachment = _value(state, "attachment")
    trust = _value(state, "trust")
    partner_blame = _attribution(context, "partner")
    intent = _selected_intent(context)
    terms = (
        ("base", 8.0),
        ("severity", severity * 0.12),
        ("attachment", attachment * 0.20),
        ("distrust", (100.0 - trust) * 0.18),
        ("partner_blame", partner_blame * 0.20),
        (
            "selected_attachment_response",
            18.0
            if intent in (
                "forgive_partner",
                "cling_to_partner",
                "seek_reassurance",
            )
            else 0.0,
        ),
    )
    duration = 180.0 + severity * 1.20 + attachment * 0.60
    return ExpressionCandidate(
        ExpressionType.BETRAYAL_HURT,
        ExpressionPhase.BETRAYAL,
        sum(value for _, value in terms),
        duration,
        terms=terms,
    )


def _betrayal_anger(state, context):
    severity = _context_percent(context, "severity", 100.0)
    exclusivity = _value(state, "exclusivity")
    boundary = _value(state, "boundary")
    partner_blame = _attribution(context, "partner")
    rival_blame = _attribution(context, "rival")
    intent = _selected_intent(context)
    terms = (
        ("base", 6.0),
        ("severity", severity * 0.12),
        ("exclusivity", exclusivity * 0.12),
        ("boundary", boundary * 0.12),
        ("partner_blame", partner_blame * 0.12),
        ("rival_blame", rival_blame * 0.30),
        (
            "selected_confrontation",
            25.0
            if intent in ("confront_partner", "confront_rival")
            else 0.0,
        ),
    )
    duration = 120.0 + severity * 0.90 + max(
        partner_blame,
        rival_blame,
    ) * 0.75
    return ExpressionCandidate(
        ExpressionType.BETRAYAL_ANGER,
        ExpressionPhase.BETRAYAL,
        sum(value for _, value in terms),
        duration,
        terms=terms,
    )


def _repair_none(state, context):
    trust = _value(state, "trust")
    boundary = _value(state, "boundary")
    terms = (
        ("base", 10.0),
        ("ordinary_response", trust * 0.05),
        ("low_boundary_intensity", (100.0 - boundary) * 0.04),
    )
    return ExpressionCandidate(
        ExpressionType.NONE,
        ExpressionPhase.REPAIR_RESPONSE,
        sum(value for _, value in terms),
        60.0,
        terms=terms,
    )


def _repair_reopening(state, context):
    trust = _value(state, "trust")
    attachment = _value(state, "attachment")
    commitment = _value(state, "commitment")
    boundary = _value(state, "boundary")
    blockers = []
    if not _accepted(context):
        blockers.append("repair_not_accepted")
    if trust < 35.0:
        blockers.append("trust_too_low_to_reopen")
    terms = (
        ("base", 8.0),
        ("trust", trust * 0.30),
        ("attachment", attachment * 0.12),
        ("commitment", commitment * 0.20),
        ("soft_boundary", (100.0 - boundary) * 0.08),
        ("accepted", 18.0 if _accepted(context) else 0.0),
        (
            "accountability",
            6.0 if _action_tag(context, "accountability") else 0.0,
        ),
    )
    duration = 150.0 + trust * 1.20 + commitment * 0.60
    return ExpressionCandidate(
        ExpressionType.REPAIR_REOPENING,
        ExpressionPhase.REPAIR_RESPONSE,
        0.0 if blockers else sum(value for _, value in terms),
        duration,
        terms=terms,
        eligible=not blockers,
        blockers=blockers,
    )


def _repair_wary(state, context):
    trust = _value(state, "trust")
    attachment = _value(state, "attachment")
    exclusivity = _value(state, "exclusivity")
    blockers = []
    if not _accepted(context):
        blockers.append("repair_not_accepted")
    if trust >= 80.0:
        blockers.append("trust_too_high_for_wariness")
    terms = (
        ("base", 8.0),
        ("attachment", attachment * 0.20),
        ("distrust", (100.0 - trust) * 0.35),
        ("exclusivity", exclusivity * 0.08),
        ("accepted_but_uncertain", 12.0 if _accepted(context) else 0.0),
    )
    duration = 210.0 + (100.0 - trust) * 1.50 + attachment * 0.60
    return ExpressionCandidate(
        ExpressionType.REPAIR_WARY,
        ExpressionPhase.REPAIR_RESPONSE,
        0.0 if blockers else sum(value for _, value in terms),
        duration,
        terms=terms,
        eligible=not blockers,
        blockers=blockers,
    )


def _repair_insufficient(state, context):
    trust = _value(state, "trust")
    boundary = _value(state, "boundary")
    exclusivity = _value(state, "exclusivity")
    blockers = []
    if (
        _accepted(context)
        and trust >= 70.0
        and boundary < 60.0
    ):
        blockers.append("repair_is_sufficient_for_current_state")
    terms = (
        ("base", 5.0),
        ("distrust", (100.0 - trust) * 0.30),
        ("boundary", boundary * 0.25),
        ("exclusivity", exclusivity * 0.06),
        ("rejected", 35.0 if not _accepted(context) else 0.0),
    )
    duration = 240.0 + (100.0 - trust) * 1.50 + boundary * 1.20
    return ExpressionCandidate(
        ExpressionType.REPAIR_INSUFFICIENT,
        ExpressionPhase.REPAIR_RESPONSE,
        0.0 if blockers else sum(value for _, value in terms),
        duration,
        terms=terms,
        eligible=not blockers,
        blockers=blockers,
    )


for _definition in (
    ExpressionDefinition(
        ExpressionType.NONE,
        ExpressionPhase.LONGING,
        _longing_none,
    ),
    ExpressionDefinition(
        ExpressionType.GENTLE_LONGING,
        ExpressionPhase.LONGING,
        _gentle_longing,
    ),
    ExpressionDefinition(
        ExpressionType.ANXIOUS_LONGING,
        ExpressionPhase.LONGING,
        _anxious_longing,
    ),
    ExpressionDefinition(
        ExpressionType.NONE,
        ExpressionPhase.REUNION,
        _reunion_none,
    ),
    ExpressionDefinition(
        ExpressionType.REUNION_RELIEF,
        ExpressionPhase.REUNION,
        _reunion_relief,
    ),
    ExpressionDefinition(
        ExpressionType.NONE,
        ExpressionPhase.BETRAYAL,
        _betrayal_none,
    ),
    ExpressionDefinition(
        ExpressionType.BETRAYAL_PRESSURE,
        ExpressionPhase.BETRAYAL,
        _betrayal_pressure,
    ),
    ExpressionDefinition(
        ExpressionType.BETRAYAL_HURT,
        ExpressionPhase.BETRAYAL,
        _betrayal_hurt,
    ),
    ExpressionDefinition(
        ExpressionType.BETRAYAL_ANGER,
        ExpressionPhase.BETRAYAL,
        _betrayal_anger,
    ),
    ExpressionDefinition(
        ExpressionType.NONE,
        ExpressionPhase.REPAIR_RESPONSE,
        _repair_none,
    ),
    ExpressionDefinition(
        ExpressionType.REPAIR_REOPENING,
        ExpressionPhase.REPAIR_RESPONSE,
        _repair_reopening,
    ),
    ExpressionDefinition(
        ExpressionType.REPAIR_WARY,
        ExpressionPhase.REPAIR_RESPONSE,
        _repair_wary,
    ),
    ExpressionDefinition(
        ExpressionType.REPAIR_INSUFFICIENT,
        ExpressionPhase.REPAIR_RESPONSE,
        _repair_insufficient,
    ),
):
    EMOTIONAL_EXPRESSIONS.register(_definition)


def select_expression(phase, state, context, roll=None):
    """Weighted selection among eligible expressions, including NONE."""
    candidates = EMOTIONAL_EXPRESSIONS.build_candidates(
        phase,
        state,
        context,
    )
    available = tuple(
        candidate
        for candidate in candidates
        if candidate.eligible and candidate.score > 0.0
    )
    if not available:
        return (None, {
            "phase": str(phase),
            "roll": None,
            "total": 0.0,
            "selected": None,
            "candidates": tuple(
                candidate.as_dict() for candidate in candidates
            ),
        })
    total = sum(candidate.score for candidate in available)
    normalized_roll = (
        random.random()
        if roll is None
        else max(0.0, min(0.999999, float(roll)))
    )
    cursor = normalized_roll * total
    selected = available[-1]
    running = 0.0
    for candidate in available:
        running += candidate.score
        if cursor < running:
            selected = candidate
            break
    return (selected, {
        "phase": str(phase),
        "roll": normalized_roll,
        "total": total,
        "selected": selected.expression_type,
        "candidates": tuple(
            candidate.as_dict() for candidate in candidates
        ),
    })

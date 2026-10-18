"""Single source of truth for romantic-journal event presentation.

This module is pure Python and deliberately has no Sims 4 imports.  It owns
stable journal categories, semantic tags, visibility policy, default
importance, localization keys, and temporary fallback text.  UI adapters and
GFX bridges consume this catalog; neither layer maintains a second event map.

The defaults here do not overwrite instance data already stored on a romantic
event.  In particular, ``RomanticEventRecord.severity`` remains authoritative.
"""

from fgeh_cheatingharder_domain import EventType
from fgeh_cheatingharder_memory_registry import EventDefinition


class JournalCategory:
    RELATIONSHIP_MILESTONE = "relationship_milestone"
    AFFECTION_INTIMACY = "affection_intimacy"
    COMMITMENT_BOUNDARY = "commitment_boundary"
    KNOWLEDGE_SECRET = "knowledge_secret"
    BETRAYAL_THIRD_PARTY = "betrayal_third_party"
    CONFLICT_CRISIS = "conflict_crisis"
    BREAKUP_SEPARATION = "breakup_separation"
    REPAIR_FORGIVENESS = "repair_forgiveness"
    RECONCILIATION_LOSS_HISTORY = "reconciliation_loss_history"
    UNKNOWN = "unknown"

    PUBLIC = (
        RELATIONSHIP_MILESTONE,
        AFFECTION_INTIMACY,
        COMMITMENT_BOUNDARY,
        KNOWLEDGE_SECRET,
        BETRAYAL_THIRD_PARTY,
        CONFLICT_CRISIS,
        BREAKUP_SEPARATION,
        REPAIR_FORGIVENESS,
        RECONCILIATION_LOSS_HISTORY,
    )
    ALL = PUBLIC + (UNKNOWN,)


CATEGORY_LABELS = {
    JournalCategory.RELATIONSHIP_MILESTONE: "关系里程碑",
    JournalCategory.AFFECTION_INTIMACY: "亲密与回应",
    JournalCategory.COMMITMENT_BOUNDARY: "承诺与边界",
    JournalCategory.KNOWLEDGE_SECRET: "秘密与证据",
    JournalCategory.BETRAYAL_THIRD_PARTY: "背叛与第三者",
    JournalCategory.CONFLICT_CRISIS: "冲突与危机",
    JournalCategory.BREAKUP_SEPARATION: "分手与分离",
    JournalCategory.REPAIR_FORGIVENESS: "修复与原谅",
    JournalCategory.RECONCILIATION_LOSS_HISTORY: "复合与长期历史",
    JournalCategory.UNKNOWN: "其他记录",
}


class JournalVisibility:
    TIMELINE = "timeline"
    SUMMARY_ONLY = "summary_only"
    DEBUG_ONLY = "debug_only"

    ALL = (TIMELINE, SUMMARY_ONLY, DEBUG_ONLY)


class JournalImportance:
    MAJOR = "major"
    NORMAL = "normal"

    ALL = (MAJOR, NORMAL)


SEMANTIC_TAGS = frozenset((
    "affection",
    "romance",
    "sexual",
    "rejection",
    "neglect",
    "attachment",
    "commitment",
    "exclusivity",
    "boundary",
    "permission",
    "promise",
    "violation",
    "secrecy",
    "deception",
    "evidence",
    "discovery",
    "betrayal",
    "jealousy",
    "rival",
    "ex_partner",
    "conflict",
    "breakup",
    "separation",
    "repair",
    "forgiveness",
    "reconciliation",
    "milestone",
    "crisis",
))


class JournalPresentationDefinition:

    def __init__(
        self,
        event_type,
        primary_category,
        visibility=JournalVisibility.TIMELINE,
        default_salience=50,
        importance=JournalImportance.NORMAL,
        title_key=None,
        summary_key=None,
        detail_key=None,
        icon_key=None,
        title_string_id=None,
        default_title="记录了一件恋爱事件",
    ):
        self.event_type = str(event_type)
        self.primary_category = str(primary_category)
        self.visibility = str(visibility)
        self.default_salience = _percent(default_salience)
        self.importance = str(importance)
        key = self.event_type
        self.title_key = str(
            title_key or "fgeh.journal.event.{}.title".format(key)
        )
        self.summary_key = str(
            summary_key or "fgeh.journal.event.{}.summary".format(key)
        )
        self.detail_key = str(
            detail_key or "fgeh.journal.event.{}.detail".format(key)
        )
        self.icon_key = str(icon_key or self.primary_category)
        self.title_string_id = (
            None if title_string_id is None else int(title_string_id)
        )
        self.default_title = str(default_title)
        self._validate()

    def _validate(self):
        if not self.event_type:
            raise ValueError("event_type is required")
        if self.primary_category not in JournalCategory.ALL:
            raise ValueError(
                "Unknown journal category: {}".format(
                    self.primary_category
                )
            )
        if self.visibility not in JournalVisibility.ALL:
            raise ValueError(
                "Unknown journal visibility: {}".format(self.visibility)
            )
        if self.importance not in JournalImportance.ALL:
            raise ValueError(
                "Unknown journal importance: {}".format(self.importance)
            )

    def as_dict(self):
        return {
            "event_type": self.event_type,
            "primary_category": self.primary_category,
            "category_label": CATEGORY_LABELS[self.primary_category],
            "visibility": self.visibility,
            "default_salience": self.default_salience,
            "importance": self.importance,
            "title_key": self.title_key,
            "summary_key": self.summary_key,
            "detail_key": self.detail_key,
            "icon_key": self.icon_key,
            "title_string_id": self.title_string_id,
            "default_title": self.default_title,
        }


class JournalEventCatalog:

    def __init__(self):
        self._event_definitions = {}
        self._presentations = {}

    def register(self, event_definition, presentation):
        if not isinstance(event_definition, EventDefinition):
            raise TypeError("event_definition must be EventDefinition")
        if not isinstance(presentation, JournalPresentationDefinition):
            raise TypeError(
                "presentation must be JournalPresentationDefinition"
            )
        if event_definition.event_type != presentation.event_type:
            raise ValueError("Event and presentation types must match")
        unknown_tags = set(event_definition.semantic_tags).difference(
            SEMANTIC_TAGS
        )
        if unknown_tags:
            raise ValueError(
                "Unknown semantic tags: {}".format(
                    tuple(sorted(unknown_tags))
                )
            )
        if event_definition.event_type in self._event_definitions:
            raise ValueError(
                "Journal event already registered: {}".format(
                    event_definition.event_type
                )
            )
        self._event_definitions[event_definition.event_type] = (
            event_definition
        )
        self._presentations[presentation.event_type] = presentation
        return event_definition, presentation

    def event_definition(self, event_type):
        return self._event_definitions.get(
            str(event_type),
            UNKNOWN_EVENT_DEFINITION,
        )

    def presentation(self, event_type):
        return self._presentations.get(
            str(event_type),
            UNKNOWN_PRESENTATION,
        )

    def registered(self, event_type):
        event_type = str(event_type)
        return (
            event_type in self._event_definitions
            and event_type in self._presentations
        )

    def event_definitions(self):
        return tuple(
            self._event_definitions[key]
            for key in sorted(self._event_definitions)
        )

    def presentations(self):
        return tuple(
            self._presentations[key] for key in sorted(self._presentations)
        )


def _percent(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(100.0, value))


UNKNOWN_EVENT_DEFINITION = EventDefinition(
    "generic",
    description="An event without a registered journal contract.",
)


UNKNOWN_PRESENTATION = JournalPresentationDefinition(
    "generic",
    JournalCategory.UNKNOWN,
    visibility=JournalVisibility.DEBUG_ONLY,
    default_salience=0,
    default_title="记录了一件恋爱事件",
)


EVENT_CATALOG = JournalEventCatalog()


_TITLE_STRING_IDS = {
    EventType.CLAIM_ESTABLISHED: 0xA743AEA2,
    EventType.DEVOTION_BOND_CREATED: 0xB62A3ECE,
    EventType.OUTSIDE_ROMANCE_REJECTED: 0x1E586CC3,
    EventType.ROMANCE_COMPLETED: 0xF630F0D8,
    EventType.BREAKUP_PROPOSED: 0xEE1A5898,
    EventType.BREAKUP_RESPONSE: 0xF1847D53,
    EventType.BREAKUP_NEGOTIATION_RESOLVED: 0xE5513870,
    EventType.BREAKUP_DECLARED: 0xA761AB54,
    EventType.BREAKUP_COMPLETED: 0x63233739,
    EventType.RECONCILIATION_PROPOSED: 0x6BBF4EE9,
    EventType.RECONCILIATION_RESPONSE: 0xE8B14E42,
    EventType.RECONCILIATION_RESOLVED: 0x49AC247F,
    EventType.REPAIR_ACTION_RESOLVED: 0x9CED3F4C,
    EventType.AFFAIR_SECRET_CREATED: 0xC257028E,
    EventType.AFFAIR_SECRET_DISCOVERED: 0xDB8D59A8,
    EventType.CAUGHT_CHEATING: 0xEEF947D9,
    EventType.ROMANTIC_BOUNDARY_DISCOVERED: 0x5FAFC208,
}


def _register(
    event_type,
    category,
    tags,
    visibility,
    severity,
    salience,
    importance,
    title,
    icon_key=None,
):
    EVENT_CATALOG.register(
        EventDefinition(
            event_type,
            description=title,
            version=1,
            semantic_tags=tags,
            default_severity=severity,
        ),
        JournalPresentationDefinition(
            event_type,
            category,
            visibility=visibility,
            default_salience=salience,
            importance=importance,
            default_title=title,
            icon_key=icon_key,
            title_string_id=_TITLE_STRING_IDS.get(event_type),
        ),
    )


_register(EventType.CLAIM_ESTABLISHED,
          JournalCategory.RELATIONSHIP_MILESTONE,
          ("commitment", "milestone"), JournalVisibility.TIMELINE,
          0, 80, JournalImportance.MAJOR, "确认了这段关系")
_register(EventType.DEVOTION_BOND_CREATED,
          JournalCategory.RELATIONSHIP_MILESTONE,
          ("attachment", "commitment", "exclusivity", "milestone"),
          JournalVisibility.TIMELINE, 0, 100, JournalImportance.MAJOR,
          "认定此生唯一挚爱", "devotion_bond")
_register(EventType.DEVOTION_LONGING_STARTED,
          JournalCategory.AFFECTION_INTIMACY,
          ("attachment", "neglect"), JournalVisibility.SUMMARY_ONLY,
          25, 30, JournalImportance.NORMAL, "开始思念挚爱")
_register(EventType.DEVOTION_CONTACT_SOUGHT,
          JournalCategory.AFFECTION_INTIMACY,
          ("attachment", "affection"), JournalVisibility.DEBUG_ONLY,
          0, 0, JournalImportance.NORMAL, "尝试寻找挚爱")
_register(EventType.DEVOTION_CONTACT_COMPLETED,
          JournalCategory.AFFECTION_INTIMACY,
          ("attachment", "affection"), JournalVisibility.SUMMARY_ONLY,
          10, 30, JournalImportance.NORMAL, "与挚爱重新亲近")
_register(EventType.OUTSIDE_ROMANCE_REJECTED,
          JournalCategory.AFFECTION_INTIMACY,
          ("romance", "rejection", "exclusivity"),
          JournalVisibility.SUMMARY_ONLY, 10, 25,
          JournalImportance.NORMAL, "拒绝了关系之外的浪漫")
_register(EventType.ROMANCE_COMPLETED,
          JournalCategory.AFFECTION_INTIMACY,
          ("romance", "affection"), JournalVisibility.SUMMARY_ONLY,
          10, 25, JournalImportance.NORMAL, "发生了浪漫互动")
_register(EventType.BREAKUP_PRESSURE,
          JournalCategory.BREAKUP_SEPARATION,
          ("breakup", "conflict"), JournalVisibility.SUMMARY_ONLY,
          45, 40, JournalImportance.NORMAL, "产生了分手压力")
_register(EventType.BREAKUP_PROPOSED,
          JournalCategory.BREAKUP_SEPARATION,
          ("breakup", "conflict", "separation"),
          JournalVisibility.TIMELINE, 70, 85, JournalImportance.MAJOR,
          "有人提出分手")
_register(EventType.BREAKUP_RESPONSE,
          JournalCategory.BREAKUP_SEPARATION,
          ("breakup", "conflict", "separation"),
          JournalVisibility.TIMELINE, 65, 80, JournalImportance.MAJOR,
          "分手请求有了回应")
_register(EventType.BREAKUP_NEGOTIATION_RESOLVED,
          JournalCategory.BREAKUP_SEPARATION,
          ("breakup", "conflict", "separation"),
          JournalVisibility.TIMELINE, 65, 85, JournalImportance.MAJOR,
          "分手协商暂时结束")
_register(EventType.BREAKUP_DECLARED,
          JournalCategory.BREAKUP_SEPARATION,
          ("breakup", "separation"), JournalVisibility.TIMELINE,
          80, 95, JournalImportance.MAJOR, "作出了分手决定")
_register(EventType.BREAKUP_COMPLETED,
          JournalCategory.BREAKUP_SEPARATION,
          ("breakup", "separation", "milestone"),
          JournalVisibility.TIMELINE, 80, 100, JournalImportance.MAJOR,
          "关系正式结束")
_register(EventType.RECONCILIATION_PROPOSED,
          JournalCategory.RECONCILIATION_LOSS_HISTORY,
          ("reconciliation", "repair"), JournalVisibility.TIMELINE,
          45, 80, JournalImportance.MAJOR, "有人提出复合")
_register(EventType.RECONCILIATION_RESPONSE,
          JournalCategory.RECONCILIATION_LOSS_HISTORY,
          ("reconciliation", "repair", "rejection"),
          JournalVisibility.TIMELINE, 45, 80, JournalImportance.MAJOR,
          "复合请求有了回应")
_register(EventType.RECONCILIATION_RESOLVED,
          JournalCategory.RECONCILIATION_LOSS_HISTORY,
          ("reconciliation", "repair", "milestone"),
          JournalVisibility.TIMELINE, 45, 90, JournalImportance.MAJOR,
          "复合有了结果")
_register(EventType.REPAIR_ACTION_RESOLVED,
          JournalCategory.REPAIR_FORGIVENESS,
          ("repair", "forgiveness"), JournalVisibility.TIMELINE,
          35, 70, JournalImportance.MAJOR, "关系修复有了进展")
_register(EventType.REACTION_EXPRESSION_SELECTED,
          JournalCategory.CONFLICT_CRISIS,
          ("conflict",), JournalVisibility.DEBUG_ONLY,
          0, 0, JournalImportance.NORMAL, "选择了情绪反应")
_register(EventType.AFFAIR_SECRET_CREATED,
          JournalCategory.BETRAYAL_THIRD_PARTY,
          ("betrayal", "secrecy", "rival"),
          JournalVisibility.TIMELINE, 65, 85, JournalImportance.MAJOR,
          "出现了一段隐瞒的关系")
_register(EventType.AFFAIR_SECRET_DISCOVERED,
          JournalCategory.BETRAYAL_THIRD_PARTY,
          ("betrayal", "secrecy", "discovery", "rival"),
          JournalVisibility.TIMELINE, 80, 95, JournalImportance.MAJOR,
          "发现了隐瞒的关系")
_register(EventType.CAUGHT_CHEATING,
          JournalCategory.BETRAYAL_THIRD_PARTY,
          ("betrayal", "discovery", "violation", "rival"),
          JournalVisibility.TIMELINE, 90, 100, JournalImportance.MAJOR,
          "亲眼发现背叛", "betrayal_discovered")
_register(EventType.ROMANTIC_BOUNDARY_DISCOVERED,
          JournalCategory.COMMITMENT_BOUNDARY,
          ("boundary", "discovery", "romance"),
          JournalVisibility.TIMELINE, 45, 75, JournalImportance.MAJOR,
          "了解了对方的浪漫边界")
_register(EventType.ROMANTIC_KNOWLEDGE_EVIDENCE_UPDATED,
          JournalCategory.KNOWLEDGE_SECRET,
          ("evidence", "discovery"), JournalVisibility.SUMMARY_ONLY,
          35, 55, JournalImportance.NORMAL, "对一件事有了新的认识")
_register(EventType.AUTONOMOUS_ACTION_RESOLVED,
          JournalCategory.CONFLICT_CRISIS,
          ("conflict",), JournalVisibility.DEBUG_ONLY,
          0, 0, JournalImportance.NORMAL, "自主行为执行完毕")
_register(EventType.RELATIONSHIP_REEVALUATION,
          JournalCategory.CONFLICT_CRISIS,
          ("crisis",), JournalVisibility.DEBUG_ONLY,
          0, 0, JournalImportance.NORMAL, "重新评估了关系")
_register(EventType.BEHAVIOR_EXECUTED,
          JournalCategory.CONFLICT_CRISIS,
          ("conflict",), JournalVisibility.DEBUG_ONLY,
          0, 0, JournalImportance.NORMAL, "执行了关系行为")
_register(EventType.VISIT_ARRIVED,
          JournalCategory.AFFECTION_INTIMACY,
          ("attachment",), JournalVisibility.DEBUG_ONLY,
          0, 0, JournalImportance.NORMAL, "到达了探访地点")
_register(EventType.VISIT_FINISHED,
          JournalCategory.AFFECTION_INTIMACY,
          ("attachment",), JournalVisibility.DEBUG_ONLY,
          0, 0, JournalImportance.NORMAL, "结束了探访")


def get_journal_presentation(event_type):
    return EVENT_CATALOG.presentation(event_type)


def journal_event_definitions():
    return EVENT_CATALOG.event_definitions()


def get_journal_event_definition(event_type):
    return EVENT_CATALOG.event_definition(event_type)


def journal_presentations():
    return EVENT_CATALOG.presentations()

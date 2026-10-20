"""Directed, role-scoped hot projections derived from event interpretations.

The five romantic dimensions describe one Sim's relationship with a romantic
counterpart.  Event roles such as "rival" are different: they are sparse,
contextual attitudes derived from what a Sim knows about a specific event.
The objective event and interpretation remain authoritative history; these
summary projections only let utility AI query that history cheaply.
"""

from fgeh_cheatingharder_memory_models import SummaryMutation, clamp_percent


class RelationshipEventRole:
    PARTNER = "partner"
    RIVAL = "rival"


class RoleAttitudeSummaryKey:

    @staticmethod
    def known_flag(role):
        return "role.{}.known".format(str(role))

    @staticmethod
    def incident_count(role):
        return "role.{}.known_incident_count".format(str(role))

    @staticmethod
    def last_incident_at(role):
        return "role.{}.last_incident_at".format(str(role))

    @staticmethod
    def responsibility(role):
        return "attribution.{}.latest_responsibility".format(str(role))

    @staticmethod
    def source_confidence(role):
        return "attribution.{}.source_confidence".format(str(role))

    @staticmethod
    def eyewitness_flag(role):
        return "role.{}.eyewitness_confirmed".format(str(role))


class RoleAttitudeView:

    def __init__(
        self,
        observer_id,
        target_id,
        role,
        known=False,
        incident_count=0,
        last_incident_at=None,
        responsibility=0.0,
        source_confidence=0.0,
        eyewitness_confirmed=False,
    ):
        self.observer_id = int(observer_id)
        self.target_id = int(target_id)
        self.role = str(role)
        self.known = bool(known)
        self.incident_count = int(incident_count)
        self.last_incident_at = last_incident_at
        self.responsibility = clamp_percent(responsibility)
        self.source_confidence = clamp_percent(source_confidence)
        self.eyewitness_confirmed = bool(eyewitness_confirmed)

    def to_data(self):
        return {
            "observer_id": self.observer_id,
            "target_id": self.target_id,
            "role": self.role,
            "known": self.known,
            "incident_count": self.incident_count,
            "last_incident_at": self.last_incident_at,
            "responsibility": self.responsibility,
            "source_confidence": self.source_confidence,
            "eyewitness_confirmed": self.eyewitness_confirmed,
        }


def build_role_attitude_mutations(
    observer_id,
    target_id,
    role,
    responsibility,
    source_confidence,
    occurred_at,
    eyewitness_confirmed=False,
    projection_version=2,
):
    """Project one known event role without changing romantic dimensions."""
    role = str(role or "").strip().lower()
    if not role:
        raise ValueError("Relationship event role cannot be empty")
    observer_id = int(observer_id)
    target_id = int(target_id)
    if observer_id <= 0 or target_id <= 0 or observer_id == target_id:
        raise ValueError("Role attitude projection requires two Sims")
    keys = RoleAttitudeSummaryKey
    mutations = [
        SummaryMutation(
            observer_id,
            target_id,
            SummaryMutation.SET_FLAG,
            keys.known_flag(role),
            True,
            projection_version=projection_version,
        ),
        SummaryMutation(
            observer_id,
            target_id,
            SummaryMutation.INCREMENT,
            keys.incident_count(role),
            1,
            projection_version=projection_version,
        ),
        SummaryMutation(
            observer_id,
            target_id,
            SummaryMutation.SET_TIMESTAMP,
            keys.last_incident_at(role),
            occurred_at,
            projection_version=projection_version,
        ),
        SummaryMutation(
            observer_id,
            target_id,
            SummaryMutation.SET_GAUGE,
            keys.responsibility(role),
            responsibility,
            projection_version=projection_version,
        ),
        SummaryMutation(
            observer_id,
            target_id,
            SummaryMutation.SET_CONFIDENCE,
            keys.source_confidence(role),
            source_confidence,
            projection_version=projection_version,
        ),
    ]
    if eyewitness_confirmed:
        mutations.append(SummaryMutation(
            observer_id,
            target_id,
            SummaryMutation.SET_FLAG,
            keys.eyewitness_flag(role),
            True,
            projection_version=projection_version,
        ))
    return tuple(mutations)


def build_betrayal_role_mutations(
    observer_id,
    partner_id,
    rival_id,
    attribution,
    source_confidence,
    occurred_at,
    eyewitness_confirmed=False,
):
    """Split one interpretation into partner- and rival-directed projections."""
    attribution = dict(attribution or {})
    partner = build_role_attitude_mutations(
        observer_id,
        partner_id,
        RelationshipEventRole.PARTNER,
        attribution.get(RelationshipEventRole.PARTNER, 0.0),
        source_confidence,
        occurred_at,
        eyewitness_confirmed=eyewitness_confirmed,
    )
    rival = build_role_attitude_mutations(
        observer_id,
        rival_id,
        RelationshipEventRole.RIVAL,
        attribution.get(RelationshipEventRole.RIVAL, 0.0),
        source_confidence,
        occurred_at,
        eyewitness_confirmed=eyewitness_confirmed,
    )
    return partner + rival


def role_attitude_view(store, observer_id, target_id, role):
    """Return a stable AI-facing view, or None when that role is unknown."""
    summary = store.get_summary(observer_id, target_id)
    if summary is None:
        return None
    role = str(role)
    keys = RoleAttitudeSummaryKey
    known = summary.flags.get(keys.known_flag(role), False)
    if not known:
        return None
    return RoleAttitudeView(
        observer_id,
        target_id,
        role,
        known=True,
        incident_count=summary.counters.get(
            keys.incident_count(role),
            0,
        ),
        last_incident_at=summary.timestamps.get(
            keys.last_incident_at(role)
        ),
        responsibility=summary.gauges.get(
            keys.responsibility(role),
            0.0,
        ),
        source_confidence=summary.confidences.get(
            keys.source_confidence(role),
            0.0,
        ),
        eyewitness_confirmed=summary.flags.get(
            keys.eyewitness_flag(role),
            False,
        ),
    )

"""Pure session state for one-primary-response betrayal episodes.

The objective ledger still records every EA signal.  This registry only owns
the reaction boundary: matching signals may strengthen the evidence for one
incident, but they must not repeatedly injure the same directed state or draw
contradictory primary behaviors while that incident is being handled.
"""


class BetrayalEpisodeStatus:
    OPEN = "open"
    SELECTED = "selected"
    SCHEDULED = "scheduled"
    PENDING = "pending"
    NEGOTIATING = "negotiating"
    RESOLVED = "resolved"

    ACTIVE = frozenset((OPEN, SELECTED, SCHEDULED, PENDING, NEGOTIATING))


class BetrayalEpisodeObservation:

    def __init__(self, episode, is_primary, merge_reason):
        self.episode = episode
        self.is_primary = bool(is_primary)
        self.merge_reason = str(merge_reason)

    def to_data(self):
        data = self.episode.to_data()
        data.update({
            "is_primary": self.is_primary,
            "merge_reason": self.merge_reason,
        })
        return data


class BetrayalReactionEpisode:

    def __init__(
        self,
        episode_id,
        observer_id,
        partner_id,
        rival_id,
        opened_at,
        primary_event_id,
        event_type,
        severity=0.0,
        evidence_keys=None,
    ):
        self.episode_id = str(episode_id)
        self.observer_id = int(observer_id)
        self.partner_id = int(partner_id)
        self.rival_id = int(rival_id)
        self.opened_at = float(opened_at)
        self.last_signal_at = float(opened_at)
        self.primary_event_id = str(primary_event_id)
        self.source_event_ids = [str(primary_event_id)]
        self.event_types = [str(event_type)]
        self.evidence_keys = set(str(value) for value in (evidence_keys or ()))
        self.max_severity = float(severity or 0.0)
        self.selected_intent = None
        self.reaction_details = {}
        self.status = BetrayalEpisodeStatus.OPEN
        self.outcome_status = None
        self.outcome_success = None

    @property
    def key(self):
        return (self.observer_id, self.partner_id, self.rival_id)

    def add_signal(
        self,
        event_id,
        event_type,
        occurred_at,
        severity=0.0,
        evidence_keys=None,
    ):
        event_id = str(event_id)
        event_type = str(event_type)
        if event_id not in self.source_event_ids:
            self.source_event_ids.append(event_id)
        if event_type not in self.event_types:
            self.event_types.append(event_type)
        self.evidence_keys.update(
            str(value) for value in (evidence_keys or ()) if value is not None
        )
        self.last_signal_at = max(self.last_signal_at, float(occurred_at))
        self.max_severity = max(self.max_severity, float(severity or 0.0))

    def to_data(self):
        return {
            "episode_id": self.episode_id,
            "observer_id": self.observer_id,
            "partner_id": self.partner_id,
            "rival_id": self.rival_id,
            "opened_at": self.opened_at,
            "last_signal_at": self.last_signal_at,
            "primary_event_id": self.primary_event_id,
            "source_event_ids": tuple(self.source_event_ids),
            "event_types": tuple(self.event_types),
            "evidence_keys": tuple(sorted(self.evidence_keys)),
            "max_severity": self.max_severity,
            "selected_intent": self.selected_intent,
            "status": self.status,
            "outcome_status": self.outcome_status,
            "outcome_success": self.outcome_success,
        }


class BetrayalReactionEpisodeRegistry:

    def __init__(self):
        self._by_key = {}
        self._by_id = {}
        self._sequence = 0

    def reset(self):
        self._by_key.clear()
        self._by_id.clear()
        self._sequence = 0

    def _new_id(self, observer_id, partner_id, rival_id):
        self._sequence += 1
        return "betrayal-episode:{}:{}:{}:{:06d}".format(
            int(observer_id),
            int(partner_id),
            int(rival_id),
            self._sequence,
        )

    def observe(
        self,
        observer_id,
        partner_id,
        rival_id,
        event_id,
        event_type,
        occurred_at,
        severity=0.0,
        evidence_keys=None,
        merge_window_minutes=30.0,
    ):
        key = (int(observer_id), int(partner_id), int(rival_id))
        now = float(occurred_at)
        evidence = set(
            str(value) for value in (evidence_keys or ()) if value is not None
        )
        current = self._by_key.get(key)
        if current is not None:
            shared_evidence = bool(current.evidence_keys.intersection(evidence))
            active = current.status in BetrayalEpisodeStatus.ACTIVE
            inside_window = (
                now - current.last_signal_at
                <= max(0.0, float(merge_window_minutes))
            )
            # The time window correlates sibling callbacks only while an
            # incident is still being handled.  Once the primary response is
            # resolved, a distinct evidence key is a new betrayal even when
            # the partner repeats the act seconds later.  Shared evidence is
            # still merged so one EA interaction cannot injure state twice.
            if active or shared_evidence:
                reason = (
                    "active_episode"
                    if active
                    else "shared_evidence"
                    if shared_evidence
                    else "temporal_correlation"
                )
                current.add_signal(
                    event_id,
                    event_type,
                    now,
                    severity=severity,
                    evidence_keys=evidence,
                )
                return BetrayalEpisodeObservation(current, False, reason)

            if (
                current.status != BetrayalEpisodeStatus.RESOLVED
                and inside_window
            ):
                current.add_signal(
                    event_id,
                    event_type,
                    now,
                    severity=severity,
                    evidence_keys=evidence,
                )
                return BetrayalEpisodeObservation(
                    current,
                    False,
                    "temporal_correlation",
                )

        episode = BetrayalReactionEpisode(
            self._new_id(*key),
            key[0],
            key[1],
            key[2],
            now,
            event_id,
            event_type,
            severity=severity,
            evidence_keys=evidence,
        )
        self._by_key[key] = episode
        self._by_id[episode.episode_id] = episode
        reason = (
            "post_resolution_reoffense"
            if current is not None
            and current.status == BetrayalEpisodeStatus.RESOLVED
            else "new_episode"
        )
        return BetrayalEpisodeObservation(episode, True, reason)

    def get(self, episode_id):
        if not episode_id:
            return None
        return self._by_id.get(str(episode_id))

    def bind_primary_reaction(self, episode_id, selected_intent, details=None):
        episode = self.get(episode_id)
        if episode is None:
            return None
        episode.selected_intent = (
            None if selected_intent is None else str(selected_intent)
        )
        episode.reaction_details = dict(details or {})
        if episode.status == BetrayalEpisodeStatus.OPEN:
            episode.status = BetrayalEpisodeStatus.SELECTED
        return episode

    def mark(self, episode_id, status):
        episode = self.get(episode_id)
        if episode is not None:
            episode.status = str(status)
        return episode

    def resolve(self, episode_id, outcome_status, success=None):
        episode = self.get(episode_id)
        if episode is None:
            return None
        episode.status = BetrayalEpisodeStatus.RESOLVED
        episode.outcome_status = str(outcome_status)
        episode.outcome_success = None if success is None else bool(success)
        return episode

    def status(self, observer_id=None, partner_id=None):
        values = tuple(self._by_id.values())
        if observer_id is not None:
            values = tuple(
                value for value in values
                if value.observer_id == int(observer_id)
            )
        if partner_id is not None:
            values = tuple(
                value for value in values
                if value.partner_id == int(partner_id)
            )
        return tuple(value.to_data() for value in values)


BETRAYAL_REACTION_EPISODES = BetrayalReactionEpisodeRegistry()


def reset_betrayal_reaction_episodes():
    BETRAYAL_REACTION_EPISODES.reset()

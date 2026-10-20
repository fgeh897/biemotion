"""Pure recent-romance correlation used by EA awareness adapters.

The objective interaction and the game's cognition notification do not always
arrive in the same callback.  This bounded cache connects them without giving
Sims access to unrelated or ambiguous world knowledge.
"""

from collections import deque


class RecentRomanceRecord:

    def __init__(
        self,
        event_id,
        actor_id,
        target_id,
        occurred_ticks,
        payload=None,
        local_witness_edges=None,
    ):
        self.event_id = str(event_id)
        self.actor_id = int(actor_id)
        self.target_id = int(target_id)
        self.occurred_ticks = int(occurred_ticks)
        self.payload = dict(payload or {})
        self.local_witness_edges = tuple(
            (int(edge[0]), int(edge[1]), int(edge[2]))
            for edge in (local_witness_edges or ())
            if isinstance(edge, (tuple, list)) and len(edge) == 3
        )

    def rival_for(self, observer_id, partner_id):
        observer_id = int(observer_id)
        partner_id = int(partner_id)
        if observer_id in (self.actor_id, self.target_id):
            return None
        if partner_id == self.actor_id:
            return self.target_id
        if partner_id == self.target_id:
            return self.actor_id
        return None

    def was_local_witness(self, observer_id, partner_id, rival_id):
        edge = (int(observer_id), int(partner_id), int(rival_id))
        return edge in self.local_witness_edges


class RomanceCorrelationMatch:

    MATCHED = "matched"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"

    def __init__(
        self,
        status,
        records=None,
        rival_ids=None,
        observer_id=None,
        partner_id=None,
        edge_matches=None,
    ):
        self.status = str(status)
        self.records = tuple(records or ())
        self.rival_ids = tuple(sorted(int(value) for value in (rival_ids or ())))
        self.observer_id = (
            None if observer_id is None else int(observer_id)
        )
        self.partner_id = (
            None if partner_id is None else int(partner_id)
        )
        self.edge_matches = tuple(edge_matches or ())

    @property
    def matched(self):
        return self.status == self.MATCHED and len(self.rival_ids) == 1

    @property
    def rival_id(self):
        return self.rival_ids[0] if self.matched else None


class RecentRomanceCorrelation:
    """Bounded, per-save cache with observer-specific consumption."""

    def __init__(self, capacity=64):
        self.capacity = max(1, int(capacity))
        self._records = deque()
        self._consumed = set()

    def clear(self):
        self._records.clear()
        self._consumed.clear()

    def record(
        self,
        event_id,
        actor_id,
        target_id,
        occurred_ticks,
        payload=None,
        local_witness_edges=None,
    ):
        record = RecentRomanceRecord(
            event_id,
            actor_id,
            target_id,
            occurred_ticks,
            payload=payload,
            local_witness_edges=local_witness_edges,
        )
        self._records.append(record)
        while len(self._records) > self.capacity:
            expired = self._records.popleft()
            self._consumed = {
                key for key in self._consumed if key[1] != expired.event_id
            }
        return record

    def match(
        self,
        observer_id,
        partner_id,
        now_ticks,
        max_age_ticks,
        allowed_rival_ids=None,
    ):
        observer_id = int(observer_id)
        partner_id = int(partner_id)
        now_ticks = int(now_ticks)
        max_age_ticks = max(0, int(max_age_ticks))
        allowed_rivals = None
        if allowed_rival_ids is not None:
            allowed_rivals = {
                int(value)
                for value in allowed_rival_ids
                if value is not None
            }
        candidates = []
        rivals = set()
        for record in self._records:
            if (observer_id, record.event_id) in self._consumed:
                continue
            age = now_ticks - record.occurred_ticks
            if age < 0 or age > max_age_ticks:
                continue
            rival_id = record.rival_for(observer_id, partner_id)
            if rival_id is None:
                continue
            if allowed_rivals is not None and rival_id not in allowed_rivals:
                continue
            candidates.append(record)
            rivals.add(rival_id)
        if not candidates:
            return RomanceCorrelationMatch(
                RomanceCorrelationMatch.MISSING,
                observer_id=observer_id,
                partner_id=partner_id,
            )
        if len(rivals) != 1:
            return RomanceCorrelationMatch(
                RomanceCorrelationMatch.AMBIGUOUS,
                records=candidates,
                rival_ids=rivals,
                observer_id=observer_id,
                partner_id=partner_id,
            )
        rival_id = next(iter(rivals))
        matching = tuple(
            record
            for record in candidates
            if record.rival_for(observer_id, partner_id) == rival_id
        )
        return RomanceCorrelationMatch(
            RomanceCorrelationMatch.MATCHED,
            records=matching,
            rival_ids=(rival_id,),
            observer_id=observer_id,
            partner_id=partner_id,
        )

    def match_relationship_signal(
        self,
        first_sim_id,
        second_sim_id,
        now_ticks,
        max_age_ticks,
        allowed_rival_ids=None,
    ):
        """Resolve the subjective direction of a mirrored EA signal.

        EA may add a romance-warning bit in either relationship direction.
        The direction is safe only when exactly one orientation connects the
        signalled pair to one recent outside-romance incident.
        """
        first_sim_id = int(first_sim_id)
        second_sim_id = int(second_sim_id)
        if first_sim_id == second_sim_id:
            return RomanceCorrelationMatch(RomanceCorrelationMatch.MISSING)
        edge_matches = tuple(
            self.match(
                observer_id,
                partner_id,
                now_ticks,
                max_age_ticks,
                allowed_rival_ids=allowed_rival_ids,
            )
            for observer_id, partner_id in (
                (first_sim_id, second_sim_id),
                (second_sim_id, first_sim_id),
            )
        )
        matched_edges = tuple(
            value for value in edge_matches if value.matched
        )
        ambiguous_edges = tuple(
            value
            for value in edge_matches
            if value.status == RomanceCorrelationMatch.AMBIGUOUS
        )
        if len(matched_edges) == 1 and not ambiguous_edges:
            return matched_edges[0]
        unresolved = matched_edges + ambiguous_edges
        if unresolved:
            records = []
            seen_event_ids = set()
            rival_ids = set()
            for value in unresolved:
                rival_ids.update(value.rival_ids)
                for record in value.records:
                    if record.event_id in seen_event_ids:
                        continue
                    seen_event_ids.add(record.event_id)
                    records.append(record)
            return RomanceCorrelationMatch(
                RomanceCorrelationMatch.AMBIGUOUS,
                records=records,
                rival_ids=rival_ids,
                edge_matches=edge_matches,
            )
        return RomanceCorrelationMatch(
            RomanceCorrelationMatch.MISSING,
            edge_matches=edge_matches,
        )

    def mark_consumed(self, observer_id, records):
        observer_id = int(observer_id)
        for record in records or ():
            self._consumed.add((observer_id, str(record.event_id)))

"""Deterministic romantic-memory pipeline.

Adapters submit an EventDraft.  The pipeline owns the only legal order:
objective event -> claims -> beliefs -> interpretations -> directed state
reducers -> summary projections -> behavior opportunities.
"""

from fgeh_cheatingharder_memory_models import (
    BeliefDraft,
    ClaimDraft,
    DIRECTED_DIMENSIONS,
    DirectedStateDelta,
    InterpretationDraft,
    MemoryOpportunity,
    ProcessingReport,
    StateChangeMode,
    SummaryMutation,
)
from fgeh_cheatingharder_memory_registry import RomanticMemoryRegistry


def _flatten(value):
    if value is None:
        return ()
    if isinstance(value, (tuple, list)):
        return tuple(value)
    return (value,)


class MemoryProcessingContext:

    def __init__(self, store, registry, event, external_context=None):
        self.store = store
        self.registry = registry
        self.event = event
        self.external_context = dict(external_context or {})
        self.claims = []
        self.beliefs = []
        self.interpretations = []
        self.state_deltas = []
        self.summary_mutations = []
        self.opportunities = []

    def directed_edges(self):
        result = []
        for value in self.external_context.get("directed_edges", ()):
            if not isinstance(value, (tuple, list)) or len(value) != 2:
                continue
            try:
                edge = (int(value[0]), int(value[1]))
            except (TypeError, ValueError):
                continue
            if (
                edge[0] > 0
                and edge[1] > 0
                and edge[0] != edge[1]
                and edge not in result
            ):
                result.append(edge)
        return tuple(result)


class RomanticMemoryPipeline:

    def __init__(
        self,
        store,
        registry,
        error_handler=None,
        opportunity_sink=None,
    ):
        self.store = store
        self.registry = registry
        self.error_handler = error_handler
        self.opportunity_sink = opportunity_sink

    def process(self, event_draft, external_context=None):
        event, created = self.store.append_event(event_draft)
        if not created:
            return ProcessingReport(event, duplicate=True)
        return self._process_record(event, external_context=external_context)

    def reprocess_event(self, event_id, external_context=None):
        event = self.store.get_event(event_id)
        if event is None:
            raise KeyError("Unknown romantic event: {}".format(event_id))
        return self._process_record(event, external_context=external_context)

    def _process_record(self, event, external_context=None):
        report = ProcessingReport(event)
        context = MemoryProcessingContext(
            self.store,
            self.registry,
            event,
            external_context=external_context,
        )
        self._run_record_stage(
            RomanticMemoryRegistry.CLAIM_STAGE,
            context,
            report,
            ClaimDraft,
            self._append_claim,
        )
        self._run_record_stage(
            RomanticMemoryRegistry.KNOWLEDGE_STAGE,
            context,
            report,
            BeliefDraft,
            self._append_belief,
        )
        self._run_record_stage(
            RomanticMemoryRegistry.INTERPRETATION_STAGE,
            context,
            report,
            InterpretationDraft,
            self._append_interpretation,
        )
        self._run_record_stage(
            RomanticMemoryRegistry.STATE_STAGE,
            context,
            report,
            DirectedStateDelta,
            self._apply_state_delta,
        )
        self._run_record_stage(
            RomanticMemoryRegistry.SUMMARY_STAGE,
            context,
            report,
            SummaryMutation,
            self._apply_summary_mutation,
        )
        self._run_record_stage(
            RomanticMemoryRegistry.OPPORTUNITY_STAGE,
            context,
            report,
            MemoryOpportunity,
            self._append_opportunity,
        )
        if report.opportunities and self.opportunity_sink is not None:
            try:
                self.opportunity_sink(tuple(report.opportunities), report)
            except Exception as exc:
                self._record_error(
                    report,
                    "opportunity_sink",
                    exc,
                )
        return report

    def _run_record_stage(
        self,
        stage,
        context,
        report,
        expected_type,
        consumer,
    ):
        for registration in self.registry.rules_for(stage, context.event.event_type):
            if self.store.has_receipt(
                registration.consumer_id,
                0,
                context.event.event_id,
                registration.version,
            ):
                continue
            try:
                produced = _flatten(registration.callback(context))
                for item in produced:
                    if not isinstance(item, expected_type):
                        raise TypeError(
                            "{}:{} returned {}, expected {}".format(
                                stage,
                                registration.key,
                                type(item).__name__,
                                expected_type.__name__,
                            )
                        )
                # Validate every result before consuming the first one.  A bad
                # second result must not leave a half-applied state/summary
                # projection whose receipt was never written.
                for item in produced:
                    self._validate_item(stage, context, item)
                for item in produced:
                    consumer(context, report, item)
                self.store.add_receipt(
                    registration.consumer_id,
                    0,
                    context.event.event_id,
                    registration.version,
                )
            except Exception as exc:
                self._record_error(
                    report,
                    registration.consumer_id,
                    exc,
                )

    def _validate_item(self, stage, context, item):
        if stage == RomanticMemoryRegistry.CLAIM_STAGE:
            for event_id in (
                item.supporting_event_ids + item.contradicting_event_ids
            ):
                if self.store.get_event(event_id) is None:
                    raise ValueError(
                        "Claim references unknown event {}".format(event_id)
                    )
            return
        if stage == RomanticMemoryRegistry.KNOWLEDGE_STAGE:
            if item.knower_id <= 0:
                raise ValueError("Belief knower id must be positive")
            if self.store.get_claim(item.claim_id) is None:
                raise ValueError(
                    "Belief references unknown claim {}".format(item.claim_id)
                )
            return
        if stage == RomanticMemoryRegistry.INTERPRETATION_STAGE:
            if item.knower_id <= 0:
                raise ValueError("Interpretation knower id must be positive")
            if self.store.get_claim(item.claim_id) is None:
                raise ValueError(
                    "Interpretation references unknown claim {}".format(
                        item.claim_id
                    )
                )
            if (
                item.source_belief_id is not None
                and self.store.get_belief(item.source_belief_id) is None
            ):
                raise ValueError(
                    "Interpretation references unknown belief {}".format(
                        item.source_belief_id
                    )
                )
            return
        if stage == RomanticMemoryRegistry.STATE_STAGE:
            self._validate_edge(item.observer_id, item.partner_id, "State delta")
            if item.dimension not in DIRECTED_DIMENSIONS:
                raise ValueError(
                    "Unknown directed dimension: {}".format(item.dimension)
                )
            if item.mode not in (
                StateChangeMode.ADD,
                StateChangeMode.SET,
                StateChangeMode.SET_IF_MISSING,
            ):
                raise ValueError(
                    "Unknown state change mode: {}".format(item.mode)
                )
            if (
                item.event_id is not None
                and self.store.get_event(item.event_id) is None
            ):
                raise ValueError(
                    "State delta references unknown event {}".format(
                        item.event_id
                    )
                )
            claim = (
                None
                if item.claim_id is None
                else self.store.get_claim(item.claim_id)
            )
            belief = (
                None
                if item.belief_id is None
                else self.store.get_belief(item.belief_id)
            )
            interpretation = (
                None
                if item.interpretation_id is None
                else self.store.get_interpretation(item.interpretation_id)
            )
            if item.claim_id is not None and claim is None:
                raise ValueError(
                    "State delta references unknown claim {}".format(
                        item.claim_id
                    )
                )
            if item.belief_id is not None and belief is None:
                raise ValueError(
                    "State delta references unknown belief {}".format(
                        item.belief_id
                    )
                )
            if item.interpretation_id is not None and interpretation is None:
                raise ValueError(
                    "State delta references unknown interpretation {}".format(
                        item.interpretation_id
                    )
                )
            if belief is not None:
                if belief.knower_id != item.observer_id:
                    raise ValueError(
                        "State delta belief belongs to a different knower"
                    )
                if claim is not None and belief.claim_id != claim.claim_id:
                    raise ValueError(
                        "State delta belief and claim do not match"
                    )
            if interpretation is not None:
                if interpretation.knower_id != item.observer_id:
                    raise ValueError(
                        "State delta interpretation belongs to a different knower"
                    )
                if (
                    belief is not None
                    and interpretation.source_belief_id != belief.belief_id
                ):
                    raise ValueError(
                        "State delta interpretation and belief do not match"
                    )
            return
        if stage == RomanticMemoryRegistry.SUMMARY_STAGE:
            self._validate_edge(
                item.observer_id,
                item.partner_id,
                "Summary mutation",
            )
            if item.operation not in (
                SummaryMutation.INCREMENT,
                SummaryMutation.SET_TIMESTAMP,
                SummaryMutation.SET_FLAG,
                SummaryMutation.SET_CONFIDENCE,
                SummaryMutation.SET_GAUGE,
            ):
                raise ValueError(
                    "Unknown summary mutation operation: {}".format(
                        item.operation
                    )
                )
            if item.projection_version <= 0:
                raise ValueError("Summary projection version must be positive")
            if item.operation == SummaryMutation.INCREMENT:
                int(item.value)
            elif item.operation == SummaryMutation.SET_CONFIDENCE:
                float(item.value)
            elif item.operation == SummaryMutation.SET_GAUGE:
                float(item.value)
            return
        if stage == RomanticMemoryRegistry.OPPORTUNITY_STAGE:
            self._validate_edge(
                item.observer_id,
                item.partner_id,
                "Memory opportunity",
            )

    @staticmethod
    def _validate_edge(observer_id, partner_id, label):
        if observer_id <= 0 or partner_id <= 0:
            raise ValueError("{} ids must be positive".format(label))
        if observer_id == partner_id:
            raise ValueError("{} cannot target the same Sim".format(label))

    def _append_claim(self, context, report, draft):
        record, created = self.store.append_claim(draft)
        if record not in context.claims:
            context.claims.append(record)
        if created:
            report.claims.append(record)

    def _append_belief(self, context, report, draft):
        if self.store.get_claim(draft.claim_id) is None:
            raise ValueError("Belief references unknown claim {}".format(draft.claim_id))
        record, created = self.store.append_belief(draft)
        if record not in context.beliefs:
            context.beliefs.append(record)
        if created:
            report.beliefs.append(record)

    def _append_interpretation(self, context, report, draft):
        if self.store.get_claim(draft.claim_id) is None:
            raise ValueError(
                "Interpretation references unknown claim {}".format(draft.claim_id)
            )
        record, created = self.store.append_interpretation(draft)
        if record not in context.interpretations:
            context.interpretations.append(record)
        if created:
            report.interpretations.append(record)

    def _apply_state_delta(self, context, report, delta):
        self.store.apply_state_delta(delta)
        context.state_deltas.append(delta)
        report.state_deltas.append(delta)

    def _apply_summary_mutation(self, context, report, mutation):
        summary = self.store.get_summary(
            mutation.observer_id,
            mutation.partner_id,
            create=True,
        )
        summary.projection_version = max(
            summary.projection_version,
            mutation.projection_version,
        )
        if mutation.operation == SummaryMutation.INCREMENT:
            summary.increment(mutation.key, mutation.value)
        elif mutation.operation == SummaryMutation.SET_TIMESTAMP:
            summary.set_timestamp(mutation.key, mutation.value)
        elif mutation.operation == SummaryMutation.SET_FLAG:
            summary.set_flag(mutation.key, mutation.value)
        elif mutation.operation == SummaryMutation.SET_CONFIDENCE:
            summary.set_confidence(mutation.key, mutation.value)
        elif mutation.operation == SummaryMutation.SET_GAUGE:
            summary.set_gauge(mutation.key, mutation.value)
        else:
            raise ValueError(
                "Unknown summary mutation operation: {}".format(
                    mutation.operation
                )
            )
        summary.last_event_sequence = max(
            summary.last_event_sequence,
            context.event.sequence,
        )
        context.summary_mutations.append(mutation)
        report.summary_edges.add(
            (mutation.observer_id, mutation.partner_id)
        )

    def _append_opportunity(self, context, report, opportunity):
        context.opportunities.append(opportunity)
        report.opportunities.append(opportunity)

    def _record_error(self, report, stage, exc):
        message = "{} failed: {}: {}".format(
            stage,
            type(exc).__name__,
            exc,
        )
        report.errors.append(message)
        if self.error_handler is not None:
            try:
                self.error_handler(message, exc)
            except Exception:
                pass

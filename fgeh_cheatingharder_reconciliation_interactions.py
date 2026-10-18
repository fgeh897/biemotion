"""Player-facing request to reconcile with a managed former partner."""

import services
import sims4.resources

from event_testing.results import TestResult
from interactions.base.immediate_interaction import ImmediateSuperInteraction
from sims.sim import Sim
from sims4.resources import Types

import fgeh_cheatingharder_injector as injector
import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception


_INSTALLED = False
_INTERACTION_TUNING = None
_INTERACTION_LOOKUP_DONE = False


def _get_interaction_tuning():
    global _INTERACTION_TUNING, _INTERACTION_LOOKUP_DONE
    if _INTERACTION_LOOKUP_DONE:
        return _INTERACTION_TUNING
    _INTERACTION_LOOKUP_DONE = True
    try:
        key = sims4.resources.get_resource_key(
            settings.RECONCILIATION_INTERACTION_ID,
            Types.INTERACTION,
        )
        _INTERACTION_TUNING = services.affordance_manager().get(key)
        log(
            "reconciliation interaction tuning lookup found={} id={}",
            _INTERACTION_TUNING is not None,
            settings.RECONCILIATION_INTERACTION_ID,
        )
        return _INTERACTION_TUNING
    except Exception:
        log_exception("reconciliation interaction tuning lookup failed")
        return None


def _has_project_edge(first, second):
    from fgeh_cheatingharder_devotion_runtime import get_devotion_bond
    from fgeh_cheatingharder_relationship import has_claim
    from fgeh_cheatingharder_state import has_initialized_relationship_pair

    if has_claim(first, second) or has_claim(second, first):
        return True
    if has_initialized_relationship_pair(first, second):
        return True
    first_bond = get_devotion_bond(first.sim_id)
    second_bond = get_devotion_bond(second.sim_id)
    return (
        first_bond is not None
        and first_bond.beloved_id == second.sim_id
    ) or (
        second_bond is not None
        and second_bond.beloved_id == first.sim_id
    )


class FgehRequestReconciliationInteraction(ImmediateSuperInteraction):

    @classmethod
    def _test(cls, target, context, **interaction_parameters):
        result = super()._test(
            target,
            context,
            **interaction_parameters
        )
        if not result:
            return result
        try:
            from fgeh_cheatingharder_reconciliation_ea import (
                are_official_partners,
                have_former_relationship_marker,
            )
            from fgeh_cheatingharder_relationship import get_sim_info

            proposer = get_sim_info(getattr(context, "sim", None))
            recipient = get_sim_info(target)
            if (
                proposer is None
                or recipient is None
                or proposer.sim_id == recipient.sim_id
            ):
                return TestResult(False, "Need two different Sims.")
            if not bool(getattr(proposer, "is_selectable", False)):
                return TestResult(
                    False,
                    "Only a player-controlled Sim can request reconciliation.",
                )
            if not _has_project_edge(proposer, recipient):
                return TestResult(
                    False,
                    "This former relationship is not managed by the framework.",
                )
            if are_official_partners(proposer, recipient):
                return TestResult(
                    False,
                    "These Sims are already official partners.",
                )
            if not have_former_relationship_marker(proposer, recipient):
                return TestResult(
                    False,
                    "EA has no former-partner marker for this pair.",
                )
            return TestResult.TRUE
        except Exception:
            log_exception("reconciliation interaction test failed")
            return TestResult(False, "Reconciliation test failed safely.")

    def _run_interaction_gen(self, timeline):
        del timeline
        try:
            from fgeh_cheatingharder_reconciliation_runtime import (
                request_reconciliation,
            )
            from fgeh_cheatingharder_relationship import get_sim_info

            proposer = get_sim_info(self.sim)
            recipient = get_sim_info(self.target)
            if proposer is not None and recipient is not None:
                request_reconciliation(
                    proposer,
                    recipient,
                    source="player_interaction",
                    force_player_proposal=True,
                )
        except Exception:
            log_exception("reconciliation interaction execution failed")
        return True
        if False:
            yield None


def install_reconciliation_interaction():
    global _INSTALLED
    if _INSTALLED:
        return True
    try:
        @injector.inject(Sim, "pre_add", safe=True)
        def _add_reconciliation_affordance(
            original,
            sim,
            manager,
            *args,
            **kwargs
        ):
            result = original(sim, manager, *args, **kwargs)
            try:
                interaction = _get_interaction_tuning()
                affordances = tuple(
                    getattr(sim, "_super_affordances", ()) or ()
                )
                if (
                    interaction is not None
                    and interaction not in affordances
                ):
                    sim._super_affordances = affordances + (interaction,)
            except Exception:
                log_exception("reconciliation affordance add failed")
            return result

        _INSTALLED = True
        log("reconciliation interaction injector installed")
        return True
    except Exception:
        log_exception("reconciliation interaction injector failed")
        return False

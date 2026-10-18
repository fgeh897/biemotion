"""Player-facing interaction for deliberately choosing one only beloved."""

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


def _get_interaction_tuning():
    try:
        key = sims4.resources.get_resource_key(
            settings.DEVOTION_INTERACTION_ID,
            Types.INTERACTION,
        )
        return services.affordance_manager().get(key)
    except Exception:
        log_exception("devotion interaction tuning lookup failed")
        return None


class FgehChooseOnlyBelovedInteraction(ImmediateSuperInteraction):

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
            from fgeh_cheatingharder_devotion_runtime import (
                get_devotion_bond,
            )
            from fgeh_cheatingharder_relationship import (
                get_sim_info,
                is_devotion_enabled,
            )

            owner = get_sim_info(getattr(context, "sim", None))
            beloved = get_sim_info(target)
            if owner is None or beloved is None or owner.sim_id == beloved.sim_id:
                return TestResult(False, "Need two different Sims.")
            if not bool(getattr(owner, "is_selectable", False)):
                return TestResult(
                    False,
                    "Only a player-controlled Sim can choose an only beloved.",
                )
            if not is_devotion_enabled(owner):
                return TestResult(
                    False,
                    "Only the permanent-devotion trait can choose an only beloved.",
                )
            bond = get_devotion_bond(owner.sim_id)
            if bond is not None:
                if bond.beloved_id == beloved.sim_id:
                    return TestResult(
                        False,
                        "This Sim is already the owner's only beloved.",
                    )
                return TestResult(
                    False,
                    "The owner already has a different only beloved.",
                )
            return TestResult.TRUE
        except Exception:
            log_exception("devotion interaction test failed")
            return TestResult(False, "Permanent devotion test failed safely.")

    def _run_interaction_gen(self, timeline):
        del timeline
        try:
            from fgeh_cheatingharder_confirmation import (
                show_permanent_devotion_confirmation,
            )
            from fgeh_cheatingharder_devotion_runtime import (
                establish_devotion,
            )
            from fgeh_cheatingharder_relationship import get_sim_info

            owner = get_sim_info(self.sim)
            beloved = get_sim_info(self.target)
            if owner is not None and beloved is not None:
                show_permanent_devotion_confirmation(
                    owner,
                    beloved,
                    lambda: establish_devotion(
                        owner,
                        beloved,
                        source="player_interaction",
                    ),
                )
        except Exception:
            log_exception("devotion interaction execution failed")
        return True
        if False:
            yield None


def install_devotion_interaction():
    global _INSTALLED
    if _INSTALLED:
        return True
    try:
        @injector.inject(Sim, "pre_add", safe=True)
        def _add_devotion_affordance(original, sim, manager, *args, **kwargs):
            result = original(sim, manager, *args, **kwargs)
            try:
                interaction = _get_interaction_tuning()
                affordances = tuple(
                    getattr(sim, "_super_affordances", ()) or ()
                )
                if interaction is not None and interaction not in affordances:
                    sim._super_affordances = affordances + (interaction,)
            except Exception:
                log_exception("devotion affordance add failed")
            return result

        _INSTALLED = True
        log("permanent devotion interaction injector installed")
        return True
    except Exception:
        log_exception("permanent devotion interaction injector failed")
        return False

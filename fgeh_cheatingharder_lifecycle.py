"""Zone lifecycle bridge for restoring persisted directed claims."""

import services
from zone import Zone

import fgeh_cheatingharder_injector as injector
import fgeh_cheatingharder_settings as settings
from fgeh_cheatingharder_debug import log, log_exception


_INSTALLED = False
_LAST_SIM_INFO_MANAGER_TOKEN = None


def mark_save_runtime_loaded():
    """Tell the zone bridge that persistence already handled this save."""
    global _LAST_SIM_INFO_MANAGER_TOKEN
    try:
        _LAST_SIM_INFO_MANAGER_TOKEN = id(services.sim_info_manager())
        return _LAST_SIM_INFO_MANAGER_TOKEN
    except Exception:
        log_exception("save runtime load marker failed")
        return None


def restore_claim_cycles():
    try:
        from fgeh_cheatingharder_relationship import get_claim_records
        from fgeh_cheatingharder_route import is_check_in_active
        from fgeh_cheatingharder_scheduler import schedule_relationship_reevaluation

        records = get_claim_records()
        for index, record in enumerate(records):
            if is_check_in_active(record["observer"], record["target"]):
                continue
            schedule_relationship_reevaluation(
                record["observer"],
                record["target"],
                reason="zone_restore",
                minutes=(
                    settings.RESTORED_CLAIM_FIRST_EVALUATION_SIM_MINUTES
                    + index
                ),
            )
        log("persisted claim cycles restored count={}", len(records))
        return len(records)
    except Exception:
        log_exception("persisted claim cycle restore failed")
        return 0


def install_zone_lifecycle():
    global _INSTALLED
    if _INSTALLED:
        return True

    @injector.inject(Zone, "on_loading_screen_animation_finished", safe=True)
    def _after_loading_screen(original, zone, *args, **kwargs):
        global _LAST_SIM_INFO_MANAGER_TOKEN
        result = original(zone, *args, **kwargs)
        try:
            from fgeh_cheatingharder_event_center import reset_save_runtime
            from fgeh_cheatingharder_events import install_game_event_observers
            from fgeh_cheatingharder_scheduler import reset_zone_runtime
            from fgeh_cheatingharder_wickedwhims import (
                install_wickedwhims_devotion_adapter,
            )

            install_game_event_observers()
            install_wickedwhims_devotion_adapter()
            manager_token = id(services.sim_info_manager())
            if (
                _LAST_SIM_INFO_MANAGER_TOKEN is not None
                and manager_token != _LAST_SIM_INFO_MANAGER_TOKEN
            ):
                reset_save_runtime()
            _LAST_SIM_INFO_MANAGER_TOKEN = manager_token
            reset_zone_runtime()
            restore_claim_cycles()
            from fgeh_cheatingharder_crisis_runtime import (
                restore_active_relationship_crises,
            )

            restore_active_relationship_crises()
            from fgeh_cheatingharder_relationship import (
                reconcile_devotion_relationship_bits,
            )

            reconcile_devotion_relationship_bits()
            from fgeh_cheatingharder_relationship import (
                reconcile_betrayal_rival_relationship_bits,
            )

            reconcile_betrayal_rival_relationship_bits()
            from fgeh_cheatingharder_longing_runtime import (
                start_longing_cycles,
            )

            start_longing_cycles()
        except Exception:
            log_exception("zone relationship lifecycle callback failed")
        return result

    _INSTALLED = True
    log("zone relationship lifecycle installed")
    return True

from fgeh_cheatingharder_debug import log, log_exception


log("loader import start")
try:
    from fgeh_cheatingharder_event_center import install_framework
    from fgeh_cheatingharder_events import install_game_event_observers
    from fgeh_cheatingharder_commands import install_debug_commands
    from fgeh_cheatingharder_devotion_runtime import install_devotion_guard
    from fgeh_cheatingharder_devotion_interactions import (
        install_devotion_interaction,
    )
    from fgeh_cheatingharder_reconciliation_interactions import (
        install_reconciliation_interaction,
    )
    from fgeh_cheatingharder_lifecycle import install_zone_lifecycle
    from fgeh_cheatingharder_memory_carrier import install_memory_persistence
    from fgeh_cheatingharder_picker import install_picker_affordance
    from fgeh_cheatingharder_romance_value_guard import (
        install_romance_value_guard,
    )
    from fgeh_cheatingharder_ea_awareness import (
        install_ea_awareness_adapter,
    )
    from fgeh_cheatingharder_breakup_adapter import install_breakup_adapter
    from fgeh_cheatingharder_scheduler import install_arrival_lifecycle
    from fgeh_cheatingharder_notebook_injection import (
        install_notebook_journal_injection,
    )
    from fgeh_cheatingharder_wickedwhims import (
        install_wickedwhims_devotion_adapter,
    )
    install_framework()
    install_devotion_guard()
    install_romance_value_guard()
    install_ea_awareness_adapter()
    install_breakup_adapter()
    install_wickedwhims_devotion_adapter()
    install_game_event_observers()
    install_debug_commands()
    install_memory_persistence()
    install_arrival_lifecycle()
    install_zone_lifecycle()
    install_notebook_journal_injection()
    install_picker_affordance()
    install_devotion_interaction()
    install_reconciliation_interaction()
except Exception:
    log_exception("loader failed")

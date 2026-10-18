"""Add the romantic ledger to the game's normal Notebook window."""

from notebook.notebook_tracker import NotebookTrackerSimInfo

import fgeh_cheatingharder_injector as injector
from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_notebook_ui import append_romantic_journal_category


_INSTALLED = False


def install_notebook_journal_injection():
    """Append our category immediately before EA sends its NotebookView."""
    global _INSTALLED
    if _INSTALLED:
        return True
    if not hasattr(NotebookTrackerSimInfo, "draw_temporary_entries"):
        log("notebook journal injection unavailable: target method missing")
        return False

    @injector.inject(NotebookTrackerSimInfo, "draw_temporary_entries", safe=True)
    def _append_romantic_category(original, tracker, notebook_msg, *args, **kwargs):
        result = original(tracker, notebook_msg, *args, **kwargs)
        try:
            append_romantic_journal_category(
                notebook_msg,
                getattr(tracker, "_owner", None),
            )
        except Exception:
            log_exception("romantic journal notebook append failed")
        return result

    _INSTALLED = True
    log("romantic journal notebook injection installed")
    return True

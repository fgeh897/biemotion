"""Game-facing behavior executors."""

from fgeh_cheatingharder_domain import ExecutionResult, IntentType


def execute_wait(intent, observer, partner):
    from fgeh_cheatingharder_scheduler import schedule_relationship_reevaluation

    handle = schedule_relationship_reevaluation(
        observer,
        partner,
        reason="wait_selected",
    )
    return ExecutionResult(
        handle is not None,
        "reevaluation_scheduled" if handle is not None else "reevaluation_failed",
    )


def execute_repair_relationship(intent, observer, partner):
    from fgeh_cheatingharder_scheduler import schedule_relationship_reevaluation

    handle = schedule_relationship_reevaluation(
        observer,
        partner,
        reason="repair_intention_selected",
    )
    return ExecutionResult(
        handle is not None,
        "repair_intention_selected" if handle is not None else "repair_retry_failed",
    )


def execute_break_up(intent, observer, partner):
    from fgeh_cheatingharder_autonomous_breakup import push_breakup_proposal

    return push_breakup_proposal(observer, partner, intent)


def execute_visit_unannounced(intent, observer, partner):
    from fgeh_cheatingharder_scheduler import schedule_delayed_check_in

    handle = schedule_delayed_check_in(
        observer,
        partner,
        trigger_reason=intent.reason,
    )
    return ExecutionResult(
        handle is not None,
        "visit_armed" if handle is not None else "visit_arm_failed",
    )


def execute_longing_wait(intent, observer, partner):
    return ExecutionResult(True, "longing_continues")


def execute_seek_beloved(intent, observer, partner):
    from fgeh_cheatingharder_longing_runtime import push_devotion_affection

    return push_devotion_affection(observer, partner)


def execute_crisis_seek_reassurance(intent, observer, partner):
    from fgeh_cheatingharder_crisis_runtime import (
        execute_crisis_seek_reassurance as execute,
    )

    return execute(intent, observer, partner)


def execute_crisis_give_space(intent, observer, partner):
    from fgeh_cheatingharder_crisis_runtime import (
        execute_crisis_give_space as execute,
    )

    return execute(intent, observer, partner)


def execute_crisis_repeat_breakup(intent, observer, partner):
    from fgeh_cheatingharder_crisis_runtime import (
        execute_crisis_repeat_breakup as execute,
    )

    return execute(intent, observer, partner)


EXECUTOR_BY_INTENT = {
    IntentType.WAIT: execute_wait,
    IntentType.REPAIR_RELATIONSHIP: execute_repair_relationship,
    IntentType.BREAK_UP: execute_break_up,
    IntentType.VISIT_UNANNOUNCED: execute_visit_unannounced,
    IntentType.LONGING_WAIT: execute_longing_wait,
    IntentType.SEEK_BELOVED: execute_seek_beloved,
    IntentType.CRISIS_SEEK_REASSURANCE: execute_crisis_seek_reassurance,
    IntentType.CRISIS_GIVE_SPACE: execute_crisis_give_space,
    IntentType.CRISIS_REPEAT_BREAKUP: execute_crisis_repeat_breakup,
}

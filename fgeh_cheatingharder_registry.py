"""Ordered extension registries used by the behavior framework."""

from fgeh_cheatingharder_debug import log_exception


class OrderedRegistry:

    def __init__(self, label):
        self.label = str(label)
        self._entries = []
        self._keys = set()

    def register(self, key, callback, priority=0):
        key = str(key)
        if key in self._keys:
            return False
        self._keys.add(key)
        self._entries.append((int(priority), key, callback))
        self._entries.sort(key=lambda entry: (-entry[0], entry[1]))
        return True

    def invoke(self, *args, **kwargs):
        results = []
        for _, key, callback in tuple(self._entries):
            try:
                result = callback(*args, **kwargs)
                if result is None:
                    continue
                if isinstance(result, (tuple, list)):
                    results.extend(result)
                else:
                    results.append(result)
            except Exception:
                log_exception("{} registry callback failed key={}".format(self.label, key))
        return tuple(results)

    def entries(self):
        return tuple(self._entries)


STATE_RULES = OrderedRegistry("state_rules")
STATE_CONSTRAINTS = OrderedRegistry("state_constraints")
OPPORTUNITY_PROVIDERS = OrderedRegistry("opportunity_providers")
BEHAVIOR_DEFINITIONS = OrderedRegistry("behavior_definitions")
SCORE_MODIFIERS = OrderedRegistry("score_modifiers")
EXECUTORS = {}


def register_executor(intent_type, callback):
    if intent_type in EXECUTORS:
        return False
    EXECUTORS[intent_type] = callback
    return True

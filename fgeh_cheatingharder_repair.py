"""Pure, extensible definitions for concrete relationship-repair actions.

The repair goal is not an EA relationship-bar mutation.  Game-facing
interactions report one resolved action here; the romantic-memory pipeline
then applies the registered directed-state effects.
"""

from fgeh_cheatingharder_domain import DirectedState
import fgeh_cheatingharder_settings as settings


class DuplicateRepairActionError(ValueError):
    pass


class RepairActionDefinition:

    def __init__(
        self,
        action_type,
        tags=(),
        accepted_actor_effects=(),
        accepted_recipient_effects=(),
        rejected_actor_effects=(),
        rejected_recipient_effects=(),
    ):
        self.action_type = str(action_type)
        self.tags = tuple(str(value) for value in tags)
        self.accepted_actor_effects = self._normalize_effects(
            accepted_actor_effects
        )
        self.accepted_recipient_effects = self._normalize_effects(
            accepted_recipient_effects
        )
        self.rejected_actor_effects = self._normalize_effects(
            rejected_actor_effects
        )
        self.rejected_recipient_effects = self._normalize_effects(
            rejected_recipient_effects
        )

    @staticmethod
    def _normalize_effects(effects):
        results = []
        for dimension, value in effects:
            dimension = str(dimension)
            if dimension not in DirectedState.DIMENSIONS:
                raise ValueError(
                    "Unknown directed relationship dimension: {}".format(
                        dimension
                    )
                )
            results.append((dimension, float(value)))
        return tuple(results)

    def effects(self, accepted):
        if bool(accepted):
            return (
                self.accepted_actor_effects,
                self.accepted_recipient_effects,
            )
        return (
            self.rejected_actor_effects,
            self.rejected_recipient_effects,
        )


class RepairActionRegistry:

    def __init__(self):
        self._definitions = {}

    def register(self, definition):
        if not isinstance(definition, RepairActionDefinition):
            raise TypeError("definition must be RepairActionDefinition")
        if definition.action_type in self._definitions:
            raise DuplicateRepairActionError(definition.action_type)
        self._definitions[definition.action_type] = definition
        return definition

    def get(self, action_type):
        return self._definitions.get(str(action_type))

    def definitions(self):
        return tuple(
            self._definitions[key]
            for key in sorted(self._definitions)
        )


REPAIR_ACTIONS = RepairActionRegistry()


def register_repair_action(definition):
    """Public extension point for feature modules such as gifts or pleading."""
    return REPAIR_ACTIONS.register(definition)


def get_repair_action(action_type):
    return REPAIR_ACTIONS.get(action_type)


def is_supported_ea_apology_affordance_id(affordance_id):
    """Exact classifier kept pure so game adapters never rely on name matching."""
    try:
        return (
            int(affordance_id)
            == settings.EA_INTERACTION_APOLOGIZE_TARGETED_FRIENDLY
        )
    except (TypeError, ValueError):
        return False


# First concrete vertical slice.  Seeking reassurance repairs the seeker's
# trust in the partner when the partner responds positively.  It deliberately
# does not modify EA friendship or romance tracks.
register_repair_action(
    RepairActionDefinition(
        "seek_reassurance",
        tags=("communication", "reassurance"),
        accepted_actor_effects=(
            ("trust", 5),
            ("commitment", 1),
        ),
        accepted_recipient_effects=(("commitment", 1),),
    )
)

# EA's apology outcome is reused as the acceptance signal.  A successful
# apology primarily repairs the recipient's trust in the apologizer, while the
# apologizer's willingness to remain accountable raises their commitment.
# Rejection is deliberately history-only for this first slice.
register_repair_action(
    RepairActionDefinition(
        "apology",
        tags=("communication", "accountability", "post_breakup"),
        accepted_actor_effects=(
            ("trust", 1),
            ("commitment", 2),
        ),
        accepted_recipient_effects=(
            ("trust", 5),
            ("commitment", 1),
        ),
    )
)

"""Registered metadata for the five directed relationship dimensions.

This module is deliberately free of Sims 4 imports.  It describes what a
dimension means to UI and extension modules; it does not contain five separate
behavior implementations.
"""

from fgeh_cheatingharder_memory_models import DIRECTED_DIMENSIONS


class DirectedDimensionDefinition:

    def __init__(
        self,
        key,
        display_name,
        description,
        picker_values=(0, 20, 40, 60, 80, 100),
    ):
        key = str(key)
        if key not in DIRECTED_DIMENSIONS:
            raise ValueError("Unknown directed dimension: {}".format(key))
        values = tuple(sorted({max(0, min(100, int(value))) for value in picker_values}))
        if not values:
            raise ValueError("A directed dimension needs at least one picker value")
        self.key = key
        self.display_name = str(display_name)
        self.description = str(description)
        self.picker_values = values


class DirectedDimensionRegistry:

    def __init__(self):
        self._definitions = {}
        self._order = []

    def register(self, definition):
        if not isinstance(definition, DirectedDimensionDefinition):
            raise TypeError("definition must be DirectedDimensionDefinition")
        if definition.key in self._definitions:
            raise ValueError(
                "Directed dimension is already registered: {}".format(
                    definition.key
                )
            )
        self._definitions[definition.key] = definition
        self._order.append(definition.key)
        return definition

    def get(self, key):
        return self._definitions.get(str(key))

    def definitions(self):
        return tuple(self._definitions[key] for key in self._order)


DIMENSION_DEFINITIONS = DirectedDimensionRegistry()


def register_dimension(
    key,
    display_name,
    description,
    picker_values=(0, 20, 40, 60, 80, 100),
):
    return DIMENSION_DEFINITIONS.register(
        DirectedDimensionDefinition(
            key,
            display_name,
            description,
            picker_values=picker_values,
        )
    )


register_dimension(
    "attachment",
    "\u4f9d\u604b",
    "\u5206\u79bb\u65f6\u7684\u601d\u5ff5\u3001\u5bfb\u627e\u548c\u4eb2\u8fd1\u503e\u5411\u3002",
)
register_dimension(
    "trust",
    "\u4fe1\u4efb",
    "\u76f8\u4fe1\u5bf9\u65b9\u53ef\u9760\uff0c\u5e76\u5bf9\u542b\u7cca\u4e8b\u4ef6\u4f5c\u5584\u610f\u89e3\u91ca\u7684\u7a0b\u5ea6\u3002",
)
register_dimension(
    "exclusivity",
    "\u6392\u4ed6\u671f\u5f85",
    "\u5e0c\u671b\u5bf9\u65b9\u53ea\u4e0e\u81ea\u5df1\u53d1\u5c55\u6d6a\u6f2b\u6216\u6027\u5173\u7cfb\u7684\u7a0b\u5ea6\u3002",
)
register_dimension(
    "commitment",
    "\u627f\u8bfa\u610f\u613f",
    "\u957f\u671f\u7ef4\u6301\u3001\u4fee\u590d\u5e76\u6295\u5165\u8fd9\u6bb5\u5173\u7cfb\u7684\u610f\u613f\u3002",
)
register_dimension(
    "boundary",
    "\u8fb9\u754c\u575a\u5b9a\u5ea6",
    "\u906d\u9047\u8d8a\u754c\u65f6\u7ef4\u62a4\u81ea\u5df1\u89c4\u5219\u3001\u62d2\u7edd\u6216\u8d28\u95ee\u7684\u575a\u5b9a\u7a0b\u5ea6\u3002",
)


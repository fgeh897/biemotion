"""Persistence boundary for romantic-memory snapshots.

The domain exports primitive snapshots.  This module defines slot semantics
without importing the game.  The current game adapter is an EA-save-attached
hidden household in ``fgeh_cheatingharder_memory_carrier``; tests and future
carriers can replace it through the same ``SnapshotBackend`` contract.
"""

import copy


class SnapshotBackend:

    def read(self, slot_key):
        raise NotImplementedError

    def write(self, slot_key, snapshot):
        raise NotImplementedError

    def delete(self, slot_key):
        raise NotImplementedError


class InMemorySnapshotBackend(SnapshotBackend):
    """Deterministic backend used by architecture tests."""

    def __init__(self):
        self._snapshots = {}

    def read(self, slot_key):
        snapshot = self._snapshots.get(str(slot_key))
        return None if snapshot is None else copy.deepcopy(snapshot)

    def write(self, slot_key, snapshot):
        self._snapshots[str(slot_key)] = copy.deepcopy(snapshot)
        return True

    def delete(self, slot_key):
        return self._snapshots.pop(str(slot_key), None) is not None

    def keys(self):
        return tuple(sorted(self._snapshots))


class MemorySnapshotCoordinator:
    """Coordinates normal save, load, and Save As without knowing the carrier."""

    def __init__(self, backend, snapshot_exporter, snapshot_restorer):
        missing_methods = tuple(
            name
            for name in ("read", "write", "delete")
            if not callable(getattr(backend, name, None))
        )
        if missing_methods:
            raise TypeError(
                "backend is missing snapshot methods: {}".format(
                    ", ".join(missing_methods)
                )
            )
        if not callable(snapshot_exporter) or not callable(snapshot_restorer):
            raise TypeError("snapshot exporter/restorer must be callable")
        self.backend = backend
        self.snapshot_exporter = snapshot_exporter
        self.snapshot_restorer = snapshot_restorer
        self.current_slot_key = None

    def save(self, slot_key):
        slot_key = str(slot_key)
        snapshot = self.snapshot_exporter()
        self.backend.write(slot_key, snapshot)
        self.current_slot_key = slot_key
        return snapshot

    def save_as(self, new_slot_key):
        """Save the current lineage to a second slot without changing ids."""
        return self.save(str(new_slot_key))

    def load(self, slot_key):
        slot_key = str(slot_key)
        snapshot = self.backend.read(slot_key)
        restored = self.snapshot_restorer(snapshot)
        self.current_slot_key = slot_key
        return (restored, snapshot is not None)

    def start_new(self, slot_key=None):
        restored = self.snapshot_restorer(None)
        self.current_slot_key = None if slot_key is None else str(slot_key)
        return restored

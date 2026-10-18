"""EA-save carrier for the romantic event ledger.

The domain owns primitive, versioned snapshots.  This module is the only layer
that knows the concrete game carrier: a hidden household whose description is
serialized by EA as part of the current save.  The pattern follows the mature
large-data carrier used by WickedWhims, but the implementation and format are
project-owned and have no runtime dependency on WickedWhims or TurboLib.
"""

import base64
import hashlib
import hmac
import json
import zlib

from fgeh_cheatingharder_debug import log, log_exception
from fgeh_cheatingharder_memory_persistence import (
    MemorySnapshotCoordinator,
    SnapshotBackend,
)


CARRIER_KIND = "ea_hidden_household_v1"
CARRIER_HOUSEHOLD_NAME = "__FGEH_ROMANTIC_MEMORY_CARRIER__"
CARRIER_CREATOR_NAME = "FGEH Romantic Event Ledger"
CARRIER_SIM_FIRST_NAME = "FGEH"
CARRIER_SIM_LAST_NAME = "Memory"
CARRIER_MAGIC = "FGEH_RM_CARRIER_V1"
CARRIER_FORMAT_VERSION = 1
MAX_ENCODED_CHARACTERS = 12 * 1024 * 1024


class SnapshotCarrierError(ValueError):
    pass


class SnapshotDecodeError(SnapshotCarrierError):
    pass


class SnapshotTooLargeError(SnapshotCarrierError):
    pass


class CompressedJsonSnapshotCodec:
    """Deterministic, non-executable snapshot envelope with corruption checks."""

    def __init__(self, max_encoded_characters=MAX_ENCODED_CHARACTERS):
        self.max_encoded_characters = int(max_encoded_characters)

    def encode(self, snapshot):
        if not isinstance(snapshot, dict):
            raise SnapshotCarrierError("romantic memory snapshot must be a mapping")
        envelope = {
            "carrier_format": CARRIER_FORMAT_VERSION,
            "snapshot": snapshot,
        }
        raw = json.dumps(
            envelope,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        compressed = zlib.compress(raw, 6)
        digest = hashlib.sha256(compressed).hexdigest()
        encoded = "{}|{}|{}".format(
            CARRIER_MAGIC,
            digest,
            base64.b64encode(compressed).decode("ascii"),
        )
        if len(encoded) > self.max_encoded_characters:
            raise SnapshotTooLargeError(
                "encoded romantic memory snapshot has {} characters; limit is {}".format(
                    len(encoded),
                    self.max_encoded_characters,
                )
            )
        return encoded

    def decode(self, encoded):
        if not isinstance(encoded, str) or not encoded:
            raise SnapshotDecodeError("romantic memory carrier is empty")
        if len(encoded) > self.max_encoded_characters:
            raise SnapshotTooLargeError(
                "encoded romantic memory carrier exceeds the configured limit"
            )
        parts = encoded.split("|", 2)
        if len(parts) != 3 or parts[0] != CARRIER_MAGIC:
            raise SnapshotDecodeError("romantic memory carrier header is invalid")
        expected_digest = parts[1]
        try:
            compressed = base64.b64decode(
                parts[2].encode("ascii"),
                validate=True,
            )
        except Exception as exc:
            raise SnapshotDecodeError(
                "romantic memory carrier base64 is invalid"
            ) from exc
        actual_digest = hashlib.sha256(compressed).hexdigest()
        if not hmac.compare_digest(expected_digest, actual_digest):
            raise SnapshotDecodeError(
                "romantic memory carrier checksum does not match"
            )
        try:
            envelope = json.loads(zlib.decompress(compressed).decode("utf-8"))
        except Exception as exc:
            raise SnapshotDecodeError(
                "romantic memory carrier payload is invalid"
            ) from exc
        if not isinstance(envelope, dict):
            raise SnapshotDecodeError("romantic memory carrier envelope is invalid")
        if int(envelope.get("carrier_format", 0)) != CARRIER_FORMAT_VERSION:
            raise SnapshotDecodeError(
                "unsupported romantic memory carrier format {}".format(
                    envelope.get("carrier_format")
                )
            )
        snapshot = envelope.get("snapshot")
        if not isinstance(snapshot, dict):
            raise SnapshotDecodeError(
                "romantic memory carrier does not contain a snapshot"
            )
        return snapshot


class HouseholdCarrierGateway:
    """Small gateway contract so game object access stays outside the backend."""

    def read_payload(self):
        raise NotImplementedError

    def write_payload(self, payload):
        raise NotImplementedError

    def delete_payload(self):
        raise NotImplementedError

    def describe(self):
        return {}


class HiddenHouseholdSnapshotBackend(SnapshotBackend):
    """Snapshot backend backed by the current EA save's hidden household."""

    def __init__(self, gateway, codec=None):
        missing_methods = tuple(
            name
            for name in ("read_payload", "write_payload", "delete_payload")
            if not callable(getattr(gateway, name, None))
        )
        if missing_methods:
            raise TypeError(
                "household carrier gateway is missing methods: {}".format(
                    ", ".join(missing_methods)
                )
            )
        self.gateway = gateway
        self.codec = codec or CompressedJsonSnapshotCodec()
        self.last_encoded_characters = 0

    def read(self, slot_key):
        del slot_key
        payload = self.gateway.read_payload()
        if not payload:
            self.last_encoded_characters = 0
            return None
        self.last_encoded_characters = len(payload)
        return self.codec.decode(payload)

    def write(self, slot_key, snapshot):
        del slot_key
        payload = self.codec.encode(snapshot)
        result = self.gateway.write_payload(payload)
        if result is False:
            raise SnapshotCarrierError(
                "EA hidden-household carrier rejected the snapshot"
            )
        self.last_encoded_characters = len(payload)
        return True

    def delete(self, slot_key):
        del slot_key
        deleted = bool(self.gateway.delete_payload())
        if deleted:
            self.last_encoded_characters = 0
        return deleted

    def describe(self):
        details = dict(self.gateway.describe() or {})
        details.update(
            {
                "kind": CARRIER_KIND,
                "encoded_characters": self.last_encoded_characters,
            }
        )
        return details


class EAHiddenHouseholdGateway(HouseholdCarrierGateway):
    """Direct adapter over EA Household and SimSpawner APIs."""

    def __init__(self):
        self._last_household_id = None
        self._duplicate_count = 0

    @staticmethod
    def _household_id(household):
        return int(getattr(household, "id", 0) or 0)

    def _matching_households(self):
        import services

        manager = services.household_manager()
        if manager is None:
            return ()
        matches = []
        for household in manager.get_all():
            if household is None:
                continue
            if (
                getattr(household, "name", "") == CARRIER_HOUSEHOLD_NAME
                and getattr(household, "creator_name", "") == CARRIER_CREATOR_NAME
            ):
                matches.append(household)
        return tuple(sorted(matches, key=self._household_id))

    def _select_household(self):
        matches = self._matching_households()
        self._duplicate_count = max(0, len(matches) - 1)
        household = matches[0] if matches else None
        self._last_household_id = (
            None if household is None else self._household_id(household)
        )
        return household

    @staticmethod
    def _protect_carrier_sims(household):
        from sims.sim_info_lod import SimInfoLODLevel

        for sim_info in tuple(household.sim_info_gen()):
            try:
                sim_info.set_aging_enabled(False)
            except Exception:
                pass
            try:
                sim_info.request_lod(SimInfoLODLevel.MINIMUM)
            except Exception:
                pass

    def _ensure_nonempty(self, household):
        if int(getattr(household, "household_size", 0) or 0) > 0:
            self._protect_carrier_sims(household)
            return
        from sims.sim_info_lod import SimInfoLODLevel
        from sims.sim_info_types import Age
        from sims.sim_spawner import SimCreator, SimSpawner

        creator = SimCreator(
            first_name=CARRIER_SIM_FIRST_NAME,
            last_name=CARRIER_SIM_LAST_NAME,
            age=Age.BABY,
        )
        sim_infos, _ = SimSpawner.create_sim_infos(
            (creator,),
            household=household,
            zone_id=0,
            creation_source="FGEH Romantic Memory Carrier",
        )
        if not sim_infos:
            raise SnapshotCarrierError(
                "EA did not create the hidden carrier SimInfo"
            )
        carrier_sim = sim_infos[0]
        carrier_sim.set_aging_enabled(False)
        carrier_sim.request_lod(SimInfoLODLevel.MINIMUM)

    def _create_household(self):
        import services
        from sims.household import Household
        from sims.sim_spawner import SimSpawner

        manager = services.household_manager()
        if manager is None:
            raise SnapshotCarrierError("EA household manager is unavailable")
        household = Household(SimSpawner._get_default_account(), starting_funds=0)
        manager.add(household)
        try:
            household.set_to_hidden()
            household.name = CARRIER_HOUSEHOLD_NAME
            household.creator_id = 0
            household.creator_name = CARRIER_CREATOR_NAME
            household.creator_uuid = None
            self._ensure_nonempty(household)
        except Exception:
            try:
                manager.remove(household)
            except Exception:
                pass
            raise
        self._last_household_id = self._household_id(household)
        return household

    def read_payload(self):
        household = self._select_household()
        if household is None:
            return None
        try:
            household.set_to_hidden()
        except Exception:
            pass
        self._protect_carrier_sims(household)
        return getattr(household, "description", "") or None

    def write_payload(self, payload):
        household = self._select_household()
        if household is None:
            household = self._create_household()
        else:
            household.set_to_hidden()
            self._ensure_nonempty(household)
        household.description = str(payload)
        self._last_household_id = self._household_id(household)
        return True

    def delete_payload(self):
        household = self._select_household()
        if household is None:
            return False
        household.description = ""
        return True

    def describe(self):
        return {
            "household_id": self._last_household_id,
            "duplicate_households": self._duplicate_count,
        }


_INSTALLED = False
_SERVICE_CLASS = None
_COORDINATOR = None
_BACKEND = None
_STATUS = {
    "installed": False,
    "registered": False,
    "ready": False,
    "write_enabled": False,
    "current_slot": None,
    "last_action": "not_installed",
    "last_error": None,
    "carrier": {"kind": CARRIER_KIND},
}


def _slot_key(save_slot_data=None):
    try:
        if save_slot_data is None:
            import services

            save_slot_data = (
                services.get_persistence_service().get_save_slot_proto_buff()
            )
        slot_id = int(getattr(save_slot_data, "slot_id", 0) or 0)
        return "Slot_{:08x}".format(slot_id)
    except Exception:
        return "Slot_unknown"


def _get_coordinator():
    global _BACKEND
    global _COORDINATOR
    if _COORDINATOR is None:
        from fgeh_cheatingharder_memory_runtime import (
            get_memory_service,
            reset_memory_service,
        )

        _BACKEND = HiddenHouseholdSnapshotBackend(
            EAHiddenHouseholdGateway()
        )
        _COORDINATOR = MemorySnapshotCoordinator(
            _BACKEND,
            lambda: get_memory_service().export_snapshot(),
            reset_memory_service,
        )
    return _COORDINATOR


def _refresh_carrier_status():
    if _BACKEND is not None:
        _STATUS["carrier"] = _BACKEND.describe()


def _load_current_save():
    slot_key = _slot_key()
    _STATUS.update(
        {
            "ready": False,
            "write_enabled": False,
            "current_slot": slot_key,
            "last_action": "loading",
            "last_error": None,
        }
    )
    try:
        from fgeh_cheatingharder_event_center import reset_save_runtime

        reset_save_runtime(reset_memory=False)
        restored, found = _get_coordinator().load(slot_key)
        del restored
        _STATUS.update(
            {
                "ready": True,
                "write_enabled": True,
                "last_action": "loaded" if found else "new_lineage",
            }
        )
        _refresh_carrier_status()
        log(
            "romantic memory persistence load slot={} found={} carrier={}",
            slot_key,
            found,
            _STATUS["carrier"],
        )
        try:
            from fgeh_cheatingharder_relationship import (
                reconcile_devotion_relationship_bits,
            )

            reconcile_devotion_relationship_bits()
        except Exception:
            log_exception(
                "devotion relationship projection restore after memory load failed"
            )
    except Exception as exc:
        try:
            from fgeh_cheatingharder_memory_runtime import reset_memory_service

            reset_memory_service()
        except Exception:
            log_exception("romantic memory fallback reset failed")
        _STATUS.update(
            {
                "ready": True,
                # Preserve the damaged carrier instead of overwriting it with
                # an empty runtime snapshot on the next normal save.
                "write_enabled": False,
                "last_action": "load_failed_write_blocked",
                "last_error": "{}: {}".format(type(exc).__name__, exc),
            }
        )
        _refresh_carrier_status()
        log_exception("romantic memory persistence load failed")
    finally:
        try:
            from fgeh_cheatingharder_lifecycle import mark_save_runtime_loaded

            mark_save_runtime_loaded()
        except Exception:
            log_exception("romantic memory save-load marker failed")


def _save_current_runtime(save_slot_data=None):
    slot_key = _slot_key(save_slot_data)
    _STATUS["current_slot"] = slot_key
    if not _STATUS["ready"]:
        _STATUS["last_action"] = "save_skipped_not_loaded"
        log("romantic memory save skipped because load is not complete")
        return False
    if not _STATUS["write_enabled"]:
        _STATUS["last_action"] = "save_skipped_write_blocked"
        log(
            "romantic memory save skipped because carrier writes are blocked error={}",
            _STATUS["last_error"],
        )
        return False
    try:
        snapshot = _get_coordinator().save(slot_key)
        _STATUS.update(
            {
                "last_action": "saved",
                "last_error": None,
            }
        )
        _refresh_carrier_status()
        log(
            "romantic memory persistence saved slot={} counts={} carrier={}",
            slot_key,
            {
                key: len(snapshot.get(key, ()))
                for key in (
                    "events",
                    "claims",
                    "beliefs",
                    "interpretations",
                    "devotion_bonds",
                    "directed_states",
                    "summaries",
                    "repair_cases",
                    "relationship_crises",
                )
            },
            _STATUS["carrier"],
        )
        return True
    except Exception as exc:
        _STATUS.update(
            {
                "write_enabled": False,
                "last_action": "save_failed_write_blocked",
                "last_error": "{}: {}".format(type(exc).__name__, exc),
            }
        )
        _refresh_carrier_status()
        log_exception("romantic memory persistence save failed")
        return False


def get_memory_persistence_status():
    status = dict(_STATUS)
    status["carrier"] = dict(_STATUS.get("carrier", {}))
    return status


def _build_service_class():
    global _SERVICE_CLASS
    if _SERVICE_CLASS is not None:
        return _SERVICE_CLASS
    from sims4.service_manager import Service

    class FGEHRomanticMemorySaveService(Service):

        def on_all_households_and_sim_infos_loaded(self, _client):
            _load_current_save()

        def save(self, save_slot_data=None, **_kwargs):
            # This service is appended after EA's services.  ServiceManager
            # saves in reverse order, so the carrier is updated before
            # HouseholdManager serializes household.description.
            _save_current_runtime(save_slot_data=save_slot_data)

        def stop(self):
            _STATUS.update(
                {
                    "ready": False,
                    "write_enabled": False,
                    "last_action": "service_stopped",
                }
            )

    _SERVICE_CLASS = FGEHRomanticMemorySaveService
    return _SERVICE_CLASS


def install_memory_persistence():
    """Register the save service before EA starts the GameServiceManager."""
    global _INSTALLED
    if _INSTALLED:
        return True
    try:
        import game_services

        import fgeh_cheatingharder_injector as injector

        service_class = _build_service_class()

        @injector.inject(
            game_services.GameServiceManager,
            "start_services",
            safe=True,
        )
        def _register_before_start(original, manager, *args, **kwargs):
            if not any(
                isinstance(service, service_class)
                for service in manager.services
            ):
                manager.services.append(service_class())
            _STATUS["registered"] = True
            return original(manager, *args, **kwargs)

        _INSTALLED = True
        _STATUS.update(
            {
                "installed": True,
                "last_action": "awaiting_game_service_start",
            }
        )
        log("romantic memory persistence service installed")
        return True
    except Exception:
        _STATUS.update(
            {
                "installed": False,
                "last_action": "install_failed",
            }
        )
        log_exception("romantic memory persistence service install failed")
        return False

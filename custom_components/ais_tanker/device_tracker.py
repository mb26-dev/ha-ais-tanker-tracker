"""Device tracker platform for the AIS Tanker Tracker integration.

One tracker per active tanker (limited by max_tracked_vessels, nearest first).
Entities are created and removed dynamically, removed ones are also deleted
from the entity registry to keep the registry and recorder clean.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .coordinator import AisTankerConfigEntry, AisTankerCoordinator

TRACKER_ATTRIBUTE_KEYS: tuple[str, ...] = (
    "name",
    "mmsi",
    "imo",
    "callsign",
    "vessel_type_code",
    "vessel_type_label",
    "vessel_class",
    "speed_knots",
    "course",
    "heading",
    "draught_m",
    "load_status",
    "length_m",
    "width_m",
    "destination",
    "eta",
    "nav_status",
    "distance_km",
    "bearing_deg",
    "source",
    "last_seen",
)


def _mmsi_from_unique_id(unique_id: str, entry_id: str) -> int | None:
    """Extract the MMSI from '<entry_id>_<mmsi>'."""
    prefix = f"{entry_id}_"
    if not unique_id.startswith(prefix):
        return None
    try:
        return int(unique_id[len(prefix) :])
    except ValueError:
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AisTankerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up dynamic tanker trackers."""
    coordinator = entry.runtime_data
    ent_reg = er.async_get(hass)
    tracked: dict[int, AisTankerTracker] = {}

    # Remove orphaned registry entries from previous runs.
    current: set[int] = set(coordinator.data.tracked_mmsi) if coordinator.data else set()
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if reg_entry.domain != Platform.DEVICE_TRACKER:
            continue
        mmsi = _mmsi_from_unique_id(reg_entry.unique_id, entry.entry_id)
        if mmsi is None or mmsi not in current:
            LOGGER.debug("Removing orphaned tracker %s", reg_entry.entity_id)
            ent_reg.async_remove(reg_entry.entity_id)

    @callback
    def _async_sync_entities() -> None:
        """Add trackers for new tankers, remove trackers for gone ones."""
        data = coordinator.data
        wanted: set[int] = set(data.tracked_mmsi) if data else set()

        new_entities = [
            AisTankerTracker(coordinator, entry, mmsi)
            for mmsi in (data.tracked_mmsi if data else [])
            if mmsi not in tracked
        ]
        for entity in new_entities:
            tracked[entity.mmsi] = entity
        if new_entities:
            async_add_entities(new_entities)

        for mmsi in [m for m in tracked if m not in wanted]:
            entity = tracked.pop(mmsi)
            reg_entity_id = ent_reg.async_get_entity_id(
                Platform.DEVICE_TRACKER, DOMAIN, entity.unique_id or ""
            )
            if reg_entity_id is not None:
                LOGGER.debug("Deregistering stale tracker %s", reg_entity_id)
                ent_reg.async_remove(reg_entity_id)
            elif entity.hass is not None:
                hass.async_create_task(entity.async_remove(force_remove=True))

    _async_sync_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_sync_entities))


class AisTankerTracker(CoordinatorEntity[AisTankerCoordinator], TrackerEntity):
    """GPS tracker entity for one tanker."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:ferry"
    _attr_source_type = SourceType.GPS

    def __init__(
        self,
        coordinator: AisTankerCoordinator,
        entry: AisTankerConfigEntry,
        mmsi: int,
    ) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator)
        self.mmsi = mmsi
        self._attr_unique_id = f"{entry.entry_id}_{mmsi}"
        self.entity_id = f"device_tracker.ais_tanker_{mmsi}"
        self._present = False
        self._update_from_data()

    @callback
    def _update_from_data(self) -> None:
        """Update position and attributes from the snapshot."""
        data = self.coordinator.data
        vessel: dict[str, Any] | None = data.by_mmsi.get(self.mmsi) if data else None
        self._present = vessel is not None
        if vessel is None:
            if not getattr(self, "_attr_name", None):
                self._attr_name = f"Tanker MMSI {self.mmsi}"
            return
        self._attr_name = f"Tanker {vessel['name']}"
        self._attr_latitude = vessel["lat"]
        self._attr_longitude = vessel["lon"]
        self._attr_extra_state_attributes = {
            key: vessel.get(key) for key in TRACKER_ATTRIBUTE_KEYS
        }

    @property
    def available(self) -> bool:
        """Available only while the tanker is active."""
        return super().available and self._present

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_from_data()
        super()._handle_coordinator_update()

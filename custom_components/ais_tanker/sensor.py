"""Sensor platform for the AIS Tanker Tracker integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_TITLE, DOMAIN, INTEGRATION_VERSION, MAX_OVERVIEW_VESSELS
from .coordinator import AisTankerConfigEntry, AisTankerCoordinator, AisTankerData

UNIT_VESSELS = "vessels"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AisTankerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            AisTankerOverviewSensor(coordinator, entry),
            AisTankerLocalCountSensor(coordinator, entry),
            AisTankerGlobalCountSensor(coordinator, entry),
        ]
    )


class AisTankerBaseSensor(CoordinatorEntity[AisTankerCoordinator], SensorEntity):
    """Common base for all AIS tanker sensors."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UNIT_VESSELS

    def __init__(
        self,
        coordinator: AisTankerCoordinator,
        entry: AisTankerConfigEntry,
        key: str,
        object_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self.entity_id = f"sensor.{object_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=DEFAULT_TITLE,
            manufacturer="AIS-catcher / AISHub",
            model="AIS Tanker Tracker",
            sw_version=INTEGRATION_VERSION,
            entry_type=DeviceEntryType.SERVICE,
        )
        self._update_from_data()

    @property
    def _data(self) -> AisTankerData:
        """Return the current snapshot (never None)."""
        return self.coordinator.data if self.coordinator.data is not None else AisTankerData()

    @callback
    def _update_from_data(self) -> None:
        """Update entity attributes from the coordinator data."""
        raise NotImplementedError

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_from_data()
        super()._handle_coordinator_update()


class AisTankerOverviewSensor(AisTankerBaseSensor):
    """Central hub sensor, data source for the Lovelace card."""

    _attr_icon = "mdi:radar"
    _unrecorded_attributes = frozenset(
        {
            "vessels",
            "mqtt_messages_total",
            "mqtt_last_message",
            "aisstream_messages_total",
            "aisstream_last_message",
        }
    )

    def __init__(self, coordinator: AisTankerCoordinator, entry: AisTankerConfigEntry) -> None:
        """Initialize the overview sensor."""
        super().__init__(coordinator, entry, "overview", "ais_tanker_overview")

    @callback
    def _update_from_data(self) -> None:
        """Update state and attributes."""
        data = self._data
        total = len(data.vessels)
        self._attr_native_value = total
        attributes: dict[str, Any] = {
            "local_sdr_count": data.local_count,
            "aisstream_count": data.aisstream_count,
            "aishub_count": data.aishub_count,
            "demo_count": data.demo_count,
            "pending_unclassified": data.pending_count,
            "last_aishub_sync": data.last_aishub_sync,
            "aishub_status": data.aishub_status,
            "aishub_last_zone": data.aishub_last_zone,
            "aishub_zones": data.aishub_zones,
            "mqtt_enabled": data.mqtt_enabled,
            "mqtt_topic": data.mqtt_topic,
            "mqtt_messages_total": data.mqtt_messages_total,
            "mqtt_last_message": data.mqtt_last_message,
            "aisstream_status": data.aisstream_status,
            "aisstream_messages_total": data.aisstream_messages_total,
            "aisstream_last_message": data.aisstream_last_message,
            "vessels_total": total,
            "vessels_truncated": total > MAX_OVERVIEW_VESSELS,
            "vessels": data.vessels[:MAX_OVERVIEW_VESSELS],
        }
        self._attr_extra_state_attributes = attributes


class AisTankerLocalCountSensor(AisTankerBaseSensor):
    """Number of tankers received via the local SDR."""

    _attr_icon = "mdi:antenna"

    def __init__(self, coordinator: AisTankerCoordinator, entry: AisTankerConfigEntry) -> None:
        """Initialize the local count sensor."""
        super().__init__(coordinator, entry, "local_count", "ais_tanker_local_count")

    @callback
    def _update_from_data(self) -> None:
        """Update state."""
        data = self._data
        self._attr_native_value = data.local_count
        self._attr_extra_state_attributes = {"mqtt_topic": data.mqtt_topic}


class AisTankerGlobalCountSensor(AisTankerBaseSensor):
    """Number of tankers received via the global networks (aisstream.io + AISHub)."""

    _attr_icon = "mdi:earth"

    def __init__(self, coordinator: AisTankerCoordinator, entry: AisTankerConfigEntry) -> None:
        """Initialize the global count sensor."""
        super().__init__(coordinator, entry, "global_count", "ais_tanker_global_count")

    @callback
    def _update_from_data(self) -> None:
        """Update state."""
        data = self._data
        self._attr_native_value = data.aisstream_count + data.aishub_count
        self._attr_extra_state_attributes = {
            "aisstream_count": data.aisstream_count,
            "aisstream_status": data.aisstream_status,
            "aishub_count": data.aishub_count,
            "aishub_status": data.aishub_status,
        }

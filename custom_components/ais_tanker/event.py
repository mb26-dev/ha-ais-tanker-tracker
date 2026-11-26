"""Event platform for the AIS Tanker Tracker integration.

One event entity per configured zone. It fires 'entered' or 'left' whenever a
tanker crosses the zone border, with the vessel data as event attributes, so
zone automations can be built in the UI without templates. The same
transitions are also fired as the bus events ais_tanker_zone_entered and
ais_tanker_zone_left.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import slugify

from .const import (
    LOGGER,
    SIGNAL_ZONE_EVENT,
    ZONE_EVENT_TYPE_ENTERED,
    ZONE_EVENT_TYPE_LEFT,
)
from .coordinator import AisTankerConfigEntry, service_device_info, unique_zone_names


def zone_slugs(names: list[str]) -> dict[str, str]:
    """Map zone names to unique entity id slugs."""
    result: dict[str, str] = {}
    used: set[str] = set()
    for name in names:
        base = slugify(name) or "zone"
        slug = base
        index = 2
        while slug in used:
            slug = f"{base}_{index}"
            index += 1
        used.add(slug)
        result[name] = slug
    return result


def _zone_unique_id(entry_id: str, slug: str) -> str:
    """Unique id of a zone event entity."""
    return f"{entry_id}_zone_{slug}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AisTankerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one zone event entity per configured zone."""
    coordinator = entry.runtime_data
    slugs = zone_slugs(unique_zone_names(coordinator.zones))
    wanted = {_zone_unique_id(entry.entry_id, slug) for slug in slugs.values()}

    # Remove event entities of zones that are no longer configured.
    ent_reg = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if reg_entry.domain == Platform.EVENT and reg_entry.unique_id not in wanted:
            LOGGER.debug("Removing zone event entity %s", reg_entry.entity_id)
            ent_reg.async_remove(reg_entry.entity_id)

    async_add_entities(
        [AisTankerZoneEvent(entry, name, slug) for name, slug in slugs.items()]
    )


class AisTankerZoneEvent(EventEntity):
    """Fires when a tanker enters or leaves one zone."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "zone"
    _attr_icon = "mdi:map-marker-radius"
    _attr_event_types = [ZONE_EVENT_TYPE_ENTERED, ZONE_EVENT_TYPE_LEFT]

    def __init__(self, entry: AisTankerConfigEntry, zone_name: str, slug: str) -> None:
        """Initialize the zone event entity."""
        self.zone_name = zone_name
        self._entry_id = entry.entry_id
        self._attr_unique_id = _zone_unique_id(entry.entry_id, slug)
        self.entity_id = f"event.ais_tanker_zone_{slug}"
        self._attr_translation_placeholders = {"zone": zone_name}
        self._attr_device_info = service_device_info(entry.entry_id)

    async def async_added_to_hass(self) -> None:
        """Listen for zone transitions of this entry."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ZONE_EVENT.format(entry_id=self._entry_id),
                self._async_handle_zone_event,
            )
        )

    @callback
    def _async_handle_zone_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Trigger the entity for transitions of its own zone."""
        if payload.get("zone") != self.zone_name or event_type not in self.event_types:
            return
        self._trigger_event(event_type, dict(payload))
        self.async_write_ha_state()

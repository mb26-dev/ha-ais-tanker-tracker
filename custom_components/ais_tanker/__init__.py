"""AIS Tanker Tracker integration for Home Assistant."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CARD_FILENAME, CARD_URL_BASE, DOMAIN, INTEGRATION_VERSION, LOGGER
from .coordinator import AisTankerConfigEntry, AisTankerCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.DEVICE_TRACKER, Platform.EVENT]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_DATA_CARD_REGISTERED = f"{DOMAIN}_card_registered"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the bundled tanker-radar-card and load it in the frontend."""
    if hass.data.get(_DATA_CARD_REGISTERED):
        return True
    www_path = Path(__file__).parent / "www"
    if not (www_path / CARD_FILENAME).is_file():
        LOGGER.warning("Bundled card not found in %s, skipping frontend registration", www_path)
        return True
    # Serve the whole www folder: the card plus the bundled Leaflet library
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL_BASE, str(www_path), cache_headers=False)]
    )
    url = f"{CARD_URL_BASE}/{CARD_FILENAME}"
    # Version query string so browsers fetch the new card after an update
    add_extra_js_url(hass, f"{url}?v={INTEGRATION_VERSION}")
    hass.data[_DATA_CARD_REGISTERED] = True
    LOGGER.debug("tanker-radar-card served at %s", url)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AisTankerConfigEntry) -> bool:
    """Set up AIS Tanker Tracker from a config entry."""
    coordinator = AisTankerCoordinator(hass, entry)

    try:
        await coordinator.async_start()
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        coordinator.async_stop()
        raise

    entry.runtime_data = coordinator
    entry.async_on_unload(coordinator.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    LOGGER.debug("AIS Tanker Tracker set up (entry %s)", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AisTankerConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = entry.runtime_data
        coordinator.async_stop()
        await coordinator.async_flush_static()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: AisTankerConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)

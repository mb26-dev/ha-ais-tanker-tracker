"""Diagnostics support for the AIS Tanker Tracker integration.

The download is meant to be attached to bug reports, so it never contains
API keys, the home location, zone coordinates or anything that could be used
to work out where the user lives (distance and bearing from home are removed
from the vessel samples).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import (
    CONF_AISHUB_API_KEY,
    CONF_AISHUB_ZONES,
    CONF_AISSTREAM_API_KEY,
    INTEGRATION_VERSION,
)
from .coordinator import AisTankerConfigEntry

TO_REDACT_OPTIONS = {CONF_AISHUB_API_KEY, CONF_AISSTREAM_API_KEY, CONF_AISHUB_ZONES}

# Vessel fields that are relative to the home location
TO_REDACT_VESSEL = {"distance_km", "bearing_deg"}

VESSEL_SAMPLE_SIZE = 5


def _size(coordinator: Any, attribute: str) -> int | None:
    """Return the length of an internal cache, or None if it does not exist."""
    value = getattr(coordinator, attribute, None)
    try:
        return len(value) if value is not None else None
    except TypeError:
        return None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AisTankerConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data

    options = {**entry.data, **entry.options}
    zones = getattr(coordinator, "_zones", None) or []

    diagnostics: dict[str, Any] = {
        "integration_version": INTEGRATION_VERSION,
        "options": async_redact_data(options, TO_REDACT_OPTIONS),
        "configured_zones": [zone.name for zone in zones],
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
            "cache_sizes": {
                "local_sdr": _size(coordinator, "_local"),
                "aisstream": _size(coordinator, "_stream"),
                "aishub": _size(coordinator, "_aishub"),
                "rejected_non_tankers": _size(coordinator, "_rejected"),
                "static_ship_database": _size(coordinator, "_static"),
            },
        },
    }

    if data is None:
        diagnostics["data"] = None
        return diagnostics

    diagnostics["data"] = {
        "vessels_total": len(data.vessels),
        "tracked_vessels": len(data.tracked_mmsi),
        "counts": {
            "local_sdr": data.local_count,
            "aisstream": data.aisstream_count,
            "aishub": data.aishub_count,
            "demo": data.demo_count,
            "pending_unclassified": data.pending_count,
        },
        "mqtt": {
            "enabled": data.mqtt_enabled,
            "topic": data.mqtt_topic,
            "messages_total": data.mqtt_messages_total,
            "last_message": data.mqtt_last_message,
        },
        "aisstream": {
            "status": data.aisstream_status,
            "messages_total": data.aisstream_messages_total,
            "last_message": data.aisstream_last_message,
        },
        "aishub": {
            "status": data.aishub_status,
            "last_sync": data.last_aishub_sync,
            "last_zone": data.aishub_last_zone,
        },
        "vessel_sample": [
            async_redact_data(vessel, TO_REDACT_VESSEL)
            for vessel in data.vessels[:VESSEL_SAMPLE_SIZE]
        ],
    }
    return diagnostics

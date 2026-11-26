"""Helpers shared by the AIS Tanker Tracker tests."""

from __future__ import annotations

from typing import Any

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ais_tanker.const import (
    CONF_TRACKER_MIN_WRITE_SECONDS,
    DEFAULT_OPTIONS,
    DEFAULT_TITLE,
    DOMAIN,
)

# Options as stored by versions before 1.2.5 (no tracker interval option)
LEGACY_OPTIONS: dict[str, Any] = {
    key: value for key, value in DEFAULT_OPTIONS.items() if key != CONF_TRACKER_MIN_WRITE_SECONDS
}


def make_entry(options: dict[str, Any] | None = None, **overrides: Any) -> MockConfigEntry:
    """Config entry with the default options, updated with the overrides."""
    base = dict(DEFAULT_OPTIONS) if options is None else dict(options)
    base.update(overrides)
    return MockConfigEntry(domain=DOMAIN, title=DEFAULT_TITLE, data={}, options=base)


def static_message(mmsi: int, shiptype: int = 80, **extra: Any) -> dict[str, Any]:
    """AIS-catcher style static message (type 5) for a 180 m ship."""
    message: dict[str, Any] = {
        "mmsi": mmsi,
        "type": 5,
        "shiptype": shiptype,
        "shipname": f"TEST {mmsi}",
        "to_bow": 150,
        "to_stern": 30,
        "to_port": 16,
        "to_starboard": 16,
        "draught": 11.0,
    }
    message.update(extra)
    return message


def position_message(mmsi: int, lat: float, lon: float, **extra: Any) -> dict[str, Any]:
    """AIS-catcher style position report (type 1)."""
    message: dict[str, Any] = {
        "mmsi": mmsi,
        "type": 1,
        "lat": lat,
        "lon": lon,
        "speed": 10.5,
        "course": 90.0,
        "heading": 91,
        "status": 0,
    }
    message.update(extra)
    return message

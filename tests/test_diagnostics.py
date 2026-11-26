"""Tests for the diagnostics download."""

from __future__ import annotations

from collections.abc import Callable
import json

from custom_components.ais_tanker.const import (
    CONF_AISHUB_API_KEY,
    CONF_AISHUB_ZONES,
    CONF_AISSTREAM_API_KEY,
    CONF_TRACKER_MIN_WRITE_SECONDS,
    INTEGRATION_VERSION,
)
from custom_components.ais_tanker.coordinator import AisTankerCoordinator
from custom_components.ais_tanker.diagnostics import async_get_config_entry_diagnostics
from homeassistant.core import HomeAssistant

REDACTED = "**REDACTED**"


async def test_diagnostics_redacts_private_data(
    hass: HomeAssistant, make_coordinator: Callable[..., AisTankerCoordinator]
) -> None:
    """API keys, zone coordinates and home-relative values are removed."""
    coordinator = make_coordinator(
        aisstream_api_key="stream-secret-key",
        aishub_api_key="hub-secret-user",
        aishub_zones="Andaman:5.25,9.75,96.5,100.5",
        enable_demo_vessels=True,
        tracker_min_write_seconds=120,
    )
    coordinator.data = coordinator._build_snapshot()

    diagnostics = await async_get_config_entry_diagnostics(hass, coordinator.config_entry)

    assert diagnostics["integration_version"] == INTEGRATION_VERSION
    options = diagnostics["options"]
    assert options[CONF_AISSTREAM_API_KEY] == REDACTED
    assert options[CONF_AISHUB_API_KEY] == REDACTED
    assert options[CONF_AISHUB_ZONES] == REDACTED
    assert options[CONF_TRACKER_MIN_WRITE_SECONDS] == 120
    assert diagnostics["configured_zones"] == ["Andaman"]
    assert diagnostics["tracker_min_write_seconds"] == 120
    assert diagnostics["zone_events"]["fired_total"] == {"entered": 0, "left": 0}

    data = diagnostics["data"]
    assert data["vessels_total"] == 3
    assert data["counts"]["demo"] == 3
    assert len(data["vessel_sample"]) == 3
    for vessel in data["vessel_sample"]:
        assert vessel["distance_km"] == REDACTED
        assert vessel["bearing_deg"] == REDACTED

    text = json.dumps(diagnostics, default=str)
    assert "stream-secret-key" not in text
    assert "hub-secret-user" not in text
    assert "5.25,9.75" not in text
    assert "96.5" not in text


async def test_diagnostics_without_data(
    hass: HomeAssistant, make_coordinator: Callable[..., AisTankerCoordinator]
) -> None:
    """Diagnostics work before the first snapshot."""
    coordinator = make_coordinator(enable_demo_vessels=True)
    coordinator.data = None

    diagnostics = await async_get_config_entry_diagnostics(hass, coordinator.config_entry)

    assert diagnostics["data"] is None
    assert diagnostics["configured_zones"] == []
    assert diagnostics["tracker_min_write_seconds"] == 300

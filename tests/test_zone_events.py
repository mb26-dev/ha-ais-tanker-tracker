"""Tests for the zone events (bus events and event entities)."""

from __future__ import annotations

from collections.abc import Callable
import time
from typing import Any
from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.ais_tanker import event as event_platform
from custom_components.ais_tanker.const import (
    DOMAIN,
    EVENT_ZONE_ENTERED,
    EVENT_ZONE_LEFT,
    SIGNAL_ZONE_EVENT,
    ZONE_REASON_APPEARED,
    ZONE_REASON_LOST,
    ZONE_REASON_MOVED,
)
from custom_components.ais_tanker.coordinator import AisTankerCoordinator
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .common import make_entry, position_message, static_message

ZONES = "Box:0.0,2.0,100.0,102.0"
MMSI = 563000200
INSIDE = (1.0, 101.0)
OUTSIDE = (3.0, 101.0)


def _publish(coordinator: AisTankerCoordinator) -> None:
    """Build a snapshot and notify the listeners like the coordinator does."""
    coordinator.data = coordinator._build_snapshot()
    coordinator.async_update_listeners()


def _move(coordinator: AisTankerCoordinator, mmsi: int, position: tuple[float, float]) -> None:
    """Report a new position from the local SDR."""
    coordinator._ingest(coordinator._local, position_message(mmsi, *position), time.time())


def _add_tanker(coordinator: AisTankerCoordinator, mmsi: int, position: tuple[float, float]) -> None:
    """Report a tanker (static data and position) from the local SDR."""
    coordinator._ingest(coordinator._local, static_message(mmsi, shipname="ZONE TESTER"), time.time())
    _move(coordinator, mmsi, position)


async def test_enter_and_leave_zone(
    hass: HomeAssistant, make_coordinator: Callable[..., AisTankerCoordinator]
) -> None:
    """Crossing the zone border fires entered and left with the vessel data."""
    coordinator = make_coordinator(aishub_zones=ZONES)
    coordinator._zone_warmup_until = 0.0
    entered = async_capture_events(hass, EVENT_ZONE_ENTERED)
    left = async_capture_events(hass, EVENT_ZONE_LEFT)
    signals: list[tuple[str, dict[str, Any]]] = []

    @callback
    def _signal(event_type: str, payload: dict[str, Any]) -> None:
        signals.append((event_type, payload))

    async_dispatcher_connect(hass, SIGNAL_ZONE_EVENT.format(entry_id=coordinator.config_entry.entry_id), _signal)

    _add_tanker(coordinator, MMSI, OUTSIDE)
    _publish(coordinator)  # baseline
    await hass.async_block_till_done()
    assert not entered
    assert not left

    _move(coordinator, MMSI, INSIDE)
    _publish(coordinator)
    await hass.async_block_till_done()
    assert len(entered) == 1
    data = entered[0].data
    assert data["mmsi"] == MMSI
    assert data["name"] == "ZONE TESTER"
    assert data["zone"] == "Box"
    assert data["reason"] == ZONE_REASON_MOVED
    assert data["load_status"] == "Laden"
    assert data["vessel_class"] == "Handysize / MR Tanker"
    assert coordinator.data.by_mmsi[MMSI]["zones"] == ["Box"]

    _publish(coordinator)  # no change, no new event
    await hass.async_block_till_done()
    assert len(entered) == 1

    _move(coordinator, MMSI, OUTSIDE)
    _publish(coordinator)
    await hass.async_block_till_done()
    assert len(left) == 1
    assert left[0].data["zone"] == "Box"
    assert left[0].data["reason"] == ZONE_REASON_MOVED

    _move(coordinator, MMSI, INSIDE)
    _publish(coordinator)
    coordinator._local.clear()
    _publish(coordinator)
    await hass.async_block_till_done()
    assert len(entered) == 2
    assert len(left) == 2
    assert left[1].data["reason"] == ZONE_REASON_LOST
    assert left[1].data["name"] == "ZONE TESTER"

    assert [event_type for event_type, _ in signals] == ["entered", "left", "entered", "left"]
    assert coordinator.zone_events_total == {"entered": 2, "left": 2}


async def test_warmup_suppresses_appeared(
    hass: HomeAssistant, make_coordinator: Callable[..., AisTankerCoordinator]
) -> None:
    """After a start, tankers already inside a zone do not fire entered."""
    coordinator = make_coordinator(aishub_zones=ZONES)
    entered = async_capture_events(hass, EVENT_ZONE_ENTERED)
    left = async_capture_events(hass, EVENT_ZONE_LEFT)

    _publish(coordinator)  # baseline (empty)
    assert coordinator.zone_warmup_active is True
    _add_tanker(coordinator, MMSI, INSIDE)
    _publish(coordinator)
    await hass.async_block_till_done()
    assert not entered

    # Leaving is still reported for the tanker found during warm-up
    _move(coordinator, MMSI, OUTSIDE)
    _publish(coordinator)
    await hass.async_block_till_done()
    assert len(left) == 1

    # After the warm-up a new tanker inside the zone fires 'appeared'
    coordinator._zone_warmup_until = 0.0
    _add_tanker(coordinator, MMSI + 1, INSIDE)
    _publish(coordinator)
    await hass.async_block_till_done()
    assert len(entered) == 1
    assert entered[0].data["mmsi"] == MMSI + 1
    assert entered[0].data["reason"] == ZONE_REASON_APPEARED


async def test_no_zones_no_events(
    hass: HomeAssistant, make_coordinator: Callable[..., AisTankerCoordinator]
) -> None:
    """Without zones nothing is fired."""
    coordinator = make_coordinator()
    coordinator._zone_warmup_until = 0.0
    entered = async_capture_events(hass, EVENT_ZONE_ENTERED)

    _publish(coordinator)
    _add_tanker(coordinator, MMSI, INSIDE)
    _publish(coordinator)
    await hass.async_block_till_done()
    assert not entered
    assert coordinator.data.by_mmsi[MMSI]["zones"] == []


async def test_overlapping_zones(
    hass: HomeAssistant, make_coordinator: Callable[..., AisTankerCoordinator]
) -> None:
    """Moving from one zone into an overlapping one fires left and entered."""
    coordinator = make_coordinator(aishub_zones="Outer:0,10,100,110;Inner:4,6,104,106")
    coordinator._zone_warmup_until = 0.0
    entered = async_capture_events(hass, EVENT_ZONE_ENTERED)
    left = async_capture_events(hass, EVENT_ZONE_LEFT)

    _add_tanker(coordinator, MMSI, (1.0, 101.0))
    _publish(coordinator)
    _move(coordinator, MMSI, (5.0, 105.0))
    _publish(coordinator)
    await hass.async_block_till_done()
    assert [event.data["zone"] for event in entered] == ["Inner"]
    assert not left

    _move(coordinator, MMSI, (20.0, 105.0))
    _publish(coordinator)
    await hass.async_block_till_done()
    assert [event.data["zone"] for event in left] == ["Outer", "Inner"]


async def test_event_platform_creates_one_entity_per_zone(
    hass: HomeAssistant, make_coordinator: Callable[..., AisTankerCoordinator]
) -> None:
    """One event entity per unique zone name, stale zone entities are removed."""
    coordinator = make_coordinator(
        aishub_zones="Singapore:0.9,1.6,103.3,104.6;Hormuz:24.5,27.5,54.5,58.5;Singapore:1,2,103,104"
    )
    entry = coordinator.config_entry
    ent_reg = er.async_get(hass)
    old = ent_reg.async_get_or_create("event", DOMAIN, f"{entry.entry_id}_zone_suez", config_entry=entry)

    added: list[event_platform.AisTankerZoneEvent] = []
    await event_platform.async_setup_entry(hass, entry, lambda entities, *args, **kwargs: added.extend(entities))

    assert [entity.zone_name for entity in added] == ["Singapore", "Hormuz"]
    assert [entity.entity_id for entity in added] == [
        "event.ais_tanker_zone_singapore",
        "event.ais_tanker_zone_hormuz",
    ]
    assert added[0].unique_id == f"{entry.entry_id}_zone_singapore"
    assert ent_reg.async_get(old.entity_id) is None


def test_zone_slugs_are_unique() -> None:
    """Names that slugify to the same id get a suffix."""
    assert event_platform.zone_slugs(["Port A", "Port-A", "Rotterdam"]) == {
        "Port A": "port_a",
        "Port-A": "port_a_2",
        "Rotterdam": "rotterdam",
    }


async def test_event_entity_triggers_for_its_zone(hass: HomeAssistant) -> None:
    """The entity fires only for transitions of its own zone."""
    entry = make_entry(aishub_zones=ZONES)
    entry.add_to_hass(hass)
    entity = event_platform.AisTankerZoneEvent(entry, "Box", "box")
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()  # type: ignore[method-assign]

    entity._async_handle_zone_event("entered", {"zone": "Other", "mmsi": 1})
    entity.async_write_ha_state.assert_not_called()

    entity._async_handle_zone_event("entered", {"zone": "Box", "mmsi": MMSI, "name": "ZONE TESTER"})
    entity.async_write_ha_state.assert_called_once()
    attributes = entity.state_attributes
    assert attributes["event_type"] == "entered"
    assert attributes["mmsi"] == MMSI
    assert attributes["name"] == "ZONE TESTER"

    entity._async_handle_zone_event("left", {"zone": "Box", "mmsi": MMSI, "reason": "lost"})
    assert entity.state_attributes["event_type"] == "left"
    assert entity.state_attributes["reason"] == "lost"

"""Tests for the tanker filter (AIS ship types 80-89) and the merged snapshot."""

from __future__ import annotations

from collections.abc import Callable
import time

import pytest

from custom_components.ais_tanker.const import SOURCE_AISHUB, SOURCE_AISSTREAM, SOURCE_LOCAL
from custom_components.ais_tanker.coordinator import (
    AisTankerCoordinator,
    is_tanker_type,
    normalize_aishub_record,
    tanker_label,
)
from homeassistant.core import HomeAssistant

from .common import position_message, static_message


@pytest.mark.parametrize(("shiptype", "expected"), [(79, False), (80, True), (84, True), (89, True), (90, False)])
def test_is_tanker_type(shiptype: int, expected: bool) -> None:
    """Only AIS ship types 80-89 are tankers."""
    assert is_tanker_type(shiptype) is expected


@pytest.mark.parametrize("value", [None, "80", 80.0, True])
def test_is_tanker_type_needs_int(value: object) -> None:
    """Non integer values are never tankers."""
    assert is_tanker_type(value) is False


def test_tanker_label() -> None:
    """Readable labels for the tanker categories."""
    assert tanker_label(81) == "Tanker (Hazardous Cat A)"
    assert tanker_label(89) == "Tanker (No Additional Info)"
    assert tanker_label(None) == "Unknown"
    assert tanker_label(70) == "Unknown"


def test_aishub_non_tanker_is_dropped() -> None:
    """AISHub records of other ship types are ignored."""
    record = {"MMSI": 211000001, "TYPE": 70, "LATITUDE": 1.0, "LONGITUDE": 103.0}
    assert normalize_aishub_record(record, time.time()) is None
    record["TYPE"] = 84
    assert normalize_aishub_record(record, time.time()) is not None


async def test_tanker_from_local_sdr(
    hass: HomeAssistant, make_coordinator: Callable[..., AisTankerCoordinator]
) -> None:
    """A tanker becomes active once type and position are known."""
    coordinator = make_coordinator()
    now = time.time()
    mmsi = 563000001

    assert coordinator._ingest(coordinator._local, static_message(mmsi), now) is False
    assert coordinator._ingest(coordinator._local, position_message(mmsi, 1.2, 103.8), now) is True

    data = coordinator._build_snapshot()
    assert [vessel["mmsi"] for vessel in data.vessels] == [mmsi]
    vessel = data.by_mmsi[mmsi]
    assert vessel["source"] == SOURCE_LOCAL
    assert vessel["name"] == f"TEST {mmsi}"
    assert vessel["length_m"] == 180
    assert vessel["width_m"] == 32
    assert vessel["vessel_class"] == "Handysize / MR Tanker"
    assert vessel["load_status"] == "Laden"
    assert vessel["zones"] == []
    assert data.local_count == 1
    assert data.tracked_mmsi == [mmsi]


async def test_non_tanker_is_rejected(
    hass: HomeAssistant, make_coordinator: Callable[..., AisTankerCoordinator]
) -> None:
    """Cargo ships are rejected and later messages of them are ignored."""
    coordinator = make_coordinator()
    now = time.time()
    mmsi = 211000001

    assert coordinator._ingest(coordinator._local, static_message(mmsi, shiptype=70), now) is False
    assert mmsi in coordinator._rejected
    assert coordinator._ingest(coordinator._local, position_message(mmsi, 1.2, 103.8), now) is False
    assert mmsi not in coordinator._local
    assert coordinator._build_snapshot().vessels == []


async def test_unclassified_vessel_is_pending(
    hass: HomeAssistant, make_coordinator: Callable[..., AisTankerCoordinator]
) -> None:
    """A position without known ship type is counted as pending, not shown."""
    coordinator = make_coordinator()
    coordinator._ingest(coordinator._local, position_message(563000002, 1.2, 103.8), time.time())

    data = coordinator._build_snapshot()
    assert data.vessels == []
    assert data.pending_count == 1


async def test_tanker_changing_to_other_type_is_removed(
    hass: HomeAssistant, make_coordinator: Callable[..., AisTankerCoordinator]
) -> None:
    """A tanker that reports another ship type disappears from the snapshot."""
    coordinator = make_coordinator()
    now = time.time()
    mmsi = 563000003
    coordinator._ingest(coordinator._local, static_message(mmsi), now)
    coordinator._ingest(coordinator._local, position_message(mmsi, 1.2, 103.8), now)
    assert mmsi in coordinator._build_snapshot().by_mmsi

    assert coordinator._ingest(coordinator._local, static_message(mmsi, shiptype=60), now) is True
    assert mmsi not in coordinator._build_snapshot().by_mmsi
    assert mmsi in coordinator._rejected


async def test_source_priority_and_merge(
    hass: HomeAssistant, make_coordinator: Callable[..., AisTankerCoordinator]
) -> None:
    """Local SDR wins over aisstream.io, missing fields come from AISHub."""
    coordinator = make_coordinator()
    now = time.time()
    mmsi = 563000004

    coordinator._aishub[mmsi] = {
        "lat": 1.0,
        "lon": 103.0,
        "shiptype": 80,
        "shipname": "FROM AISHUB",
        "destination": "SINGAPORE",
        "last_seen": now,
    }
    coordinator._ingest(coordinator._stream, position_message(mmsi, 1.1, 103.1), now)
    data = coordinator._build_snapshot()
    vessel = data.by_mmsi[mmsi]
    assert vessel["source"] == SOURCE_AISSTREAM
    assert vessel["lat"] == 1.1
    assert vessel["destination"] == "SINGAPORE"

    coordinator._ingest(coordinator._local, position_message(mmsi, 1.2, 103.2), now)
    vessel = coordinator._build_snapshot().by_mmsi[mmsi]
    assert vessel["source"] == SOURCE_LOCAL
    assert vessel["lat"] == 1.2
    assert vessel["name"] == "FROM AISHUB"

    coordinator._local.clear()
    coordinator._stream.clear()
    assert coordinator._build_snapshot().by_mmsi[mmsi]["source"] == SOURCE_AISHUB


async def test_stale_vessels_are_purged(
    hass: HomeAssistant, make_coordinator: Callable[..., AisTankerCoordinator]
) -> None:
    """Vessels without updates within the stale timeout are removed."""
    coordinator = make_coordinator(stale_timeout_minutes=10)
    old = time.time() - 11 * 60
    mmsi = 563000005
    coordinator._ingest(coordinator._local, static_message(mmsi), old)
    coordinator._ingest(coordinator._local, position_message(mmsi, 1.2, 103.8), old)

    assert coordinator._build_snapshot().vessels == []
    assert mmsi not in coordinator._local


async def test_max_tracked_vessels(
    hass: HomeAssistant, make_coordinator: Callable[..., AisTankerCoordinator]
) -> None:
    """Only the nearest N tankers get a device tracker."""
    coordinator = make_coordinator(max_tracked_vessels=2)
    now = time.time()
    home_lat = hass.config.latitude
    home_lon = hass.config.longitude
    for index, mmsi in enumerate((563000011, 563000012, 563000013)):
        coordinator._ingest(coordinator._local, static_message(mmsi), now)
        coordinator._ingest(
            coordinator._local, position_message(mmsi, home_lat + 0.1 * (3 - index), home_lon), now
        )

    data = coordinator._build_snapshot()
    assert [vessel["mmsi"] for vessel in data.vessels] == [563000013, 563000012, 563000011]
    assert data.tracked_mmsi == [563000013, 563000012]

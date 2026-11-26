"""Tests for the throttled device tracker state writes and the interval option."""

from __future__ import annotations

from collections.abc import Callable, Generator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.ais_tanker.const import (
    CONF_TRACKER_MIN_WRITE_SECONDS,
    DEFAULT_TRACKER_MIN_WRITE_SECONDS,
    TRACKER_HEARTBEAT_SECONDS,
)
from custom_components.ais_tanker.coordinator import AisTankerCoordinator, clamp_tracker_interval
from custom_components.ais_tanker.device_tracker import AisTankerTracker
from homeassistant.core import HomeAssistant

from .common import LEGACY_OPTIONS

MMSI = 563000100


class FakeClock:
    """Controllable replacement for time.monotonic in the tracker module."""

    def __init__(self) -> None:
        """Start at an arbitrary point in time."""
        self.now = 10_000.0

    def monotonic(self) -> float:
        """Return the current fake time."""
        return self.now


@pytest.fixture
def clock() -> Generator[FakeClock]:
    """Patch the clock used by the device tracker."""
    fake = FakeClock()
    with patch("custom_components.ais_tanker.device_tracker.time", fake):
        yield fake


def _vessel(lat: float = 1.2, lon: float = 103.8, **extra: Any) -> dict[str, Any]:
    """Vessel dict as published by the coordinator."""
    vessel: dict[str, Any] = {
        "mmsi": MMSI,
        "name": "THROTTLE TEST",
        "lat": lat,
        "lon": lon,
        "load_status": "Laden",
        "nav_status": "Under way using engine",
        "destination": "SINGAPORE",
        "draught_m": 11.0,
        "source": "local_sdr",
        "speed_knots": 10.0,
        "zones": [],
    }
    vessel.update(extra)
    return vessel


def _coordinator(interval: int) -> SimpleNamespace:
    """Minimal coordinator stand-in for the tracker entity."""
    return SimpleNamespace(
        data=SimpleNamespace(by_mmsi={MMSI: _vessel()}),
        last_update_success=True,
        tracker_min_write_seconds=interval,
    )


def _tracker(coordinator: SimpleNamespace) -> AisTankerTracker:
    """Tracker entity with a mocked state writer."""
    tracker = AisTankerTracker(coordinator, SimpleNamespace(entry_id="test_entry"), MMSI)  # type: ignore[arg-type]
    tracker.async_write_ha_state = MagicMock()  # type: ignore[method-assign]
    return tracker


def _publish(tracker: AisTankerTracker, coordinator: SimpleNamespace, vessel: dict[str, Any] | None) -> None:
    """Publish a new snapshot to the tracker."""
    coordinator.data = SimpleNamespace(by_mmsi={MMSI: vessel} if vessel is not None else {})
    tracker._handle_coordinator_update()


def test_default_interval(clock: FakeClock) -> None:
    """Changes are written at most every 300 s, unchanged state every 1800 s."""
    coordinator = _coordinator(DEFAULT_TRACKER_MIN_WRITE_SECONDS)
    tracker = _tracker(coordinator)
    writes = tracker.async_write_ha_state

    _publish(tracker, coordinator, _vessel())
    assert writes.call_count == 1  # first state is always written

    clock.now += 10
    _publish(tracker, coordinator, _vessel(lat=1.3))
    assert writes.call_count == 1  # changed, but too early

    clock.now += 290
    _publish(tracker, coordinator, _vessel(lat=1.3))
    assert writes.call_count == 2  # 300 s since the last write

    clock.now += 1
    _publish(tracker, coordinator, _vessel(lat=1.3, speed_knots=11.0))
    assert writes.call_count == 2  # speed is not part of the signature

    clock.now += TRACKER_HEARTBEAT_SECONDS - 2
    _publish(tracker, coordinator, _vessel(lat=1.3))
    assert writes.call_count == 2

    clock.now += 1
    _publish(tracker, coordinator, _vessel(lat=1.3))
    assert writes.call_count == 3  # heartbeat


def test_availability_change_is_written_immediately(clock: FakeClock) -> None:
    """Appearing and disappearing tankers are never throttled."""
    coordinator = _coordinator(DEFAULT_TRACKER_MIN_WRITE_SECONDS)
    tracker = _tracker(coordinator)
    writes = tracker.async_write_ha_state

    _publish(tracker, coordinator, _vessel())
    assert tracker.available is True

    clock.now += 5
    _publish(tracker, coordinator, None)
    assert writes.call_count == 2
    assert tracker.available is False

    clock.now += 5
    _publish(tracker, coordinator, _vessel())
    assert writes.call_count == 3
    assert tracker.available is True


def test_custom_short_interval(clock: FakeClock) -> None:
    """A shorter configured interval writes changes sooner."""
    coordinator = _coordinator(60)
    tracker = _tracker(coordinator)
    writes = tracker.async_write_ha_state

    _publish(tracker, coordinator, _vessel())
    clock.now += 59
    _publish(tracker, coordinator, _vessel(lat=1.3))
    assert writes.call_count == 1
    clock.now += 1
    _publish(tracker, coordinator, _vessel(lat=1.3))
    assert writes.call_count == 2

    # The heartbeat stays at 30 minutes for short intervals
    clock.now += 61
    _publish(tracker, coordinator, _vessel(lat=1.3))
    assert writes.call_count == 2


def test_long_interval_stretches_heartbeat(clock: FakeClock) -> None:
    """An interval longer than the heartbeat also delays the heartbeat."""
    coordinator = _coordinator(3600)
    tracker = _tracker(coordinator)
    writes = tracker.async_write_ha_state

    _publish(tracker, coordinator, _vessel())
    clock.now += TRACKER_HEARTBEAT_SECONDS + 1
    _publish(tracker, coordinator, _vessel())
    assert writes.call_count == 1
    clock.now += 3600 - TRACKER_HEARTBEAT_SECONDS - 1
    _publish(tracker, coordinator, _vessel())
    assert writes.call_count == 2


def test_zone_change_is_relevant(clock: FakeClock) -> None:
    """Entering a zone counts as a relevant change."""
    coordinator = _coordinator(DEFAULT_TRACKER_MIN_WRITE_SECONDS)
    tracker = _tracker(coordinator)
    writes = tracker.async_write_ha_state

    _publish(tracker, coordinator, _vessel())
    clock.now += DEFAULT_TRACKER_MIN_WRITE_SECONDS
    _publish(tracker, coordinator, _vessel(zones=["Singapore"]))
    assert writes.call_count == 2
    assert tracker.extra_state_attributes["zones"] == ["Singapore"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(300, 300), (45, 45), (5, 30), (99999, 3600), ("120", 120), (None, 300), ("abc", 300), (90.7, 90)],
)
def test_clamp_tracker_interval(value: object, expected: int) -> None:
    """Invalid or out of range values are corrected."""
    assert clamp_tracker_interval(value) == expected


async def test_existing_entries_keep_300_seconds(
    hass: HomeAssistant, make_coordinator: Callable[..., AisTankerCoordinator]
) -> None:
    """Entries created before 1.2.5 have no option and keep 300 s."""
    assert CONF_TRACKER_MIN_WRITE_SECONDS not in LEGACY_OPTIONS
    coordinator = make_coordinator(LEGACY_OPTIONS)
    assert coordinator.tracker_min_write_seconds == 300


async def test_configured_interval_is_used(
    hass: HomeAssistant, make_coordinator: Callable[..., AisTankerCoordinator]
) -> None:
    """The option from the options flow reaches the coordinator."""
    coordinator = make_coordinator(**{CONF_TRACKER_MIN_WRITE_SECONDS: 90})
    assert coordinator.tracker_min_write_seconds == 90

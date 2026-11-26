"""Shared fixtures for the AIS Tanker Tracker tests."""

from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.ais_tanker.coordinator import AisTankerCoordinator
from homeassistant.core import HomeAssistant

from .common import make_entry


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow Home Assistant to load the integration from custom_components."""


@pytest.fixture
def mock_clientsession() -> Generator[MagicMock]:
    """Never open a real HTTP session in the coordinator."""
    with patch("custom_components.ais_tanker.coordinator.async_get_clientsession") as mock:
        yield mock


@pytest.fixture
def make_coordinator(
    hass: HomeAssistant, mock_clientsession: MagicMock
) -> Generator[Callable[..., AisTankerCoordinator]]:
    """Factory for coordinators bound to a fresh config entry.

    The delayed write of the static ship cache is patched out, so no timer is
    left behind after a test.
    """
    created: list[AisTankerCoordinator] = []

    def _make(options: dict[str, Any] | None = None, **overrides: Any) -> AisTankerCoordinator:
        entry = make_entry(options, **overrides)
        entry.add_to_hass(hass)
        coordinator = AisTankerCoordinator(hass, entry)
        entry.runtime_data = coordinator
        created.append(coordinator)
        return coordinator

    with patch.object(AisTankerCoordinator, "_schedule_save"):
        yield _make
    for coordinator in created:
        coordinator.async_stop()

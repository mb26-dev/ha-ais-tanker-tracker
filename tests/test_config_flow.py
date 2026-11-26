"""Tests for the config and options flow."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol

from custom_components.ais_tanker.config_flow import _validate_input
from custom_components.ais_tanker.const import (
    CONF_ENABLE_DEMO_VESSELS,
    CONF_ENABLE_MQTT,
    CONF_TRACKER_MIN_WRITE_SECONDS,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .common import LEGACY_OPTIONS, make_entry


@pytest.fixture(autouse=True)
def skip_dependencies(hass: HomeAssistant) -> None:
    """Treat the http and frontend dependencies as already set up.

    The flows only need the integration to be loadable; the bundled card and
    its static path are not part of these tests.
    """
    hass.config.components.add("http")
    hass.config.components.add("frontend")


@pytest.fixture
def mock_setup() -> Generator[AsyncMock]:
    """Do not set up the integration when an entry is created."""
    with (
        patch("custom_components.ais_tanker.async_setup", return_value=True),
        patch("custom_components.ais_tanker.async_setup_entry", return_value=True) as mock_entry,
    ):
        yield mock_entry


async def test_user_flow_default_interval(hass: HomeAssistant, mock_setup: AsyncMock) -> None:
    """The setup form defaults to 300 s and stores the chosen interval."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    defaults = result["data_schema"]({CONF_ENABLE_DEMO_VESSELS: True})
    assert defaults[CONF_TRACKER_MIN_WRITE_SECONDS] == 300

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENABLE_MQTT: False, CONF_ENABLE_DEMO_VESSELS: True, CONF_TRACKER_MIN_WRITE_SECONDS: 120},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_TRACKER_MIN_WRITE_SECONDS] == 120
    assert result["options"][CONF_ENABLE_DEMO_VESSELS] is True
    assert len(mock_setup.mock_calls) == 1


async def test_user_flow_needs_a_source(hass: HomeAssistant, mock_setup: AsyncMock) -> None:
    """Without any source the form shows an error."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ENABLE_MQTT: False, CONF_ENABLE_DEMO_VESSELS: False}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_source"}


async def test_user_flow_rejects_out_of_range_interval(hass: HomeAssistant, mock_setup: AsyncMock) -> None:
    """The number selector enforces 30-3600 s."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with pytest.raises(vol.Invalid):
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ENABLE_MQTT: False, CONF_ENABLE_DEMO_VESSELS: True, CONF_TRACKER_MIN_WRITE_SECONDS: 10},
        )


async def test_single_instance(hass: HomeAssistant) -> None:
    """Only one entry is allowed."""
    make_entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


@pytest.mark.parametrize(("value", "valid"), [(30, True), (3600, True), (29, False), (3601, False)])
def test_validate_interval_bounds(value: int, valid: bool) -> None:
    """The form validation checks the interval bounds as well."""
    _, errors = _validate_input(
        {**DEFAULT_OPTIONS, CONF_ENABLE_DEMO_VESSELS: True, CONF_TRACKER_MIN_WRITE_SECONDS: value}
    )
    assert (CONF_TRACKER_MIN_WRITE_SECONDS in errors) is not valid


async def test_options_flow_legacy_entry(hass: HomeAssistant, mock_setup: AsyncMock) -> None:
    """An entry from before 1.2.5 shows 300 s and can store a new value."""
    entry = make_entry(LEGACY_OPTIONS, enable_mqtt=False, enable_demo_vessels=True)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    defaults = result["data_schema"]({})
    assert defaults[CONF_TRACKER_MIN_WRITE_SECONDS] == 300
    assert defaults[CONF_ENABLE_DEMO_VESSELS] is True

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ENABLE_MQTT: False, CONF_ENABLE_DEMO_VESSELS: True, CONF_TRACKER_MIN_WRITE_SECONDS: 600},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_TRACKER_MIN_WRITE_SECONDS] == 600
    assert entry.options[CONF_ENABLE_DEMO_VESSELS] is True

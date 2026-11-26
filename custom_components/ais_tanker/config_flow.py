"""Config and options flow for the AIS Tanker Tracker integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    AISHUB_MIN_INTERVAL_SECONDS,
    CONF_AISHUB_API_KEY,
    CONF_AISHUB_SCAN_INTERVAL,
    CONF_AISHUB_ZONES,
    CONF_AISSTREAM_API_KEY,
    CONF_ENABLE_DEMO_VESSELS,
    CONF_ENABLE_MQTT,
    CONF_MAX_TRACKED_VESSELS,
    CONF_MQTT_TOPIC,
    CONF_STALE_TIMEOUT_MINUTES,
    CONF_TRACKER_MIN_WRITE_SECONDS,
    DEFAULT_OPTIONS,
    DEFAULT_TITLE,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MAX_STALE_TIMEOUT_MINUTES,
    MAX_TRACKED_LIMIT,
    MAX_TRACKER_WRITE_SECONDS,
    MIN_STALE_TIMEOUT_MINUTES,
    MIN_TRACKER_WRITE_SECONDS,
)
from .coordinator import parse_zones


def _valid_subscribe_topic(topic: str) -> bool:
    """Validate a MQTT subscribe topic including wildcards."""
    if not topic or len(topic.encode("utf-8")) > 65535 or "\0" in topic:
        return False
    levels = topic.split("/")
    for index, level in enumerate(levels):
        if "#" in level and (level != "#" or index != len(levels) - 1):
            return False
        if "+" in level and level != "+":
            return False
    return True


def _build_schema(values: Mapping[str, Any]) -> vol.Schema:
    """Build the form schema prefilled with the given values."""
    return vol.Schema(
        {
            vol.Required(
                CONF_ENABLE_MQTT, default=bool(values[CONF_ENABLE_MQTT])
            ): BooleanSelector(),
            vol.Optional(
                CONF_MQTT_TOPIC,
                description={"suggested_value": values[CONF_MQTT_TOPIC]},
            ): TextSelector(),
            vol.Optional(
                CONF_AISSTREAM_API_KEY,
                description={"suggested_value": values[CONF_AISSTREAM_API_KEY]},
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            vol.Optional(
                CONF_AISHUB_API_KEY,
                description={"suggested_value": values[CONF_AISHUB_API_KEY]},
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            vol.Optional(
                CONF_AISHUB_ZONES,
                description={"suggested_value": values[CONF_AISHUB_ZONES]},
            ): TextSelector(TextSelectorConfig(multiline=True)),
            vol.Required(
                CONF_AISHUB_SCAN_INTERVAL,
                default=int(values[CONF_AISHUB_SCAN_INTERVAL]),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=AISHUB_MIN_INTERVAL_SECONDS,
                    max=MAX_SCAN_INTERVAL,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
            vol.Required(
                CONF_STALE_TIMEOUT_MINUTES,
                default=int(values[CONF_STALE_TIMEOUT_MINUTES]),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_STALE_TIMEOUT_MINUTES,
                    max=MAX_STALE_TIMEOUT_MINUTES,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            ),
            vol.Required(
                CONF_MAX_TRACKED_VESSELS,
                default=int(values[CONF_MAX_TRACKED_VESSELS]),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=MAX_TRACKED_LIMIT,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_TRACKER_MIN_WRITE_SECONDS,
                default=int(values[CONF_TRACKER_MIN_WRITE_SECONDS]),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_TRACKER_WRITE_SECONDS,
                    max=MAX_TRACKER_WRITE_SECONDS,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
            vol.Required(
                CONF_ENABLE_DEMO_VESSELS,
                default=bool(values[CONF_ENABLE_DEMO_VESSELS]),
            ): BooleanSelector(),
        }
    )


def _validate_input(user_input: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Clean and validate the submitted form."""
    errors: dict[str, str] = {}
    cleaned: dict[str, Any] = {
        CONF_ENABLE_MQTT: bool(user_input.get(CONF_ENABLE_MQTT, False)),
        CONF_MQTT_TOPIC: str(user_input.get(CONF_MQTT_TOPIC) or "").strip(),
        CONF_AISSTREAM_API_KEY: str(user_input.get(CONF_AISSTREAM_API_KEY) or "").strip(),
        CONF_AISHUB_API_KEY: str(user_input.get(CONF_AISHUB_API_KEY) or "").strip(),
        CONF_AISHUB_ZONES: str(user_input.get(CONF_AISHUB_ZONES) or "").strip(),
        CONF_AISHUB_SCAN_INTERVAL: int(
            user_input.get(CONF_AISHUB_SCAN_INTERVAL, DEFAULT_OPTIONS[CONF_AISHUB_SCAN_INTERVAL])
        ),
        CONF_STALE_TIMEOUT_MINUTES: int(
            user_input.get(CONF_STALE_TIMEOUT_MINUTES, DEFAULT_OPTIONS[CONF_STALE_TIMEOUT_MINUTES])
        ),
        CONF_MAX_TRACKED_VESSELS: int(
            user_input.get(CONF_MAX_TRACKED_VESSELS, DEFAULT_OPTIONS[CONF_MAX_TRACKED_VESSELS])
        ),
        CONF_ENABLE_DEMO_VESSELS: bool(user_input.get(CONF_ENABLE_DEMO_VESSELS, False)),
        CONF_TRACKER_MIN_WRITE_SECONDS: int(
            user_input.get(
                CONF_TRACKER_MIN_WRITE_SECONDS, DEFAULT_OPTIONS[CONF_TRACKER_MIN_WRITE_SECONDS]
            )
        ),
    }

    if cleaned[CONF_ENABLE_MQTT] and not _valid_subscribe_topic(cleaned[CONF_MQTT_TOPIC]):
        errors[CONF_MQTT_TOPIC] = "invalid_topic"

    try:
        parse_zones(cleaned[CONF_AISHUB_ZONES])
    except ValueError:
        errors[CONF_AISHUB_ZONES] = "invalid_zones"

    if cleaned[CONF_AISHUB_SCAN_INTERVAL] < AISHUB_MIN_INTERVAL_SECONDS:
        errors[CONF_AISHUB_SCAN_INTERVAL] = "scan_interval_too_low"

    if not (
        MIN_TRACKER_WRITE_SECONDS
        <= cleaned[CONF_TRACKER_MIN_WRITE_SECONDS]
        <= MAX_TRACKER_WRITE_SECONDS
    ):
        errors[CONF_TRACKER_MIN_WRITE_SECONDS] = "tracker_interval_out_of_range"

    if not (
        cleaned[CONF_ENABLE_MQTT]
        or cleaned[CONF_AISSTREAM_API_KEY]
        or cleaned[CONF_AISHUB_API_KEY]
        or cleaned[CONF_ENABLE_DEMO_VESSELS]
    ):
        errors["base"] = "no_source"

    return cleaned, errors


class AisTankerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and process the setup form."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        values: dict[str, Any] = dict(DEFAULT_OPTIONS)
        if user_input is not None:
            cleaned, errors = _validate_input(user_input)
            if not errors:
                return self.async_create_entry(
                    title=DEFAULT_TITLE, data={}, options=cleaned
                )
            values.update(cleaned)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(values),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AisTankerOptionsFlow:
        """Return the options flow handler."""
        return AisTankerOptionsFlow()


class AisTankerOptionsFlow(OptionsFlow):
    """Handle option changes after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and process the options form."""
        errors: dict[str, str] = {}
        values: dict[str, Any] = {
            **DEFAULT_OPTIONS,
            **self.config_entry.data,
            **self.config_entry.options,
        }
        if user_input is not None:
            cleaned, errors = _validate_input(user_input)
            if not errors:
                return self.async_create_entry(data=cleaned)
            values.update(cleaned)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(values),
            errors=errors,
        )

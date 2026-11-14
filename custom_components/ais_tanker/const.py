"""Constants for the AIS Tanker Tracker integration."""

from __future__ import annotations

import logging
from typing import Any, Final

DOMAIN: Final = "ais_tanker"
LOGGER: Final = logging.getLogger(__package__)

# Bundled Lovelace card, served by the integration itself
CARD_FILENAME: Final = "tanker-radar-card.js"
CARD_URL_BASE: Final = "/ais_tanker_static"

DEFAULT_TITLE: Final = "AIS Tanker Tracker"
INTEGRATION_VERSION: Final = "1.2.0"

# ---------------------------------------------------------------------------
# Config / options keys
# ---------------------------------------------------------------------------
CONF_ENABLE_MQTT: Final = "enable_mqtt"
CONF_MQTT_TOPIC: Final = "mqtt_topic"
CONF_AISHUB_API_KEY: Final = "aishub_api_key"
CONF_AISSTREAM_API_KEY: Final = "aisstream_api_key"
CONF_AISHUB_ZONES: Final = "aishub_zones"
CONF_AISHUB_SCAN_INTERVAL: Final = "aishub_scan_interval"
CONF_STALE_TIMEOUT_MINUTES: Final = "stale_timeout_minutes"
CONF_MAX_TRACKED_VESSELS: Final = "max_tracked_vessels"
CONF_ENABLE_DEMO_VESSELS: Final = "enable_demo_vessels"

DEFAULT_ENABLE_MQTT: Final = True
DEFAULT_MQTT_TOPIC: Final = "ais/#"
DEFAULT_AISHUB_API_KEY: Final = ""
DEFAULT_AISSTREAM_API_KEY: Final = ""
DEFAULT_AISHUB_ZONES: Final = ""
DEFAULT_AISHUB_SCAN_INTERVAL: Final = 90
DEFAULT_STALE_TIMEOUT_MINUTES: Final = 30
DEFAULT_MAX_TRACKED_VESSELS: Final = 50
DEFAULT_ENABLE_DEMO_VESSELS: Final = False

DEFAULT_OPTIONS: Final[dict[str, Any]] = {
    CONF_ENABLE_MQTT: DEFAULT_ENABLE_MQTT,
    CONF_MQTT_TOPIC: DEFAULT_MQTT_TOPIC,
    CONF_AISHUB_API_KEY: DEFAULT_AISHUB_API_KEY,
    CONF_AISSTREAM_API_KEY: DEFAULT_AISSTREAM_API_KEY,
    CONF_AISHUB_ZONES: DEFAULT_AISHUB_ZONES,
    CONF_AISHUB_SCAN_INTERVAL: DEFAULT_AISHUB_SCAN_INTERVAL,
    CONF_STALE_TIMEOUT_MINUTES: DEFAULT_STALE_TIMEOUT_MINUTES,
    CONF_MAX_TRACKED_VESSELS: DEFAULT_MAX_TRACKED_VESSELS,
    CONF_ENABLE_DEMO_VESSELS: DEFAULT_ENABLE_DEMO_VESSELS,
}

# Limits for the UI
MIN_STALE_TIMEOUT_MINUTES: Final = 1
MAX_STALE_TIMEOUT_MINUTES: Final = 1440
MAX_TRACKED_LIMIT: Final = 500
MAX_SCAN_INTERVAL: Final = 3600

# ---------------------------------------------------------------------------
# AISHub
# ---------------------------------------------------------------------------
AISHUB_URL: Final = "https://data.aishub.net/ws.php"
AISHUB_MIN_INTERVAL_SECONDS: Final = 65
AISHUB_REQUEST_TIMEOUT_SECONDS: Final = 30
AISHUB_RATE_LIMIT_BACKOFF_FACTOR: Final = 2

AISHUB_STATUS_OK: Final = "ok"
AISHUB_STATUS_DISABLED: Final = "disabled"
AISHUB_STATUS_RATE_LIMITED: Final = "rate_limited"
AISHUB_STATUS_PENDING: Final = "pending"

# ---------------------------------------------------------------------------
# aisstream.io (websocket, real time)
# ---------------------------------------------------------------------------
AISSTREAM_URL: Final = "wss://stream.aisstream.io/v0/stream"
AISSTREAM_HEARTBEAT_SECONDS: Final = 30
AISSTREAM_BACKOFF_MIN_SECONDS: Final = 5
AISSTREAM_BACKOFF_MAX_SECONDS: Final = 300
AISSTREAM_STABLE_SECONDS: Final = 60
AISSTREAM_DEFAULT_BOX_DEG: Final = 3.0
AISSTREAM_MESSAGE_TYPES: Final[tuple[str, ...]] = (
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
    "ShipStaticData",
    "StaticDataReport",
)

AISSTREAM_STATUS_DISABLED: Final = "disabled"
AISSTREAM_STATUS_CONNECTING: Final = "connecting"
AISSTREAM_STATUS_CONNECTED: Final = "connected"

# Shared key in hass.data to keep the AISHub rate limit across reloads
DATA_AISHUB_LAST_REQUEST: Final = "aishub_last_request_monotonic"

# ---------------------------------------------------------------------------
# Coordinator tuning
# ---------------------------------------------------------------------------
COORDINATOR_INTERVAL_SECONDS: Final = 15
PUSH_DEBOUNCE_SECONDS: Final = 5
MAX_RAW_CACHE: Final = 5000
MAX_REJECTED_CACHE: Final = 20000
REJECTED_TTL_SECONDS: Final = 6 * 3600
MAX_OVERVIEW_VESSELS: Final = 500

# Persistent cache of static vessel data (survives restarts and reloads)
STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = "ais_tanker.static_cache"
STORAGE_SAVE_DELAY_SECONDS: Final = 120
STATIC_TTL_SECONDS: Final = 14 * 86400
MAX_STATIC_CACHE: Final = 10000
STATIC_FIELDS: Final = (
    "shiptype",
    "shipname",
    "callsign",
    "imo",
    "destination",
    "draught",
    "eta",
    "to_bow",
    "to_stern",
    "to_port",
    "to_starboard",
)

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
SOURCE_LOCAL: Final = "local_sdr"
SOURCE_AISSTREAM: Final = "aisstream"
SOURCE_AISHUB: Final = "aishub"
SOURCE_DEMO: Final = "demo"

# ---------------------------------------------------------------------------
# AIS semantics
# ---------------------------------------------------------------------------
TANKER_TYPE_MIN: Final = 80
TANKER_TYPE_MAX: Final = 89

TANKER_TYPE_LABELS: Final[dict[int, str]] = {
    80: "Tanker (General)",
    81: "Tanker (Hazardous Cat A)",
    82: "Tanker (Hazardous Cat B)",
    83: "Tanker (Hazardous Cat C)",
    84: "Tanker (Hazardous Cat D)",
    85: "Tanker (Reserved)",
    86: "Tanker (Reserved)",
    87: "Tanker (Reserved)",
    88: "Tanker (Reserved)",
    89: "Tanker (No Additional Info)",
}

NAV_STATUS_LABELS: Final[dict[int, str]] = {
    0: "Under way using engine",
    1: "At anchor",
    2: "Not under command",
    3: "Restricted manoeuvrability",
    4: "Constrained by her draught",
    5: "Moored",
    6: "Aground",
    7: "Engaged in fishing",
    8: "Under way sailing",
    9: "Reserved (HSC)",
    10: "Reserved (WIG)",
    11: "Power-driven vessel towing astern",
    12: "Power-driven vessel pushing ahead or towing alongside",
    13: "Reserved",
    14: "AIS-SART / MOB / EPIRB active",
    15: "Undefined",
}
NAV_STATUS_UNKNOWN: Final = "Unknown"

VESSEL_CLASS_UNKNOWN: Final = "Unknown"
LOAD_STATUS_LADEN: Final = "Laden"
LOAD_STATUS_BALLAST: Final = "Ballast"
LOAD_STATUS_PARTIAL: Final = "Partial / Transit"
LOAD_STATUS_UNKNOWN: Final = "Unknown"

# Load estimation: draught / length ratio, separate thresholds for small
# coastal / bunker tankers (fuller hull form, deeper relative draught).
SMALL_TANKER_LENGTH_M: Final = 120
LADEN_RATIO_SMALL: Final = 0.065
BALLAST_RATIO_SMALL: Final = 0.050
LADEN_RATIO_LARGE: Final = 0.055
BALLAST_RATIO_LARGE: Final = 0.042

# AIS "not available" markers
AIS_LAT_NA: Final = 91.0
AIS_LON_NA: Final = 181.0
AIS_SPEED_NA: Final = 102.3
AIS_COURSE_NA: Final = 360.0
AIS_HEADING_NA: Final = 511

# ---------------------------------------------------------------------------
# Demo vessels (Andaman Sea / Strait of Malacca)
# ---------------------------------------------------------------------------
DEMO_LOOP_SECONDS: Final = 3 * 3600
DEMO_VESSELS: Final[tuple[dict[str, Any], ...]] = (
    {
        "mmsi": 563999001,
        "shipname": "DEMO ANDAMAN STAR",
        "shiptype": 80,
        "imo": 9900011,
        "callsign": "9VDM1",
        "destination": "PHUKET",
        "draught": 8.5,
        "eta_offset_hours": 6,
        "to_bow": 140,
        "to_stern": 40,
        "to_port": 16,
        "to_starboard": 16,
        "status": 0,
        "speed": 11.4,
        "course": 200.0,
        "heading": 199,
        "start_lat": 7.80,
        "start_lon": 98.10,
    },
    {
        "mmsi": 533999002,
        "shipname": "DEMO MALACCA PIONEER",
        "shiptype": 81,
        "imo": 9900023,
        "callsign": "9MDM2",
        "destination": "SINGAPORE",
        "draught": 16.1,
        "eta_offset_hours": 30,
        "to_bow": 230,
        "to_stern": 44,
        "to_port": 24,
        "to_starboard": 24,
        "status": 0,
        "speed": 13.2,
        "course": 135.0,
        "heading": 134,
        "start_lat": 4.10,
        "start_lon": 99.95,
    },
    {
        "mmsi": 567999003,
        "shipname": "DEMO PENANG SPIRIT",
        "shiptype": 89,
        "imo": 9900035,
        "callsign": "HSDM3",
        "destination": "PENANG",
        "draught": 5.8,
        "eta_offset_hours": 2,
        "to_bow": 70,
        "to_stern": 25,
        "to_port": 8,
        "to_starboard": 8,
        "status": 1,
        "speed": 0.1,
        "course": 45.0,
        "heading": 40,
        "start_lat": 5.36,
        "start_lon": 100.38,
    },
)

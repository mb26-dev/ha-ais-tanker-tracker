"""Data coordinator for the AIS Tanker Tracker integration.

Merges three sources per MMSI (priority in this order):
  * local AIS-catcher JSON messages received via MQTT (push)
  * the aisstream.io websocket stream (push, real time)
  * the global AISHub JSON web service (poll, rate limited)
and publishes a filtered, enriched snapshot of tanker vessels (types 80..89).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
import math
import random
import re
import time
from typing import Any

import aiohttp

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    AISHUB_MIN_INTERVAL_SECONDS,
    AISHUB_RATE_LIMIT_BACKOFF_FACTOR,
    AISHUB_REQUEST_TIMEOUT_SECONDS,
    AISHUB_STATUS_DISABLED,
    AISHUB_STATUS_OK,
    AISHUB_STATUS_PENDING,
    AISHUB_STATUS_RATE_LIMITED,
    AISHUB_URL,
    AISSTREAM_BACKOFF_MAX_SECONDS,
    AISSTREAM_BACKOFF_MIN_SECONDS,
    AISSTREAM_DEFAULT_BOX_DEG,
    AISSTREAM_HEARTBEAT_SECONDS,
    AISSTREAM_MESSAGE_TYPES,
    AISSTREAM_STABLE_SECONDS,
    AISSTREAM_STATUS_CONNECTED,
    AISSTREAM_STATUS_CONNECTING,
    AISSTREAM_STATUS_DISABLED,
    AISSTREAM_URL,
    AIS_COURSE_NA,
    AIS_HEADING_NA,
    AIS_LAT_NA,
    AIS_LON_NA,
    AIS_SPEED_NA,
    BALLAST_RATIO_LARGE,
    BALLAST_RATIO_SMALL,
    CONF_AISHUB_API_KEY,
    CONF_AISHUB_SCAN_INTERVAL,
    CONF_AISHUB_ZONES,
    CONF_AISSTREAM_API_KEY,
    CONF_ENABLE_DEMO_VESSELS,
    CONF_ENABLE_MQTT,
    CONF_MAX_TRACKED_VESSELS,
    CONF_MQTT_TOPIC,
    CONF_STALE_TIMEOUT_MINUTES,
    COORDINATOR_INTERVAL_SECONDS,
    DATA_AISHUB_LAST_REQUEST,
    DEFAULT_OPTIONS,
    DEMO_LOOP_SECONDS,
    DEMO_VESSELS,
    DOMAIN,
    LADEN_RATIO_LARGE,
    LADEN_RATIO_SMALL,
    LOAD_STATUS_BALLAST,
    LOAD_STATUS_LADEN,
    LOAD_STATUS_PARTIAL,
    LOAD_STATUS_UNKNOWN,
    LOGGER,
    MAX_RAW_CACHE,
    MAX_REJECTED_CACHE,
    MAX_STATIC_CACHE,
    MAX_TRACKED_LIMIT,
    NAV_STATUS_LABELS,
    NAV_STATUS_UNKNOWN,
    PUSH_DEBOUNCE_SECONDS,
    REJECTED_TTL_SECONDS,
    SMALL_TANKER_LENGTH_M,
    SOURCE_AISHUB,
    SOURCE_AISSTREAM,
    SOURCE_DEMO,
    SOURCE_LOCAL,
    STATIC_FIELDS,
    STATIC_TTL_SECONDS,
    STORAGE_KEY,
    STORAGE_SAVE_DELAY_SECONDS,
    STORAGE_VERSION,
    TANKER_TYPE_LABELS,
    TANKER_TYPE_MAX,
    TANKER_TYPE_MIN,
    VESSEL_CLASS_UNKNOWN,
)

EARTH_RADIUS_KM = 6371.0088

_NUMBER = r"(-?\d+(?:\.\d+)?)"
_ZONE_PATTERN = re.compile(
    r"([A-Za-z0-9_\-\. ]+?)\s*:\s*"
    + _NUMBER
    + r"\s*,\s*"
    + _NUMBER
    + r"\s*,\s*"
    + _NUMBER
    + r"\s*,\s*"
    + _NUMBER
)
_ZONE_SEPARATORS = ",;|\n\r\t "
_ETA_PATTERN = re.compile(r"^(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{1,2})")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class AisHubError(Exception):
    """Generic AISHub error."""


class AisHubRateLimitedError(AisHubError):
    """AISHub rejected the request because of the rate limit."""


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class AisHubZone:
    """Geographic bounding box for AISHub requests."""

    name: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float


@dataclass(slots=True)
class AisTankerData:
    """Snapshot published to all entities."""

    vessels: list[dict[str, Any]] = field(default_factory=list)
    by_mmsi: dict[int, dict[str, Any]] = field(default_factory=dict)
    tracked_mmsi: list[int] = field(default_factory=list)
    local_count: int = 0
    aisstream_count: int = 0
    aishub_count: int = 0
    demo_count: int = 0
    pending_count: int = 0
    last_aishub_sync: str | None = None
    aishub_status: str = AISHUB_STATUS_DISABLED
    aishub_last_zone: str | None = None
    aishub_zones: list[str] = field(default_factory=list)
    mqtt_enabled: bool = False
    mqtt_topic: str | None = None
    mqtt_messages_total: int = 0
    mqtt_last_message: str | None = None
    aisstream_status: str = AISSTREAM_STATUS_DISABLED
    aisstream_messages_total: int = 0
    aisstream_last_message: str | None = None


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------
def parse_zones(raw: str | None) -> list[AisHubZone]:
    """Parse 'name:latmin,latmax,lonmin,lonmax' entries.

    Several zones may be separated by ',', ';', '|' or new lines.
    Raises ValueError on invalid input. Empty input returns an empty list
    (meaning: global request without bounding box).
    """
    text = (raw or "").strip()
    zones: list[AisHubZone] = []
    pos = 0
    length = len(text)
    while pos < length:
        while pos < length and text[pos] in _ZONE_SEPARATORS:
            pos += 1
        if pos >= length:
            break
        match = _ZONE_PATTERN.match(text, pos)
        if match is None:
            raise ValueError(f"Invalid zone definition near '{text[pos:pos + 40]}'")
        name = match.group(1).strip()
        lat_min, lat_max, lon_min, lon_max = (
            float(match.group(index)) for index in range(2, 6)
        )
        if not name:
            raise ValueError("Zone name must not be empty")
        if not (-90.0 <= lat_min < lat_max <= 90.0):
            raise ValueError(f"Zone '{name}': latmin must be lower than latmax")
        if not (-180.0 <= lon_min < lon_max <= 180.0):
            raise ValueError(f"Zone '{name}': lonmin must be lower than lonmax")
        zones.append(AisHubZone(name, lat_min, lat_max, lon_min, lon_max))
        pos = match.end()
    return zones


def is_tanker_type(shiptype: Any) -> bool:
    """Return True if the AIS ship type code is a tanker (80..89)."""
    return isinstance(shiptype, int) and TANKER_TYPE_MIN <= shiptype <= TANKER_TYPE_MAX


def tanker_label(shiptype: int | None) -> str:
    """Return a readable tanker label."""
    if shiptype is None:
        return "Unknown"
    return TANKER_TYPE_LABELS.get(shiptype, "Unknown")


def vessel_class(length_m: float | None) -> str:
    """Return the tanker size class for a given length."""
    if length_m is None or length_m <= 0:
        return VESSEL_CLASS_UNKNOWN
    if length_m < 120:
        return "Coastal / Bunker Tanker"
    if length_m < 190:
        return "Handysize / MR Tanker"
    if length_m < 250:
        return "Panamax / Aframax"
    if length_m < 300:
        return "Suezmax"
    return "VLCC / ULCC Supertanker"


def load_status(draught_m: float | None, length_m: float | None) -> str:
    """Estimate the loading condition from the draught / length ratio.

    Small coastal and bunker tankers (< 120 m) have a much deeper draught in
    relation to their length, so they use their own thresholds. A fixed
    absolute draught limit is not used, because it is wrong for both very
    small and very large (VLCC) tankers.
    """
    if draught_m is None or length_m is None or draught_m <= 0 or length_m <= 0:
        return LOAD_STATUS_UNKNOWN
    ratio = draught_m / length_m
    if length_m < SMALL_TANKER_LENGTH_M:
        laden_ratio, ballast_ratio = LADEN_RATIO_SMALL, BALLAST_RATIO_SMALL
    else:
        laden_ratio, ballast_ratio = LADEN_RATIO_LARGE, BALLAST_RATIO_LARGE
    if ratio >= laden_ratio:
        return LOAD_STATUS_LADEN
    if ratio <= ballast_ratio:
        return LOAD_STATUS_BALLAST
    return LOAD_STATUS_PARTIAL


def nav_status_label(status: int | None) -> str:
    """Return the readable AIS navigational status."""
    if status is None:
        return NAV_STATUS_UNKNOWN
    return NAV_STATUS_LABELS.get(status, NAV_STATUS_UNKNOWN)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great circle distance in kilometres."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2 in degrees (0..360)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)
    x = math.sin(d_lambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(
        d_lambda
    )
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def destination_point(
    lat: float, lon: float, bearing_deg: float, distance_km: float
) -> tuple[float, float]:
    """Point reached from lat/lon after distance_km on a given bearing."""
    delta = distance_km / EARTH_RADIUS_KM
    theta = math.radians(bearing_deg)
    phi1 = math.radians(lat)
    lambda1 = math.radians(lon)
    phi2 = math.asin(
        math.sin(phi1) * math.cos(delta)
        + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    )
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    lon2 = (math.degrees(lambda2) + 540.0) % 360.0 - 180.0
    return math.degrees(phi2), lon2


def _to_float(value: Any) -> float | None:
    """Convert to float or return None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _to_int(value: Any) -> int | None:
    """Convert to int or return None."""
    number = _to_float(value)
    if number is None:
        return None
    return int(number)


def _clean_text(value: Any) -> str | None:
    """Clean AIS 6-bit text fields (padding '@', whitespace)."""
    if value is None:
        return None
    text = str(value).replace("@", " ")
    text = " ".join(text.split())
    return text or None


def _valid_position(lat: float | None, lon: float | None) -> bool:
    """Check AIS position validity."""
    if lat is None or lon is None:
        return False
    if lat == AIS_LAT_NA or lon == AIS_LON_NA:
        return False
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return False
    return not (lat == 0.0 and lon == 0.0)


def _normalize_eta_string(value: Any) -> str | None:
    """Normalize ETA strings to 'MM-DD HH:MM'."""
    text = _clean_text(value)
    if text is None:
        return None
    match = _ETA_PATTERN.match(text)
    if match is None:
        return text
    month, day, hour, minute = (int(match.group(index)) for index in range(1, 5))
    return _format_eta(month, day, hour, minute)


def _format_eta(month: int | None, day: int | None, hour: int | None, minute: int | None) -> str | None:
    """Format ETA components, return None for AIS 'not available' values."""
    if month is None or day is None or hour is None or minute is None:
        return None
    if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{month:02d}-{day:02d} {hour:02d}:{minute:02d}"


def _first(obj: dict[str, Any], *keys: str) -> Any:
    """Return the first present (not None) value of the given keys."""
    for key in keys:
        value = obj.get(key)
        if value is not None:
            return value
    return None


def normalize_local_message(obj: dict[str, Any]) -> tuple[int, dict[str, Any]] | None:
    """Normalize one AIS-catcher JSON message (JSON_FULL / gpsdecode style)."""
    mmsi = _to_int(obj.get("mmsi"))
    if mmsi is None or not 0 < mmsi <= 999999999:
        return None

    msg_type = _to_int(obj.get("type"))
    out: dict[str, Any] = {}

    lat = _to_float(obj.get("lat"))
    lon = _to_float(obj.get("lon"))
    if _valid_position(lat, lon):
        out["lat"] = lat
        out["lon"] = lon

    speed = _to_float(obj.get("speed"))
    if speed is not None and 0.0 <= speed < AIS_SPEED_NA:
        out["speed"] = speed

    course = _to_float(obj.get("course"))
    if course is not None and 0.0 <= course < AIS_COURSE_NA:
        out["course"] = course

    heading = _to_int(obj.get("heading"))
    if heading is not None and 0 <= heading < 360 and heading != AIS_HEADING_NA:
        out["heading"] = heading

    if msg_type is None or msg_type in (1, 2, 3, 27):
        status = _to_int(_first(obj, "status", "navstatus", "nav_status"))
        if status is not None and 0 <= status <= 15:
            out["status"] = status

    shiptype = _to_int(_first(obj, "shiptype", "ship_type"))
    if shiptype is not None and 0 <= shiptype <= 99:
        out["shiptype"] = shiptype

    shipname = _clean_text(_first(obj, "shipname", "name"))
    if shipname:
        out["shipname"] = shipname

    callsign = _clean_text(obj.get("callsign"))
    if callsign:
        out["callsign"] = callsign

    destination = _clean_text(obj.get("destination"))
    if destination:
        out["destination"] = destination

    imo = _to_int(obj.get("imo"))
    if imo is not None and imo > 0:
        out["imo"] = imo

    draught = _to_float(obj.get("draught"))
    if draught is not None and draught > 0:
        out["draught"] = draught

    for key in ("to_bow", "to_stern", "to_port", "to_starboard"):
        dim = _to_int(obj.get(key))
        if dim is not None and dim > 0:
            out[key] = dim

    eta: str | None = None
    if isinstance(obj.get("eta"), str):
        eta = _normalize_eta_string(obj.get("eta"))
    elif msg_type == 5:
        eta = _format_eta(
            _to_int(_first(obj, "eta_month", "month")),
            _to_int(_first(obj, "eta_day", "day")),
            _to_int(_first(obj, "eta_hour", "hour")),
            _to_int(_first(obj, "eta_minute", "minute")),
        )
    if eta:
        out["eta"] = eta

    return mmsi, out


def _parse_aishub_time(value: Any, fallback: float) -> float:
    """Parse AISHub TIME ('2026-11-14 03:15:30 GMT' or unix seconds)."""
    if value is None:
        return fallback
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if text.isdigit():
        return float(text)
    for suffix in (" GMT", " UTC", "Z"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC).timestamp()
        except ValueError:
            continue
    return fallback


def normalize_aishub_record(
    rec: dict[str, Any], now: float
) -> tuple[int, dict[str, Any]] | None:
    """Normalize one AISHub vessel (format=1). Returns None for non tankers."""
    mmsi = _to_int(rec.get("MMSI"))
    if mmsi is None or not 0 < mmsi <= 999999999:
        return None
    shiptype = _to_int(rec.get("TYPE"))
    if not is_tanker_type(shiptype):
        return None
    lat = _to_float(rec.get("LATITUDE"))
    lon = _to_float(rec.get("LONGITUDE"))
    if not _valid_position(lat, lon):
        return None

    out: dict[str, Any] = {"lat": lat, "lon": lon, "shiptype": shiptype}

    speed = _to_float(rec.get("SOG"))
    if speed is not None and 0.0 <= speed < AIS_SPEED_NA:
        out["speed"] = speed
    course = _to_float(rec.get("COG"))
    if course is not None and 0.0 <= course < AIS_COURSE_NA:
        out["course"] = course
    heading = _to_int(rec.get("HEADING"))
    if heading is not None and 0 <= heading < 360:
        out["heading"] = heading
    status = _to_int(rec.get("NAVSTAT"))
    if status is not None and 0 <= status <= 15:
        out["status"] = status
    imo = _to_int(rec.get("IMO"))
    if imo is not None and imo > 0:
        out["imo"] = imo
    name = _clean_text(rec.get("NAME"))
    if name:
        out["shipname"] = name
    callsign = _clean_text(rec.get("CALLSIGN"))
    if callsign:
        out["callsign"] = callsign
    destination = _clean_text(rec.get("DEST"))
    if destination:
        out["destination"] = destination
    draught = _to_float(rec.get("DRAUGHT"))
    if draught is not None and draught > 0:
        out["draught"] = draught
    eta = _normalize_eta_string(rec.get("ETA"))
    if eta:
        out["eta"] = eta
    for src_key, dst_key in (
        ("A", "to_bow"),
        ("B", "to_stern"),
        ("C", "to_port"),
        ("D", "to_starboard"),
    ):
        dim = _to_int(rec.get(src_key))
        if dim is not None and dim > 0:
            out[dst_key] = dim

    seen = _parse_aishub_time(rec.get("TIME"), now)
    out["last_seen"] = min(seen, now)
    return mmsi, out


def split_aishub_payload(payload: Any) -> list[dict[str, Any]]:
    """Validate the AISHub response '[header, vessels]' and return the vessels."""
    header: dict[str, Any] = {}
    records: list[Any] = []
    if isinstance(payload, dict):
        header = payload
    elif isinstance(payload, list):
        if payload and isinstance(payload[0], dict):
            header = payload[0]
        if len(payload) > 1 and isinstance(payload[1], list):
            records = payload[1]
    else:
        raise AisHubError("unexpected response format")

    error_flag = header.get("ERROR")
    if error_flag is True or str(error_flag).strip().lower() in ("true", "1"):
        message = str(header.get("ERROR_MESSAGE") or "unknown error").strip()
        if "frequent" in message.lower():
            raise AisHubRateLimitedError(message)
        raise AisHubError(message)
    return [record for record in records if isinstance(record, dict)]


def _dimension_fields(dimension: Any) -> dict[str, Any]:
    """Map an aisstream Dimension object to AIS-catcher field names."""
    if not isinstance(dimension, dict):
        return {}
    return {
        "to_bow": dimension.get("A"),
        "to_stern": dimension.get("B"),
        "to_port": dimension.get("C"),
        "to_starboard": dimension.get("D"),
    }


def convert_aisstream_message(obj: dict[str, Any]) -> dict[str, Any] | None:
    """Translate one aisstream.io message into AIS-catcher style JSON."""
    message_type = obj.get("MessageType")
    message = obj.get("Message")
    meta = obj.get("MetaData")
    if not isinstance(message_type, str) or not isinstance(message, dict):
        return None
    body = message.get(message_type)
    if not isinstance(body, dict) or body.get("Valid") is False:
        return None
    meta = meta if isinstance(meta, dict) else {}
    mmsi = meta.get("MMSI") or body.get("UserID")
    if mmsi is None:
        return None

    out: dict[str, Any] = {"mmsi": mmsi}
    if message_type in (
        "PositionReport",
        "StandardClassBPositionReport",
        "ExtendedClassBPositionReport",
    ):
        out["type"] = {
            "PositionReport": 1,
            "StandardClassBPositionReport": 18,
            "ExtendedClassBPositionReport": 19,
        }[message_type]
        out["lat"] = body.get("Latitude")
        out["lon"] = body.get("Longitude")
        out["speed"] = body.get("Sog")
        out["course"] = body.get("Cog")
        out["heading"] = body.get("TrueHeading")
        if message_type == "PositionReport":
            out["status"] = body.get("NavigationalStatus")
        if message_type == "ExtendedClassBPositionReport":
            out["shiptype"] = body.get("Type")
            out["shipname"] = body.get("Name")
            out.update(_dimension_fields(body.get("Dimension")))
        if not _clean_text(out.get("shipname")) and _clean_text(meta.get("ShipName")):
            out["shipname"] = meta.get("ShipName")
    elif message_type == "ShipStaticData":
        out["type"] = 5
        out["shiptype"] = body.get("Type")
        out["shipname"] = body.get("Name")
        out["callsign"] = body.get("CallSign")
        out["imo"] = body.get("ImoNumber")
        out["destination"] = body.get("Destination")
        out["draught"] = body.get("MaximumStaticDraught")
        out.update(_dimension_fields(body.get("Dimension")))
        eta = body.get("Eta")
        if isinstance(eta, dict):
            out["eta_month"] = eta.get("Month")
            out["eta_day"] = eta.get("Day")
            out["eta_hour"] = eta.get("Hour")
            out["eta_minute"] = eta.get("Minute")
    elif message_type == "StaticDataReport":
        out["type"] = 24
        report_a = body.get("ReportA")
        report_b = body.get("ReportB")
        if isinstance(report_a, dict) and report_a.get("Valid"):
            out["shipname"] = report_a.get("Name")
        if isinstance(report_b, dict) and report_b.get("Valid"):
            out["shiptype"] = report_b.get("ShipType")
            out["callsign"] = report_b.get("CallSign")
            out.update(_dimension_fields(report_b.get("Dimension")))
    else:
        return None
    return out


def iter_json_objects(payload: Any) -> Iterator[dict[str, Any]]:
    """Yield JSON objects from a MQTT payload (object, array or NDJSON)."""
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", errors="ignore")
    if not isinstance(payload, str):
        return
    text = payload.strip()
    if not text:
        return
    try:
        data = json.loads(text)
    except ValueError:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict):
                yield item
        return
    if isinstance(data, dict):
        yield data
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                yield item


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------
class AisTankerCoordinator(DataUpdateCoordinator[AisTankerData]):
    """Coordinator merging local MQTT AIS data and AISHub data."""

    config_entry: AisTankerConfigEntry

    def __init__(self, hass: HomeAssistant, entry: AisTankerConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=COORDINATOR_INTERVAL_SECONDS),
        )
        options: dict[str, Any] = {**DEFAULT_OPTIONS, **entry.data, **entry.options}

        self._mqtt_enabled: bool = bool(options[CONF_ENABLE_MQTT])
        self._mqtt_topic: str = str(options[CONF_MQTT_TOPIC] or "").strip()
        self._aishub_key: str = str(options[CONF_AISHUB_API_KEY] or "").strip()
        self._aisstream_key: str = str(options[CONF_AISSTREAM_API_KEY] or "").strip()
        try:
            self._zones: list[AisHubZone] = parse_zones(options[CONF_AISHUB_ZONES])
        except ValueError as err:
            LOGGER.error("Invalid AISHub zones, falling back to global request: %s", err)
            self._zones = []
        self._aishub_interval: int = max(
            AISHUB_MIN_INTERVAL_SECONDS, int(options[CONF_AISHUB_SCAN_INTERVAL])
        )
        self._stale_minutes: int = max(1, int(options[CONF_STALE_TIMEOUT_MINUTES]))
        self._stale_seconds: float = self._stale_minutes * 60.0
        self._max_tracked: int = max(
            0, min(MAX_TRACKED_LIMIT, int(options[CONF_MAX_TRACKED_VESSELS]))
        )
        self._demo_enabled: bool = bool(options[CONF_ENABLE_DEMO_VESSELS])

        self._session = async_get_clientsession(hass)

        # Raw caches keyed by MMSI
        self._local: dict[int, dict[str, Any]] = {}
        self._stream: dict[int, dict[str, Any]] = {}
        self._aishub: dict[int, dict[str, Any]] = {}
        self._rejected: dict[int, float] = {}

        # Persistent static data (ship type, name, dimensions) keyed by MMSI
        self._static: dict[int, dict[str, Any]] = {}
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._save_pending: bool = False

        # AISHub state
        self._aishub_status: str = (
            AISHUB_STATUS_PENDING if self._aishub_key else AISHUB_STATUS_DISABLED
        )
        self._aishub_last_sync: str | None = None
        self._aishub_last_zone: str | None = None
        self._aishub_zone_index: int = 0
        self._aishub_blocked_until: float = 0.0

        # MQTT state
        self._unsub_mqtt: CALLBACK_TYPE | None = None
        self._push_unsub: CALLBACK_TYPE | None = None
        self._mqtt_messages_total: int = 0
        self._mqtt_last_message: float | None = None
        self._stopped: bool = False

        # aisstream.io state
        self._aisstream_task: asyncio.Task[None] | None = None
        self._aisstream_status: str = (
            AISSTREAM_STATUS_CONNECTING if self._aisstream_key else AISSTREAM_STATUS_DISABLED
        )
        self._aisstream_messages_total: int = 0
        self._aisstream_last_message: float | None = None

        self._demo_epoch: float = time.time()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def async_start(self) -> None:
        """Subscribe to MQTT and start the aisstream.io connection if enabled."""
        await self._async_load_static()

        if self._mqtt_enabled and "mqtt" not in self.hass.config.components:
            LOGGER.warning(
                "Local SDR source is enabled but the MQTT integration is not set up; "
                "continuing without the local MQTT feed"
            )
        elif self._mqtt_enabled:
            if not await mqtt.async_wait_for_mqtt_client(self.hass):
                raise ConfigEntryNotReady("MQTT integration is not available")
            self._unsub_mqtt = await mqtt.async_subscribe(
                self.hass, self._mqtt_topic, self._handle_mqtt_message, qos=0
            )
            LOGGER.info("Subscribed to AIS MQTT topic '%s'", self._mqtt_topic)
        else:
            LOGGER.debug("MQTT source disabled")

        if self._aisstream_key:
            self._aisstream_task = self.config_entry.async_create_background_task(
                self.hass, self._async_aisstream_loop(), name="ais_tanker_aisstream"
            )

    @callback
    def async_stop(self) -> None:
        """Release MQTT subscription and timers (idempotent)."""
        self._stopped = True
        if self._unsub_mqtt is not None:
            self._unsub_mqtt()
            self._unsub_mqtt = None
        if self._push_unsub is not None:
            self._push_unsub()
            self._push_unsub = None
        if self._aisstream_task is not None:
            self._aisstream_task.cancel()
            self._aisstream_task = None

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        self.async_stop()
        await super().async_shutdown()

    # ------------------------------------------------------------------
    # MQTT handling (local push)
    # ------------------------------------------------------------------
    @callback
    def _handle_mqtt_message(self, msg: mqtt.ReceiveMessage) -> None:
        """Handle one MQTT message from AIS-catcher."""
        if self._stopped:
            return
        now = time.time()
        relevant = False
        for obj in iter_json_objects(msg.payload):
            self._mqtt_messages_total += 1
            if self._ingest(self._local, obj, now):
                relevant = True
        self._mqtt_last_message = now
        if relevant:
            self._schedule_push()

    @callback
    def _ingest(self, cache: dict[int, dict[str, Any]], obj: dict[str, Any], now: float) -> bool:
        """Merge one normalized AIS message into the given MMSI cache.

        Returns True if the active tanker data may have changed.
        """
        normalized = normalize_local_message(obj)
        if normalized is None:
            return False
        mmsi, fields = normalized

        if mmsi in self._rejected:
            self._rejected[mmsi] = now
            return False

        shiptype = fields.get("shiptype")
        if shiptype is not None and not is_tanker_type(shiptype):
            was_active = any(
                self._is_active(mmsi, source[mmsi])
                for source in (self._local, self._stream)
                if mmsi in source
            )
            self._local.pop(mmsi, None)
            self._stream.pop(mmsi, None)
            self._static.pop(mmsi, None)
            self._rejected[mmsi] = now
            if len(self._rejected) > MAX_REJECTED_CACHE:
                self._prune_rejected(now, force=True)
            self._schedule_save()
            return was_active

        record = cache.get(mmsi)
        if record is None:
            if len(cache) >= MAX_RAW_CACHE:
                self._evict(cache)
            record = {}
            known = self._static.get(mmsi)
            if known is not None:
                record.update({k: v for k, v in known.items() if k != "ts"})
            cache[mmsi] = record
        record.update(fields)
        if shiptype is not None:
            self._remember_static(mmsi, record, now)
        record["last_seen"] = now
        return self._is_active(mmsi, record)

    def _effective_shiptype(self, mmsi: int, record: dict[str, Any]) -> int | None:
        """Ship type from the record, falling back to the other sources."""
        shiptype = record.get("shiptype")
        if shiptype is None:
            for source in (self._local, self._stream, self._aishub, self._static):
                other = source.get(mmsi)
                if other is not None and other.get("shiptype") is not None:
                    return other.get("shiptype")
        return shiptype

    # ------------------------------------------------------------------
    # Persistent static cache
    # ------------------------------------------------------------------
    async def _async_load_static(self) -> None:
        """Load cached static vessel data and known non-tankers from disk."""
        try:
            stored = await self._store.async_load()
        except Exception as err:  # noqa: BLE001 - corrupt store must not block setup
            LOGGER.warning("Could not load static vessel cache: %s", err)
            return
        if not isinstance(stored, dict):
            return
        now = time.time()
        static_raw = stored.get("static")
        if isinstance(static_raw, dict):
            for key, value in static_raw.items():
                mmsi = _to_int(key)
                if mmsi is None or not isinstance(value, dict):
                    continue
                ts = _to_float(value.get("ts"))
                if ts is None or now - ts > STATIC_TTL_SECONDS:
                    continue
                entry = {k: value[k] for k in STATIC_FIELDS if k in value}
                if not is_tanker_type(entry.get("shiptype")):
                    continue
                entry["ts"] = ts
                self._static[mmsi] = entry
        rejected_raw = stored.get("rejected")
        if isinstance(rejected_raw, dict):
            for key, value in rejected_raw.items():
                mmsi = _to_int(key)
                ts = _to_float(value)
                if mmsi is None or ts is None or now - ts > REJECTED_TTL_SECONDS:
                    continue
                self._rejected[mmsi] = ts
        LOGGER.info(
            "Static vessel cache loaded: %d tankers, %d non-tankers",
            len(self._static),
            len(self._rejected),
        )

    def _remember_static(self, mmsi: int, record: dict[str, Any], now: float) -> None:
        """Store the static fields of a classified tanker."""
        entry = {k: record[k] for k in STATIC_FIELDS if k in record}
        if not is_tanker_type(entry.get("shiptype")):
            return
        previous = self._static.get(mmsi)
        entry["ts"] = now
        self._static[mmsi] = entry
        if len(self._static) > MAX_STATIC_CACHE:
            oldest = sorted(self._static.items(), key=lambda item: item[1].get("ts", 0.0))
            for old_mmsi, _ in oldest[: len(self._static) - MAX_STATIC_CACHE]:
                del self._static[old_mmsi]
        if previous is None or {k: v for k, v in previous.items() if k != "ts"} != {
            k: v for k, v in entry.items() if k != "ts"
        } or now - float(previous.get("ts", 0.0)) > 3600:
            self._schedule_save()

    @callback
    def _schedule_save(self) -> None:
        """Write the static cache to disk with a delay (batched).

        Store.async_delay_save restarts its timer on every call, so it is only
        armed once until the write happened. Otherwise a busy feed would push
        the write out forever.
        """
        if self._save_pending:
            return
        self._save_pending = True
        self._store.async_delay_save(self._static_data_to_save, STORAGE_SAVE_DELAY_SECONDS)

    async def async_flush_static(self) -> None:
        """Write the static cache immediately (used on unload / reload)."""
        try:
            await self._store.async_save(self._static_data_to_save())
        except Exception as err:  # noqa: BLE001 - never block unload
            LOGGER.warning("Could not save static vessel cache: %s", err)

    @callback
    def _static_data_to_save(self) -> dict[str, Any]:
        """Serializable snapshot of the static cache."""
        self._save_pending = False
        return {
            "static": {str(mmsi): dict(entry) for mmsi, entry in self._static.items()},
            "rejected": {str(mmsi): ts for mmsi, ts in self._rejected.items()},
        }

    def _is_active(self, mmsi: int, record: dict[str, Any]) -> bool:
        """True if a record is a tanker with a known position."""
        return (
            is_tanker_type(self._effective_shiptype(mmsi, record))
            and "lat" in record
            and "lon" in record
        )

    @staticmethod
    def _evict(cache: dict[int, dict[str, Any]]) -> None:
        """Drop the oldest unclassified entry (or oldest overall) from a cache."""
        pending = [
            (rec.get("last_seen", 0.0), mmsi)
            for mmsi, rec in cache.items()
            if rec.get("shiptype") is None
        ]
        candidates = pending or [
            (rec.get("last_seen", 0.0), mmsi) for mmsi, rec in cache.items()
        ]
        if candidates:
            _, oldest = min(candidates)
            cache.pop(oldest, None)

    def _prune_rejected(self, now: float, force: bool = False) -> None:
        """Expire rejected (non tanker) MMSI entries."""
        cutoff = now - REJECTED_TTL_SECONDS
        for mmsi in [m for m, ts in self._rejected.items() if ts < cutoff]:
            del self._rejected[mmsi]
        if force and len(self._rejected) > MAX_REJECTED_CACHE:
            ordered = sorted(self._rejected.items(), key=lambda item: item[1])
            for mmsi, _ in ordered[: len(ordered) // 2]:
                del self._rejected[mmsi]

    @callback
    def _schedule_push(self) -> None:
        """Throttle entity updates triggered by MQTT."""
        if self._push_unsub is not None or self._stopped:
            return
        self._push_unsub = async_call_later(
            self.hass, PUSH_DEBOUNCE_SECONDS, self._async_push_now
        )

    @callback
    def _async_push_now(self, _now: datetime) -> None:
        """Publish a new snapshot without resetting the poll timer."""
        self._push_unsub = None
        if self._stopped:
            return
        self.data = self._build_snapshot()
        self.async_update_listeners()

    # ------------------------------------------------------------------
    # aisstream.io websocket (real time push)
    # ------------------------------------------------------------------
    def _aisstream_subscription(self) -> dict[str, Any]:
        """Build the aisstream.io subscription message."""
        boxes: list[list[list[float]]] = [
            [[zone.lat_min, zone.lon_min], [zone.lat_max, zone.lon_max]]
            for zone in self._zones
        ]
        if not boxes:
            lat = float(self.hass.config.latitude)
            lon = float(self.hass.config.longitude)
            boxes = [
                [
                    [max(-90.0, lat - AISSTREAM_DEFAULT_BOX_DEG), max(-180.0, lon - AISSTREAM_DEFAULT_BOX_DEG)],
                    [min(90.0, lat + AISSTREAM_DEFAULT_BOX_DEG), min(180.0, lon + AISSTREAM_DEFAULT_BOX_DEG)],
                ]
            ]
        return {
            "APIKey": self._aisstream_key,
            "BoundingBoxes": boxes,
            "FilterMessageTypes": list(AISSTREAM_MESSAGE_TYPES),
        }

    async def _async_aisstream_loop(self) -> None:
        """Keep the aisstream.io websocket connected with backoff."""
        backoff = float(AISSTREAM_BACKOFF_MIN_SECONDS)
        while not self._stopped:
            self._aisstream_status = AISSTREAM_STATUS_CONNECTING
            connected_at: float | None = None
            reason = "connection closed"
            try:
                async with self._session.ws_connect(
                    AISSTREAM_URL,
                    heartbeat=AISSTREAM_HEARTBEAT_SECONDS,
                    compress=15,
                ) as ws:
                    await ws.send_str(json.dumps(self._aisstream_subscription()))
                    connected_at = time.monotonic()
                    LOGGER.info("aisstream.io connected, subscription sent")
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.BINARY:
                            self._handle_aisstream_text(
                                msg.data.decode("utf-8", errors="ignore")
                            )
                        elif msg.type == aiohttp.WSMsgType.TEXT:
                            self._handle_aisstream_text(msg.data)
                        elif msg.type in (
                            aiohttp.WSMsgType.CLOSE,
                            aiohttp.WSMsgType.CLOSING,
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR,
                        ):
                            break
                    reason = f"closed by server (code {ws.close_code})"
            except asyncio.CancelledError:
                raise
            except (aiohttp.ClientError, TimeoutError, OSError, ValueError) as err:
                reason = f"{type(err).__name__}: {err}"

            if self._stopped:
                return
            if connected_at is not None and time.monotonic() - connected_at >= AISSTREAM_STABLE_SECONDS:
                backoff = float(AISSTREAM_BACKOFF_MIN_SECONDS)
            delay = backoff + random.uniform(0.0, backoff / 2)
            self._aisstream_status = f"error: {reason}"
            LOGGER.warning(
                "aisstream.io disconnected (%s), reconnecting in %.0f s", reason, delay
            )
            await asyncio.sleep(delay)
            backoff = min(backoff * 2, float(AISSTREAM_BACKOFF_MAX_SECONDS))

    @callback
    def _handle_aisstream_text(self, text: str) -> None:
        """Handle one aisstream.io frame."""
        if self._stopped:
            return
        try:
            obj = json.loads(text)
        except ValueError:
            return
        if not isinstance(obj, dict):
            return
        error = obj.get("error") or obj.get("Error")
        if error:
            self._aisstream_status = f"error: {error}"
            LOGGER.warning("aisstream.io error: %s", error)
            return
        self._aisstream_status = AISSTREAM_STATUS_CONNECTED
        now = time.time()
        self._aisstream_last_message = now
        converted = convert_aisstream_message(obj)
        if converted is None:
            return
        self._aisstream_messages_total += 1
        if self._ingest(self._stream, converted, now):
            self._schedule_push()

    # ------------------------------------------------------------------
    # Polling (housekeeping + AISHub)
    # ------------------------------------------------------------------
    async def _async_update_data(self) -> AisTankerData:
        """Poll AISHub when due and rebuild the snapshot."""
        await self._async_poll_aishub()
        return self._build_snapshot()

    def _next_zone(self) -> AisHubZone | None:
        """Rotate through the configured zones."""
        if not self._zones:
            return None
        zone = self._zones[self._aishub_zone_index % len(self._zones)]
        self._aishub_zone_index = (self._aishub_zone_index + 1) % len(self._zones)
        return zone

    async def _async_poll_aishub(self) -> None:
        """Request AISHub if enabled and the rate limit window allows it."""
        if not self._aishub_key:
            self._aishub_status = AISHUB_STATUS_DISABLED
            return

        now_mono = time.monotonic()
        if now_mono < self._aishub_blocked_until:
            return
        shared: dict[str, Any] = self.hass.data.setdefault(DOMAIN, {})
        last_request = shared.get(DATA_AISHUB_LAST_REQUEST)
        if last_request is not None and now_mono - last_request < self._aishub_interval:
            return

        zone = self._next_zone()
        shared[DATA_AISHUB_LAST_REQUEST] = now_mono
        zone_name = zone.name if zone else "global"

        try:
            records = await self._async_fetch_aishub(zone)
        except AisHubRateLimitedError as err:
            self._aishub_status = AISHUB_STATUS_RATE_LIMITED
            self._aishub_blocked_until = now_mono + (
                self._aishub_interval * AISHUB_RATE_LIMIT_BACKOFF_FACTOR
            )
            LOGGER.warning("AISHub rate limit hit (%s), backing off", err)
            return
        except AisHubError as err:
            self._aishub_status = f"error: {err}"
            LOGGER.warning("AISHub request for zone '%s' failed: %s", zone_name, err)
            return
        except (aiohttp.ClientError, TimeoutError) as err:
            self._aishub_status = f"error: connection failed ({type(err).__name__})"
            LOGGER.warning("AISHub connection error for zone '%s': %s", zone_name, err)
            return

        now = time.time()
        cutoff = now - self._stale_seconds
        added = 0
        for record in records:
            normalized = normalize_aishub_record(record, now)
            if normalized is None:
                continue
            mmsi, vessel = normalized
            if vessel["last_seen"] < cutoff:
                continue
            self._aishub[mmsi] = vessel
            added += 1

        self._aishub_status = AISHUB_STATUS_OK
        self._aishub_last_sync = dt_util.utcnow().isoformat()
        self._aishub_last_zone = zone_name
        LOGGER.debug(
            "AISHub zone '%s': %d records, %d tankers accepted",
            zone_name,
            len(records),
            added,
        )

    async def _async_fetch_aishub(self, zone: AisHubZone | None) -> list[dict[str, Any]]:
        """Execute one AISHub request."""
        params: dict[str, str] = {
            "username": self._aishub_key,
            "format": "1",
            "output": "json",
            "compress": "0",
            "interval": str(self._stale_minutes),
        }
        if zone is not None:
            params["latmin"] = f"{zone.lat_min:g}"
            params["latmax"] = f"{zone.lat_max:g}"
            params["lonmin"] = f"{zone.lon_min:g}"
            params["lonmax"] = f"{zone.lon_max:g}"

        async with self._session.get(
            AISHUB_URL,
            params=params,
            timeout=aiohttp.ClientTimeout(total=AISHUB_REQUEST_TIMEOUT_SECONDS),
        ) as response:
            if response.status == 429:
                raise AisHubRateLimitedError("HTTP 429")
            if response.status != 200:
                raise AisHubError(f"HTTP {response.status}")
            raw = await response.text()

        try:
            payload = json.loads(raw)
        except ValueError as err:
            snippet = raw.strip()[:80]
            if "frequent" in snippet.lower():
                raise AisHubRateLimitedError(snippet) from err
            raise AisHubError("invalid JSON response") from err
        return split_aishub_payload(payload)

    # ------------------------------------------------------------------
    # Snapshot building
    # ------------------------------------------------------------------
    def _purge_stale(self, now: float) -> None:
        """Remove vessels without updates within the stale timeout."""
        cutoff = now - self._stale_seconds
        for mmsi in [m for m, r in self._local.items() if r.get("last_seen", 0.0) < cutoff]:
            del self._local[mmsi]
        for mmsi in [m for m, r in self._stream.items() if r.get("last_seen", 0.0) < cutoff]:
            del self._stream[mmsi]
        for mmsi in [m for m, r in self._aishub.items() if r.get("last_seen", 0.0) < cutoff]:
            del self._aishub[mmsi]
        self._prune_rejected(now)

    def _demo_records(self, now: float) -> list[tuple[int, dict[str, Any]]]:
        """Generate moving demo tankers."""
        elapsed = (now - self._demo_epoch) % DEMO_LOOP_SECONDS
        eta_base = dt_util.utcnow()
        result: list[tuple[int, dict[str, Any]]] = []
        for demo in DEMO_VESSELS:
            distance_km = float(demo["speed"]) * 1.852 * elapsed / 3600.0
            lat, lon = destination_point(
                float(demo["start_lat"]),
                float(demo["start_lon"]),
                float(demo["course"]),
                distance_km,
            )
            eta_dt = eta_base + timedelta(hours=int(demo["eta_offset_hours"]))
            record: dict[str, Any] = {
                key: value
                for key, value in demo.items()
                if key not in ("mmsi", "start_lat", "start_lon", "eta_offset_hours")
            }
            record["lat"] = lat
            record["lon"] = lon
            record["eta"] = eta_dt.strftime("%m-%d %H:%M")
            record["last_seen"] = now
            result.append((int(demo["mmsi"]), record))
        return result

    def _build_vessel(
        self,
        mmsi: int,
        rec: dict[str, Any],
        source: str,
        home_lat: float | None,
        home_lon: float | None,
    ) -> dict[str, Any]:
        """Build the public vessel dictionary with derived metrics."""
        shiptype: int | None = rec.get("shiptype")
        length_sum = int(rec.get("to_bow") or 0) + int(rec.get("to_stern") or 0)
        width_sum = int(rec.get("to_port") or 0) + int(rec.get("to_starboard") or 0)
        length_m: int | None = length_sum if length_sum > 0 else None
        width_m: int | None = width_sum if width_sum > 0 else None
        draught: float | None = rec.get("draught")
        lat = float(rec["lat"])
        lon = float(rec["lon"])

        distance_km: float | None = None
        bearing_deg: float | None = None
        if home_lat is not None and home_lon is not None:
            distance_km = round(haversine_km(home_lat, home_lon, lat, lon), 2)
            bearing_deg = round(initial_bearing_deg(home_lat, home_lon, lat, lon), 1)

        status: int | None = rec.get("status")
        speed: float | None = rec.get("speed")
        course: float | None = rec.get("course")
        last_seen = float(rec.get("last_seen") or time.time())

        return {
            "mmsi": mmsi,
            "name": rec.get("shipname") or f"MMSI {mmsi}",
            "vessel_type_code": shiptype,
            "vessel_type_label": tanker_label(shiptype),
            "vessel_class": vessel_class(length_m),
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "speed_knots": round(speed, 1) if speed is not None else None,
            "course": round(course, 1) if course is not None else None,
            "heading": rec.get("heading"),
            "draught_m": round(draught, 1) if draught is not None else None,
            "load_status": load_status(draught, length_m),
            "length_m": length_m,
            "width_m": width_m,
            "imo": rec.get("imo"),
            "callsign": rec.get("callsign"),
            "destination": rec.get("destination"),
            "eta": rec.get("eta"),
            "nav_status": nav_status_label(status),
            "nav_status_code": status,
            "distance_km": distance_km,
            "bearing_deg": bearing_deg,
            "source": source,
            "last_seen": dt_util.utc_from_timestamp(last_seen).isoformat(),
        }

    def _build_snapshot(self) -> AisTankerData:
        """Merge all sources into a sorted snapshot."""
        now = time.time()
        self._purge_stale(now)

        home_lat: float | None = self.hass.config.latitude
        home_lon: float | None = self.hass.config.longitude

        vessels: dict[int, dict[str, Any]] = {}
        pending: set[int] = set()

        # Priority: local SDR, then aisstream.io. Lower priority sources
        # only fill fields that the preferred source does not have yet.
        push_sources: tuple[tuple[str, dict[int, dict[str, Any]], tuple[dict[int, dict[str, Any]], ...]], ...] = (
            (SOURCE_LOCAL, self._local, (self._aishub, self._stream)),
            (SOURCE_AISSTREAM, self._stream, (self._aishub,)),
        )
        for source, cache, fallbacks in push_sources:
            for mmsi, record in cache.items():
                if mmsi in vessels:
                    continue
                shiptype = self._effective_shiptype(mmsi, record)
                if shiptype is None:
                    pending.add(mmsi)
                    continue
                if not is_tanker_type(shiptype) or "lat" not in record or "lon" not in record:
                    continue
                pending.discard(mmsi)
                merged: dict[str, Any] = {}
                for fallback in fallbacks:
                    if mmsi in fallback:
                        merged.update(fallback[mmsi])
                merged.update(record)
                merged["shiptype"] = shiptype
                vessels[mmsi] = self._build_vessel(mmsi, merged, source, home_lat, home_lon)

        for mmsi, record in self._aishub.items():
            if mmsi in vessels:
                continue
            vessels[mmsi] = self._build_vessel(mmsi, record, SOURCE_AISHUB, home_lat, home_lon)

        if self._demo_enabled:
            for mmsi, record in self._demo_records(now):
                if mmsi not in vessels:
                    vessels[mmsi] = self._build_vessel(
                        mmsi, record, SOURCE_DEMO, home_lat, home_lon
                    )

        ordered = sorted(
            vessels.values(),
            key=lambda v: (
                v["distance_km"] is None,
                v["distance_km"] if v["distance_km"] is not None else 0.0,
                v["mmsi"],
            ),
        )
        tracked = [vessel["mmsi"] for vessel in ordered[: self._max_tracked]]

        return AisTankerData(
            vessels=ordered,
            by_mmsi={vessel["mmsi"]: vessel for vessel in ordered},
            tracked_mmsi=tracked,
            local_count=sum(1 for v in ordered if v["source"] == SOURCE_LOCAL),
            aisstream_count=sum(1 for v in ordered if v["source"] == SOURCE_AISSTREAM),
            aishub_count=sum(1 for v in ordered if v["source"] == SOURCE_AISHUB),
            demo_count=sum(1 for v in ordered if v["source"] == SOURCE_DEMO),
            pending_count=len(pending - set(vessels)),
            last_aishub_sync=self._aishub_last_sync,
            aishub_status=self._aishub_status,
            aishub_last_zone=self._aishub_last_zone,
            aishub_zones=[zone.name for zone in self._zones] if self._aishub_key else [],
            mqtt_enabled=self._mqtt_enabled,
            mqtt_topic=self._mqtt_topic if self._mqtt_enabled else None,
            mqtt_messages_total=self._mqtt_messages_total,
            mqtt_last_message=(
                dt_util.utc_from_timestamp(self._mqtt_last_message).isoformat()
                if self._mqtt_last_message is not None
                else None
            ),
            aisstream_status=self._aisstream_status,
            aisstream_messages_total=self._aisstream_messages_total,
            aisstream_last_message=(
                dt_util.utc_from_timestamp(self._aisstream_last_message).isoformat()
                if self._aisstream_last_message is not None
                else None
            ),
        )


type AisTankerConfigEntry = ConfigEntry[AisTankerCoordinator]

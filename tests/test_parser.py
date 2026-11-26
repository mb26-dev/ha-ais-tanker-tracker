"""Tests for the AIS message parsers (AIS-catcher, aisstream.io, AISHub) and zones."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.ais_tanker.coordinator import (
    AisHubError,
    AisHubRateLimitedError,
    AisHubZone,
    convert_aisstream_message,
    iter_json_objects,
    normalize_aishub_record,
    normalize_local_message,
    parse_zones,
    split_aishub_payload,
    unique_zone_names,
    zone_event_payload,
    zones_containing,
)

# ---------------------------------------------------------------------------
# AIS-catcher (local SDR via MQTT)
# ---------------------------------------------------------------------------


def test_local_position_report() -> None:
    """A JSON_FULL position report is normalized."""
    result = normalize_local_message(
        {
            "class": "AIS",
            "type": 1,
            "mmsi": 563123456,
            "status": 0,
            "speed": 12.3,
            "course": 180.5,
            "heading": 181,
            "lat": 1.25,
            "lon": 103.8,
        }
    )
    assert result == (
        563123456,
        {"lat": 1.25, "lon": 103.8, "speed": 12.3, "course": 180.5, "heading": 181, "status": 0},
    )


def test_local_not_available_values_are_dropped() -> None:
    """AIS 'not available' markers never end up in the record."""
    mmsi, fields = normalize_local_message(
        {"type": 1, "mmsi": 563123456, "lat": 91.0, "lon": 181.0, "speed": 102.3, "course": 360.0, "heading": 511}
    )
    assert mmsi == 563123456
    assert fields == {}


def test_local_null_island_is_dropped() -> None:
    """Position 0/0 is treated as invalid."""
    _, fields = normalize_local_message({"type": 1, "mmsi": 563123456, "lat": 0.0, "lon": 0.0})
    assert "lat" not in fields
    assert "lon" not in fields


@pytest.mark.parametrize("mmsi", [None, 0, -5, "abc", 1_000_000_000, True])
def test_local_invalid_mmsi(mmsi: object) -> None:
    """Messages without a valid MMSI are ignored."""
    assert normalize_local_message({"type": 1, "mmsi": mmsi, "lat": 1.0, "lon": 103.0}) is None


def test_local_static_message() -> None:
    """Type 5 static data with padding and ETA components."""
    _, fields = normalize_local_message(
        {
            "type": 5,
            "mmsi": 563123456,
            "shiptype": 80,
            "shipname": "OCEAN@STAR@@@@",
            "callsign": "9V1234@",
            "destination": "SG SIN@@@",
            "imo": 9876543,
            "draught": 12.4,
            "to_bow": 200,
            "to_stern": 44,
            "to_port": 21,
            "to_starboard": 21,
            "eta_month": 11,
            "eta_day": 27,
            "eta_hour": 8,
            "eta_minute": 30,
        }
    )
    assert fields["shiptype"] == 80
    assert fields["shipname"] == "OCEAN STAR"
    assert fields["callsign"] == "9V1234"
    assert fields["destination"] == "SG SIN"
    assert fields["imo"] == 9876543
    assert fields["draught"] == 12.4
    assert fields["to_bow"] == 200
    assert fields["to_starboard"] == 21
    assert fields["eta"] == "11-27 08:30"


def test_local_eta_not_available() -> None:
    """ETA 0-0 24:60 (AIS default) is dropped."""
    _, fields = normalize_local_message(
        {"type": 5, "mmsi": 563123456, "eta_month": 0, "eta_day": 0, "eta_hour": 24, "eta_minute": 60}
    )
    assert "eta" not in fields


def test_local_eta_string_is_normalized() -> None:
    """ETA strings are normalized to MM-DD HH:MM."""
    _, fields = normalize_local_message({"type": 5, "mmsi": 563123456, "eta": "3-7 4:05"})
    assert fields["eta"] == "03-07 04:05"


def test_local_status_only_from_class_a_position() -> None:
    """The navigational status is only taken from class A position reports."""
    _, fields = normalize_local_message({"type": 18, "mmsi": 563123456, "status": 5})
    assert "status" not in fields
    _, fields = normalize_local_message({"type": 3, "mmsi": 563123456, "status": 5})
    assert fields["status"] == 5


# ---------------------------------------------------------------------------
# aisstream.io
# ---------------------------------------------------------------------------


def test_aisstream_position_report() -> None:
    """aisstream.io PositionReport becomes an AIS-catcher style message."""
    converted = convert_aisstream_message(
        {
            "MessageType": "PositionReport",
            "MetaData": {"MMSI": 563123456, "ShipName": "OCEAN STAR   "},
            "Message": {
                "PositionReport": {
                    "UserID": 563123456,
                    "Valid": True,
                    "Latitude": 1.2,
                    "Longitude": 103.9,
                    "Sog": 11.0,
                    "Cog": 45.0,
                    "TrueHeading": 44,
                    "NavigationalStatus": 0,
                }
            },
        }
    )
    assert converted is not None
    assert converted["type"] == 1
    assert converted["shipname"] == "OCEAN STAR   "
    mmsi, fields = normalize_local_message(converted)
    assert mmsi == 563123456
    assert fields["lat"] == 1.2
    assert fields["speed"] == 11.0
    assert fields["status"] == 0
    assert fields["shipname"] == "OCEAN STAR"


def test_aisstream_static_data() -> None:
    """aisstream.io ShipStaticData keeps type, dimensions and ETA."""
    converted = convert_aisstream_message(
        {
            "MessageType": "ShipStaticData",
            "MetaData": {"MMSI": 563123456},
            "Message": {
                "ShipStaticData": {
                    "Valid": True,
                    "Type": 84,
                    "Name": "GAS ONE",
                    "CallSign": "9VGAS",
                    "ImoNumber": 9111111,
                    "Destination": "SINGAPORE",
                    "MaximumStaticDraught": 9.8,
                    "Dimension": {"A": 150, "B": 30, "C": 15, "D": 15},
                    "Eta": {"Month": 12, "Day": 1, "Hour": 6, "Minute": 0},
                }
            },
        }
    )
    _, fields = normalize_local_message(converted)
    assert fields["shiptype"] == 84
    assert fields["to_bow"] == 150
    assert fields["to_stern"] == 30
    assert fields["eta"] == "12-01 06:00"


@pytest.mark.parametrize(
    "message",
    [
        {"MessageType": "UnknownMessage", "MetaData": {"MMSI": 1}, "Message": {"UnknownMessage": {}}},
        {"MessageType": "PositionReport", "MetaData": {"MMSI": 1}, "Message": {"PositionReport": {"Valid": False}}},
        {"MessageType": "PositionReport", "Message": "broken"},
        {"MessageType": "PositionReport", "Message": {"PositionReport": {"Valid": True}}},
    ],
)
def test_aisstream_ignored_messages(message: dict) -> None:
    """Unknown, invalid or incomplete aisstream.io messages are ignored."""
    assert convert_aisstream_message(message) is None


# ---------------------------------------------------------------------------
# AISHub
# ---------------------------------------------------------------------------


def test_aishub_record() -> None:
    """A tanker record is normalized with its report time."""
    now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC).timestamp()
    result = normalize_aishub_record(
        {
            "MMSI": 563123456,
            "TYPE": 81,
            "LATITUDE": 1.25,
            "LONGITUDE": 103.8,
            "SOG": 9.5,
            "COG": 270.0,
            "HEADING": 268,
            "NAVSTAT": 0,
            "NAME": "CHEM ONE",
            "DRAUGHT": 8.2,
            "A": 120,
            "B": 20,
            "TIME": "2026-11-26 11:55:00 GMT",
        },
        now,
    )
    assert result is not None
    mmsi, fields = result
    assert mmsi == 563123456
    assert fields["shiptype"] == 81
    assert fields["shipname"] == "CHEM ONE"
    assert fields["to_bow"] == 120
    assert fields["last_seen"] == now - 300


def test_aishub_future_time_is_clamped() -> None:
    """A report time in the future never lies after 'now'."""
    now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC).timestamp()
    _, fields = normalize_aishub_record(
        {"MMSI": 563123456, "TYPE": 80, "LATITUDE": 1.0, "LONGITUDE": 103.0, "TIME": "2026-11-26 13:00:00 GMT"},
        now,
    )
    assert fields["last_seen"] == now


def test_aishub_unix_time() -> None:
    """AISHub TIME may also be unix seconds."""
    _, fields = normalize_aishub_record(
        {"MMSI": 563123456, "TYPE": 80, "LATITUDE": 1.0, "LONGITUDE": 103.0, "TIME": "1700000000"},
        1_800_000_000.0,
    )
    assert fields["last_seen"] == 1_700_000_000.0


def test_split_aishub_payload() -> None:
    """The vessel list is returned, non-dict entries are dropped."""
    payload = [{"ERROR": False}, [{"MMSI": 1}, "junk", {"MMSI": 2}]]
    assert split_aishub_payload(payload) == [{"MMSI": 1}, {"MMSI": 2}]


def test_split_aishub_rate_limited() -> None:
    """'Too frequent requests' becomes a rate limit error."""
    with pytest.raises(AisHubRateLimitedError):
        split_aishub_payload([{"ERROR": True, "ERROR_MESSAGE": "Too frequent requests!"}])


def test_split_aishub_error() -> None:
    """Other AISHub errors raise AisHubError."""
    with pytest.raises(AisHubError) as err:
        split_aishub_payload([{"ERROR": "true", "ERROR_MESSAGE": "Invalid username"}])
    assert not isinstance(err.value, AisHubRateLimitedError)
    with pytest.raises(AisHubError):
        split_aishub_payload("not json")


# ---------------------------------------------------------------------------
# MQTT payloads
# ---------------------------------------------------------------------------


def test_iter_json_objects_variants() -> None:
    """Objects, arrays, NDJSON and bytes are accepted."""
    assert list(iter_json_objects('{"mmsi": 1}')) == [{"mmsi": 1}]
    assert list(iter_json_objects('[{"mmsi": 1}, 5, {"mmsi": 2}]')) == [{"mmsi": 1}, {"mmsi": 2}]
    assert list(iter_json_objects('{"mmsi": 1}\nnot json\n\n{"mmsi": 2}\n')) == [{"mmsi": 1}, {"mmsi": 2}]
    assert list(iter_json_objects(b'{"mmsi": 3}')) == [{"mmsi": 3}]
    assert list(iter_json_objects("   ")) == []
    assert list(iter_json_objects(None)) == []


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------


def test_parse_zones() -> None:
    """Zones separated by ; and new lines are parsed."""
    zones = parse_zones("Singapore:0.9,1.6,103.3,104.6;Hormuz:24.5,27.5,54.5,58.5\nGulf_of_Mexico:27,30.5,-97.5,-88")
    assert [zone.name for zone in zones] == ["Singapore", "Hormuz", "Gulf_of_Mexico"]
    assert zones[2] == AisHubZone("Gulf_of_Mexico", 27.0, 30.5, -97.5, -88.0)
    assert parse_zones("") == []
    assert parse_zones(None) == []


@pytest.mark.parametrize(
    "raw",
    ["Singapore", "Bad:2,1,103,104", "Bad:1,2,104,103", "Bad:1,2,103", "Bad:-91,2,103,104"],
)
def test_parse_zones_invalid(raw: str) -> None:
    """Invalid zone definitions raise ValueError."""
    with pytest.raises(ValueError):
        parse_zones(raw)


def test_zones_containing() -> None:
    """Overlapping zones are all reported, in configuration order."""
    zones = parse_zones("Outer:0,10,100,110;Inner:4,6,104,106;Outer:20,30,100,110")
    assert zones_containing(zones, 5.0, 105.0) == ["Outer", "Inner"]
    assert zones_containing(zones, 1.0, 101.0) == ["Outer"]
    assert zones_containing(zones, 25.0, 105.0) == ["Outer"]
    assert zones_containing(zones, 15.0, 105.0) == []
    # Borders belong to the zone
    assert zones_containing(zones, 0.0, 100.0) == ["Outer"]
    assert unique_zone_names(zones) == ["Outer", "Inner"]


def test_zone_event_payload() -> None:
    """The event data contains the documented vessel fields."""
    vessel = {
        "mmsi": 563123456,
        "name": "OCEAN STAR",
        "load_status": "Laden",
        "vessel_class": "Suezmax",
        "vessel_type_code": 80,
        "vessel_type_label": "Tanker (General)",
        "draught_m": 15.1,
        "speed_knots": 12.0,
        "course": 90.0,
        "destination": "SINGAPORE",
        "lat": 1.2,
        "lon": 103.9,
        "source": "aisstream",
        "distance_km": 12.3,
    }
    payload = zone_event_payload(vessel, "Singapore", "moved")
    assert payload["mmsi"] == 563123456
    assert payload["name"] == "OCEAN STAR"
    assert payload["zone"] == "Singapore"
    assert payload["reason"] == "moved"
    assert payload["load_status"] == "Laden"
    assert payload["vessel_class"] == "Suezmax"
    # Values relative to the home location are not part of the event
    assert "distance_km" not in payload

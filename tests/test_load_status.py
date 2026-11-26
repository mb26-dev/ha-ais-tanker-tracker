"""Tests for the laden / ballast estimate and the size classes."""

from __future__ import annotations

import pytest

from custom_components.ais_tanker.const import (
    LOAD_STATUS_BALLAST,
    LOAD_STATUS_LADEN,
    LOAD_STATUS_PARTIAL,
    LOAD_STATUS_UNKNOWN,
    VESSEL_CLASS_UNKNOWN,
)
from custom_components.ais_tanker.coordinator import load_status, vessel_class


@pytest.mark.parametrize(
    ("draught", "length", "expected"),
    [
        # Small coastal / bunker tankers (< 120 m): laden >= 0.065, ballast <= 0.050
        (7.0, 100, LOAD_STATUS_LADEN),
        (5.7, 100, LOAD_STATUS_PARTIAL),
        (4.5, 100, LOAD_STATUS_BALLAST),
        # Large tankers: laden >= 0.055, ballast <= 0.042
        (20.0, 330, LOAD_STATUS_LADEN),
        (16.0, 330, LOAD_STATUS_PARTIAL),
        (10.0, 330, LOAD_STATUS_BALLAST),
        (11.0, 180, LOAD_STATUS_LADEN),
        (6.0, 180, LOAD_STATUS_BALLAST),
    ],
)
def test_load_status(draught: float, length: int, expected: str) -> None:
    """Draught / length ratio with separate thresholds for small tankers."""
    assert load_status(draught, length) == expected


def test_small_and_large_thresholds_differ() -> None:
    """The same ratio means partial for a small and laden for a large tanker."""
    assert load_status(6.0, 100) == LOAD_STATUS_PARTIAL
    assert load_status(18.0, 300) == LOAD_STATUS_LADEN


@pytest.mark.parametrize(
    ("draught", "length"),
    [(None, 180), (11.0, None), (0.0, 180), (11.0, 0), (-1.0, 180), (None, None)],
)
def test_load_status_unknown(draught: float | None, length: int | None) -> None:
    """Missing or invalid values give Unknown."""
    assert load_status(draught, length) == LOAD_STATUS_UNKNOWN


@pytest.mark.parametrize(
    ("length", "expected"),
    [
        (None, VESSEL_CLASS_UNKNOWN),
        (0, VESSEL_CLASS_UNKNOWN),
        (80, "Coastal / Bunker Tanker"),
        (119, "Coastal / Bunker Tanker"),
        (120, "Handysize / MR Tanker"),
        (189, "Handysize / MR Tanker"),
        (190, "Panamax / Aframax"),
        (249, "Panamax / Aframax"),
        (250, "Suezmax"),
        (299, "Suezmax"),
        (300, "VLCC / ULCC Supertanker"),
        (380, "VLCC / ULCC Supertanker"),
    ],
)
def test_vessel_class(length: int | None, expected: str) -> None:
    """Size classes by ship length."""
    assert vessel_class(length) == expected

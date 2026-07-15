"""Tests for the application's pure helper functions."""

import pytest

from utils.helpers import (
    calculate_days_remaining,
    get_idle_bucket,
    validate_enabled_param,
)


@pytest.mark.parametrize(
    ("days_idle", "expected"),
    [
        (0, "Σήμερα"),
        (1, "1-7 μέρες"),
        (7, "1-7 μέρες"),
        (8, "8-30 μέρες"),
        (30, "8-30 μέρες"),
        (31, "31-90 μέρες"),
        (90, "31-90 μέρες"),
        (91, "90+ μέρες"),
        (365, "90+ μέρες"),
    ],
)
def test_get_idle_bucket_boundaries(days_idle, expected):
    assert get_idle_bucket(days_idle) == expected


def test_get_idle_bucket_rejects_negative_days():
    with pytest.raises(ValueError, match="cannot be negative"):
        get_idle_bucket(-1)


@pytest.mark.parametrize(
    ("delete_after", "now", "expected"),
    [
        ("2026-07-17 12:00:00", "2026-07-14 12:00:00", 3.0),
        ("2026-07-15T00:00:00", "2026-07-14T12:00:00", 0.5),
        ("2026-07-15T00:00:00", "2026-07-14T16:00:00", 0.33),
        ("2026-07-14T12:00:00", "2026-07-14T12:00:00", 0.0),
        ("2026-07-13T06:00:00", "2026-07-14T12:00:00", -1.25),
    ],
)
def test_calculate_days_remaining(delete_after, now, expected):
    assert calculate_days_remaining(delete_after, now) == expected


@pytest.mark.parametrize(
    ("param", "expected"),
    [
        ("true", True),
        ("false", False),
    ],
)
def test_validate_enabled_param_accepts_valid_values(param, expected):
    assert validate_enabled_param(param) is expected


@pytest.mark.parametrize("param", ["True", "FALSE", "yes", "1", ""])
def test_validate_enabled_param_rejects_invalid_values(param):
    with pytest.raises(ValueError, match="enabled must be true or false"):
        validate_enabled_param(param)

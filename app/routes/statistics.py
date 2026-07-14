"""Statistics endpoints for terminal data."""

import json
from datetime import datetime, timezone
from typing import Callable

import pandas as pd
from flask import Blueprint, jsonify

from cache import redis_client
from settings import logger
from database import get_terminals_df


statistics_bp = Blueprint("statistics", __name__, url_prefix="/statistics")

CACHE_TTL_SECONDS = 60
IDLE_RANGES = (
    "Σήμερα",
    "1-7 μέρες",
    "8-30 μέρες",
    "31-90 μέρες",
    "90+ μέρες",
)


def _generated_at() -> str:
    """Return a JSON-friendly ISO 8601 timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat()


def _cached_response(cache_key: str, build_payload: Callable[[], dict]):
    """Return a cached payload or calculate and cache it for 60 seconds."""
    try:
        cached_payload = redis_client.get(cache_key)
        if cached_payload is not None:
            logger.info("Cache HIT for %s", cache_key)
            return jsonify(json.loads(cached_payload))

        logger.info("Cache MISS for %s", cache_key)
        payload = build_payload()
        redis_client.setex(
            cache_key,
            CACHE_TTL_SECONDS,
            json.dumps(payload, ensure_ascii=False),
        )
        return jsonify(payload)
    except Exception:
        logger.exception("Failed to serve statistics for cache key %s", cache_key)
        return jsonify({"error": "Internal server error"}), 500


def _required_series(terminals_df: pd.DataFrame, column: str) -> pd.Series:
    """Return a required column while allowing a valid, empty result set."""
    if column in terminals_df.columns:
        return terminals_df[column]
    if terminals_df.empty:
        return pd.Series(dtype="object")
    raise KeyError(f"Missing required column: {column}")


def _grouped_counts(column: str) -> dict:
    terminals_df = get_terminals_df()
    values = _required_series(terminals_df, column).astype("object")
    values = values.where(values.notna(), "Unknown")
    counts = values.groupby(values, sort=True).size()

    return {
        "generated_at": _generated_at(),
        "data": [
            {column: str(value), "count": int(count)}
            for value, count in counts.items()
        ],
    }


@statistics_bp.get("/by-hardware")
def statistics_by_hardware():
    """Count terminals by hardware model."""
    return _cached_response(
        "statistics:by-hardware",
        lambda: _grouped_counts("hardware_model"),
    )


@statistics_bp.get("/by-hardware-family")
def statistics_by_hardware_family():
    """Count terminals by hardware family."""
    return _cached_response(
        "statistics:by-hardware-family",
        lambda: _grouped_counts("hardware_family"),
    )


@statistics_bp.get("/by-state")
def statistics_by_state():
    """Count active, inactive, and total terminals."""

    def build_payload() -> dict:
        terminals_df = get_terminals_df()
        enabled = pd.to_numeric(
            _required_series(terminals_df, "enabled"), errors="coerce"
        )

        return {
            "generated_at": _generated_at(),
            "active": int(enabled.eq(1).sum()),
            "inactive": int(enabled.eq(0).sum()),
            "total": int(len(terminals_df.index)),
        }

    return _cached_response("statistics:by-state", build_payload)


@statistics_bp.get("/idle-distribution")
def statistics_idle_distribution():
    """Count terminals by the number of days since their last call."""

    def build_payload() -> dict:
        terminals_df = get_terminals_df()
        last_calls = pd.to_datetime(
            _required_series(terminals_df, "last_call_stamp"),
            errors="coerce",
            utc=True,
        )
        now = pd.Timestamp.now(tz="UTC")

        # A terminal without a last call is treated as belonging to the longest
        # idle range, since the response contract permits exactly five buckets.
        idle_days = ((now - last_calls).dt.total_seconds() // 86_400).clip(lower=0)
        ranges = pd.Series("90+ μέρες", index=terminals_df.index)
        ranges.loc[idle_days.le(0)] = "Σήμερα"
        ranges.loc[idle_days.between(1, 7)] = "1-7 μέρες"
        ranges.loc[idle_days.between(8, 30)] = "8-30 μέρες"
        ranges.loc[idle_days.between(31, 90)] = "31-90 μέρες"
        counts = ranges.value_counts()

        return {
            "generated_at": _generated_at(),
            "data": [
                {"range": idle_range, "count": int(counts.get(idle_range, 0))}
                for idle_range in IDLE_RANGES
            ],
        }

    return _cached_response("statistics:idle-distribution", build_payload)

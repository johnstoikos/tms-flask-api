"""Pure helper functions shared by the application."""

from datetime import datetime


def get_idle_bucket(days_idle: int) -> str:
    """Return the display bucket for a terminal's number of idle days."""
    if days_idle < 0:
        raise ValueError("days_idle cannot be negative")
    if days_idle == 0:
        return "Σήμερα"
    if days_idle <= 7:
        return "1-7 μέρες"
    if days_idle <= 30:
        return "8-30 μέρες"
    if days_idle <= 90:
        return "31-90 μέρες"
    return "90+ μέρες"


def calculate_days_remaining(delete_after_str: str, now_str: str) -> float:
    """Return the difference between two ISO datetime strings in days."""
    delete_after = datetime.fromisoformat(delete_after_str)
    now = datetime.fromisoformat(now_str)
    difference_in_days = (delete_after - now).total_seconds() / 86_400
    return round(difference_in_days, 2)


def validate_enabled_param(param: str) -> bool:
    """Convert a valid lowercase enabled query parameter to a boolean."""
    if param == "true":
        return True
    if param == "false":
        return False
    raise ValueError("enabled must be true or false")

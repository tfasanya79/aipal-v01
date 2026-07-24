"""User-local calendar helpers."""

from datetime import date, datetime
from zoneinfo import ZoneInfo


def _default_timezone():
    return datetime.now().astimezone().tzinfo or ZoneInfo("UTC")


def user_local_today(tz_name: str | None) -> date:
    try:
        if not tz_name or tz_name.upper() == "UTC":
            tz = _default_timezone()
        else:
            tz = ZoneInfo(tz_name)
    except Exception:
        tz = _default_timezone()
    return datetime.now(tz).date()

from datetime import UTC, datetime, timedelta, timezone
from math import ceil

HOUR = 3600
DAY = 24 * HOUR
DICK_COOLDOWN = 12 * HOUR
PREGNANCY_DURATION = 9 * DAY
POSTPARTUM_COOLDOWN = 2 * DAY
REQUEST_DURATION = 15 * 60
MSK = timezone(timedelta(hours=3), "МСК")


def utc_now() -> float:
    return datetime.now(UTC).timestamp()


def moscow_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).astimezone(MSK).strftime("%d.%m.%Y %H:%M:%S МСК")


def duration(seconds: float) -> str:
    remaining = max(0, ceil(seconds))
    days, remaining = divmod(remaining, DAY)
    hours, remaining = divmod(remaining, HOUR)
    minutes, seconds = divmod(remaining, 60)
    return " ".join(
        f"{value} {unit}"
        for value, unit in ((days, "д."), (hours, "ч."), (minutes, "мин."), (seconds, "сек."))
        if value
    ) or "0 сек."


def availability(timestamp: float, now: float) -> str:
    if timestamp <= now:
        return "сейчас!"
    return f"через {duration(timestamp - now)} ({moscow_time(timestamp)})"

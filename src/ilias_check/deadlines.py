"""Conservative source-date normalization independent of the host timezone."""

from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo


_MONTHS = {
    "jan": 1, "januar": 1, "feb": 2, "februar": 2, "mär": 3, "märz": 3, "maerz": 3,
    "apr": 4, "april": 4, "mai": 5, "jun": 6, "juni": 6, "jul": 7, "juli": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "okt": 10, "oktober": 10, "nov": 11, "november": 11, "dez": 12, "dezember": 12,
}


def normalize_deadline(raw: str | None, installation_timezone: str | None) -> tuple[datetime | None, str]:
    if not raw or raw.strip().casefold() in {"keine abgabefrist", "no deadline"}:
        return None, "no_deadline"
    value = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None, "deadline_time_missing"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        numeric = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})[ ,]+(\d{1,2}):(\d{2})", value)
        words = re.fullmatch(r"(\d{1,2})\.\s*([^\W\d_]+)\.?\s+(\d{4}),?\s+(\d{1,2}):(\d{2})", value)
        try:
            if numeric:
                day, month, year, hour, minute = map(int, numeric.groups())
            elif words:
                day, month_text, year, hour, minute = words.groups()
                month = _MONTHS[month_text.casefold()]
                day, year, hour, minute = map(int, (day, year, hour, minute))
            else:
                return None, "unparseable_deadline"
            parsed = datetime(year, month, day, hour, minute)
        except (ValueError, KeyError):
            return None, "unparseable_deadline"
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc), "resolved"
    if not installation_timezone:
        return None, "installation_timezone_missing"
    zone = ZoneInfo(installation_timezone)
    candidates = set()
    for fold in (0, 1):
        local = parsed.replace(tzinfo=zone, fold=fold)
        instant = local.astimezone(timezone.utc)
        if instant.astimezone(zone).replace(tzinfo=None) == parsed:
            candidates.add(instant)
    if not candidates:
        return None, "nonexistent_local_time"
    if len(candidates) != 1:
        return None, "ambiguous_local_time"
    return candidates.pop(), "resolved"

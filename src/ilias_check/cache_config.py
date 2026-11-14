"""Host capacity and user retention policy; no bot-controlled quota override."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class CacheError(ValueError):
    """Sanitized cache/configuration error."""


def positive(values: Mapping, key: str, default: int) -> int:
    raw = values.get(key)
    try:
        value = int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        raise CacheError(f"{key} must be a positive integer.") from None
    if value <= 0:
        raise CacheError(f"{key} must be a positive integer.")
    return value


def boolean(values: Mapping, key: str, default: bool = False) -> bool:
    raw = values.get(key)
    if raw in (None, ""):
        return default
    if str(raw).lower() not in {"true", "false"}:
        raise CacheError(f"{key} must be true or false.")
    return str(raw).lower() == "true"


@dataclass(frozen=True)
class CachePolicy:
    enabled: bool = False
    directory: Path = Path("~/.local/share/ilias-check/support")
    max_bytes: int = 200000000
    max_file_bytes: int = 20 * 1024 * 1024
    max_run_bytes: int = 100 * 1024 * 1024
    revalidate_hours: int = 12
    no_deadline_hours: int = 168
    retention_max_hours: int | None = None

    @classmethod
    def from_mapping(cls, values: Mapping) -> CachePolicy:
        return cls(
            enabled=boolean(values, "ILIAS_PENDING_DOWNLOAD_SUPPORT"),
            directory=Path(values.get("ILIAS_PENDING_OUTPUT_DIR") or "~/.local/share/ilias-check/support"),
            max_bytes=positive(values, "ILIAS_SUPPORT_CACHE_MAX_BYTES", 200000000),
            max_file_bytes=positive(values, "ILIAS_SUPPORT_MAX_FILE_BYTES", 20 * 1024 * 1024),
            max_run_bytes=positive(values, "ILIAS_SUPPORT_MAX_RUN_BYTES", 100 * 1024 * 1024),
            revalidate_hours=positive(values, "ILIAS_SUPPORT_REVALIDATE_HOURS", 12),
            no_deadline_hours=positive(values, "ILIAS_SUPPORT_NO_DEADLINE_TTL_HOURS", 168),
            retention_max_hours=(positive(values, "ILIAS_SUPPORT_RETENTION_MAX_HOURS", 168)
                                 if values.get("ILIAS_SUPPORT_RETENTION_MAX_HOURS") else None),
        )

    def with_retention(self, no_deadline_hours: int | None = None, retention_max_hours: int | None = None) -> CachePolicy:
        """Only the two allowlisted user fields can override host policy."""
        from dataclasses import replace
        if no_deadline_hours is not None and (type(no_deadline_hours) is not int or no_deadline_hours <= 0):
            raise CacheError("Invalid no-deadline retention.")
        if retention_max_hours is not None and (type(retention_max_hours) is not int or retention_max_hours <= 0):
            raise CacheError("Invalid retention cap.")
        return replace(self, no_deadline_hours=no_deadline_hours or self.no_deadline_hours,
                       retention_max_hours=retention_max_hours)

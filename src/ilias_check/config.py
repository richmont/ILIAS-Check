"""Explicit, validated runtime configuration."""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from dotenv import dotenv_values
from ilias_check.policy import ClassificationPolicy, PolicyError
from ilias_check.cache_config import CachePolicy, CacheError


class ConfigurationError(ValueError):
    """Safe-to-display configuration error (contains no secret values)."""


@dataclass(frozen=True, slots=True)
class CollectorConfig:
    base_url: str
    client_id: str
    username: str
    password: str
    roots: tuple[str, ...]
    root_occurrences: tuple[str, ...]
    timeout_seconds: float = 20.0
    max_depth: int = 12
    max_requests: int = 500
    classification_policy: ClassificationPolicy = field(default_factory=ClassificationPolicy)
    cache_policy: CachePolicy = field(default_factory=CachePolicy)

    @classmethod
    def from_environment(
        cls,
        env_file: str | Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> "CollectorConfig":
        """Load only the selected dotenv file, then overlay the process environment."""
        return cls.from_mapping(load_environment(env_file, environ))

    @classmethod
    def from_mapping(cls, values: Mapping[str, str | None]) -> "CollectorConfig":
        base_url = _required(values, "ILIAS_BASE_URL")
        client_id = _required(values, "ILIAS_CLIENT_ID")
        username = _required(values, "ILIAS_USER")
        password = _required(values, "ILIAS_PASS", preserve_whitespace=True)
        roots_text = _required(values, "ILIAS_PENDING_ROOTS")

        parsed_url = urlsplit(base_url)
        if (
            parsed_url.scheme.lower() != "https"
            or not parsed_url.hostname
            or parsed_url.username is not None
            or parsed_url.password is not None
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ConfigurationError(
                "ILIAS_BASE_URL must be an HTTPS installation URL without credentials, query, or fragment."
            )
        if not re.fullmatch(r"[A-Za-z0-9_-]+", client_id):
            raise ConfigurationError("ILIAS_CLIENT_ID contains unsupported characters.")

        occurrences: list[str] = []
        roots: list[str] = []
        for raw in roots_text.split(","):
            item = raw.strip()
            if not item:
                continue
            if not re.fullmatch(r"[0-9]+", item) or int(item) <= 0:
                raise ConfigurationError("ILIAS_PENDING_ROOTS must contain positive numeric reference IDs.")
            normalized = str(int(item))
            occurrences.append(normalized)
            if normalized not in roots:
                roots.append(normalized)
        if not roots:
            raise ConfigurationError("ILIAS_PENDING_ROOTS must contain at least one positive reference ID.")

        timeout = _positive_float(values, "ILIAS_TIMEOUT_SECONDS", 20.0)
        max_depth = _positive_int(values, "ILIAS_PENDING_MAX_DEPTH", 12)
        max_requests = _positive_int(values, "ILIAS_PENDING_MAX_REQUESTS", 500)
        try:
            policy = ClassificationPolicy.from_mapping(values)
            cache_policy = CachePolicy.from_mapping(values)
        except (PolicyError, CacheError) as exc:
            raise ConfigurationError(str(exc)) from None

        # Normalize installation URL without changing its path semantics.
        normalized_base = base_url.rstrip("/")
        return cls(
            base_url=normalized_base,
            client_id=client_id,
            username=username,
            password=password,
            roots=tuple(roots),
            root_occurrences=tuple(occurrences),
            timeout_seconds=timeout,
            max_depth=max_depth,
            max_requests=max_requests,
            classification_policy=policy,
            cache_policy=cache_policy,
        )


def load_environment(
    env_file: str | Path | None = None, environ: Mapping[str, str] | None = None,
) -> dict[str, str | None]:
    """Load only an explicit dotenv file, then overlay the process environment."""
    values: dict[str, str | None] = {}
    if env_file is not None:
        path = Path(env_file).expanduser()
        if not path.is_file():
            raise ConfigurationError("The explicitly selected dotenv file is unavailable.")
        try:
            values.update(dotenv_values(path, encoding="utf-8"))
        except (OSError, UnicodeError):
            raise ConfigurationError("The explicitly selected dotenv file could not be read.") from None
    values.update(dict(os.environ if environ is None else environ))
    return values


def _required(
    values: Mapping[str, str | None],
    key: str,
    *,
    preserve_whitespace: bool = False,
) -> str:
    value = values.get(key)
    if value is None or not value.strip():
        raise ConfigurationError(f"Missing required configuration: {key}.")
    return value if preserve_whitespace else value.strip()


def _positive_int(values: Mapping[str, str | None], key: str, default: int) -> int:
    raw = values.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ConfigurationError(f"{key} must be a positive integer.") from None
    if value <= 0:
        raise ConfigurationError(f"{key} must be a positive integer.")
    return value


def _positive_float(values: Mapping[str, str | None], key: str, default: float) -> float:
    raw = values.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ConfigurationError(f"{key} must be a finite positive number.") from None
    if not math.isfinite(value) or value <= 0:
        raise ConfigurationError(f"{key} must be a finite positive number.")
    return value

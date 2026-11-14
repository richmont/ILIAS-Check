"""Collection orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ilias_check.auth import Authenticator
from ilias_check.config import CollectorConfig
from ilias_check.inventory import build_inventory
from ilias_check.traversal import RepositoryCrawler
from ilias_check.transport import SafeTransport


def collect_inventory(
    config: CollectorConfig,
    transport: Any | None = None,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    owns_transport = transport is None
    safe_transport = transport if transport is not None else SafeTransport(config)
    try:
        result = RepositoryCrawler(
            config,
            Authenticator(config=config, transport=safe_transport),
        ).collect()
        return build_inventory(result, config, checked_at=checked_at)
    finally:
        if owns_transport:
            close = getattr(safe_transport, "close", None)
            if callable(close):
                close()

"""Collection orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ilias_check.auth import Authenticator
from ilias_check.config import CollectorConfig
from ilias_check.inventory import build_inventory
from ilias_check.traversal import RepositoryCrawler
from ilias_check.transport import SafeTransport
from ilias_check.support_cache import cache_inventory


def collect_inventory(
    config: CollectorConfig,
    transport: Any | None = None,
    checked_at: datetime | None = None,
    progress: Any | None = None,
) -> dict[str, Any]:
    owns_transport = transport is None
    safe_transport = transport if transport is not None else SafeTransport(config)
    if progress is not None and hasattr(safe_transport, "on_request"):
        safe_transport.on_request = progress.request
    completed = False
    try:
        if progress is not None:
            progress.start(len(config.roots), config.max_requests)
        auth = Authenticator(config=config, transport=safe_transport)
        result = RepositoryCrawler(config, auth, progress).collect()
        inventory = build_inventory(result, config, checked_at=checked_at)
        inventory = cache_inventory(inventory, config, auth)
        completed = True
        return inventory
    finally:
        if progress is not None:
            progress.finish(completed)
        if owns_transport:
            close = getattr(safe_transport, "close", None)
            if callable(close):
                close()

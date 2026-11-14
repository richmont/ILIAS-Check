"""Versioned JSON inventory serialization."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ilias_check.config import CollectorConfig
from ilias_check.traversal import TraversalResult


SCHEMA_VERSION = "1.0"


def build_inventory(
    result: TraversalResult,
    config: CollectorConfig,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    timestamp = checked_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("Inventory timestamps must include a timezone.")
    timestamp = timestamp.astimezone(timezone.utc)
    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": timestamp.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "scope": {
            "base_url": config.base_url,
            "client_id": config.client_id,
            "root_ids": list(config.roots),
        },
        "coverage": [
            {
                "root_id": root.root_id,
                "complete": root.complete,
                "empty": bool(root.complete and root.objects_discovered <= 1),
                "objects_discovered": root.objects_discovered,
                "warnings": sorted(set(root.warnings)),
                **({"error": root.error} if root.error else {}),
            }
            for root in result.coverage
        ],
        "objects": [
            {
                "id": item.ref_id,
                "type": item.object_type,
                "type_code": item.type_code,
                "title": item.title,
                "instructions": item.instructions,
                "paths": item.paths,
                "url": item.url,
                "url_kind": item.url_kind,
                "documents": item.documents,
                "sequence_resolution": item.sequence_resolution,
                "sequence_steps": item.sequence_steps,
                "warnings": sorted(set(item.warnings)),
            }
            for item in sorted(
                result.objects.values(),
                key=lambda object_record: (object_record.type_code, object_record.ref_id),
            )
        ],
        "errors": result.errors,
    }

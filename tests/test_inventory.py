from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ilias_check.config import CollectorConfig
from ilias_check.inventory import build_inventory
from ilias_check.traversal import RepositoryCrawler


ROOT = Path(__file__).parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "inventory-v1.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
BASE = "https://ilias.example.edu"


def config(roots: str) -> CollectorConfig:
    return CollectorConfig.from_mapping(
        {
            "ILIAS_BASE_URL": BASE,
            "ILIAS_CLIENT_ID": "academy",
            "ILIAS_USER": "synthetic-user",
            "ILIAS_PASS": "synthetic-password",
            "ILIAS_PENDING_ROOTS": roots,
        }
    )


class OfflineAuth:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages

    def get(self, url: str):
        if url not in self.pages:
            raise RuntimeError("synthetic offline page unavailable")
        return type("Response", (), {"url": url, "text": self.pages[url]})()


def url(ref_id: str) -> str:
    return f"{BASE}/goto.php?target=fold_{ref_id}&client_id=academy"


def validate_result(roots: str, pages: dict[str, str]) -> dict:
    result = RepositoryCrawler(config(roots), OfflineAuth(pages)).collect()
    inventory = build_inventory(
        result,
        config(roots),
        checked_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
    )
    VALIDATOR.validate(inventory)
    assert inventory["checked_at"] == "2026-01-02T03:04:05Z"
    return inventory


def test_complete_empty_root_is_distinct_and_schema_valid() -> None:
    inventory = validate_result("1001", {url("1001"): "<main><h1>Empty</h1></main>"})
    assert inventory["coverage"] == [
        {
            "root_id": "1001",
            "complete": True,
            "empty": True,
            "objects_discovered": 1,
            "warnings": [],
        }
    ]
    assert inventory["objects"][0]["title"] == "Empty"


def test_complete_nonempty_result_is_schema_valid() -> None:
    inventory = validate_result(
        "1001",
        {
            url("1001"): (
                '<main><h1>Root</h1><div class="ilContainerListItem">'
                '<a href="/goto.php?target=fold_1002">German Titel</a>'
                "</div></main>"
            ),
            url("1002"): "<main><h1>German Titel</h1></main>",
        },
    )
    assert inventory["coverage"][0]["complete"]
    assert not inventory["coverage"][0]["empty"]
    assert [item["title"] for item in inventory["objects"]] == [
        "Root",
        "German Titel",
    ]


def test_partial_result_retains_successful_root_and_redacted_error() -> None:
    inventory = validate_result(
        "1001,1002",
        {url("1002"): "<main><h1>Accessible</h1></main>"},
    )
    assert [item["complete"] for item in inventory["coverage"]] == [False, True]
    assert inventory["errors"] == [
        {
            "category": "object_read_failed",
            "root_id": "1001",
            "object_id": "1001",
            "message": "The object could not be read or parsed.",
        }
    ]
    assert "synthetic-password" not in json.dumps(inventory)


def test_all_failed_result_is_schema_valid_not_an_empty_success() -> None:
    inventory = validate_result("1001", {})
    assert not inventory["coverage"][0]["complete"]
    assert not inventory["coverage"][0]["empty"]
    assert inventory["errors"][0]["category"] == "object_read_failed"


def test_exported_links_are_canonical_and_token_free() -> None:
    inventory = validate_result("1001", {url("1001"): "<main><h1>Root</h1></main>"})
    for record in inventory["objects"]:
        assert record["url"] == url(record["id"])
        assert not any(
            key in record["url"].lower()
            for key in ("sesskey", "session", "token", "phpsessid")
        )


def test_checked_in_synthetic_example_validates_without_course_data() -> None:
    example = json.loads((ROOT / "examples" / "inventory-empty.json").read_text())
    VALIDATOR.validate(example)
    rendered = json.dumps(example)
    assert "example.edu" in rendered
    assert "synthetic" in rendered.lower()
    assert "dehydration" not in rendered.lower()

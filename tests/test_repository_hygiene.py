from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).parents[1]


def test_example_configuration_parses_and_contains_placeholders() -> None:
    values = dotenv_values(ROOT / ".env.example")
    assert values["ILIAS_BASE_URL"] == "https://ilias.example.edu"
    assert values["ILIAS_CLIENT_ID"].startswith("replace-with-")
    assert values["ILIAS_USER"].startswith("replace-with-")
    assert values["ILIAS_PASS"].startswith("replace-with-")
    assert values["ILIAS_PENDING_ROOTS"] == "123456"


def test_dotenv_variants_ignored_but_example_is_not() -> None:
    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", ".env.prod"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    example = subprocess.run(
        ["git", "check-ignore", "--no-index", ".env.example"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert ignored.returncode == 0
    assert example.returncode != 0


def test_runtime_has_no_ai_or_translation_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    dependencies = project["project"]["dependencies"]
    assert not any(
        marker in dependency.lower()
        for dependency in dependencies
        for marker in ("openai", "anthropic", "translate", "google-genai", "llm")
    )
    source = "\n".join(path.read_text() for path in (ROOT / "src").rglob("*.py"))
    assert "import openai" not in source
    assert "import anthropic" not in source

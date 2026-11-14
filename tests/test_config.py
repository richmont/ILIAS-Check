from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from ilias_check.config import CollectorConfig, ConfigurationError


BASE = {
    "ILIAS_BASE_URL": "https://ilias.example.edu",
    "ILIAS_CLIENT_ID": "academy",
    "ILIAS_USER": "student",
    "ILIAS_PASS": "not-a-real-password",
    "ILIAS_PENDING_ROOTS": "1001, 1001, 1002",
}


def test_defaults_and_duplicate_roots_preserve_scope() -> None:
    config = CollectorConfig.from_mapping(BASE)
    assert config.roots == ("1001", "1002")
    assert config.root_occurrences == ("1001", "1001", "1002")
    assert config.timeout_seconds == 20
    assert config.max_depth == 12
    assert config.max_requests == 500


@pytest.mark.parametrize(
    "key,value",
    [
        ("ILIAS_BASE_URL", "http://ilias.example.edu"),
        ("ILIAS_BASE_URL", "https://user:pass@ilias.example.edu"),
        ("ILIAS_BASE_URL", "https://ilias.example.edu/?token=x"),
        ("ILIAS_CLIENT_ID", "bad/client"),
        ("ILIAS_PENDING_ROOTS", ""),
        ("ILIAS_PENDING_ROOTS", "nope"),
        ("ILIAS_PENDING_ROOTS", "0"),
        ("ILIAS_TIMEOUT_SECONDS", "0"),
        ("ILIAS_TIMEOUT_SECONDS", "inf"),
        ("ILIAS_PENDING_MAX_DEPTH", "-1"),
        ("ILIAS_PENDING_MAX_REQUESTS", "abc"),
    ],
)
def test_invalid_settings_rejected(key: str, value: str) -> None:
    values = BASE | {key: value}
    with pytest.raises(ConfigurationError):
        CollectorConfig.from_mapping(values)


def test_missing_required_value_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="ILIAS_PENDING_ROOTS"):
        CollectorConfig.from_mapping(BASE | {"ILIAS_PENDING_ROOTS": " "})


@pytest.mark.parametrize("password", [" leading", "trailing ", " both "])
def test_password_whitespace_is_preserved(password: str) -> None:
    config = CollectorConfig.from_mapping(BASE | {"ILIAS_PASS": password})
    assert config.password == password


def test_whitespace_only_password_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="ILIAS_PASS"):
        CollectorConfig.from_mapping(BASE | {"ILIAS_PASS": " \t "})


def test_explicit_dotenv_from_unrelated_working_directory(tmp_path: Path) -> None:
    env_file = tmp_path / "chosen.env"
    env_file.write_text("\n".join(f"{key}={value}" for key, value in BASE.items()))
    work = tmp_path / "unrelated" / "nested"
    work.mkdir(parents=True)
    (tmp_path / ".env").write_text("ILIAS_PENDING_ROOTS=9999\n")
    script = """
from ilias_check.config import CollectorConfig
print(','.join(CollectorConfig.from_environment(%r, environ={}).roots))
""" % str(env_file)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=work,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "1001,1002"


def test_process_environment_overrides_dotenv(tmp_path: Path) -> None:
    env_file = tmp_path / "selected.env"
    env_file.write_text("\n".join(f"{key}={value}" for key, value in BASE.items()))
    config = CollectorConfig.from_environment(
        env_file,
        environ={"ILIAS_PENDING_ROOTS": "2001"},
    )
    assert config.roots == ("2001",)


def test_explicit_missing_dotenv_fails_without_discovery(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="explicitly selected"):
        CollectorConfig.from_environment(tmp_path / "missing.env", environ=BASE)

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

from ilias_check import cli, collector
from ilias_check.transport import SafeTransport


ROOT = Path(__file__).parents[1]
LOGIN_FIXTURE = (ROOT / "tests/fixtures/login/search-first.html").read_text()
DASHBOARD_FIXTURE = (ROOT / "tests/fixtures/login/dashboard.html").read_text()
SCHEMA = json.loads((ROOT / "schemas/inventory-v1.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        text: str = "",
        headers: dict[str, str] | None = None,
        url: str = "",
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.url = url


class FakeSession:
    def __init__(self, root_pages: dict[str, FakeResponse]) -> None:
        self.root_pages = root_pages
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        parsed = urlsplit(url)
        if method == "GET" and parsed.path.endswith("/login.php"):
            return FakeResponse(text=LOGIN_FIXTURE, url=url)
        if method == "POST" and parsed.path.endswith("/login.php"):
            return FakeResponse(
                status_code=302,
                headers={"Location": "/ilias.php?baseClass=ilDashboardGUI"},
                url=url,
            )
        if method == "GET" and parsed.path.endswith("/ilias.php"):
            return FakeResponse(text=DASHBOARD_FIXTURE, url=url)
        if method == "GET" and parsed.path.endswith("/goto.php"):
            target = dict(
                part.split("=", 1) for part in parsed.query.split("&") if "=" in part
            ).get("target", "")
            ref_id = target.rsplit("_", 1)[-1]
            return self.root_pages.get(
                ref_id,
                FakeResponse(status_code=404, text="synthetic unavailable", url=url),
            )
        raise AssertionError(f"Unexpected fake request: {method} {url}")

    def close(self) -> None:
        pass


def _env_file(tmp_path: Path, roots: str = "1001") -> Path:
    path = tmp_path / "selected.env"
    path.write_text(
        "\n".join(
            [
                "ILIAS_BASE_URL=https://ilias.example.edu",
                "ILIAS_CLIENT_ID=academy",
                "ILIAS_USER=synthetic-user",
                "ILIAS_PASS=synthetic-password",
                f"ILIAS_PENDING_ROOTS={roots}",
            ]
        )
    )
    return path


def _install_fake_transport(monkeypatch, pages: dict[str, FakeResponse]) -> FakeSession:
    session = FakeSession(pages)

    def fake_safe_transport(config):
        return SafeTransport(config, session=session, sleeper=lambda _: None)

    monkeypatch.setattr(collector, "SafeTransport", fake_safe_transport)
    return session


def test_cli_complete_run_emits_only_schema_valid_json(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    session = _install_fake_transport(
        monkeypatch,
        {
            "1001": FakeResponse(
                text="<main><h1>Synthetic empty root</h1></main>",
                url="https://ilias.example.edu/goto.php?target=fold_1001",
            )
        },
    )
    env_file = _env_file(tmp_path)
    status = cli.main(["collect", "--env-file", str(env_file)])
    output = capsys.readouterr()
    assert status == 0
    assert output.err == ""
    inventory = json.loads(output.out)
    VALIDATOR.validate(inventory)
    assert inventory["coverage"][0]["empty"] is True
    assert all(call[0] in {"GET", "POST"} for call in session.calls)
    assert [call[0] for call in session.calls].count("POST") == 1
    assert all(call[2]["allow_redirects"] is False for call in session.calls)


def test_cli_partial_run_keeps_good_root_and_redacted_stderr(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    _install_fake_transport(
        monkeypatch,
        {
            "1001": FakeResponse(
                text="<main><h1>Available</h1></main>",
                url="https://ilias.example.edu/goto.php?target=fold_1001",
            )
        },
    )
    status = cli.main(
        ["collect", "--env-file", str(_env_file(tmp_path, "1001,1002"))]
    )
    output = capsys.readouterr()
    assert status == 2
    inventory = json.loads(output.out)
    VALIDATOR.validate(inventory)
    assert [item["complete"] for item in inventory["coverage"]] == [True, False]
    assert "Collection incomplete" in output.err
    assert "synthetic-password" not in output.out + output.err


def test_cli_all_roots_failed_is_json_not_empty_success(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    _install_fake_transport(monkeypatch, {})
    status = cli.main(
        ["collect", "--env-file", str(_env_file(tmp_path, "1001"))]
    )
    output = capsys.readouterr()
    assert status == 1
    inventory = json.loads(output.out)
    VALIDATOR.validate(inventory)
    assert inventory["coverage"][0]["complete"] is False
    assert inventory["coverage"][0]["empty"] is False
    assert "Collection failed" in output.err


def test_cli_fatal_configuration_error_has_no_network_or_non_json_stdout(
    monkeypatch, capsys
) -> None:
    for key in (
        "ILIAS_BASE_URL",
        "ILIAS_CLIENT_ID",
        "ILIAS_USER",
        "ILIAS_PASS",
        "ILIAS_PENDING_ROOTS",
    ):
        monkeypatch.delenv(key, raising=False)
    status = cli.main(["collect"])
    output = capsys.readouterr()
    assert status == 1
    assert output.out == ""
    assert "Configuration error" in output.err
    assert "password" not in output.err.lower()

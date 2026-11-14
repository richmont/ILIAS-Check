from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from ilias_check.auth import AuthError, Authenticator
from ilias_check.config import CollectorConfig


FIXTURES = Path(__file__).parent / "fixtures" / "login"
CONFIG = CollectorConfig.from_mapping(
    {
        "ILIAS_BASE_URL": "https://ilias.example.edu",
        "ILIAS_CLIENT_ID": "academy",
        "ILIAS_USER": "synthetic-user",
        "ILIAS_PASS": "synthetic-password",
        "ILIAS_PENDING_ROOTS": "1001",
    }
)


@dataclass
class Response:
    text: str
    url: str = "https://ilias.example.edu/login.php?client_id=academy"


class FakeTransport:
    def __init__(self, gets: list[Response], posts: list[Response] | None = None) -> None:
        self.get_responses = list(gets)
        self.post_responses = list(posts or [])
        self.get_urls: list[str] = []
        self.posts: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str) -> Response:
        self.get_urls.append(url)
        if not self.get_responses:
            raise AssertionError("Unexpected GET")
        return self.get_responses.pop(0)

    def post_login(self, url: str, data: dict[str, str]) -> Response:
        self.posts.append((url, data))
        if self.post_responses:
            return self.post_responses.pop(0)
        return Response("")


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_search_first_uses_password_form_and_relative_action() -> None:
    transport = FakeTransport(
        [
            Response(fixture("search-first.html")),
            Response(fixture("dashboard.html"), "https://ilias.example.edu/ilias.php"),
        ]
    )
    Authenticator(CONFIG, transport).login()
    assert len(transport.posts) == 1
    action, data = transport.posts[0]
    assert action == "https://ilias.example.edu/login.php?client_id=academy"
    assert data == {
        "csrf_token": "fixture-csrf",
        "username": "synthetic-user",
        "password": "synthetic-password",
    }
    assert all("search.php" not in url for url in transport.get_urls)


def test_legacy_login_form_keeps_hidden_and_submit_fields() -> None:
    transport = FakeTransport(
        [
            Response(fixture("legacy.html")),
            Response(fixture("dashboard.html"), "https://ilias.example.edu/ilias.php"),
        ]
    )
    Authenticator(CONFIG, transport).login()
    action, data = transport.posts[0]
    assert action == "https://ilias.example.edu/login.php?client_id=academy"
    assert data == {
        "auth_mode": "standard",
        "login": "synthetic-user",
        "passwd": "synthetic-password",
        "cmd[doStandardAuthentication]": "Anmelden",
    }


def test_search_only_error_page_never_receives_credentials() -> None:
    transport = FakeTransport([Response(fixture("search-only.html"))])
    with pytest.raises(AuthError, match="password login form"):
        Authenticator(CONFIG, transport).login()
    assert transport.posts == []


def test_rejected_login_is_reported_without_echoing_secrets() -> None:
    transport = FakeTransport(
        [
            Response(fixture("search-first.html")),
            Response(fixture("rejected.html"), "https://ilias.example.edu/ilias.php"),
        ]
    )
    with pytest.raises(AuthError) as error:
        Authenticator(CONFIG, transport).login()
    assert "synthetic-password" not in str(error.value)
    assert "synthetic-user" not in str(error.value)


def test_transport_diagnostic_does_not_echo_password_cookie_or_token() -> None:
    class LeakyFailureTransport:
        def get(self, url: str) -> Any:
            raise RuntimeError(
                "synthetic-password Cookie: synthetic-cookie session=synthetic-token"
            )

        def post_login(self, url: str, data: dict[str, str]) -> Any:
            raise AssertionError("login form must not be posted")

    with pytest.raises(AuthError) as error:
        Authenticator(CONFIG, LeakyFailureTransport()).login()
    message = str(error.value)
    for secret in ("synthetic-password", "synthetic-cookie", "synthetic-token"):
        assert secret not in message


def test_expired_session_reauthenticates_once_for_safe_read() -> None:
    login = Response(fixture("search-first.html"))
    dashboard = Response(fixture("dashboard.html"), "https://ilias.example.edu/ilias.php")
    expired = Response(
        '<form><input type="text" name="username"><input type="password" '
        'name="password"></form><input name="cmd[doStandardAuthentication]">',
        "https://ilias.example.edu/goto.php?target=fold_1001",
    )
    content = Response("<html><title>Repository</title></html>", "https://ilias.example.edu/goto.php?target=fold_1001")
    transport = FakeTransport(
        [login, dashboard, expired, login, dashboard, content]
    )
    response = Authenticator(CONFIG, transport).get(
        "https://ilias.example.edu/goto.php?target=fold_1001"
    )
    assert response is content
    assert len(transport.posts) == 2


def test_second_expiry_fails_after_only_one_recovery() -> None:
    login = Response(fixture("search-first.html"))
    dashboard = Response(fixture("dashboard.html"), "https://ilias.example.edu/ilias.php")
    expired = Response(
        '<form><input type="password" name="password"></form>'
        '<input name="cmd[doStandardAuthentication]">'
    )
    transport = FakeTransport([login, dashboard, expired, login, dashboard, expired])
    with pytest.raises(AuthError, match="one recovery"):
        Authenticator(CONFIG, transport).get("https://ilias.example.edu/goto.php?target=fold_1")

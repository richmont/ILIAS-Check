from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
import requests

from ilias_check.config import CollectorConfig
from ilias_check.transport import SafeTransport, TransportError


CONFIG = CollectorConfig.from_mapping(
    {
        "ILIAS_BASE_URL": "https://ilias.example.edu",
        "ILIAS_CLIENT_ID": "academy",
        "ILIAS_USER": "synthetic-user",
        "ILIAS_PASS": "synthetic-password",
        "ILIAS_PENDING_ROOTS": "1001",
        "ILIAS_TIMEOUT_SECONDS": "3.5",
        "ILIAS_PENDING_MAX_REQUESTS": "5",
    }
)


@dataclass
class Response:
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    text: str = "ok"


class FakeSession:
    def __init__(self, responses: list[Response | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> Response:
        self.calls.append((method, url, kwargs))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_safe_get_has_timeout_tls_and_redirects_disabled() -> None:
    session = FakeSession([Response()])
    transport = SafeTransport(CONFIG, session=session)
    transport.get("https://ilias.example.edu/goto.php?target=fold_1001")
    assert session.calls[0][0] == "GET"
    assert session.calls[0][2]["timeout"] == 3.5
    assert session.calls[0][2]["verify"] is True
    assert session.calls[0][2]["allow_redirects"] is False


def test_safe_get_allows_empty_default_cmd_but_not_action_values() -> None:
    session = FakeSession([Response()])
    transport = SafeTransport(CONFIG, session=session)
    transport.get(
        "https://ilias.example.edu/ilias.php?baseClass=ilRepositoryGUI&cmd="
    )
    assert len(session.calls) == 1


def test_safe_get_allows_only_force_login_command_on_login_route() -> None:
    session = FakeSession([Response()])
    transport = SafeTransport(CONFIG, session=session)
    transport.get("https://ilias.example.edu/login.php?cmd=force_login")
    assert len(session.calls) == 1

    blocked = SafeTransport(CONFIG, session=FakeSession([]))
    with pytest.raises(TransportError):
        blocked.get("https://ilias.example.edu/ilias.php?cmd=force_login")


def test_safe_get_allows_repository_info_screen_only() -> None:
    session = FakeSession([Response()])
    SafeTransport(CONFIG, session=session).get(
        "https://ilias.example.edu/ilias.php"
        "?baseClass=ilRepositoryGUI&cmd=infoScreen&ref_id=456"
    )
    assert len(session.calls) == 1


def test_safe_get_allows_only_exercise_handler_info_screen() -> None:
    session = FakeSession([Response()])
    SafeTransport(CONFIG, session=session).get(
        "https://ilias.example.edu/ilias.php"
        "?baseClass=ilExerciseHandlerGUI&ref_id=789&cmd=infoScreen"
    )
    assert len(session.calls) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://ilias.example.edu/ilias.php?baseClass=ilExerciseHandlerGUI&ref_id=789&cmd=post",
        "https://ilias.example.edu/ilias.php?baseClass=ilExerciseHandlerGUI&ref_id=789&cmd[next]=",
        "https://ilias.example.edu/ilias.php?baseClass=ilExerciseHandlerGUI&ref_id=789&cmd=infoScreen&cmdClass=ilObjExerciseGUI",
    ],
)
def test_safe_get_rejects_non_allowlisted_exercise_commands(url: str) -> None:
    session = FakeSession([])
    with pytest.raises(TransportError):
        SafeTransport(CONFIG, session=session).get(url)
    assert session.calls == []


def test_legacy_ilias_login_post_uses_narrow_allowlist() -> None:
    session = FakeSession([Response()])
    transport = SafeTransport(CONFIG, session=session)
    transport.post_login(
        "https://ilias.example.edu/ilias.php"
        "?baseClass=ilStartupGUI&cmd=post&fallbackCmd=doStandardAuthentication",
        {"login": "synthetic-user", "password": "synthetic-password"},
    )
    assert [call[0] for call in session.calls] == ["POST"]


@pytest.mark.parametrize(
    "url",
    [
        "https://ilias.example.edu/ilias.php?baseClass=ilStartupGUI&cmd=next",
        "https://ilias.example.edu/ilias.php?baseClass=ilDashboardGUI&cmd=post&fallbackCmd=doStandardAuthentication",
        "https://ilias.example.edu/ilias.php?baseClass=ilStartupGUI&cmd=post&fallbackCmd=leave",
    ],
)
def test_unsafe_ilias_login_post_actions_never_reach_transport(url: str) -> None:
    session = FakeSession([])
    transport = SafeTransport(CONFIG, session=session)
    with pytest.raises(TransportError):
        transport.post_login(url, {"login": "synthetic-user", "password": "secret"})
    assert session.calls == []


@pytest.mark.parametrize(
    "url",
    [
        "https://attacker.example/goto.php?target=fold_1001",
        "https://user:secret@ilias.example.edu/goto.php?target=fold_1001",
        "https://ilias.example.edu/goto.php?target=fold_1001&sesskey=abc",
        "https://ilias.example.edu/goto.php?target=seq_1&cmd=next",
        "https://ilias.example.edu/delete.php?ref_id=1",
        "https://ilias.example.edu/goto.php?target=fold_1001&token=secret",
        "https://ilias.example.edu/goto.php?target=fold_1001&cmd[next]=1",
        "https://ilias.example.edu/goto.php?target=fold_1001&cmd%5Bnext%5D=1",
        "https://ilias.example.edu/goto.php?target=fold_1001&save[draft]=1",
    ],
)
def test_forbidden_get_never_reaches_transport(url: str) -> None:
    session = FakeSession([])
    transport = SafeTransport(CONFIG, session=session)
    with pytest.raises(TransportError):
        transport.get(url)
    assert session.calls == []


@pytest.mark.parametrize(
    "url",
    [
        "https://attacker.example/login.php",
        "https://ilias.example.edu/delete.php",
        "https://ilias.example.edu/login.php?sesskey=secret",
    ],
)
def test_forbidden_login_post_never_reaches_transport(url: str) -> None:
    session = FakeSession([])
    transport = SafeTransport(CONFIG, session=session)
    with pytest.raises(TransportError):
        transport.post_login(url, {"username": "synthetic-user", "password": "secret"})
    assert session.calls == []


def test_off_origin_redirect_never_receives_cookies_or_credentials() -> None:
    session = FakeSession(
        [Response(status_code=302, headers={"Location": "https://attacker.example/steal"})]
    )
    transport = SafeTransport(CONFIG, session=session)
    with pytest.raises(TransportError, match="Off-origin"):
        transport.get("https://ilias.example.edu/goto.php?target=fold_1001")
    assert len(session.calls) == 1
    assert session.calls[0][1].startswith("https://ilias.example.edu/")
    assert session.calls[0][2]["allow_redirects"] is False


def test_login_post_redirect_does_not_replay_credentials() -> None:
    session = FakeSession(
        [
            Response(status_code=302, headers={"Location": "/ilias.php?baseClass=ilDashboardGUI"}),
        ]
    )
    transport = SafeTransport(CONFIG, session=session)
    transport.post_login(
        "https://ilias.example.edu/login.php?client_id=academy",
        {"username": "synthetic-user", "password": "synthetic-password"},
    )
    assert [call[0] for call in session.calls] == ["POST"]
    assert session.calls[0][2]["data"]["password"] == "synthetic-password"


def test_request_budget_counts_attempts_and_redirects() -> None:
    limited = CollectorConfig.from_mapping(
        {
            "ILIAS_BASE_URL": CONFIG.base_url,
            "ILIAS_CLIENT_ID": "academy",
            "ILIAS_USER": "u",
            "ILIAS_PASS": "p",
            "ILIAS_PENDING_ROOTS": "1",
            "ILIAS_PENDING_MAX_REQUESTS": "1",
        }
    )
    session = FakeSession(
        [
            Response(status_code=302, headers={"Location": "/ilias.php?baseClass=ilDashboardGUI"}),
            Response(),
        ]
    )
    transport = SafeTransport(limited, session=session)
    with pytest.raises(TransportError, match="budget"):
        transport.get("https://ilias.example.edu/goto.php?target=fold_1")
    assert len(session.calls) == 1
    assert transport.request_count == 1


def test_get_retries_transient_once_and_respects_retry_after_cap() -> None:
    delays: list[float] = []
    session = FakeSession(
        [
            Response(status_code=429, headers={"Retry-After": "99"}),
            Response(),
        ]
    )
    transport = SafeTransport(CONFIG, session=session, sleeper=delays.append)
    transport.get("https://ilias.example.edu/goto.php?target=fold_1001")
    assert len(session.calls) == 2
    assert transport.request_count == 2
    assert delays == [2.0]


def test_get_retries_one_request_exception_only() -> None:
    session = FakeSession([requests.Timeout(), Response()])
    transport = SafeTransport(CONFIG, session=session, sleeper=lambda _: None)
    assert transport.get("https://ilias.example.edu/goto.php?target=fold_1001").status_code == 200
    assert transport.request_count == 2


def test_transport_reports_each_attempt_to_the_progress_hook() -> None:
    seen: list[int] = []
    session = FakeSession(
        [
            Response(status_code=429, headers={"Retry-After": "1"}),
            Response(),
        ]
    )
    transport = SafeTransport(
        CONFIG, session=session, sleeper=lambda _: None, on_request=lambda: seen.append(1)
    )
    transport.get("https://ilias.example.edu/goto.php?target=fold_1001")
    assert transport.request_count == 2
    assert len(seen) == 2


def test_transport_without_progress_hook_still_counts_requests() -> None:
    transport = SafeTransport(CONFIG, session=FakeSession([Response()]))
    transport.get("https://ilias.example.edu/goto.php?target=fold_1001")
    assert transport.request_count == 1

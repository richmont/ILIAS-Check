"""Read-only ILIAS login and bounded session recovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from ilias_check._ilias_form import named_input_values, select_password_form
from ilias_check.config import CollectorConfig


class AuthError(RuntimeError):
    """Authentication failed; messages intentionally omit response/credential data."""


class AuthTransport(Protocol):
    def get(self, url: str) -> Any: ...

    def post_login(self, url: str, data: dict[str, str]) -> Any: ...


@dataclass(slots=True)
class Authenticator:
    config: CollectorConfig
    transport: AuthTransport
    _authenticated: bool = False

    @property
    def login_url(self) -> str:
        return (
            f"{self.config.base_url}/login.php?"
            f"{urlencode({'client_id': self.config.client_id})}"
        )

    @property
    def dashboard_url(self) -> str:
        return f"{self.config.base_url}/ilias.php?baseClass=ilDashboardGUI"

    def login(self) -> None:
        try:
            login_page = self.transport.get(self.login_url)
        except Exception:
            raise AuthError("Could not load the ILIAS login page.") from None

        soup = BeautifulSoup(login_page.text, "html.parser")
        form = select_password_form(soup)
        if form is None:
            raise AuthError("Supported password login form was not found.")

        form_url = getattr(login_page, "url", self.login_url) or self.login_url
        action = str(form.get("action", "")).strip()
        action_url = urljoin(form_url, action) if action else form_url
        payload = named_input_values(form)

        username_field = _credential_field(form, "text", {"username", "user", "login", "email"})
        password_field = _credential_field(form, "password", set())
        if username_field is None or password_field is None:
            raise AuthError("Supported username/password fields were not found.")
        payload[username_field] = self.config.username
        payload[password_field] = self.config.password

        # Legacy ILIAS forms require the named submit control's value.
        if form.find(attrs={"name": "cmd[doStandardAuthentication]"}) is not None:
            payload["cmd[doStandardAuthentication]"] = "Anmelden"

        try:
            self.transport.post_login(action_url, payload)
            dashboard = self.transport.get(self.dashboard_url)
        except Exception:
            raise AuthError("The ILIAS login request failed.") from None

        if self._looks_like_login_page(dashboard.text) or not self._has_logout_marker(
            dashboard.text
        ):
            raise AuthError("ILIAS did not confirm an authenticated session.")
        self._authenticated = True

    def get(self, url: str) -> Any:
        """Read a page and reauthenticate at most once when ILIAS returns login HTML."""
        if not self._authenticated:
            self.login()
        try:
            response = self.transport.get(url)
        except Exception:
            raise AuthError("The ILIAS read request failed.") from None
        if not self._looks_like_login_page(response.text):
            return response

        self._authenticated = False
        self.login()
        try:
            response = self.transport.get(url)
        except Exception:
            raise AuthError("The ILIAS read request failed after session recovery.") from None
        if self._looks_like_login_page(response.text):
            self._authenticated = False
            raise AuthError("The ILIAS session expired again after one recovery attempt.")
        return response

    @staticmethod
    def _looks_like_login_page(html: str) -> bool:
        soup = BeautifulSoup(html, "html.parser")
        has_password = soup.find("input", attrs={"type": "password"}) is not None
        has_auth_marker = "doStandardAuthentication" in html or "force_login" in html
        return has_password and has_auth_marker and not Authenticator._has_logout_marker(html)

    @staticmethod
    def _has_logout_marker(html: str) -> bool:
        soup = BeautifulSoup(html, "html.parser")
        return soup.find(
            "a", href=lambda href: href and "doLogout" in href
        ) is not None


def _credential_field(form: Any, input_type: str, preferred: set[str]) -> str | None:
    candidates: list[str] = []
    for field in form.find_all("input"):
        name = field.get("name")
        if not name or str(field.get("type", "")).lower() != input_type:
            continue
        if name.lower() in preferred:
            return name
        candidates.append(name)
    return candidates[0] if candidates else None

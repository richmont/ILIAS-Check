"""Same-origin, budgeted HTTP transport for the read-only ILIAS adapter."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlsplit

import requests

from ilias_check.config import CollectorConfig


class TransportError(RuntimeError):
    """Sanitized transport or policy error."""


_READ_PATHS = {"login.php", "goto.php", "ilias.php", "repository.php"}
_LOGIN_POST_PATHS = {"login.php", "authenticate.php", "index.php"}
_ACTION_QUERY_KEYS = {
    "action",
    "cmd",
    "delete",
    "finish",
    "complete",
    "join",
    "leave",
    "logout",
    "submit",
    "save",
    "unsubscribe",
    "step",
    "next",
    "previous",
}
_SENSITIVE_QUERY_PARTS = ("token", "session", "sesskey", "csrf", "authkey", "phpsessid")
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
_REDIRECT_STATUS = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 5
_MAX_GET_ATTEMPTS = 2


@dataclass(slots=True)
class SafeTransport:
    config: CollectorConfig
    session: Any | None = None
    sleeper: Callable[[float], None] = time.sleep
    request_count: int = 0
    _base_origin: tuple[str, str, int] = field(init=False, repr=False)
    _base_path: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = requests.Session()
        self._base_origin = _origin(self.config.base_url)
        self._base_path = urlsplit(self.config.base_url).path.rstrip("/")

    def get(self, url: str) -> Any:
        self._validate_read_url(url)
        return self._request_with_retry("GET", url)

    def close(self) -> None:
        close = getattr(self.session, "close", None)
        if callable(close):
            close()

    def post_login(self, url: str, data: dict[str, str]) -> Any:
        self._validate_login_post_url(url)
        # Authentication POSTs are never retried; credentials are never sent
        # to a redirect target. The redirect chain, if any, is manually checked.
        return self._request_chain("POST", url, data=data)

    def _request_with_retry(self, method: str, url: str) -> Any:
        for attempt in range(_MAX_GET_ATTEMPTS):
            try:
                response = self._request_chain(method, url)
            except requests.RequestException:
                if attempt + 1 == _MAX_GET_ATTEMPTS:
                    raise TransportError("The ILIAS request failed after a bounded retry.") from None
                continue
            if getattr(response, "status_code", 200) not in _TRANSIENT_STATUS:
                _raise_http_error(response)
                return response
            if attempt + 1 == _MAX_GET_ATTEMPTS:
                raise TransportError("The ILIAS server returned a transient error.")
            self._respect_retry_after(response)
        raise TransportError("The ILIAS request failed.")

    def _request_chain(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, str] | None = None,
    ) -> Any:
        current_method = method
        current_url = url
        current_data = data
        for redirect_count in range(_MAX_REDIRECTS + 1):
            self._validate_origin(current_url)
            if current_method == "GET":
                self._validate_read_url(current_url)
            elif current_method == "POST":
                self._validate_login_post_url(current_url)

            response = self._send(current_method, current_url, data=current_data)
            status = getattr(response, "status_code", 200)
            if status not in _REDIRECT_STATUS:
                return response
            location = _header(response, "Location")
            if not location:
                raise TransportError("ILIAS returned a redirect without a location.")
            next_url = urljoin(current_url, location)
            self._validate_origin(next_url)
            if redirect_count == _MAX_REDIRECTS:
                raise TransportError("ILIAS exceeded the redirect limit.")
            if current_method == "POST":
                # Never replay credentials or form data after a redirect.
                current_method, current_data = "GET", None
            elif status == 303:
                current_method = "GET"
            current_url = next_url
        raise TransportError("ILIAS exceeded the redirect limit.")

    def _send(self, method: str, url: str, *, data: dict[str, str] | None) -> Any:
        if self.request_count >= self.config.max_requests:
            raise TransportError("The configured ILIAS request budget was exhausted.")
        self.request_count += 1
        try:
            return self.session.request(
                method,
                url,
                data=data,
                timeout=self.config.timeout_seconds,
                verify=True,
                allow_redirects=False,
                headers={"User-Agent": "ILIAS-Check/0.1 (read-only collector)"},
            )
        except requests.RequestException:
            raise
        except Exception:
            # Do not leak transport representations, URLs, or cookie values.
            raise TransportError("The ILIAS transport failed.") from None

    def _validate_origin(self, url: str) -> None:
        try:
            parsed = urlsplit(url)
            origin = _origin(url)
        except ValueError:
            raise TransportError("ILIAS returned an invalid URL.") from None
        if parsed.username is not None or parsed.password is not None:
            raise TransportError("Credential-bearing URLs are not allowed.")
        if origin != self._base_origin:
            raise TransportError("Off-origin ILIAS URLs are not allowed.")
        if _has_sensitive_url_material(url):
            raise TransportError("Token-bearing URLs are not allowed.")

    def _validate_read_url(self, url: str) -> None:
        self._validate_origin(url)
        parsed = urlsplit(url)
        basename = parsed.path.rsplit("/", 1)[-1].lower()
        if basename not in _READ_PATHS:
            raise TransportError("This ILIAS route is not on the read allowlist.")
        if self._base_path and not (
            parsed.path == self._base_path
            or parsed.path.startswith(self._base_path + "/")
        ):
            raise TransportError("The URL is outside the configured ILIAS installation path.")
        for key, _value in parse_qsl(parsed.query, keep_blank_values=True):
            lowered = key.lower()
            if lowered in _ACTION_QUERY_KEYS or any(
                part in lowered for part in _SENSITIVE_QUERY_PARTS
            ):
                raise TransportError("Action or session parameters are not allowed on reads.")

    def _validate_login_post_url(self, url: str) -> None:
        self._validate_origin(url)
        parsed = urlsplit(url)
        basename = parsed.path.rsplit("/", 1)[-1].lower()
        if basename not in _LOGIN_POST_PATHS:
            raise TransportError("The login form action is not on the authentication allowlist.")
        if self._base_path and not (
            parsed.path == self._base_path
            or parsed.path.startswith(self._base_path + "/")
        ):
            raise TransportError("The login action is outside the configured installation path.")
        if _has_sensitive_url_material(url):
            raise TransportError("Token-bearing login action URLs are not allowed.")

    def _respect_retry_after(self, response: Any) -> None:
        raw = _header(response, "Retry-After")
        try:
            delay = float(raw) if raw else 0.25
        except (TypeError, ValueError):
            delay = 0.25
        self.sleeper(min(max(delay, 0.0), 2.0))


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("HTTPS URL with a host required")
    try:
        port = parsed.port or 443
    except ValueError:
        raise ValueError("Invalid URL port") from None
    return "https", parsed.hostname.lower(), port


def _has_sensitive_url_material(url: str) -> bool:
    parsed = urlsplit(url)
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        normalized = re.sub(r"[^a-z0-9]", "", key.lower())
        if any(part in normalized for part in _SENSITIVE_QUERY_PARTS):
            return True
        if re.search(r"(?:^|[;])(?:PHP)?SESSID=", value, re.I):
            return True
    return bool(re.search(r"/(?:sesskey|session|token)/[^/?#]+", parsed.path, re.I))


def _header(response: Any, name: str) -> str | None:
    headers = getattr(response, "headers", {})
    for key, value in headers.items():
        if key.lower() == name.lower():
            return str(value)
    return None


def _raise_http_error(response: Any) -> None:
    status = getattr(response, "status_code", 200)
    if status >= 400:
        raise TransportError(f"ILIAS returned HTTP status {status}.")

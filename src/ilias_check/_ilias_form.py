"""Small adapted form-parsing helper from the upstream ILIAS MCP project.

Only password-form selection and named-input extraction are reused; transport,
authentication policy, redirects, and all mutation capabilities are independent.
"""

from __future__ import annotations

from typing import Any


def select_password_form(soup: Any) -> Any | None:
    """Return the first form containing a password field, never a search form."""
    return next(
        (
            candidate
            for candidate in soup.find_all("form")
            if candidate.find("input", attrs={"type": "password"}) is not None
        ),
        None,
    )


def named_input_values(form: Any) -> dict[str, str]:
    """Return named input values so hidden anti-CSRF fields survive login."""
    values: dict[str, str] = {}
    for field in form.find_all("input"):
        name = field.get("name")
        if name:
            values[name] = field.get("value", "")
    return values

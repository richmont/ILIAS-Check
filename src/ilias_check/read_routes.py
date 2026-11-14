"""Validated passive routes used by the ILIAS MCP read services."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit


def exercise_overview_url(base_url: str, client_id: str, ref_id: str) -> str:
    if not re.fullmatch(r"[1-9][0-9]*", ref_id):
        raise ValueError("Invalid exercise reference ID.")
    return f"{base_url}/ilias.php?" + urlencode({
        "baseClass": "ilrepositorygui",
        "cmdClass": "ilObjExerciseGUI",
        "cmd": "showOverview",
        "ref_id": ref_id,
        "mode": "all",
        "from_overview": "1",
        "client_id": client_id,
    })


def passive_read_route(url: str) -> bool:
    """Recognize complete route shapes, rather than allowing command words globally."""
    parsed = urlsplit(url)
    if parsed.path.rsplit("/", 1)[-1].lower() != "ilias.php":
        return False
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    values = {key.lower(): value for key, value in pairs}
    if len(values) != len(pairs):
        return False
    base_class = values.get("baseclass", "").lower()
    if base_class == "illmpresentationgui":
        # ILIAS 9 resume() only renders layout(); it is the goto landing route.
        return (
            values.get("cmd", "").lower() == "resume"
            and re.fullmatch(r"[1-9][0-9]*", values.get("ref_id", "")) is not None
            and set(values).issubset({"baseclass", "cmd", "ref_id", "client_id"})
        )
    if base_class not in {"ilrepositorygui", "ilexercisehandlergui"}:
        return False
    if not re.fullmatch(r"[1-9][0-9]*", values.get("ref_id", "")):
        return False
    allowed = {
        "baseclass", "ref_id", "client_id", "cmd", "cmdclass", "cmdnode", "cmdmode",
        "mode", "from_overview",
    }
    if values.get("mode", "all") not in {"all", "current"}:
        return False
    if values.get("from_overview", "1") != "1":
        return False
    command = values.get("cmd", "").lower()
    controller = values.get("cmdclass", "").lower()
    if controller == "ilobjexercisegui" and command == "showoverview":
        pass
    elif (controller, command) in {
        ("ilexsubmissionfilegui", "submissionscreen"),
        ("ilexsubmissionteamgui", "submissionscreenteam"),
        ("ilassignmentpresentationgui", ""),
        ("ilassignmentpresentationgui", "showoverview"),
    }:
        allowed.add("ass_id")
        if not re.fullmatch(r"[1-9][0-9]*", values.get("ass_id", "")):
            return False
    elif base_class == "ilrepositorygui" and not controller and command == "view":
        pass
    else:
        return False
    if not set(values).issubset(allowed):
        return False
    if "cmdnode" in values and not re.fullmatch(r"[A-Za-z0-9_.:-]+", values["cmdnode"]):
        return False
    if values.get("cmdmode", "").lower() not in {"", "asynch", "sync"}:
        return False
    return True

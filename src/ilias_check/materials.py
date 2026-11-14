"""Traceable support associations; this module never fetches document bodies."""

from __future__ import annotations

from hashlib import sha256
from pathlib import PurePosixPath
import re
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import Tag

from ilias_check.links import normalize_object_link
from ilias_check.parser import _clean_text, _inside_excluded_area
from ilias_check.transport import _has_sensitive_url_material, _origin


_SECTIONS = {
    "dateien": ("assignment_attachment", "support"),
    "files": ("assignment_attachment", "support"),
    "attachments": ("assignment_attachment", "support"),
    "anhänge": ("assignment_attachment", "support"),
    "arbeitsanweisung": ("instruction_link", "support"),
    "instructions": ("instruction_link", "support"),
    "musterlösung": ("assignment_attachment", "model_answer"),
    "musterlösungen": ("assignment_attachment", "model_answer"),
    "model answers": ("assignment_attachment", "model_answer"),
    "sample solution": ("assignment_attachment", "model_answer"),
    "feedback": ("assignment_attachment", "feedback"),
    "rückmeldung": ("assignment_attachment", "feedback"),
    "einreichung": ("assignment_attachment", "learner_submission"),
    "submission": ("assignment_attachment", "learner_submission"),
    "abgegebene dateien": ("assignment_attachment", "learner_submission"),
}
NEGATIVE_ROLES = {"model_answer", "feedback", "learner_submission"}
_FILE_SUFFIXES = {".pdf", ".doc", ".docx", ".odt", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp", ".txt", ".rtf"}


def extract_assignment_materials(
    scope: Tag, exercise_id: str, assignment_id: str, page_url: str,
    base_url: str, client_id: str,
) -> list[dict]:
    """Use only the unit's own sections and instruction markup, never filename similarity."""
    materials = []
    seen = set()
    for node in scope.select("a[href], button[data-action]"):
        if _inside_excluded_area(node):
            continue
        owner = node.find_parent(attrs={"data-ass-id": True})
        if owner is not None and str(owner.get("data-ass-id")) != assignment_id:
            continue
        section, association, role = _section(node, scope)
        if association is None:
            continue
        href = str(node.get("href") or node.get("data-action") or "").strip()
        reference = document_reference(
            href, _title(node), exercise_id, assignment_id, page_url, base_url,
            client_id, association, role, section,
        )
        if reference is None:
            continue
        key = reference["document_id"], association, role, section
        if key not in seen:
            materials.append(reference)
            seen.add(key)
    return materials


def document_reference(
    href: str, title: str, exercise_id: str, assignment_id: str | None,
    page_url: str, base_url: str, client_id: str, association: str,
    role: str, section: str,
) -> dict | None:
    if not href or href.startswith(("#", "javascript:", "mailto:")):
        return None
    absolute = urljoin(page_url, href)
    try:
        parsed = urlsplit(absolute)
        if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None or _has_sensitive_url_material(absolute):
            return None
        decoded_path = unquote(parsed.path)
        if "\\" in decoded_path or any(segment in {".", ".."} for segment in decoded_path.split("/")):
            return None
        query = parse_qs(parsed.query, keep_blank_values=True)
        if any(len(values) != 1 for values in query.values()):
            return None
        if client_id and query.get("client_id", [client_id]) != [client_id]:
            return None
        same_installation = _origin(absolute) == _origin(base_url) and parsed.path.startswith(urlsplit(base_url).path.rstrip("/") + "/")
    except ValueError:
        return None
    identity = None
    source_url = None
    download_url = None
    reasons = []
    command = (query.get("cmd") or [""])[0].casefold()
    controller = (query.get("cmdClass") or [""])[0].casefold()
    if controller == "ilexsubmissiongui" and command in {"downloadfile", "downloadglobalfeedbackfile"}:
        if query.get("ref_id") != [exercise_id] or query.get("ass_id") != [assignment_id]:
            return None
        if not same_installation or parsed.path.rsplit("/", 1)[-1] != "ilias.php":
            return None
        if not set(query).issubset({"baseClass", "cmdClass", "cmd", "cmdNode", "ref_id", "ass_id", "file", "mode", "from_overview", "client_id"}):
            return None
        if (query.get("baseClass") or [""])[0].casefold() not in {"ilrepositorygui", "ilexercisehandlergui"}:
            return None
        file_key = (query.get("file") or [""])[0]
        decoded_key = unquote(file_key)
        if command == "downloadfile" and (not file_key or "/" in decoded_key or "\\" in decoded_key or decoded_key in {".", ".."}):
            return None
        if any(ord(char) < 32 for char in decoded_key):
            return None
        key_hash = sha256(file_key.encode()).hexdigest()
        identity = f"assignment:{exercise_id}:{assignment_id}:{command}:{key_hash}"
        source_url = page_url
        download_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode({key: values[0] for key, values in query.items()}), ""))
        if command == "downloadglobalfeedbackfile":
            role = "model_answer"
        if not title or title.casefold() in {"download", "herunterladen"}:
            title = file_key or section
    else:
        ref = normalize_object_link(href, page_url, base_url, client_id)
        if ref is not None and ref.object_type == "document":
            identity = f"file:{ref.ref_id}"
            source_url = ref.url
            # A goto object page is a manual source, not an invented byte route.
            if same_installation and (
                re.fullmatch(r"file_[1-9][0-9]*_download", (query.get("target") or [""])[0])
                or command == "sendfile"
                or parsed.path.rstrip("/").endswith("/download")
            ):
                download_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
        elif ref is not None:
            return None
        elif association == "instruction_link" and not command:
            # Explicit instruction links may be plain URLs. Unknown routes remain
            # manual-only; no credentials are forwarded to external sources.
            if any(key.casefold().split("[", 1)[0] in {"action", "cmd", "step", "next", "previous", "lsocmd", "lsov", "lsoni", "lson", "lsop", "submit", "save", "delete", "finish", "complete", "join", "leave", "logout", "unsubscribe"} for key in query):
                return None
            stable = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(sorted((key, values[0]) for key, values in query.items())), ""))
            identity = "url:" + sha256(stable.encode()).hexdigest()
            source_url = stable if same_installation else page_url
            if same_installation and not query and PurePosixPath(parsed.path).suffix.casefold() in _FILE_SUFFIXES:
                download_url = stable
            else:
                reasons.append("download_route_unavailable" if same_installation else "off_origin_instruction_link")
        else:
            return None
    role = _negative_label(title) or role
    if role in NEGATIVE_ROLES:
        reasons.append("known_answer_material")
    elif role == "unknown":
        reasons.append("document_role_unknown")
    if not download_url:
        reasons.append("download_route_unavailable")
    return {
        "document_id": identity, "title": title or "ILIAS document",
        "association": association, "role": role, "source_url": source_url,
        "download_url": download_url,
        "source_location": {
            "page_url": page_url, "section": section,
            "exercise_id": exercise_id, "assignment_id": assignment_id,
            "container_id": None, "path": [],
        },
        "state": "metadata_only" if download_url else "unavailable",
        "reason_codes": list(dict.fromkeys(reasons)), "selected_for_support": False,
    }


def sequence_materials(obj: dict) -> list[dict]:
    """Visible filenames are metadata only; neither object IDs nor file URLs are guessed."""
    result = []
    for index, entry in enumerate(obj.get("sequence_outline", [])):
        title = entry["title"]
        if PurePosixPath(title).suffix.casefold() not in _FILE_SUFFIXES:
            continue
        result.append({
            "document_id": None, "title": title, "association": "contextual",
            "role": _negative_label(title) or "unknown",
            "source_url": obj["url"], "download_url": None,
            "source_location": {
                "page_url": obj["url"], "section": f"sequence_outline:{index}",
                "exercise_id": obj["id"], "assignment_id": None,
                "container_id": obj["id"], "path": [],
            },
            "state": "unavailable", "reason_codes": ["sequence_document_identity_unresolved"],
            "selected_for_support": False,
        })
    return result


def contextual_materials(obj: dict, assignment_id: str | None, objects: list[dict], base_url: str, client_id: str) -> list[dict]:
    result = []
    seen = set()
    parent_paths = {(path["root_id"], tuple(path["path"][:-1])) for path in obj["paths"] if path["path"]}
    for folder in objects:
        if folder["type"] != "folder":
            continue
        for path in folder["paths"]:
            if (path["root_id"], tuple(path["path"])) not in parent_paths:
                continue
            for document in folder["documents"]:
                reference = document_reference(
                    document["url"], document["title"], obj["id"], assignment_id,
                    folder["url"], base_url, client_id, "contextual", "unknown", "repository_folder",
                )
                if reference is None or reference["document_id"] in seen:
                    continue
                reference["source_location"].update(container_id=folder["id"], path=list(path["path"]))
                result.append(reference)
                seen.add(reference["document_id"])
    return result


def select_materials(materials: list[dict], status: str, include_contextual: bool, negative_ids: set[str]) -> list[dict]:
    result = []
    for material in materials:
        reasons = list(material["reason_codes"])
        if material["document_id"] in negative_ids:
            reasons.append("known_answer_material")
        if status != "pending":
            reasons.append("pending_not_confirmed")
        if material["association"] == "contextual" and not include_contextual:
            reasons.append("contextual_opt_in_required")
        if not material["download_url"]:
            reasons.append("download_route_unavailable")
        eligible = (
            status == "pending" and material["role"] == "support"
            and material["document_id"] not in negative_ids and bool(material["download_url"])
            and (material["association"] != "contextual" or include_contextual)
        )
        result.append({**material, "reason_codes": list(dict.fromkeys(reasons)), "selected_for_support": eligible})
    return result


def _section(node: Tag, scope: Tag) -> tuple[str, str | None, str]:
    candidate = None
    instruction_hint = None
    for ancestor in node.parents:
        if not isinstance(ancestor, Tag):
            continue
        if ancestor.css.match('.panel-sub, [data-material-section]'):
            heading = ancestor.select_one(".ilBlockHeader, .panel-title")
            label = str(ancestor.get("data-material-section") or (heading.get_text(" ", strip=True) if heading else ""))
            normalized = _clean_text(label).casefold()
            if normalized in _SECTIONS:
                association, role = _SECTIONS[normalized]
                if role in NEGATIVE_ROLES:
                    return label, association, role
                candidate = candidate or (label, association, role)
            elif _negative_label(label):
                return label, "assignment_attachment", _negative_label(label)
            else:
                candidate = candidate or (label, "assignment_attachment", "unknown")
        if ancestor.css.match('[data-ilias-instructions], .ilc_text_block, .ilc_text_block_Standard, .ilText'):
            # Keep looking for a containing negative section before declaring support.
            instruction_hint = instruction_hint or ("instructions", "instruction_link", "support")
        if ancestor is scope:
            break
    return candidate or instruction_hint or ("", None, "unknown")


def merge_materials(*groups: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for group in groups:
        for reference in group:
            key = (
                reference["document_id"], reference["association"], reference["role"],
                reference["source_location"]["page_url"], reference["source_location"]["section"],
            )
            if key not in seen:
                result.append(reference)
                seen.add(key)
    return result


def _title(node: Tag) -> str:
    value = _clean_text(node.get_text(" ", strip=True)) or str(node.get("title") or node.get("aria-label") or "")
    if not value or value.casefold() in {"download", "herunterladen"}:
        row = node.find_parent(class_="row")
        label = row.select_one(".control-label") if row else None
        if label:
            value = _clean_text(label.get_text(" ", strip=True)) or value
    return value


def _negative_label(title: str) -> str | None:
    if re.search(r"\b(?:Musterlösung(?:en)?|Lösung(?:en)?|sample solution|model answer|answer key|Lösungsvorschlag)\b", title, re.IGNORECASE):
        return "model_answer"
    if re.search(r"\b(?:Feedback|Rückmeldung)\b", title, re.IGNORECASE):
        return "feedback"
    if re.search(r"\b(?:learner submission|submitted answer|abgegebene Dateien)\b", title, re.IGNORECASE):
        return "learner_submission"
    return None

"""Read-only exercise metadata, compatible with the MCP's ILIAS layouts.

Deadline/status and submission/team table extraction adapt the upstream MIT
helpers recorded in THIRD_PARTY_NOTICES.md. No answer bodies are retrieved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from ilias_check.parser import _clean_text, _inside_excluded_area
from ilias_check.read_routes import passive_read_route
from ilias_check.transport import _has_sensitive_url_material, _origin
from ilias_check.materials import extract_assignment_materials, merge_materials


_DATE = (
    r"(?:\d{1,2}\.\s*[^\W\d_]{3,10}\.?\s+\d{4}(?:,\s*\d{1,2}:\d{2})?"
    r"|\d{2}\.\d{2}\.\d{4}(?:\s+\d{1,2}:\d{2})?)"
)


@dataclass(slots=True)
class ExerciseAssignment:
    ass_id: str
    title: str
    deadline: str = ""
    status: str = ""
    instructions: str | None = None
    requirement: str | None = None
    delivery_type: str = "unknown"
    availability: str = "unknown"
    submission_source: str | None = None
    submission_scope: str = "unknown"
    learner_team_confirmed: bool | None = None
    applicability: str = "unknown"
    contradictory: bool = False
    presentation_url: str | None = None
    submission_url: str | None = None
    team_url: str | None = None
    submitted_files: list[dict[str, str]] | None = None
    team_members: list[dict[str, str]] | None = None
    warnings: list[str] = field(default_factory=list)
    support_documents: list[dict] = field(default_factory=list)
    support_warnings: list[str] = field(default_factory=list)
    support_detail_complete: bool = False


def extract_deadline(text: str) -> str:
    if re.search(r"\b(?:Keine Abgabefrist|No deadline)\b", text, re.IGNORECASE):
        return ""
    labelled = re.search(
        rf"(?:Beendet am|Abgabetermin|Abgabe bis|Frist)\D{{0,20}}?({_DATE})", text
    )
    first = labelled or (None if "Datum der letzten Abgabe" in text else re.search(_DATE, text))
    return (first.group(1) if labelled else first.group(0)).strip() if first else ""


def extract_status(text: str) -> str:
    lowered = text.lower()
    for needle in (
        "nicht abgegeben", "bereits abgegeben", "abgegeben", "submitted",
        "nicht bewertet", "bewertet",
    ):
        if needle in lowered:
            return needle
    return ""


def _safe_screen_url(href: str, page_url: str, base_url: str, ref_id: str, ass_id: str) -> str | None:
    url = urljoin(page_url, href)
    try:
        parsed = urlsplit(url)
        base = urlsplit(base_url)
        if _origin(url) != _origin(base_url) or parsed.username or parsed.password:
            return None
        if not parsed.path.startswith(base.path.rstrip("/") + "/"):
            return None
        if _has_sensitive_url_material(url) or not passive_read_route(url):
            return None
    except ValueError:
        return None
    query = parse_qs(parsed.query)
    if query.get("ref_id") != [ref_id] or query.get("ass_id") != [ass_id]:
        return None
    return url


def parse_exercise_assignments(html: str, ref_id: str, page_url: str, base_url: str, client_id: str = "") -> list[ExerciseAssignment]:
    soup = BeautifulSoup(html, "html.parser")
    assignments: dict[str, ExerciseAssignment] = {}
    # The overview has one presentation link per unit. Keep units independent;
    # buttons elsewhere in a row may point at another assignment or an action.
    for anchor in soup.select("a[href], button[data-action]"):
        if _inside_excluded_area(anchor):
            continue
        href = str(anchor.get("href") or anchor.get("data-action") or "")
        try:
            absolute = urljoin(page_url, href)
            parsed = urlsplit(absolute)
            if (
                _origin(absolute) != _origin(base_url)
                or parsed.username or parsed.password
                or _has_sensitive_url_material(absolute)
                or not parsed.path.startswith(urlsplit(base_url).path.rstrip("/") + "/")
            ):
                continue
        except ValueError:
            continue
        query = parse_qs(urlsplit(href).query)
        ass_id = (query.get("ass_id") or [""])[0]
        if not re.fullmatch(r"[1-9][0-9]*", ass_id) or len(query.get("ass_id", [])) != 1:
            continue
        if query.get("ref_id", [ref_id]) != [ref_id]:
            continue
        if "AssignmentPresentationGUI" not in href and "showOverview" not in href:
            continue
        if ass_id in assignments:
            continue
        row = anchor.find_parent(["tr", "li"])
        if row is None:
            row = next((parent for parent in anchor.parents if getattr(parent, "css", None)
                        and parent.css.match("[data-ass-id], .ilAssignment, .il_VAccordionInnerContainer, .il-std-item")), None)
        if row is None:
            row = anchor.find_parent("div")
        text = _clean_text(row.get_text(" ", strip=True)) if row else ""
        instruction_nodes = row.select("[data-ilias-instructions], .ilc_text_block, .ilc_text_block_Standard, .ilText") if row else []
        instructions = "\n".join(dict.fromkeys(
            _clean_text(node.get_text(" ", strip=True)) for node in instruction_nodes
            if not _inside_excluded_area(node)
        )) or None
        requirement = re.search(
            r"Anforderung\s+(.+?)(?=\s+(?:Datum der letzten Abgabe|Type|Typ|Status|Abgabetermin|Beendet am)\b|$)", text
        )
        delivery = "unknown"
        if re.search(r"\b(?:Type|Typ)\s+(?:Datei|File)\b", text, re.IGNORECASE):
            delivery = "file_upload"
        elif re.search(r"\b(?:Type|Typ)\s+Text\b", text, re.IGNORECASE):
            delivery = "text"
        scope = "unknown"
        type_value = ""
        if row:
            for label in row.select(".il-item-property-name"):
                if _clean_text(label.get_text(" ", strip=True)).casefold() in {"type", "typ"}:
                    value = label.find_next_sibling(class_="il-item-property-value")
                    type_value = _clean_text(value.get_text(" ", strip=True)) if value else ""
                    break
        if type_value.casefold() in {"datei", "file", "file upload"}:
            scope = "personal"
        elif type_value.casefold() in {"datei als team", "datei als team einreichen", "team upload", "team file upload"}:
            scope = "team"
        elif re.search(r"\b(?:Type|Typ)\s+(?:Datei|File)\s*(?=Status\b|Anforderung\b|$)", text, re.IGNORECASE):
            scope = "personal"
        assignments[ass_id] = ExerciseAssignment(
            ass_id=ass_id,
            title=_clean_text(anchor.get_text(" ", strip=True)),
            deadline=extract_deadline(text),
            status=extract_status(text),
            instructions=instructions,
            requirement=requirement.group(1).strip() if requirement else None,
            delivery_type=delivery,
            submission_scope=scope,
            availability="closed" if re.search(r"\bBeendet am\b", text) else "unknown",
            presentation_url=_safe_screen_url(href, page_url, base_url, ref_id, ass_id),
            support_documents=extract_assignment_materials(row, ref_id, ass_id, page_url, base_url, client_id) if row else [],
        )
    # Retain dynamic cmdNode from the exact matching link. Never substitute an
    # assignment ID into a different unit's route.
    for node in soup.select("a[href], button[data-action]"):
        if _inside_excluded_area(node):
            continue
        href = str(node.get("href") or node.get("data-action") or "")
        query = parse_qs(urlsplit(href).query)
        ass_id = (query.get("ass_id") or [""])[0]
        assignment = assignments.get(ass_id)
        if assignment is None:
            continue
        url = _safe_screen_url(href, page_url, base_url, ref_id, ass_id)
        if url is None:
            continue
        controller = (query.get("cmdClass") or [""])[0].lower()
        if controller == "ilexsubmissionfilegui":
            assignment.submission_url = url
            assignment.delivery_type = "file_upload"
        elif controller == "ilexsubmissionteamgui":
            assignment.team_url = url
            assignment.submission_scope = "team"
    return list(assignments.values())


def read_assignment_detail(
    assignment: ExerciseAssignment, html: str, ref_id: str, page_url: str, base_url: str,
    client_id: str = "",
) -> bool:
    """Enrich one unit from its own source detail page, without inferring ownership.

    A blank primary panel is not evidence of an empty delivery list. In ILIAS it
    can also represent a unit whose details are unavailable to this learner.
    """
    soup = BeautifulSoup(html, "html.parser")
    panel = soup.select_one(".panel-primary")
    if panel is None or _inside_excluded_area(panel):
        return False
    assignment.support_documents = merge_materials(
        assignment.support_documents,
        extract_assignment_materials(panel, ref_id, assignment.ass_id, page_url, base_url, client_id),
    )
    assignment.support_detail_complete = bool(panel.select(".panel-sub"))
    recognized = False
    for subpanel in panel.select(".panel-sub"):
        heading = subpanel.select_one(".ilBlockHeader, .panel-title")
        body = subpanel.select_one(".panel-body")
        if heading is None or body is None:
            continue
        label = _clean_text(heading.get_text(" ", strip=True)).casefold()
        if label in {"arbeitsanweisung", "instructions"}:
            assignment.instructions = _clean_text(body.get_text(" ", strip=True)) or None
            recognized = True
        elif label in {"einreichung", "submission"}:
            recognized = True
            text = _clean_text(body.get_text(" ", strip=True))
            if re.search(r"\bSie haben noch keine Datei abgegeben[.!]?", text):
                assignment.submitted_files = []
                assignment.submission_source = "assignment_detail_explicit_empty"
        elif label in {"dateien", "files", "attachments", "anhänge", "musterlösung", "feedback", "rückmeldung"}:
            recognized = True
    text = _clean_text(panel.get_text(" ", strip=True))
    if re.search(r"\bBeendet am\s*:", text):
        assignment.availability = "closed"
    for node in panel.select("a[href], button[data-action]"):
        href = str(node.get("href") or node.get("data-action") or "")
        url = _safe_screen_url(href, page_url, base_url, ref_id, assignment.ass_id)
        if url is None:
            continue
        query = parse_qs(urlsplit(url).query)
        controller = (query.get("cmdClass") or [""])[0].casefold()
        if controller == "ilexsubmissionfilegui":
            assignment.submission_url = url
            recognized = True
        elif controller == "ilexsubmissionteamgui":
            assignment.team_url = url
            recognized = True
    return recognized


def parse_submitted_files(html: str) -> list[dict[str, str]] | None:
    """Unknown layouts return None; an explicit delivery table can be empty."""
    soup = BeautifulSoup(html, "html.parser")
    inputs = [node for node in soup.select('input[name="delivered[]"]') if not _inside_excluded_area(node)]
    recognized = bool(inputs) or soup.select_one('[data-submission-list], table[id*="delivered"], table[id*="submission"]') is not None
    if not recognized:
        # ILIAS empty-table marker inside the expected submission form.
        recognized = any(
            "ExSubmissionFileGUI" in str(form.get("action", ""))
            and any(
                re.fullmatch(
                    r"\s*(?:Keine (?:Einträge|Dateien)(?: vorhanden)?|No (?:entries|files)(?: available)?)[.!]?\s*",
                    marker.get_text(" ", strip=True), re.IGNORECASE,
                )
                for marker in form.select(".ilTableFootLight, .alert-info, .ilNoItems, td.ilCenter")
            )
            for form in soup.find_all("form")
        )
    if not recognized:
        return None
    files = []
    seen = set()
    for node in inputs:
        delivery_id = str(node.get("value", "")).strip()
        if not delivery_id or delivery_id in seen:
            continue
        seen.add(delivery_id)
        row = node.find_parent("tr")
        cells = row.find_all("td") if row else []
        texts = [cell.get_text(strip=True) for cell in cells]
        name = submitter = date = ""
        if len(texts) >= 4:
            name, submitter, date = texts[1:4]
        elif len(texts) == 3:
            name, submitter, date = texts
        files.append({"delivery_id": delivery_id, "filename": name, "submitter": submitter, "date": date})
    return files


def submission_acceptance(html: str, page_url: str, base_url: str, ref_id: str, ass_id: str) -> bool:
    """An enabled, exact upload-form control is evidence; it is never followed."""
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select("a[href], button[data-action]"):
        if _inside_excluded_area(node) or node.has_attr("disabled") or node.get("aria-disabled") == "true":
            continue
        if any("disabled" in parent.get("class", []) for parent in (node, *node.parents) if hasattr(parent, "get")):
            continue
        href = str(node.get("href") or node.get("data-action") or "")
        url = urljoin(page_url, href)
        try:
            parsed = urlsplit(url)
            if _origin(url) != _origin(base_url) or parsed.username or parsed.password or _has_sensitive_url_material(url):
                continue
            if not parsed.path.startswith(urlsplit(base_url).path.rstrip("/") + "/"):
                continue
        except ValueError:
            continue
        query = parse_qs(parsed.query)
        if (
            parsed.path.rsplit("/", 1)[-1] == "ilias.php"
            and query.get("baseClass", [""])[0].casefold() in {"ilrepositorygui", "ilexercisehandlergui"}
            and query.get("cmdClass", [""])[0].casefold() == "ilexsubmissionfilegui"
            and query.get("cmd") == ["uploadForm"]
            and query.get("ref_id") == [ref_id]
            and query.get("ass_id") == [ass_id]
            and all(len(values) == 1 for values in query.values())
            and set(query).issubset({"baseClass", "cmdClass", "cmd", "ref_id", "ass_id", "cmdNode", "cmdMode", "mode", "from_overview", "client_id"})
        ):
            return True
    return False


def parse_team_members(html: str) -> list[dict[str, str]] | None:
    soup = BeautifulSoup(html, "html.parser")
    inputs = [node for node in soup.select('input[name="id[]"]') if not _inside_excluded_area(node)]
    if not inputs and not soup.select_one("[data-team-members], table[id*='team']"):
        return None
    members = []
    seen = set()
    for node in inputs:
        user_id = str(node.get("value", "")).strip()
        if not user_id or user_id in seen:
            continue
        seen.add(user_id)
        cell = node.find_parent("td")
        name_cell = cell.find_next_sibling("td") if cell else None
        row = node.find_parent(["tr", "li", "div"])
        name = _clean_text(name_cell.get_text(" ", strip=True)) if name_cell else ""
        if not name and row:
            name = re.sub(r"\s*Entfernen\s*", "", _clean_text(row.get_text(" ", strip=True))).strip()
        members.append({"user_id": user_id, "name": name})
    return members

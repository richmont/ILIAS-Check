"""Content-scoped parsing of repository object metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from bs4 import BeautifulSoup, Tag

from ilias_check.links import (
    ObjectRef,
    normalize_object_link,
    object_ref_from_parts,
)


_CONTENT_SELECTORS = (
    "main",
    '[role="main"]',
    "#ilContentContainer",
    ".ilMainContent",
    ".ilContent",
    ".ilRepositoryList",
    ".ilContainerList",
    ".ilObjList",
    ".ilContainerListItem",
    ".il_ContainerListItem",
    ".ilObjListRow",
    "[data-ref-id]",
)
_EXCLUDED_ANCESTORS = (
    "nav",
    "aside",
    "header",
    "footer",
    ".breadcrumb",
    ".breadcrumbs",
    ".ilBreadcrumb",
    ".ilTopBar",
    ".ilMainMenu",
    '[role="navigation"]',
)
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ParsedLink:
    ref: ObjectRef
    title: str


@dataclass(slots=True)
class ParsedPage:
    title: str
    instructions: str | None = None
    links: list[ParsedLink] = field(default_factory=list)
    sequence_steps: list[ParsedLink] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sequence_resolution: str | None = None


def resolve_legacy_object_ref(
    ref: ObjectRef,
    response_url: str,
    html: str,
    base_url: str,
    client_id: str,
) -> ObjectRef | None:
    """Resolve a legacy reference only from explicit, matching passive metadata."""
    if ref.read_url is None:
        return None

    response_path = response_url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    if response_path.lower() in {"goto.php", "ilias.php", "repository.php"}:
        response_ref = normalize_object_link(
            response_url, ref.read_url, base_url, client_id
        )
        if response_ref is not None and response_ref.object_type not in {
            "unsupported",
            "unresolved",
        }:
            if response_ref.ref_id != ref.ref_id:
                return None
            return response_ref

    soup = BeautifulSoup(html, "html.parser")
    candidates: dict[str, ObjectRef] = {}
    for node in soup.select("[data-ref-id][data-object-type]"):
        if not isinstance(node, Tag) or _inside_excluded_area(node):
            continue
        candidate = object_ref_from_parts(
            base_url,
            client_id,
            str(node.get("data-object-type", "")),
            str(node.get("data-ref-id", "")),
        )
        if (
            candidate is not None
            and candidate.ref_id == ref.ref_id
            and candidate.object_type != "unsupported"
        ):
            candidates[candidate.key] = candidate
    return next(iter(candidates.values())) if len(candidates) == 1 else None


def parse_repository_page(
    html: str,
    page_url: str,
    base_url: str,
    client_id: str,
    object_type: str,
) -> ParsedPage:
    """Extract only page title and object references inside recognized content."""
    soup = BeautifulSoup(html, "html.parser")
    title = _page_title(soup)
    instructions = _page_instructions(soup)
    links: list[ParsedLink] = []
    seen: set[str] = set()
    roots: list[Tag] = []
    for selector in _CONTENT_SELECTORS:
        for node in soup.select(selector):
            if isinstance(node, Tag) and not any(node is parent for parent in roots):
                roots.append(node)

    # A recognized content root may contain nested recognized roots. De-duplicate
    # anchors by object identity while retaining source order.
    anchors: list[Tag] = []
    anchor_ids: set[int] = set()
    for root in roots:
        for anchor in root.find_all("a", href=True):
            if id(anchor) not in anchor_ids and not _inside_excluded_area(anchor):
                anchors.append(anchor)
                anchor_ids.add(id(anchor))

    for anchor in anchors:
        ref = normalize_object_link(
            str(anchor.get("href", "")), page_url, base_url, client_id
        )
        if ref is None or ref.key in seen:
            continue
        link_title = _clean_text(anchor.get_text(" ", strip=True))
        if not link_title:
            link_title = _clean_text(str(anchor.get("title", "")))
        if not link_title:
            link_title = f"ILIAS {ref.object_type} {ref.ref_id}"
        links.append(ParsedLink(ref=ref, title=link_title))
        seen.add(ref.key)

    sequence_steps: list[ParsedLink] = []
    sequence_resolution: str | None = None
    warnings: list[str] = []
    if object_type == "learning_sequence":
        for node in soup.select("[data-sequence-step][data-ref-id], [data-step-ref-id]"):
            if not isinstance(node, Tag) or _inside_excluded_area(node):
                continue
            ref_id = node.get("data-ref-id") or node.get("data-step-ref-id")
            type_code = (
                node.get("data-object-type")
                or node.get("data-type")
                or node.get("data-step-type")
            )
            ref = (
                object_ref_from_parts(base_url, client_id, str(type_code), str(ref_id))
                if type_code and ref_id
                else None
            )
            if ref is None or ref.key in seen:
                continue
            step_title = _clean_text(node.get_text(" ", strip=True))
            if not step_title:
                step_title = f"ILIAS {ref.object_type} {ref.ref_id}"
            link = ParsedLink(ref=ref, title=step_title)
            links.append(link)
            seen.add(ref.key)

        sequence_steps = [
            link for link in links if link.ref.object_type != "document"
        ]
        sequence_resolution = "resolved" if sequence_steps else "unresolved"
        if not sequence_steps:
            warnings.append("sequence_steps_not_exposed_as_passive_object_links")
    if object_type == "unsupported":
        warnings.append("unsupported_repository_object_type")
    return ParsedPage(
        title=title,
        instructions=instructions,
        links=links,
        sequence_steps=sequence_steps,
        warnings=warnings,
        sequence_resolution=sequence_resolution,
    )


def _page_title(soup: BeautifulSoup) -> str:
    for selector in (".ilMainHeader h1", ".ilHeader h1", "main h1", "h1", "title"):
        element = soup.select_one(selector)
        if element is not None:
            text = _clean_text(element.get_text(" ", strip=True))
            if text:
                return text
    return "Untitled ILIAS object"


def _page_instructions(soup: BeautifulSoup) -> str | None:
    blocks: list[str] = []
    seen: set[int] = set()
    for selector in (
        "[data-ilias-instructions]",
        ".ilc_text_block",
        ".ilc_text_block_Standard",
        ".ilText",
    ):
        for element in soup.select(selector):
            if not isinstance(element, Tag) or id(element) in seen:
                continue
            if _inside_excluded_area(element):
                continue
            text = _clean_text(element.get_text(" ", strip=True))
            if text:
                blocks.append(text)
                seen.add(id(element))
    return "\n".join(blocks) if blocks else None


def _inside_excluded_area(anchor: Tag) -> bool:
    for selector in _EXCLUDED_ANCESTORS:
        if anchor.parent and any(
            element is anchor for element in anchor.parent.select(selector)
        ):
            return True
        if anchor.find_parent(selector):
            return True
    return False


def _clean_text(value: str) -> str:
    # Whitespace normalization only; source-language text is not translated.
    return _WHITESPACE.sub(" ", value).strip()

"""Bounded, deduplicated traversal of repository object references."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from ilias_check.auth import Authenticator
from ilias_check.config import CollectorConfig
from ilias_check.exercises import (
    parse_exercise_assignments, parse_submitted_files, parse_team_members, read_assignment_detail,
    submission_acceptance,
)
from ilias_check.read_routes import exercise_overview_url
from ilias_check.links import ObjectRef, canonical_object_url
from ilias_check.parser import (
    ParsedPage,
    parse_repository_page,
    resolve_legacy_object_ref,
)


@dataclass(slots=True)
class InventoryObject:
    ref_id: str
    type_code: str
    object_type: str
    title: str
    instructions: str | None
    url: str
    url_kind: str = "activity"
    paths: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, str]] = field(default_factory=list)
    sequence_steps: list[dict[str, str]] = field(default_factory=list)
    sequence_outline: list[dict[str, str]] = field(default_factory=list)
    sequence_resolution: str | None = None
    warnings: list[str] = field(default_factory=list)
    assignments: list[dict[str, Any]] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.type_code}:{self.ref_id}"


@dataclass(slots=True)
class RootCoverage:
    root_id: str
    complete: bool = True
    objects_discovered: int = 0
    warnings: list[str] = field(default_factory=list)
    error: dict[str, str] | None = None


@dataclass(slots=True)
class TraversalResult:
    objects: dict[str, InventoryObject]
    coverage: list[RootCoverage]
    errors: list[dict[str, str]]


@dataclass(frozen=True, slots=True)
class _QueueItem:
    ref: ObjectRef
    root_id: str
    path: tuple[str, ...]
    depth: int
    ancestors: frozenset[str]


def _traversal_priority(object_type: str) -> int:
    """Explore likely activity-bearing containers before generic legacy items."""
    return {
        "exercise": 0,
        "folder": 1,
        "course": 1,
        "category": 1,
        "group": 1,
        "learning_sequence": 2,
        "unresolved": 3,
    }.get(object_type, 4)


def _promote_legacy_identity(
    legacy_key: str,
    resolved_ref: ObjectRef,
    objects: dict[str, InventoryObject],
    root_object_pairs: set[tuple[str, str]],
    coverage_by_root: dict[str, RootCoverage],
    expanded_paths: set[tuple[str, str, tuple[str, ...]]],
    parsed_pages: dict[str, ParsedPage],
    fetched: set[str],
) -> InventoryObject:
    resolved_key = resolved_ref.key
    record = objects.pop(legacy_key)
    existing = objects.get(resolved_key)
    if existing is None:
        existing = record
        objects[resolved_key] = existing
    else:
        for path in record.paths:
            if path not in existing.paths:
                existing.paths.append(path)
        for document in record.documents:
            if document not in existing.documents:
                existing.documents.append(document)
        for step in record.sequence_steps:
            if step not in existing.sequence_steps:
                existing.sequence_steps.append(step)
        for step in record.sequence_outline:
            if step not in existing.sequence_outline:
                existing.sequence_outline.append(step)
        for assignment in record.assignments:
            if assignment not in existing.assignments:
                existing.assignments.append(assignment)
        for warning in record.warnings:
            if (
                warning != "unresolved_legacy_repository_reference"
                and warning not in existing.warnings
            ):
                existing.warnings.append(warning)
        if existing.instructions is None:
            existing.instructions = record.instructions

    existing.ref_id = resolved_ref.ref_id
    existing.type_code = resolved_ref.type_code
    existing.object_type = resolved_ref.object_type
    existing.url = resolved_ref.url
    existing.url_kind = (
        "sequence_entry"
        if resolved_ref.object_type == "learning_sequence"
        else "activity"
    )
    existing.warnings = [
        warning
        for warning in existing.warnings
        if warning != "unresolved_legacy_repository_reference"
    ]

    for root_id, object_key in list(root_object_pairs):
        if object_key != legacy_key:
            continue
        root_object_pairs.remove((root_id, legacy_key))
        resolved_pair = (root_id, resolved_key)
        if resolved_pair in root_object_pairs:
            coverage_by_root[root_id].objects_discovered = max(
                0, coverage_by_root[root_id].objects_discovered - 1
            )
        else:
            root_object_pairs.add(resolved_pair)

    for root_id, object_key, path in list(expanded_paths):
        if object_key != legacy_key:
            continue
        expanded_paths.remove((root_id, legacy_key, path))
        expanded_paths.add((root_id, resolved_key, path))

    legacy_page = parsed_pages.pop(legacy_key, None)
    if legacy_page is not None and resolved_key not in parsed_pages:
        parsed_pages[resolved_key] = legacy_page
    if legacy_key in fetched:
        fetched.add(resolved_key)
    return existing


class RepositoryCrawler:
    def __init__(self, config: CollectorConfig, authenticator: Authenticator) -> None:
        self.config = config
        self.authenticator = authenticator

    def collect(self) -> TraversalResult:
        objects: dict[str, InventoryObject] = {}
        coverage = [RootCoverage(root_id=root_id) for root_id in self.config.roots]
        coverage_by_root = {item.root_id: item for item in coverage}
        errors: list[dict[str, str]] = []
        queue: deque[_QueueItem] = deque()
        for root_id in self.config.roots:
            root = ObjectRef(
                ref_id=root_id,
                type_code="fold",
                object_type="folder",
                url=canonical_object_url(
                    self.config.base_url, self.config.client_id, "fold", root_id
                ),
            )
            queue.append(_QueueItem(root, root_id, (), 0, frozenset()))

        fetched: set[str] = set()
        failed_objects: dict[str, dict[str, str]] = {}
        parsed_pages: dict[str, ParsedPage] = {}
        expanded_paths: set[tuple[str, str, tuple[str, ...]]] = set()
        root_object_pairs: set[tuple[str, str]] = set()
        resolved_aliases: dict[str, ObjectRef] = {}
        while queue:
            item = queue.popleft()
            ref = resolved_aliases.get(item.ref.key, item.ref)
            if item.ref.key != ref.key and item.ref.key in objects:
                _promote_legacy_identity(
                    item.ref.key, ref, objects, root_object_pairs, coverage_by_root,
                    expanded_paths, parsed_pages, fetched,
                )
            if ref.object_type == "unresolved":
                typed_matches = [
                    candidate
                    for candidate in objects.values()
                    if candidate.ref_id == ref.ref_id
                    and candidate.type_code != "obj"
                    and candidate.object_type not in {"unresolved", "unsupported"}
                ]
                if len(typed_matches) == 1:
                    candidate = typed_matches[0]
                    resolved_ref = ObjectRef(
                        ref_id=candidate.ref_id,
                        type_code=candidate.type_code,
                        object_type=candidate.object_type,
                        url=candidate.url,
                    )
                    legacy_key = ref.key
                    _promote_legacy_identity(
                        legacy_key,
                        resolved_ref,
                        objects,
                        root_object_pairs,
                        coverage_by_root,
                        expanded_paths,
                        parsed_pages,
                        fetched,
                    )
                    resolved_aliases[legacy_key] = resolved_ref
                    ref = resolved_ref
            key = ref.key
            ancestors = frozenset(
                resolved_aliases[ancestor].key
                if ancestor in resolved_aliases
                else ancestor
                for ancestor in item.ancestors
            )
            record = objects.get(key)
            if record is None:
                record = InventoryObject(
                    ref_id=ref.ref_id,
                    type_code=ref.type_code,
                    object_type=ref.object_type,
                    title=f"ILIAS {ref.object_type} {ref.ref_id}",
                    instructions=None,
                    url=ref.read_url or ref.url,
                    url_kind=(
                        "sequence_entry"
                        if ref.object_type == "learning_sequence"
                        else "activity"
                    ),
                )
                objects[key] = record

            path_record = {"root_id": item.root_id, "path": list(item.path)}
            if path_record not in record.paths:
                record.paths.append(path_record)
            root_pair = (item.root_id, key)
            if root_pair not in root_object_pairs:
                root_object_pairs.add(root_pair)
                coverage_by_root[item.root_id].objects_discovered += 1

            if ref.object_type == "document":
                continue
            if ref.object_type == "unsupported":
                coverage_by_root[item.root_id].complete = False
                coverage_by_root[item.root_id].warnings.append(
                    "unsupported_repository_object_type"
                )
                record.warnings.append("unsupported_repository_object_type")
                continue

            previous_failure = failed_objects.get(key)
            if previous_failure is not None:
                coverage_by_root[item.root_id].complete = False
                coverage_by_root[item.root_id].warnings.append(
                    "object_read_failed_or_unsupported"
                )
                error = {
                    "category": "object_read_failed",
                    "root_id": item.root_id,
                    "object_id": ref.ref_id,
                    "message": "The object could not be read or parsed.",
                }
                if error not in errors:
                    errors.append(error)
                continue

            if key not in fetched:
                fetched.add(key)
                try:
                    response = self.authenticator.get(ref.read_url or ref.url)
                    response_url = (
                        getattr(response, "url", None) or ref.read_url or ref.url
                    )
                    if ref.object_type == "unresolved":
                        resolved_ref = resolve_legacy_object_ref(
                            ref,
                            response_url,
                            response.text,
                            self.config.base_url,
                            self.config.client_id,
                        )
                        if resolved_ref is None:
                            coverage_by_root[item.root_id].complete = False
                            if (
                                "unresolved_legacy_repository_reference"
                                not in coverage_by_root[item.root_id].warnings
                            ):
                                coverage_by_root[item.root_id].warnings.append(
                                    "unresolved_legacy_repository_reference"
                                )
                            if (
                                "unresolved_legacy_repository_reference"
                                not in record.warnings
                            ):
                                record.warnings.append(
                                    "unresolved_legacy_repository_reference"
                                )
                        else:
                            legacy_key = key
                            record = _promote_legacy_identity(
                                legacy_key,
                                resolved_ref,
                                objects,
                                root_object_pairs,
                                coverage_by_root,
                                expanded_paths,
                                parsed_pages,
                                fetched,
                            )
                            resolved_aliases[legacy_key] = resolved_ref
                            ref = resolved_ref
                            key = ref.key
                    page = parse_repository_page(
                        response.text,
                        response_url,
                        self.config.base_url,
                        self.config.client_id,
                        ref.object_type,
                    )
                    parsed_pages[key] = page
                    record.title = page.title
                    record.instructions = page.instructions
                    record.sequence_resolution = page.sequence_resolution
                    record.sequence_outline = page.sequence_outline
                    record.warnings.extend(page.warnings)
                    if ref.object_type == "exercise":
                        self._read_assignments(record, page)
                    record.sequence_steps = [
                        {
                            "ref_id": step.ref.ref_id,
                            "type": step.ref.object_type,
                            "title": step.title,
                            "url": step.ref.url,
                            "url_kind": (
                                "sequence_entry"
                                if step.ref.object_type == "learning_sequence"
                                else "activity"
                            ),
                        }
                        for step in page.sequence_steps
                    ]
                    if page.sequence_resolution == "unresolved":
                        coverage_by_root[item.root_id].complete = False
                        coverage_by_root[item.root_id].warnings.append(
                            "unresolved_learning_sequence"
                        )
                    for child in page.links:
                        if child.ref.object_type == "document":
                            metadata = {
                                "ref_id": child.ref.ref_id,
                                "title": child.title,
                                "url": child.ref.url,
                            }
                            if metadata not in record.documents:
                                record.documents.append(metadata)
                except Exception:
                    failed_objects[key] = {
                        "category": "object_read_failed",
                        "object_id": ref.ref_id,
                    }
                    coverage_by_root[item.root_id].complete = False
                    coverage_by_root[item.root_id].warnings.append(
                        "object_read_failed_or_unsupported"
                    )
                    if ref.object_type == "unresolved":
                        if (
                            "unresolved_legacy_repository_reference"
                            not in coverage_by_root[item.root_id].warnings
                        ):
                            coverage_by_root[item.root_id].warnings.append(
                                "unresolved_legacy_repository_reference"
                            )
                        if (
                            "unresolved_legacy_repository_reference"
                            not in record.warnings
                        ):
                            record.warnings.append(
                                "unresolved_legacy_repository_reference"
                            )
                    error = {
                        "category": "object_read_failed",
                        "root_id": item.root_id,
                        "object_id": ref.ref_id,
                        "message": "The object could not be read or parsed.",
                    }
                    if item.depth == 0:
                        coverage_by_root[item.root_id].error = {
                            "category": "root_read_failed",
                            "object_id": ref.ref_id,
                        }
                    if error not in errors:
                        errors.append(error)
                    continue

            page = parsed_pages.get(key)
            if any(warning.startswith("exercise_") for warning in record.warnings):
                coverage_by_root[item.root_id].complete = False
                coverage_by_root[item.root_id].warnings.extend(
                    warning for warning in record.warnings
                    if warning.startswith("exercise_")
                    and warning not in coverage_by_root[item.root_id].warnings
                )
            if page is None:
                continue
            expansion_key = (item.root_id, key, item.path)
            if expansion_key in expanded_paths:
                continue
            expanded_paths.add(expansion_key)

            if item.depth >= self.config.max_depth and page.links:
                coverage_by_root[item.root_id].complete = False
                coverage_by_root[item.root_id].warnings.append("maximum_depth_reached")
                continue
            prioritized_links = sorted(
                page.links,
                key=lambda link: _traversal_priority(link.ref.object_type),
            )
            for link in reversed(prioritized_links):
                link = replace(link, ref=resolved_aliases.get(link.ref.key, link.ref))
                child_key = link.ref.key
                if child_key in ancestors or child_key == key:
                    warning = "cycle_detected"
                    if warning not in coverage_by_root[item.root_id].warnings:
                        coverage_by_root[item.root_id].warnings.append(warning)
                    continue
                child_path = item.path + (link.title,)
                child = objects.get(child_key)
                if child is None:
                    child = InventoryObject(
                        ref_id=link.ref.ref_id,
                        type_code=link.ref.type_code,
                        object_type=link.ref.object_type,
                        title=link.title,
                        instructions=None,
                        url=link.ref.url,
                        url_kind=(
                            "sequence_entry"
                            if link.ref.object_type == "learning_sequence"
                            else "activity"
                        ),
                    )
                    objects[child_key] = child
                child_path = item.path + (link.title,)
                path_record = {"root_id": item.root_id, "path": list(child_path)}
                if path_record not in child.paths:
                    child.paths.append(path_record)
                child_root_pair = (item.root_id, child_key)
                if child_root_pair not in root_object_pairs:
                    root_object_pairs.add(child_root_pair)
                    coverage_by_root[item.root_id].objects_discovered += 1
                if link.ref.object_type == "document":
                    metadata = {
                        "ref_id": link.ref.ref_id,
                        "title": link.title,
                        "url": link.ref.url,
                    }
                    if metadata not in record.documents:
                        record.documents.append(metadata)
                    continue
                if link.ref.object_type == "unsupported":
                    coverage_by_root[item.root_id].complete = False
                    coverage_by_root[item.root_id].warnings.append(
                        "unsupported_repository_object_type"
                    )
                    child.warnings.append("unsupported_repository_object_type")
                    continue
                if link.ref.object_type == "unresolved":
                    child.url = link.ref.read_url or link.ref.url
                queue.appendleft(
                    _QueueItem(
                        ref=link.ref,
                        root_id=item.root_id,
                        path=child_path,
                        depth=item.depth + 1,
                        ancestors=ancestors | {key},
                    )
                )

        return TraversalResult(objects=objects, coverage=coverage, errors=errors)

    def _read_assignments(self, record: InventoryObject, repository_page: ParsedPage) -> None:
        """Use the MCP all-unit overview and only its exact passive screen links."""
        url = exercise_overview_url(self.config.base_url, self.config.client_id, record.ref_id)
        try:
            response = self.authenticator.get(url)
            response_url = getattr(response, "url", None) or url
            overview_page = parse_repository_page(
                response.text, response_url, self.config.base_url,
                self.config.client_id, "exercise",
            )
            assignments = parse_exercise_assignments(
                response.text, record.ref_id, response_url,
                self.config.base_url, self.config.client_id,
            )
        except Exception:
            record.warnings.append("exercise_overview_read_failed")
            return
        known_links = {link.ref.key for link in repository_page.links}
        for link in overview_page.links:
            if link.ref.key not in known_links:
                repository_page.links.append(link)
                known_links.add(link.ref.key)
        if overview_page.instructions:
            record.instructions = "\n".join(dict.fromkeys(
                text for text in (record.instructions, overview_page.instructions) if text
            ))
        if not assignments:
            record.warnings.append("exercise_assignment_units_unresolved")
        for assignment in assignments:
            needs_delivery_detail = assignment.delivery_type == "file_upload" and assignment.submission_url is None
            if assignment.presentation_url is not None:
                try:
                    detail = self.authenticator.get(assignment.presentation_url)
                    recognized = read_assignment_detail(
                        assignment, detail.text, record.ref_id,
                        getattr(detail, "url", None) or assignment.presentation_url,
                        self.config.base_url, self.config.client_id,
                    )
                    if not recognized:
                        assignment.support_warnings.append("support_detail_unavailable")
                        if needs_delivery_detail:
                            assignment.warnings.append("assignment_detail_unavailable")
                except Exception:
                    assignment.support_warnings.append("support_detail_read_failed")
                    if needs_delivery_detail:
                        assignment.warnings.append("assignment_detail_read_failed")
            else:
                assignment.support_warnings.append("support_presentation_link_unavailable")
            for link, parser, attribute in (
                (assignment.submission_url, parse_submitted_files, "submitted_files"),
                (assignment.team_url, parse_team_members, "team_members"),
            ):
                if link is None:
                    continue
                try:
                    page = self.authenticator.get(link)
                    metadata = parser(page.text)
                    setattr(assignment, attribute, metadata)
                    if attribute == "submitted_files" and metadata is not None:
                        assignment.submission_source = "submission_screen"
                        if submission_acceptance(
                            page.text, getattr(page, "url", None) or link,
                            self.config.base_url, record.ref_id, assignment.ass_id,
                        ):
                            assignment.availability = "accepting_submissions"
                    if attribute == "team_members" and metadata is not None:
                        assignment.learner_team_confirmed = bool(metadata)
                    if metadata is None:
                        assignment.warnings.append(f"{attribute}_unrecognized")
                except Exception:
                    assignment.warnings.append(f"{attribute}_read_failed")
            if (
                assignment.delivery_type == "file_upload"
                and assignment.submission_url is None
                and assignment.submitted_files is None
                and not assignment.warnings
            ):
                assignment.warnings.append("submission_screen_not_exposed")
            if assignment.warnings:
                record.warnings.append("exercise_assignment_metadata_partial")
            record.assignments.append(asdict(assignment))

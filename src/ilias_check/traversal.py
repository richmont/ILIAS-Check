"""Bounded, deduplicated traversal of repository object references."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ilias_check.auth import Authenticator
from ilias_check.config import CollectorConfig
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
    sequence_resolution: str | None = None
    warnings: list[str] = field(default_factory=list)

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
                    record.warnings.extend(page.warnings)
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
            for link in page.links:
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
                queue.append(
                    _QueueItem(
                        ref=link.ref,
                        root_id=item.root_id,
                        path=child_path,
                        depth=item.depth + 1,
                        ancestors=ancestors | {key},
                    )
                )

        return TraversalResult(objects=objects, coverage=coverage, errors=errors)

"""Adapt collected metadata into classified, consultable activity results."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, replace
from datetime import datetime
import json
from typing import Any

from ilias_check.activities import (
    ActivityLinkKind, ActivityStatus, Applicability, AssignmentObservation,
    Availability, DeliveryType, SubmissionHistory, SubmissionScope,
)
from ilias_check.classification import SubmissionEvidence, classify_assignment
from ilias_check.deadlines import normalize_deadline
from ilias_check.policy import ClassificationPolicy
from ilias_check.materials import (
    NEGATIVE_ROLES, contextual_materials, merge_materials, select_materials, sequence_materials,
)


SELECTIONS = {
    "all": None,
    "pending": ActivityStatus.PENDING,
    "submitted": ActivityStatus.SUBMITTED,
    "closed-without-submission": ActivityStatus.CLOSED_WITHOUT_SUBMISSION,
    "needs-verification": ActivityStatus.UNKNOWN,
    "not-yet-open": ActivityStatus.NOT_YET_OPEN,
    "excluded": ActivityStatus.EXCLUDED,
}


def classify_inventory(
    inventory: dict[str, Any], policy: ClassificationPolicy = ClassificationPolicy(),
) -> dict[str, Any]:
    """Classify the stored observation time; this function never refreshes ILIAS."""
    if inventory.get("schema_version") != "1.0":
        raise ValueError("Unsupported inventory version.")
    checked_at = datetime.fromisoformat(inventory["checked_at"].replace("Z", "+00:00"))
    if checked_at.tzinfo is None:
        raise ValueError("Inventory observation time must include a timezone.")
    groups: dict[tuple[str, str | None], tuple[dict, dict, list]] = {}
    unresolved_sequences = []
    for obj in inventory["objects"]:
        if obj["type"] == "learning_sequence" and obj["sequence_resolution"] != "resolved":
            unresolved_sequences.append(obj)
        if obj["type"] != "exercise":
            continue
        for unit in obj.get("assignments") or [{"ass_id": None, "title": obj["title"]}]:
            key = obj["id"], unit["ass_id"]
            paths = [list(path["path"]) for path in obj["paths"]]
            if key not in groups:
                groups[key] = obj, dict(unit), []
            _, prior, all_paths = groups[key]
            support_fields = {"support_documents", "support_warnings", "support_detail_complete"}
            if {key: value for key, value in prior.items() if key not in support_fields} != {key: value for key, value in unit.items() if key not in support_fields}:
                prior["contradictory"] = True
            prior["support_documents"] = merge_materials(prior.get("support_documents", []), unit.get("support_documents", []))
            prior["support_warnings"] = list(dict.fromkeys(prior.get("support_warnings", []) + unit.get("support_warnings", [])))
            prior["support_detail_complete"] = prior.get("support_detail_complete", False) or unit.get("support_detail_complete", False)
            for path in paths:
                if path not in all_paths:
                    all_paths.append(path)
    activities = []
    for obj, unit, paths in groups.values():
        activity = _classify_unit(obj, unit, paths, policy, checked_at)
        documents = unit.get("support_documents", [])
        if policy.include_contextual:
            documents = merge_materials(documents, contextual_materials(
                obj, unit["ass_id"], inventory["objects"],
                inventory["scope"]["base_url"], inventory["scope"]["client_id"],
            ))
        warnings = list(unit.get("support_warnings", []))
        if not unit.get("support_detail_complete") and not warnings:
            warnings.append("support_detail_not_collected")
        activities.append(replace(activity, support_documents=tuple(documents), support_warnings=tuple(warnings)))
    for obj in unresolved_sequences:
        activities.append(AssignmentObservation(
            exercise_id=obj["id"], assignment_id=None, title=obj["title"],
            reason_codes=("sequence_delivery_unresolved",),
            evidence={"sequence_resolution": "unresolved"},
            instructions=obj["instructions"], url=obj["url"],
            url_kind=ActivityLinkKind.SEQUENCE_ENTRY,
            paths=tuple(tuple(path["path"]) for path in obj["paths"]),
            support_documents=tuple(sequence_materials(obj)),
            support_warnings=("sequence_materials_metadata_only",),
        ))
    negative_ids = {
        document["document_id"] for activity in activities for document in activity.support_documents
        if document["document_id"] and document["role"] in NEGATIVE_ROLES
    }
    activities = [replace(
        activity, support_documents=tuple(select_materials(
            list(activity.support_documents), activity.status.value, policy.include_contextual, negative_ids,
        )),
    ) for activity in activities]
    activities.sort(key=lambda activity: (int(activity.exercise_id), int(activity.assignment_id or 0)))
    counts = Counter(activity.status.value for activity in activities)
    collection_complete = bool(inventory["coverage"]) and all(root["complete"] for root in inventory["coverage"]) and not inventory["errors"]
    complete = collection_complete and not counts["unknown"]
    warnings = list(policy.warnings)
    if not collection_complete:
        warnings.append("collection_incomplete")
    if counts["unknown"]:
        warnings.append("unresolved_activities")
    for activity in activities:
        resolution = activity.evidence.get("deadline_resolution")
        if resolution not in {None, "resolved", "no_deadline"} and resolution not in warnings:
            warnings.append(resolution)
    payload = json.loads(json.dumps([asdict(activity) for activity in activities], default=lambda value: value.isoformat()))
    return {
        **inventory,
        "activities": payload,
        "classification": {
            "complete": complete,
            "all_clear": complete and not counts["pending"],
            "counts": {status.value: counts[status.value] for status in ActivityStatus},
            "warnings": warnings,
            "selection": "all",
            "returned_count": len(payload),
        },
    }


def select_activities(inventory: dict[str, Any], selection: str) -> dict[str, Any]:
    """Filter activities only; coverage and full-run counts remain authoritative."""
    status = SELECTIONS[selection]
    activities = [activity for activity in inventory["activities"] if status is None or activity["status"] == status]
    return {
        **inventory, "activities": activities,
        "classification": {**inventory["classification"], "selection": selection, "returned_count": len(activities)},
    }


def _classify_unit(obj: dict, unit: dict, paths: list, policy: ClassificationPolicy, checked_at: datetime) -> AssignmentObservation:
    scope = _enum(SubmissionScope, unit.get("submission_scope"))
    applicable = _enum(Applicability, unit.get("applicability"))
    files = unit.get("submitted_files")
    decision = policy.selection(obj["id"])
    applicability_source = None
    if decision == "selected" and applicable is not Applicability.NOT_APPLICABLE:
        applicable = Applicability.APPLICABLE
        applicability_source = "configured_alternative_selection"
    elif decision in {"excluded", "unselected"}:
        applicable = Applicability.NOT_APPLICABLE
        applicability_source = "explicit_exclusion" if decision == "excluded" else "unselected_alternative"
    elif applicable is Applicability.APPLICABLE:
        applicability_source = "platform_ownership"
    elif applicable is Applicability.UNKNOWN:
        if scope is SubmissionScope.PERSONAL and files is not None and unit.get("submission_source"):
            applicable = Applicability.APPLICABLE
            applicability_source = "personal_submission_context"
        elif scope is SubmissionScope.TEAM and unit.get("learner_team_confirmed") is True:
            applicable = Applicability.APPLICABLE
            applicability_source = "platform_team_context"
    raw_deadline = unit.get("deadline") or None
    deadline, resolution = normalize_deadline(raw_deadline, policy.timezone)
    delivery_type = _enum(DeliveryType, unit.get("delivery_type"))
    availability = _enum(Availability, unit.get("availability"))
    history = tuple(
        SubmissionHistory(
            submitted_at=normalize_deadline(entry.get("date"), policy.timezone)[0],
            attachment_present=True if entry.get("filename") else None,
            attachment_count=1 if entry.get("filename") else None,
            scope=scope,
        ) for entry in (files or [])
    )
    observation = AssignmentObservation(
        exercise_id=obj["id"], assignment_id=unit["ass_id"], title=unit["title"],
        submission_type=delivery_type,
        applicability=applicable,
        availability=availability,
        evidence={
            "delivery_confirmed": None if delivery_type is DeliveryType.UNKNOWN else delivery_type is DeliveryType.FILE_UPLOAD,
            "acceptance_confirmed": None if availability is Availability.UNKNOWN else availability is Availability.ACCEPTING_SUBMISSIONS,
            "applicability_source": applicability_source,
            "submission_source": unit.get("submission_source"),
            "deadline_resolution": resolution,
        },
        deadline_text=raw_deadline, deadline_at=deadline,
        deadline_timezone=policy.timezone,
        overdue=checked_at > deadline if deadline else None,
        url=unit.get("presentation_url") or obj["url"],
        url_kind=ActivityLinkKind.ASSIGNMENT if unit.get("presentation_url") else ActivityLinkKind.EXERCISE,
        paths=tuple(tuple(path) for path in paths), submission_history=history,
        instructions=unit.get("instructions") if unit["ass_id"] is not None else obj["instructions"],
        requirement_text=unit.get("requirement"),
    )
    classified = classify_assignment(
        observation,
        SubmissionEvidence(
            present=bool(files) if files is not None else None,
            scope=scope, learner_team_confirmed=unit.get("learner_team_confirmed"),
        ),
        excluded=decision in {"excluded", "unselected"},
        contradictory=unit.get("contradictory") is True,
    )
    reasons = list(classified.reason_codes)
    if decision == "unselected":
        reasons = ["unselected_alternative"]
    reasons.extend(unit.get("warnings", []))
    if decision == "excluded" and any(obj["id"] in group.selected for group in policy.alternative_sets):
        reasons.append("selected_exercise_explicitly_excluded")
    return replace(classified, reason_codes=tuple(dict.fromkeys(reasons)))


def _enum(kind, value):
    try:
        return kind(value)
    except (ValueError, TypeError):
        return kind.UNKNOWN

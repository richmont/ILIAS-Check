from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timezone
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ilias_check.activities import (
    ActivityLinkKind,
    ActivityStatus,
    Applicability,
    AssignmentObservation,
    Availability,
    DeliveryType,
    SubmissionHistory,
    SubmissionScope,
)


ROOT = Path(__file__).parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "inventory-v1.schema.json").read_text())
ACTIVITY_VALIDATOR = Draft202012Validator(
    SCHEMA["properties"]["activities"]["items"],
    format_checker=FormatChecker(),
)


def test_activity_observation_defaults_missing_evidence_to_unknown() -> None:
    observation = AssignmentObservation(
        exercise_id="101",
        assignment_id="202",
        title="Synthetic exercise",
    )

    assert observation.submission_type is DeliveryType.UNKNOWN
    assert observation.applicability is Applicability.UNKNOWN
    assert observation.availability is Availability.UNKNOWN
    assert observation.status is ActivityStatus.UNKNOWN
    assert observation.deadline_text is None
    assert observation.deadline_at is None
    assert observation.url is None


def test_submission_history_keeps_missing_date_and_attachment_details_unknown() -> None:
    history = SubmissionHistory(scope=SubmissionScope.TEAM)

    assert history.submitted_at is None
    assert history.attachment_present is None
    assert history.attachment_count is None
    assert history.approved is None
    assert history.completed is None


def test_activity_schema_accepts_unknown_nullable_evidence() -> None:
    activity = {
        "exercise_id": "101",
        "assignment_id": None,
        "title": "Synthetic exercise",
        "submission_type": "unknown",
        "applicability": "unknown",
        "availability": "unknown",
        "status": "unknown",
        "reason_codes": ["assignment_identity_missing"],
        "evidence": {
            "delivery_confirmed": None,
            "acceptance_confirmed": None,
            "submission_present": None,
            "applicability_source": None,
            "submission_source": None,
        },
        "deadline_text": None,
        "deadline_at": None,
        "url": "https://ilias.example.edu/goto.php?target=exc_101",
        "url_kind": "exercise",
        "paths": [["Synthetic root", "Synthetic exercise"]],
        "submission_history": [
            {
                "submitted_at": None,
                "attachment_present": None,
                "attachment_count": None,
                "scope": "unknown",
                "approved": None,
                "completed": None,
            }
        ],
    }

    ACTIVITY_VALIDATOR.validate(activity)


def test_activity_schema_supports_explicit_submission_metadata() -> None:
    activity = {
        "exercise_id": "101",
        "assignment_id": "202",
        "title": "Synthetic exercise",
        "submission_type": DeliveryType.FILE_UPLOAD.value,
        "applicability": Applicability.APPLICABLE.value,
        "availability": Availability.ACCEPTING_SUBMISSIONS.value,
        "status": ActivityStatus.SUBMITTED.value,
        "reason_codes": ["team_submission_confirmed"],
        "evidence": {
            "delivery_confirmed": True,
            "acceptance_confirmed": True,
            "submission_present": True,
            "applicability_source": "platform_team_context",
            "submission_source": "team_submission_list",
        },
        "deadline_text": None,
        "deadline_at": None,
        "url": "https://ilias.example.edu/goto.php?target=ass_202",
        "url_kind": ActivityLinkKind.ASSIGNMENT.value,
        "paths": [],
        "submission_history": [
            {
                "submitted_at": datetime(2026, 1, 2, tzinfo=timezone.utc).isoformat(),
                "attachment_present": True,
                "attachment_count": 1,
                "scope": SubmissionScope.TEAM.value,
                "approved": None,
                "completed": None,
            }
        ],
    }

    ACTIVITY_VALIDATOR.validate(activity)


def test_observation_model_has_no_answer_body_field() -> None:
    assert "answer_body" not in {item.name for item in fields(AssignmentObservation)}
    assert "answer_body" not in {item.name for item in fields(SubmissionHistory)}

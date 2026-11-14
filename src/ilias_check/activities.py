"""Typed, answer-body-free observations for ILIAS assignment units."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class DeliveryType(StrEnum):
    FILE_UPLOAD = "file_upload"
    TEXT = "text"
    OTHER = "other"
    UNKNOWN = "unknown"


class Availability(StrEnum):
    ACCEPTING_SUBMISSIONS = "accepting_submissions"
    NOT_YET_OPEN = "not_yet_open"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class Applicability(StrEnum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class ActivityStatus(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    CLOSED_WITHOUT_SUBMISSION = "closed_without_submission"
    NOT_YET_OPEN = "not_yet_open"
    EXCLUDED = "excluded"
    UNKNOWN = "unknown"


class ActivityLinkKind(StrEnum):
    ASSIGNMENT = "assignment"
    EXERCISE = "exercise"
    SEQUENCE_ENTRY = "sequence_entry"


class SubmissionScope(StrEnum):
    PERSONAL = "personal"
    TEAM = "team"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SubmissionHistory:
    """Metadata about a submission; never contains learner answer contents."""

    submitted_at: datetime | None = None
    attachment_present: bool | None = None
    attachment_count: int | None = None
    scope: SubmissionScope = SubmissionScope.UNKNOWN
    approved: bool | None = None
    completed: bool | None = None


@dataclass(frozen=True, slots=True)
class AssignmentObservation:
    """Evidence for one assignment unit, independent of its exercise page."""

    exercise_id: str
    assignment_id: str | None
    title: str
    submission_type: DeliveryType = DeliveryType.UNKNOWN
    applicability: Applicability = Applicability.UNKNOWN
    availability: Availability = Availability.UNKNOWN
    status: ActivityStatus = ActivityStatus.UNKNOWN
    reason_codes: tuple[str, ...] = ()
    evidence: dict[str, bool | str | None] = field(default_factory=dict)
    deadline_text: str | None = None
    deadline_at: datetime | None = None
    url: str | None = None
    url_kind: ActivityLinkKind = ActivityLinkKind.EXERCISE
    paths: tuple[tuple[str, ...], ...] = ()
    submission_history: tuple[SubmissionHistory, ...] = ()
    instructions: str | None = None
    requirement_text: str | None = None
    deadline_timezone: str | None = None
    overdue: bool | None = None
    support_documents: tuple[dict[str, object], ...] = ()
    support_warnings: tuple[str, ...] = ()

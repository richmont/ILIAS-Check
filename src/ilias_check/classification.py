"""Pure classification of per-unit evidence, without network or clock access."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ilias_check.activities import (
    ActivityStatus,
    Applicability,
    AssignmentObservation,
    Availability,
    DeliveryType,
    SubmissionScope,
)


@dataclass(frozen=True, slots=True)
class SubmissionEvidence:
    """Current submission-list evidence for this unit, never answer contents.

    ``present=False`` requires an explicitly parsed empty applicable list.
    Team lists require confirmation that they describe the learner's team.
    Historical entries alone do not establish the current delivery state.
    """

    present: bool | None = None
    scope: SubmissionScope = SubmissionScope.UNKNOWN
    learner_team_confirmed: bool | None = None
    contradictory: bool = False


def classify_assignment(
    observation: AssignmentObservation,
    submission: SubmissionEvidence = SubmissionEvidence(),
    *,
    excluded: bool = False,
    contradictory: bool = False,
) -> AssignmentObservation:
    """Return a new observation with an explainable, conservative upload state.

    Adapters must set ``contradictory`` for conflicting availability, ownership,
    or delivery signals. No status is inferred from titles, deadlines, history,
    approval, or an earlier classification. Explicit exclusions win over such
    conflicts. All other decisions require a stable assignment identity.
    """

    evidence = dict(observation.evidence)
    evidence.update(
        submission_present=submission.present,
        submission_scope=submission.scope.value,
        learner_team_confirmed=submission.learner_team_confirmed,
        explicitly_excluded=excluded,
        contradictory_evidence=contradictory or submission.contradictory,
    )

    def result(status: ActivityStatus, reason: str) -> AssignmentObservation:
        return replace(observation, status=status, reason_codes=(reason,), evidence=evidence)

    if excluded:
        return result(ActivityStatus.EXCLUDED, "explicitly_excluded")
    if observation.applicability is Applicability.NOT_APPLICABLE:
        return result(ActivityStatus.EXCLUDED, "not_applicable")
    if contradictory or submission.contradictory:
        return result(ActivityStatus.UNKNOWN, "contradictory_evidence")
    if observation.submission_type in {DeliveryType.TEXT, DeliveryType.OTHER}:
        return result(ActivityStatus.EXCLUDED, "non_file_delivery")
    if observation.submission_type is not DeliveryType.FILE_UPLOAD:
        return result(ActivityStatus.UNKNOWN, "delivery_type_unknown")
    if not observation.assignment_id or not observation.assignment_id.strip():
        return result(ActivityStatus.UNKNOWN, "assignment_identity_missing")
    if observation.applicability is not Applicability.APPLICABLE:
        return result(ActivityStatus.UNKNOWN, "applicability_unknown")
    if submission.scope is SubmissionScope.UNKNOWN:
        return result(ActivityStatus.UNKNOWN, "submission_scope_unknown")
    if (
        submission.scope is SubmissionScope.TEAM
        and submission.learner_team_confirmed is not True
    ):
        return result(ActivityStatus.UNKNOWN, "learner_team_unconfirmed")
    if submission.present is True:
        reason = (
            "team_submission_confirmed"
            if submission.scope is SubmissionScope.TEAM
            else "personal_submission_confirmed"
        )
        return result(ActivityStatus.SUBMITTED, reason)
    if submission.present is not False:
        return result(ActivityStatus.UNKNOWN, "submission_presence_unknown")
    if observation.availability is Availability.CLOSED:
        return result(ActivityStatus.CLOSED_WITHOUT_SUBMISSION, "closed_without_submission")
    if observation.availability is Availability.NOT_YET_OPEN:
        return result(ActivityStatus.NOT_YET_OPEN, "not_yet_open")
    if observation.availability is Availability.ACCEPTING_SUBMISSIONS:
        return result(ActivityStatus.PENDING, "accepting_without_submission")
    return result(ActivityStatus.UNKNOWN, "availability_unknown")

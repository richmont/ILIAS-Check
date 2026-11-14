from dataclasses import replace
from datetime import datetime, timezone

import pytest

from ilias_check.activities import (
    ActivityStatus as Status,
    Applicability,
    AssignmentObservation,
    Availability,
    DeliveryType,
    SubmissionHistory,
    SubmissionScope,
)
from ilias_check.classification import SubmissionEvidence, classify_assignment


def unit(**changes):
    return replace(
        AssignmentObservation(
            exercise_id="101",
            assignment_id="202",
            title="Originaltitel – Übung",
            submission_type=DeliveryType.FILE_UPLOAD,
            applicability=Applicability.APPLICABLE,
            availability=Availability.ACCEPTING_SUBMISSIONS,
        ),
        **changes,
    )


@pytest.mark.parametrize(
    "availability,present,expected,reason",
    [
        (Availability.ACCEPTING_SUBMISSIONS, False, Status.PENDING, "accepting_without_submission"),
        (Availability.CLOSED, False, Status.CLOSED_WITHOUT_SUBMISSION, "closed_without_submission"),
        (Availability.NOT_YET_OPEN, False, Status.NOT_YET_OPEN, "not_yet_open"),
        (Availability.UNKNOWN, False, Status.UNKNOWN, "availability_unknown"),
        *[(value, True, Status.SUBMITTED, "personal_submission_confirmed") for value in Availability],
        *[(value, None, Status.UNKNOWN, "submission_presence_unknown") for value in Availability],
    ],
)
def test_status_matrix(availability, present, expected, reason):
    result = classify_assignment(
        unit(availability=availability),
        SubmissionEvidence(present=present, scope=SubmissionScope.PERSONAL),
    )
    assert result.status is expected
    assert result.reason_codes == (reason,)


@pytest.mark.parametrize(
    "changes,reason,expected",
    [
        ({"submission_type": DeliveryType.UNKNOWN}, "delivery_type_unknown", Status.UNKNOWN),
        ({"submission_type": DeliveryType.TEXT}, "non_file_delivery", Status.EXCLUDED),
        ({"submission_type": DeliveryType.OTHER}, "non_file_delivery", Status.EXCLUDED),
        ({"assignment_id": None}, "assignment_identity_missing", Status.UNKNOWN),
        ({"assignment_id": " "}, "assignment_identity_missing", Status.UNKNOWN),
        ({"applicability": Applicability.UNKNOWN}, "applicability_unknown", Status.UNKNOWN),
        ({"applicability": Applicability.NOT_APPLICABLE}, "not_applicable", Status.EXCLUDED),
    ],
)
def test_required_evidence(changes, reason, expected):
    result = classify_assignment(
        unit(**changes), SubmissionEvidence(False, SubmissionScope.PERSONAL)
    )
    assert result.status is expected
    assert result.reason_codes == (reason,)


@pytest.mark.parametrize("present", [True, False, None])
@pytest.mark.parametrize("team_confirmed", [True, False, None])
def test_team_delivery_requires_current_learner_team(present, team_confirmed):
    result = classify_assignment(
        unit(), SubmissionEvidence(present, SubmissionScope.TEAM, team_confirmed)
    )
    expected = Status.UNKNOWN
    if team_confirmed is True and present is not None:
        expected = Status.SUBMITTED if present else Status.PENDING
    assert result.status is expected
    if expected is Status.SUBMITTED:
        assert result.reason_codes == ("team_submission_confirmed",)


@pytest.mark.parametrize("present", [True, False, None])
def test_unknown_scope_cannot_establish_submission(present):
    result = classify_assignment(unit(), SubmissionEvidence(present=present))
    assert result.status is Status.UNKNOWN
    assert result.reason_codes == ("submission_scope_unknown",)


@pytest.mark.parametrize("conflict_source", ["unit", "submission"])
def test_conflicts_block_decision_but_explicit_exclusion_wins(conflict_source):
    submission = SubmissionEvidence(
        True, SubmissionScope.PERSONAL, contradictory=conflict_source == "submission"
    )
    options = {"contradictory": conflict_source == "unit"}
    result = classify_assignment(unit(), submission, **options)
    assert result.status is Status.UNKNOWN
    assert result.reason_codes == ("contradictory_evidence",)
    excluded = classify_assignment(unit(), submission, excluded=True, **options)
    assert excluded.status is Status.EXCLUDED
    assert excluded.evidence["contradictory_evidence"] is True


def test_no_inference_from_title_deadline_history_or_approval():
    observation = unit(
        title="Group 1 – mandatory upload",
        availability=Availability.UNKNOWN,
        deadline_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
        submission_history=(SubmissionHistory(approved=True, completed=True),),
    )
    assert classify_assignment(observation).status is Status.UNKNOWN
    assert classify_assignment(
        observation, SubmissionEvidence(False, SubmissionScope.PERSONAL)
    ).status is Status.UNKNOWN


def test_explicit_acceptance_survives_old_or_unparseable_deadline():
    for changes in [
        {"deadline_at": datetime(2000, 1, 1, tzinfo=timezone.utc)},
        {"deadline_text": "unrecognized date"},
    ]:
        result = classify_assignment(
            unit(**changes), SubmissionEvidence(False, SubmissionScope.PERSONAL)
        )
        assert result.status is Status.PENDING


def test_classification_preserves_source_and_does_not_mutate_input():
    observation = unit(
        status=Status.SUBMITTED,
        reason_codes=("old_decision",),
        evidence={"requirement_text": "Optional practice"},
        submission_history=(SubmissionHistory(scope=SubmissionScope.PERSONAL),),
        paths=(("Root", "Course"),),
        url="https://ilias.example.edu/goto.php?target=exc_101",
    )
    result = classify_assignment(
        observation, SubmissionEvidence(False, SubmissionScope.PERSONAL)
    )
    assert result.status is Status.PENDING
    assert observation.status is Status.SUBMITTED
    assert observation.evidence == {"requirement_text": "Optional practice"}
    assert result.evidence["requirement_text"] == "Optional practice"
    for name in ("title", "paths", "url", "submission_history", "deadline_text"):
        assert getattr(result, name) == getattr(observation, name)
    assert classify_assignment(
        result, SubmissionEvidence(False, SubmissionScope.PERSONAL)
    ) == result


def test_sibling_units_are_classified_independently():
    submitted = classify_assignment(
        unit(), SubmissionEvidence(True, SubmissionScope.PERSONAL)
    )
    pending = classify_assignment(
        unit(assignment_id="203"), SubmissionEvidence(False, SubmissionScope.PERSONAL)
    )
    text = classify_assignment(unit(assignment_id="204", submission_type=DeliveryType.TEXT))
    assert [item.status for item in (submitted, pending, text)] == [
        Status.SUBMITTED, Status.PENDING, Status.EXCLUDED
    ]

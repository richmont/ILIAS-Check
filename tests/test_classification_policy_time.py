from datetime import datetime, timezone
import json

import pytest

from ilias_check.config import CollectorConfig, ConfigurationError
from ilias_check.deadlines import normalize_deadline
from ilias_check.policy import ClassificationPolicy, PolicyError
from ilias_check.results import classify_inventory


@pytest.mark.parametrize("values", [
    {"ILIAS_TIMEZONE": "invalid/timezone"},
    {"ILIAS_PENDING_EXCLUDE_EXERCISES": "0"},
    {"ILIAS_PENDING_EXCLUDE_EXERCISES": "1,,2"},
    {"ILIAS_PENDING_ALTERNATIVE_SETS": "[]"},
    {"ILIAS_PENDING_ALTERNATIVE_SETS": "invalid"},
    {"ILIAS_PENDING_ALTERNATIVE_SETS": '{"a":{"members":["1"],"selected":["2"]}}'},
    {"ILIAS_PENDING_ALTERNATIVE_SETS": '{"a":{"members":[1],"selected":[]}}'},
    {"ILIAS_PENDING_ALTERNATIVE_SETS": '{"a":{"members":["1","1"],"selected":[]}}'},
    {"ILIAS_PENDING_ALTERNATIVE_SETS": '{"a":{"members":[],"selected":[]}}'},
    {"ILIAS_PENDING_ALTERNATIVE_SETS": '{"a":{"members":["1"],"selected":[],"extra":true}}'},
    {"ILIAS_PENDING_ALTERNATIVE_SETS": '{"a":{"members":["1"],"selected":[]},"b":{"members":["1"],"selected":["1"]}}'},
    {"ILIAS_PENDING_ALTERNATIVE_SETS": '{"a":{"members":["1"],"selected":[]},"a":{"members":["2"],"selected":[]}}'},
])
def test_invalid_classification_policy_is_rejected_without_raw_values(values):
    with pytest.raises(PolicyError) as captured:
        ClassificationPolicy.from_mapping(values)
    assert "invalid/timezone" not in str(captured.value)
    assert '{"a"' not in str(captured.value)


def test_collector_validates_classification_policy_before_network():
    values = {
        "ILIAS_BASE_URL": "https://ilias.example.edu", "ILIAS_CLIENT_ID": "academy",
        "ILIAS_USER": "synthetic-user", "ILIAS_PASS": "synthetic-password", "ILIAS_PENDING_ROOTS": "1001",
        "ILIAS_TIMEZONE": "invalid/timezone",
    }
    with pytest.raises(ConfigurationError, match="ILIAS_TIMEZONE"):
        CollectorConfig.from_mapping(values)


@pytest.mark.parametrize("raw,zone,expected,reason", [
    (None, None, None, "no_deadline"),
    ("Keine Abgabefrist", "Europe/Berlin", None, "no_deadline"),
    ("2026-11-14", "Europe/Berlin", None, "deadline_time_missing"),
    ("4. Mai 2026, 08:00", None, None, "installation_timezone_missing"),
    ("4. Mai 2026, 08:00", "Europe/Berlin", "2026-05-04T06:00:00+00:00", "resolved"),
    ("3. Jul 2026, 23:59", "Europe/Berlin", "2026-07-03T21:59:00+00:00", "resolved"),
    ("04.05.2026 08:00", "Europe/Berlin", "2026-05-04T06:00:00+00:00", "resolved"),
    ("2026-11-14T12:00:00+02:00", None, "2026-11-14T10:00:00+00:00", "resolved"),
    ("25. Oktober 2026, 02:30", "Europe/Berlin", None, "ambiguous_local_time"),
    ("29. März 2026, 02:30", "Europe/Berlin", None, "nonexistent_local_time"),
    ("31. Februar 2026, 08:00", "Europe/Berlin", None, "unparseable_deadline"),
    ("unrecognized", "Europe/Berlin", None, "unparseable_deadline"),
])
def test_deadline_resolution_matrix(raw, zone, expected, reason):
    result, actual_reason = normalize_deadline(raw, zone)
    assert actual_reason == reason
    assert (result.isoformat() if result else None) == expected


def test_explicit_timezone_is_independent_of_host_timezone(monkeypatch):
    monkeypatch.setenv("TZ", "America/Belem")
    first = normalize_deadline("4. Mai 2026, 08:00", "Europe/Berlin")
    monkeypatch.setenv("TZ", "Pacific/Auckland")
    assert normalize_deadline("4. Mai 2026, 08:00", "Europe/Berlin") == first
    assert first[0] == datetime(2026, 5, 4, 6, tzinfo=timezone.utc)


def test_fixed_observation_time_records_overdue_without_closing_acceptance():
    # Use the complete synthetic contract from the checked-in inventory fixture.
    from test_classified_inventory import obj, snapshot, unit

    policy = ClassificationPolicy.from_mapping({"ILIAS_TIMEZONE": "Europe/Berlin"})
    source = snapshot([obj(assignments=[unit(deadline="4. Mai 2026, 08:00")])])
    result = classify_inventory(source, policy)
    activity = result["activities"][0]
    assert activity["status"] == "pending"
    assert activity["overdue"] is True
    assert activity["deadline_timezone"] == "Europe/Berlin"
    assert activity["deadline_at"] == "2026-05-04T06:00:00+00:00"
    for deadline in ("unrecognized", "25. Oktober 2026, 02:30"):
        source["objects"][0]["assignments"][0]["deadline"] = deadline
        activity = classify_inventory(source, policy)["activities"][0]
        assert activity["status"] == "pending"
        assert activity["overdue"] is None
        assert activity["deadline_text"] == deadline

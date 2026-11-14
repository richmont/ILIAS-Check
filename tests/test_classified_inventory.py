from dataclasses import asdict
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pytest

from ilias_check import cli
from ilias_check.exercises import ExerciseAssignment, extract_deadline, parse_exercise_assignments, submission_acceptance
from ilias_check.policy import ClassificationPolicy
from ilias_check.results import classify_inventory, select_activities


BASE = "https://ilias.example.edu"
SCHEMA = json.loads((Path(__file__).parents[1] / "schemas/inventory-v1.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def unit(ass_id="41", **changes):
    values = {
        **asdict(ExerciseAssignment(ass_id, "Originaltitel", delivery_type="file_upload")),
        "submission_scope": "personal", "submission_source": "submission_screen",
        "submitted_files": [], "availability": "accepting_submissions",
        "presentation_url": f"{BASE}/ilias.php?baseClass=ilrepositorygui&cmdClass=ilAssignmentPresentationGUI&ref_id=444&ass_id={ass_id}",
        **changes,
    }
    if values.get("submitted_files") is not None:
        values["submitted_files"] = [
            {"delivery_id": "71", "filename": "", "submitter": "", "date": "", **entry}
            for entry in values["submitted_files"]
        ]
    return values


def obj(ref_id="444", kind="exercise", assignments=None, **changes):
    result = {
        "id": ref_id, "type": kind, "type_code": "exc" if kind == "exercise" else "lso",
        "title": "Originaltitel", "instructions": "General exercise context",
        "paths": [{"root_id": "1001", "path": ["Course", "Übungen"]}],
        "url": f"{BASE}/goto.php?target={'exc' if kind == 'exercise' else 'lso'}_{ref_id}&client_id=academy",
        "url_kind": "activity" if kind == "exercise" else "sequence_entry",
        "documents": [], "sequence_resolution": None if kind == "exercise" else "unresolved",
        "sequence_steps": [], "warnings": [], **changes,
    }
    if kind == "exercise":
        result["assignments"] = [unit()] if assignments is None else assignments
    return result


def snapshot(objects=None, complete=True):
    return {
        "schema_version": "1.0", "checked_at": "2026-11-14T12:00:00Z",
        "scope": {"base_url": BASE, "client_id": "academy", "root_ids": ["1001"]},
        "coverage": [{"root_id": "1001", "complete": complete, "empty": False, "objects_discovered": 2, "warnings": []}],
        "objects": objects if objects is not None else [obj()], "errors": [],
    }


@pytest.mark.parametrize("changes,status", [
    ({}, "pending"),
    ({"submitted_files": [{"delivery_id": "71", "filename": "answer.pdf", "date": "2026-11-01T12:00:00Z"}]}, "submitted"),
    ({"availability": "closed"}, "closed_without_submission"),
    ({"availability": "not_yet_open"}, "not_yet_open"),
    ({"availability": "unknown"}, "unknown"),
    ({"submitted_files": None}, "unknown"),
    ({"delivery_type": "text"}, "excluded"),
    ({"submission_scope": "unknown"}, "unknown"),
    ({"contradictory": True}, "unknown"),
])
def test_classified_inventory_state_matrix_is_schema_valid(changes, status):
    result = classify_inventory(snapshot([obj(assignments=[unit(**changes)])]))
    VALIDATOR.validate(result)
    assert result["activities"][0]["status"] == status
    assert result["classification"]["counts"][status] == 1
    assert result["classification"]["complete"] is (status != "unknown")
    assert result["classification"]["all_clear"] is (status not in {"pending", "unknown"})


def test_submitted_history_keeps_unknown_details_and_does_not_infer_approval():
    files = [{"delivery_id": "71", "filename": "", "date": ""}]
    result = classify_inventory(snapshot([obj(assignments=[unit(submitted_files=files)])]))
    history = result["activities"][0]["submission_history"][0]
    assert history == {"submitted_at": None, "attachment_present": None, "attachment_count": None, "scope": "personal", "approved": None, "completed": None}


@pytest.mark.parametrize("present,team_confirmed,status", [
    (True, True, "submitted"), (False, True, "pending"),
    (True, False, "unknown"), (False, False, "unknown"), (True, None, "unknown"),
])
def test_current_team_context_is_required(present, team_confirmed, status):
    files = [{"delivery_id": "71", "filename": "team.pdf", "date": ""}] if present else []
    source = snapshot([obj(assignments=[unit(submission_scope="team", learner_team_confirmed=team_confirmed, submitted_files=files)])])
    result = classify_inventory(source)
    assert result["activities"][0]["status"] == status
    if status == "submitted":
        assert result["activities"][0]["submission_history"][0]["scope"] == "team"
        assert result["activities"][0]["submission_history"][0]["approved"] is None


def test_alternative_selection_excludes_only_declared_unselected_members():
    policy = ClassificationPolicy.from_mapping({"ILIAS_PENDING_ALTERNATIVE_SETS": json.dumps({"group": {"members": ["441", "442", "443", "444", "445"], "selected": ["442"]}})})
    source = snapshot([obj(ref_id=str(ref_id)) for ref_id in range(441, 447)])
    result = classify_inventory(source, policy)
    assert [a["status"] for a in result["activities"]] == ["excluded", "pending", "excluded", "excluded", "excluded", "pending"]
    assert result["activities"][-1]["evidence"]["applicability_source"] == "personal_submission_context"


def test_five_unconfirmed_team_alternatives_are_not_all_pending():
    source = snapshot([obj(ref_id=str(ref_id), assignments=[unit(submission_scope="team")]) for ref_id in range(441, 446)])
    result = classify_inventory(source)
    assert result["classification"]["counts"]["pending"] == 0
    assert result["classification"]["counts"]["unknown"] == 5


def test_exclusion_beats_selection_with_visible_configuration_warning():
    policy = ClassificationPolicy.from_mapping({
        "ILIAS_PENDING_EXCLUDE_EXERCISES": "444",
        "ILIAS_PENDING_ALTERNATIVE_SETS": '{"group":{"members":["444","445"],"selected":["444"]}}',
    })
    result = classify_inventory(snapshot(), policy)
    assert result["activities"][0]["status"] == "excluded"
    assert "selected_exercise_explicitly_excluded" in result["classification"]["warnings"]
    assert "selected_exercise_explicitly_excluded" in result["activities"][0]["reason_codes"]


def test_known_non_applicability_is_not_overridden_by_selection():
    policy = ClassificationPolicy.from_mapping({"ILIAS_PENDING_ALTERNATIVE_SETS": '{"group":{"members":["444"],"selected":["444"]}}'})
    result = classify_inventory(snapshot([obj(assignments=[unit(applicability="not_applicable")])]), policy)
    assert result["activities"][0]["status"] == "excluded"


def test_unknown_sequence_prevents_all_clear_and_survives_filters():
    files = [{"delivery_id": "71", "filename": "answer.pdf", "date": ""}]
    result = classify_inventory(snapshot([obj(assignments=[unit(submitted_files=files)]), obj("555", "learning_sequence")]))
    VALIDATOR.validate(result)
    assert result["classification"]["all_clear"] is False
    assert result["classification"]["complete"] is False
    sequence = select_activities(result, "needs-verification")["activities"][0]
    assert sequence["url_kind"] == "sequence_entry" and sequence["assignment_id"] is None
    assert sequence["reason_codes"] == ["sequence_delivery_unresolved"]
    pending = select_activities(result, "pending")
    assert pending["activities"] == []
    assert pending["classification"]["counts"]["unknown"] == 1
    assert pending["classification"]["all_clear"] is False
    assert result["classification"]["selection"] == "all"


def test_failed_collection_never_produces_all_clear_without_unknown_activities():
    result = classify_inventory(snapshot(objects=[], complete=False))
    assert result["activities"] == []
    assert result["classification"]["all_clear"] is False
    assert "collection_incomplete" in result["classification"]["warnings"]


def test_reclassifying_a_filtered_snapshot_restores_all_categories():
    result = classify_inventory(snapshot([obj(assignments=[unit(), unit("42", availability="closed")])]))
    filtered = select_activities(result, "pending")
    assert len(filtered["activities"]) == 1
    restored = classify_inventory(filtered)
    assert [a["status"] for a in restored["activities"]] == ["pending", "closed_without_submission"]
    assert restored["classification"]["selection"] == "all"


def test_unknown_acceptance_is_nullable_evidence():
    result = classify_inventory(snapshot([obj(assignments=[unit(availability="unknown")])]))
    assert result["activities"][0]["evidence"]["acceptance_confirmed"] is None


def test_submission_date_never_substitutes_for_a_missing_deadline():
    for text in (
        "Abgabetermin Keine Abgabefrist Datum der letzten Abgabe 4. Mai 2026, 08:00",
        "Datum der letzten Abgabe 4. Mai 2026, 08:00",
    ):
        assert extract_deadline(text) == ""


def test_duplicate_paths_do_not_duplicate_units_or_hide_pending_sibling():
    files = [{"delivery_id": "71", "filename": "answer.pdf", "date": ""}]
    units = [unit(submitted_files=files), unit("42")]
    source = snapshot([obj(assignments=units), obj(assignments=units, paths=[{"root_id": "1001", "path": ["Second route"]}])])
    result = classify_inventory(source)
    assert [a["status"] for a in result["activities"]] == ["submitted", "pending"]
    assert all(len(a["paths"]) == 2 for a in result["activities"])
    assert "activities" not in source


def test_conflicting_duplicate_observations_are_unknown():
    result = classify_inventory(snapshot([obj(), obj(assignments=[unit(submitted_files=[{"filename": "file.pdf", "date": ""}])])]))
    assert len(result["activities"]) == 1
    assert result["activities"][0]["status"] == "unknown"
    assert "contradictory_evidence" in result["activities"][0]["reason_codes"]


def test_source_optionality_is_preserved_without_curriculum_claims():
    result = classify_inventory(snapshot([obj(assignments=[unit(requirement="Optional", instructions="Übung für alte Kohorte; Selbsttest.")])]))
    activity = result["activities"][0]
    assert activity["status"] == "pending"
    assert activity["requirement_text"] == "Optional"
    assert activity["instructions"] == "Übung für alte Kohorte; Selbsttest."
    assert "obligatory" not in activity
    assert classify_inventory(snapshot())["activities"][0]["instructions"] is None


def test_old_snapshot_without_scope_is_unknown_instead_of_assuming_ownership():
    source_unit = unit()
    del source_unit["submission_scope"]
    result = classify_inventory(snapshot([obj(assignments=[source_unit])]))
    assert result["activities"][0]["status"] == "unknown"


@pytest.mark.parametrize("suffix", ["", "&ass_id=42", "&rtoken=secret"])
def test_acceptance_uses_exact_enabled_upload_control_without_requesting_it(suffix):
    url = f"{BASE}/ilias.php?baseClass=ilrepositorygui&cmdClass=ilExSubmissionFileGUI&cmd=uploadForm&ref_id=444&ass_id=41" + suffix
    html = f'<main><a href="{url}">Datei abgeben</a></main>'
    assert submission_acceptance(html, BASE, BASE, "444", "41") is (suffix == "")
    assert not submission_acceptance(html.replace('<a ', '<a aria-disabled="true" '), BASE, BASE, "444", "41")


def test_structured_delivery_scope_is_not_guessed_from_group_title():
    html = '''<main><li><a href="ilias.php?cmdClass=ilAssignmentPresentationGUI&ass_id=41">Group 1</a>
    <span class="il-item-property-name">Type</span><span class="il-item-property-value">Datei</span></li></main>'''
    parsed = parse_exercise_assignments(html, "444", BASE, BASE)
    assert parsed[0].submission_scope == "personal"
    assert parse_exercise_assignments(html.replace('>Datei<', '>Datei als Team<'), "444", BASE, BASE)[0].submission_scope == "team"
    assert parse_exercise_assignments(html.replace('>Datei<', '>Unrecognized<'), "444", BASE, BASE)[0].submission_scope == "unknown"


def test_offline_cli_needs_no_credentials_or_network_and_returns_partial_for_unknown(tmp_path, monkeypatch, capsys):
    source = snapshot([obj(), obj("555", "learning_sequence")])
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(source))
    monkeypatch.setattr(cli, "collect_inventory", lambda *_: pytest.fail("Offline command attempted collection"))
    result = cli.main(["classify", "--input", str(path), "--select", "pending"])
    captured = capsys.readouterr()
    assert result == 2
    payload = json.loads(captured.out)
    VALIDATOR.validate(payload)
    assert [a["status"] for a in payload["activities"]] == ["pending"]
    assert payload["classification"]["counts"]["unknown"] == 1
    assert "Classification incomplete" in captured.err


@pytest.mark.parametrize("selection,status", [
    ("pending", "pending"), ("submitted", "submitted"),
    ("closed-without-submission", "closed_without_submission"),
    ("needs-verification", "unknown"),
])
def test_cli_categories_preserve_original_links(tmp_path, capsys, selection, status):
    units = [unit(), unit("42", submitted_files=[{"filename": "file.pdf", "date": ""}]), unit("43", availability="closed"), unit("44", submitted_files=None)]
    path = tmp_path / "input.json"
    path.write_text(json.dumps(snapshot([obj(assignments=units)])))
    assert cli.main(["classify", "--input", str(path), "--select", selection]) == 2
    result = json.loads(capsys.readouterr().out)
    assert len(result["activities"]) == 1
    assert result["activities"][0]["status"] == status
    assert result["activities"][0]["url"].startswith(BASE)


def test_malformed_offline_input_has_sanitized_diagnostic(tmp_path, capsys):
    path = tmp_path / "invalid.json"
    path.write_text('private-token invalid document')
    assert cli.main(["classify", "--input", str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "private-token" not in captured.err


def test_collect_cli_classifies_real_transport_flow_without_requesting_upload_control(tmp_path, monkeypatch, capsys):
    from ilias_check import collector
    from ilias_check.read_routes import exercise_overview_url
    from ilias_check.transport import SafeTransport

    screen = f"{BASE}/ilias.php?baseClass=ilrepositorygui&cmdClass=ilExSubmissionFileGUI&cmd=submissionScreen&ref_id=444&ass_id=41&cmdNode=xn:r8"
    upload = screen.replace("submissionScreen", "uploadForm")
    pages = {
        f"{BASE}/goto.php?target=fold_1001&client_id=academy": '<main><a href="/go/exc/444">Originaltitel</a><a href="/go/lso/555">Sequence</a></main>',
        f"{BASE}/goto.php?target=exc_444&client_id=academy": '<main>Exercise</main>',
        f"{BASE}/goto.php?target=lso_555&client_id=academy": '<main>Unresolved sequence</main>',
        exercise_overview_url(BASE, "academy", "444"): f'''<main><li><a href="ilias.php?baseClass=ilrepositorygui&cmdClass=ilAssignmentPresentationGUI&ref_id=444&ass_id=41">Blatt</a>
            <span class="il-item-property-name">Type</span><span class="il-item-property-value">Datei</span><a href="{screen}">Files</a></li></main>''',
        screen: f'<main><table data-submission-list></table><a href="{upload}">Datei abgeben</a></main>',
    }

    class Session:
        def __init__(self):
            self.calls = []

        def request(self, method, url, **kwargs):
            self.calls.append((method, url))
            if "login.php" in url:
                text = '<form action="/login.php"><input type="text" name="username"><input type="password" name="password"></form>'
            elif "ilDashboardGUI" in url:
                text = '<a href="?cmd=doLogout">Logout</a>'
            else:
                text = pages[url]
            return type("Response", (), {"status_code": 200, "headers": {}, "url": url, "text": text})()

        def close(self):
            pass

    session = Session()
    monkeypatch.setattr(collector, "SafeTransport", lambda config: SafeTransport(config, session=session))
    env = tmp_path / "synthetic.env"
    env.write_text("\n".join([
        f"ILIAS_BASE_URL={BASE}", "ILIAS_CLIENT_ID=academy", "ILIAS_USER=synthetic-user",
        "ILIAS_PASS=synthetic-password", "ILIAS_PENDING_ROOTS=1001",
    ]))
    assert cli.main(["collect", "--env-file", str(env), "--select", "pending"]) == 2
    result = json.loads(capsys.readouterr().out)
    VALIDATOR.validate(result)
    assert len(result["activities"]) == 1
    assert result["activities"][0]["status"] == "pending"
    assert result["classification"]["counts"]["unknown"] == 1
    assert not result["classification"]["all_clear"]
    assert all(url != upload for _, url in session.calls)
    assert sum(method == "POST" for method, _ in session.calls) == 1

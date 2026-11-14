"""Offline contracts from richmont/ilias-mcp ca4f4ee5 (see third-party notices)."""

from dataclasses import asdict, replace
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from jsonschema import Draft202012Validator, FormatChecker
import pytest

from ilias_check.config import CollectorConfig
from ilias_check.collector import collect_inventory
from ilias_check.exercises import (
    extract_deadline, extract_status, parse_exercise_assignments,
    parse_submitted_files, parse_team_members,
)
from ilias_check.inventory import build_inventory
from ilias_check.links import normalize_object_link
from ilias_check.parser import parse_repository_page
from ilias_check.read_routes import exercise_overview_url
from ilias_check.transport import SafeTransport, TransportError
from ilias_check.traversal import RepositoryCrawler


BASE = "https://ilias.example.edu"
ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "repository"


def config():
    return CollectorConfig.from_mapping({
        "ILIAS_BASE_URL": BASE, "ILIAS_CLIENT_ID": "academy",
        "ILIAS_USER": "synthetic-user", "ILIAS_PASS": "synthetic-password",
        "ILIAS_PENDING_ROOTS": "1001",
    })


def test_repository_mcp_contract_including_buttons_downloads_and_icons():
    page = parse_repository_page(
        (FIXTURES / "mcp-layouts.html").read_text(),
        f"{BASE}/ilias.php?baseClass=ilrepositorygui&cmd=view&ref_id=1001",
        BASE, "academy", "folder",
    )
    assert [(link.title, link.ref.object_type, link.ref.ref_id) for link in page.links] == [
        ("Material", "folder", "111"), ("Slides", "document", "222"),
        ("Seminar", "course", "333"), ("Übungen", "exercise", "444"),
        ("Notes", "document", "555"),
    ]
    assert "cmd=view" in page.links[2].ref.read_url
    assert all("download" not in link.ref.url for link in page.links)


@pytest.mark.parametrize("scope", ["il_center_col", "mainscrolldiv", "ilContentContainer"])
def test_mcp_content_scopes_do_not_leak_breadcrumbs(scope):
    html = (
        f'<div id="{scope}"><div class="breadcrumb"><a href="/go/fold/99">Parent</a></div>'
        '<button data-action="/go/exc/444" aria-label="Übungen"></button></div>'
        '<aside><a href="/go/crs/777">Other</a></aside>'
    )
    page = parse_repository_page(html, f"{BASE}/ilias.php", BASE, "academy", "folder")
    assert [(link.ref.ref_id, link.title) for link in page.links] == [("444", "Übungen")]


@pytest.mark.parametrize("href,kind", [
    ("/go/fold/111", "folder"), ("/go/exc/444", "exercise"),
    ("/go/file/222/download", "document"),
    ("/goto.php?target=file_222_download", "document"),
    ("/ilias.php?cmdClass=ilObjFileGUI&cmd=sendfile&ref_id=222", "document"),
])
def test_mcp_link_formats_canonicalize_to_metadata(href, kind):
    ref = normalize_object_link(href, f"{BASE}/ilias.php", BASE, "academy")
    assert ref is not None and ref.object_type == kind
    assert "download" not in ref.url and "sendfile" not in ref.url


def assignments():
    return parse_exercise_assignments(
        (FIXTURES / "mcp-exercise-overview.html").read_text(),
        "444", exercise_overview_url(BASE, "academy", "444"), BASE,
    )


def test_per_unit_metadata_matches_mcp_contract_and_preserves_source():
    first, second, text = assignments()
    assert [{key: asdict(item)[key] for key in ("ass_id", "title", "deadline", "status")}
            for item in (first, second, text)] == [
        {"ass_id": "41", "title": "Blatt 1", "deadline": "4. Mai 2026, 08:00", "status": "bereits abgegeben"},
        {"ass_id": "42", "title": "Blatt 2", "deadline": "04.12.2026 08:00", "status": "nicht abgegeben"},
        {"ass_id": "43", "title": "Textaufgabe", "deadline": "", "status": ""},
    ]
    assert [item.delivery_type for item in (first, second, text)] == ["file_upload", "file_upload", "text"]
    assert first.instructions == "Originale Anleitung für Übung 1."
    assert second.requirement == "Optional"
    assert second.instructions == "Selbsttest, keine Pflicht."
    assert parse_qs(urlsplit(first.submission_url).query)["cmdNode"] == ["xn:r6"]
    assert parse_qs(urlsplit(second.submission_url).query)["cmdNode"] == ["xn:r8"]
    assert text.submission_url is None


@pytest.mark.parametrize("text,deadline,status", [
    ("Abgabetermin 04.05.2026 08:00 Nicht abgegeben", "04.05.2026 08:00", "nicht abgegeben"),
    ("Blatt 1 Verpflichtend", "", ""),
    ("Abgegeben Nicht bewertet", "", "abgegeben"),
    ("Datum der letzten Abgabe 3. Mai 2026, 09:51 Beendet am 4. Mai 2026, 08:00", "4. Mai 2026, 08:00", ""),
])
def test_mcp_deadline_and_negation_contracts(text, deadline, status):
    assert extract_deadline(text) == deadline
    assert extract_status(text) == status


SUBMISSIONS = '''<table><tr><td><input name="delivered[]" value="71"></td>
<td><a href="/answer-body">Synthetic answer.pdf</a></td><td>Teammate</td><td>3. Mai 2026, 09:51</td>
</tr></table>'''
TEAM = '''<table><tr><td><input name="id[]" value="81"></td><td>Synthetic Teammate</td>
<td>Entfernen</td></tr></table>'''


def test_submission_and_team_contracts_do_not_download_answer_bodies():
    assert parse_submitted_files(SUBMISSIONS) == [{
        "delivery_id": "71", "filename": "Synthetic answer.pdf", "submitter": "Teammate", "date": "3. Mai 2026, 09:51",
    }]
    assert parse_team_members(TEAM) == [{"user_id": "81", "name": "Synthetic Teammate"}]
    assert parse_submitted_files("<main>Unknown layout</main>") is None
    assert parse_team_members("<main>Unknown layout</main>") is None
    assert parse_submitted_files('<table data-submission-list></table>') == []
    assert parse_team_members('<table data-team-members></table>') == []


def test_target_installation_empty_submission_table_is_recognized():
    html = '''<form action="ilias.php?baseClass=ilrepositorygui&amp;cmdClass=ilExSubmissionFileGUI&amp;cmd=post">
      <table class="table table-striped fullwidth"><tr>
        <td class="ilCenter">Keine Einträge</td>
      </tr></table></form>'''
    assert parse_submitted_files(html) == []
    assert parse_submitted_files(html.replace("Keine Einträge", "Unknown page")) is None
    assert parse_submitted_files(html.replace("ilExSubmissionFileGUI", "ilRepositorySearchGUI")) is None


def test_target_installation_retains_overview_parameters_on_handler_screen():
    html = '''<main><li class="il-std-item-container">
      <h4 class="il-item-title"><a href="ilias.php?baseClass=ilExerciseHandlerGUI&amp;cmdClass=ilAssignmentPresentationGUI&amp;ass_id=41&amp;ref_id=444">Blatt</a></h4>
      <span class="il-item-property-name">Type</span> <span class="il-item-property-value">Datei</span>
      <a href="ilias.php?baseClass=ilExerciseHandlerGUI&amp;cmdClass=ilExSubmissionFileGUI&amp;cmd=submissionScreen&amp;ass_id=41&amp;ref_id=444&amp;cmdNode=xn:r8&amp;mode=all&amp;from_overview=1">Files</a>
    </li></main>'''
    result = parse_exercise_assignments(html, "444", f"{BASE}/ilias.php", BASE)
    assert len(result) == 1
    assert result[0].delivery_type == "file_upload"
    assert result[0].submission_url is not None
    query = parse_qs(urlsplit(result[0].submission_url).query)
    assert query["mode"] == ["all"]
    assert query["from_overview"] == ["1"]


@pytest.mark.parametrize("href", [
    "https://external.example/ilias.php?baseClass=ilrepositorygui&cmdClass=ilExSubmissionFileGUI&cmd=submissionScreen&ref_id=444&ass_id=41",
    "/ilias.php?baseClass=ilrepositorygui&cmdClass=ilExSubmissionFileGUI&cmd=uploadForm&ref_id=444&ass_id=41",
    "/ilias.php?baseClass=ilrepositorygui&cmdClass=ilExSubmissionFileGUI&cmd=submissionScreen&ref_id=445&ass_id=41",
    "/ilias.php?baseClass=ilrepositorygui&cmdClass=ilExSubmissionFileGUI&cmd=submissionScreen&ref_id=444&ass_id=41&rtoken=secret",
    "/ilias.php?baseClass=ilrepositorygui&cmdClass=ilExSubmissionFileGUI&cmd=submissionScreen&ref_id=444&ass_id=41&cmd[deleteDelivered]=1",
])
def test_unsafe_or_wrong_assignment_screen_is_never_selected(href):
    html = (
        '<main><div><a href="ilias.php?cmdClass=ilAssignmentPresentationGUI&ass_id=41">Blatt</a>'
        f'<a href="{href}">Files</a></div></main>'
    )
    result = parse_exercise_assignments(html, "444", f"{BASE}/ilias.php", BASE)
    assert len(result) == 1 and result[0].submission_url is None


@pytest.mark.parametrize("base_class", ["ilrepositorygui", "ilExerciseHandlerGUI"])
@pytest.mark.parametrize("controller,command,extra", [
    ("ilObjExerciseGUI", "showOverview", "&mode=all&from_overview=1"),
    ("ilExSubmissionFileGUI", "submissionScreen", "&ass_id=41&cmdNode=xn:r6&mode=all&from_overview=1"),
    ("ilExSubmissionTeamGUI", "submissionScreenTeam", "&ass_id=41&cmdNode=xn:r7&mode=all&from_overview=1"),
])
def test_transport_allows_only_the_passive_mcp_routes(base_class, controller, command, extra):
    transport = SafeTransport(config())
    try:
        route = f"{BASE}/ilias.php?baseClass={base_class}&cmdClass={controller}&cmd={command}&ref_id=444{extra}"
        transport._validate_read_url(route)
        for suffix in ("&cmd[deleteDelivered]=1", "&cmd=save", "&rtoken=secret", "&ass_id=999", "&step=next"):
            with pytest.raises(TransportError):
                transport._validate_read_url(route + suffix)
    finally:
        transport.close()


@pytest.mark.parametrize("command", ["uploadForm", "upload", "save", "deleteDelivered", "confirmDeleteDelivered", "addUserFromAutoComplete", "removeTeamMember", "next", "complete"])
def test_transport_rejects_mcp_mutations(command):
    transport = SafeTransport(config())
    try:
        with pytest.raises(TransportError):
            transport._validate_read_url(f"{BASE}/ilias.php?baseClass=ilrepositorygui&cmdClass=ilExSubmissionFileGUI&cmd={command}&ref_id=444&ass_id=41")
    finally:
        transport.close()


class OfflineAuth:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        if url not in self.pages:
            raise RuntimeError("Synthetic unavailable page")
        return type("Response", (), {"text": self.pages[url], "url": url})()


def exercise_pages():
    first, second, text = assignments()
    pages = {
        f"{BASE}/goto.php?target=fold_1001&client_id=academy": '<main><a href="/go/exc/444">Übungen</a></main>',
        f"{BASE}/goto.php?target=exc_444&client_id=academy": "<main><h1>Übungen</h1></main>",
        exercise_overview_url(BASE, "academy", "444"): (FIXTURES / "mcp-exercise-overview.html").read_text(),
        first.submission_url: SUBMISSIONS,
        first.team_url: TEAM,
        second.submission_url: '<table data-submission-list></table>',
    }
    for assignment in (first, second, text):
        pages[assignment.presentation_url] = (
            '<main><div class="panel-primary"><div class="panel-sub">'
            '<h3 class="ilBlockHeader">Arbeitsanweisung</h3><div class="panel-body">'
            + (assignment.instructions or "Synthetic instructions")
            + '</div></div></div></main>'
        )
    return pages


def test_crawler_requests_all_units_and_exports_mcp_metadata_with_schema():
    pages = exercise_pages()
    auth = OfflineAuth(pages)
    result = RepositoryCrawler(config(), auth).collect()
    assert set(auth.calls) == set(pages)
    assert len(auth.calls) == len(pages)
    assert result.coverage[0].complete
    inventory = build_inventory(result, config())
    schema = json.loads((ROOT / "schemas" / "inventory-v1.schema.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(inventory)
    exercise = next(item for item in inventory["objects"] if item["id"] == "444")
    assert [item["ass_id"] for item in exercise["assignments"]] == ["41", "42", "43"]
    assert exercise["assignments"][0]["submitted_files"][0]["delivery_id"] == "71"
    assert exercise["assignments"][1]["submitted_files"] == []
    assert exercise["documents"] == [{
        "ref_id": "666", "title": "Synthetic support.pdf",
        "url": f"{BASE}/goto.php?target=file_666&client_id=academy",
    }]
    assert any(item["id"] == "666" and item["type"] == "document" for item in inventory["objects"])
    assert all("answer-body" not in call and "uploadForm" not in call for call in auth.calls)


def test_failed_unit_does_not_erase_sibling_results_or_claim_complete_coverage():
    pages = exercise_pages()
    first, second, _ = assignments()
    del pages[second.submission_url]
    result = RepositoryCrawler(config(), OfflineAuth(pages)).collect()
    exercise = result.objects["exc:444"]
    assert not result.coverage[0].complete
    assert exercise.assignments[0]["submitted_files"] == parse_submitted_files(SUBMISSIONS)
    assert exercise.assignments[1]["submitted_files"] is None
    assert exercise.assignments[1]["warnings"] == ["submitted_files_read_failed"]
    assert len(exercise.assignments) == 3


def test_missing_assignment_route_is_not_borrowed_from_another_unit():
    overview = (FIXTURES / "mcp-exercise-overview.html").read_text()
    overview = overview.replace("ass_id=42&amp;cmdNode=xn:r8", "ass_id=999&amp;cmdNode=xn:r8")
    result = parse_exercise_assignments(overview, "444", f"{BASE}/ilias.php", BASE)
    assert result[0].submission_url is not None
    assert result[1].submission_url is None


@pytest.mark.parametrize("limit", [8, 50])
def test_full_authenticated_transport_preserves_request_budget_and_metadata(limit):
    class Session:
        def __init__(self):
            self.calls = []
            self.pages = exercise_pages()
            self.pages[f"{BASE}/login.php?client_id=academy"] = (
                '<form action="/login.php"><input type="text" name="username">'
                '<input type="password" name="password"></form>'
            )
            self.pages[f"{BASE}/ilias.php?baseClass=ilDashboardGUI"] = '<a href="?cmd=doLogout">Logout</a>'

        def request(self, method, url, **kwargs):
            self.calls.append((method, url))
            assert kwargs["verify"] is True
            assert kwargs["allow_redirects"] is False
            if method == "POST":
                assert url == f"{BASE}/login.php"
                text = ""
            else:
                text = self.pages[url]
            return type("Response", (), {"status_code": 200, "headers": {}, "url": url, "text": text})()

    settings = replace(config(), max_requests=limit)
    session = Session()
    transport = SafeTransport(settings, session=session)
    inventory = collect_inventory(settings, transport=transport)
    assert transport.request_count == len(session.calls) <= limit
    assert [method for method, _ in session.calls].count("POST") == 1
    assert all("answer-body" not in url and "uploadForm" not in url for _, url in session.calls)
    exercise = next(item for item in inventory["objects"] if item["id"] == "444")
    assert len(exercise["assignments"]) == 3
    if limit == 8:
        assert not inventory["coverage"][0]["complete"]
        assert exercise["assignments"][0]["submitted_files"] is not None
        assert exercise["assignments"][1]["submitted_files"] is None
    else:
        assert inventory["coverage"][0]["complete"]


def test_shared_exercise_failure_is_reported_for_every_root_without_duplicate_reads():
    pages = exercise_pages()
    second = assignments()[1]
    del pages[second.submission_url]
    pages[f"{BASE}/goto.php?target=fold_1002&client_id=academy"] = pages[f"{BASE}/goto.php?target=fold_1001&client_id=academy"]
    settings = replace(config(), roots=("1001", "1002"))
    auth = OfflineAuth(pages)
    result = RepositoryCrawler(settings, auth).collect()
    assert [root.complete for root in result.coverage] == [False, False]
    assert all("exercise_assignment_metadata_partial" in root.warnings for root in result.coverage)
    assert auth.calls.count(exercise_overview_url(BASE, "academy", "444")) == 1
    assert len(result.objects["exc:444"].paths) == 2


def test_links_outside_installation_path_are_not_discovered():
    assert normalize_object_link(
        "/other/go/exc/444", f"{BASE}/installation/ilias.php",
        f"{BASE}/installation", "academy",
    ) is None
    assert normalize_object_link(
        "/installation/go/exc/444", f"{BASE}/installation/ilias.php",
        f"{BASE}/installation", "academy",
    ) is not None

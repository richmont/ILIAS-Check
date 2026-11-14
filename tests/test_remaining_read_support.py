"""Synthetic regressions for remaining layouts found in authorized live reads."""

from pathlib import Path
import json

from jsonschema import Draft202012Validator, FormatChecker
import pytest

from ilias_check.config import CollectorConfig
from ilias_check.exercises import ExerciseAssignment, read_assignment_detail
from ilias_check.inventory import build_inventory
from ilias_check.links import normalize_object_link
from ilias_check.parser import parse_repository_page, resolve_legacy_object_ref
from ilias_check.read_routes import exercise_overview_url
from ilias_check.transport import SafeTransport, TransportError
from ilias_check.traversal import RepositoryCrawler


BASE = "https://ilias.example.edu"


def config():
    return CollectorConfig.from_mapping({
        "ILIAS_BASE_URL": BASE, "ILIAS_CLIENT_ID": "academy",
        "ILIAS_USER": "synthetic-user", "ILIAS_PASS": "synthetic-password",
        "ILIAS_PENDING_ROOTS": "1001",
    })


def goto(kind, ref_id):
    return f"{BASE}/goto.php?target={kind}_{ref_id}&client_id=academy"


def legacy(ref_id):
    return f"{BASE}/ilias.php?baseClass=ilRepositoryGUI&ref_id={ref_id}&client_id=academy"


class OfflineAuth:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        return type("Response", (), {"url": url, "text": self.pages[url]})()


def test_learning_module_goto_follows_only_the_validated_resume_redirect():
    destination = f"{BASE}/ilias.php?baseClass=illmpresentationgui&cmd=resume&ref_id=901"

    class Session:
        def __init__(self):
            self.calls = []

        def request(self, method, url, **kwargs):
            self.calls.append(url)
            if len(self.calls) == 1:
                return type("Response", (), {"status_code": 302, "headers": {"Location": destination}})()
            return type("Response", (), {"status_code": 200, "headers": {}, "text": "<main>Module</main>"})()

    session = Session()
    transport = SafeTransport(config(), session=session)
    assert transport.get(goto("lm", "901")).text == "<main>Module</main>"
    assert session.calls == [goto("lm", "901"), destination]
    ref = normalize_object_link(destination, destination, BASE, "academy")
    assert ref.object_type == "learning_module"


@pytest.mark.parametrize("suffix", [
    "&cmd=save", "&cmd[finish]=1", "&lsocmd=lsonext", "&lsov=9", "&lsoni=9",
    "&ref_id=902", "&obj_id=902", "&rtoken=secret", "&cmdClass=ilObjExerciseGUI",
])
def test_module_resume_allowlist_rejects_other_actions(suffix):
    transport = SafeTransport(config())
    try:
        with pytest.raises(TransportError):
            transport._validate_read_url(
                f"{BASE}/ilias.php?baseClass=illmpresentationgui&cmd=resume&ref_id=901" + suffix
            )
    finally:
        transport.close()


@pytest.mark.parametrize("kind,expected", [("tst", "test"), ("fold", "folder"), ("lso", "learning_sequence")])
def test_generic_reference_uses_own_header_icon(kind, expected):
    ref = normalize_object_link(legacy("456"), legacy("1001"), BASE, "academy")
    html = f'<img id="headerimage" src="/images/icon_{kind}.svg"><main></main>'
    resolved = resolve_legacy_object_ref(ref, legacy("456"), html, BASE, "academy")
    assert resolved.object_type == expected
    assert resolved.ref_id == "456"


def test_header_resolution_rejects_conflicts_and_other_object_ids():
    ref = normalize_object_link(legacy("456"), legacy("1001"), BASE, "academy")
    html = '<img id="headerimage" src="/images/icon_tst.svg">'
    assert resolve_legacy_object_ref(ref, legacy("999"), html, BASE, "academy") is None
    assert resolve_legacy_object_ref(
        ref, legacy("456"), html + '<main data-ref-id="456" data-object-type="fold"></main>', BASE, "academy"
    ) is None
    assert resolve_legacy_object_ref(
        ref, legacy("456"), '<main><img src="/images/icon_tst.svg"></main>', BASE, "academy"
    ) is None


def test_later_legacy_links_do_not_recreate_resolved_alias_objects():
    pages = {
        goto("fold", "1001"): '<main><a href="/go/fold/1002">First</a><a href="/go/fold/1003">Second</a></main>',
        goto("fold", "1002"): f'<main><a href="{legacy("456")}">Shared</a></main>',
        goto("fold", "1003"): f'<main><a href="{legacy("456")}">Shared</a></main>',
        legacy("456"): '<img id="headerimage" src="/images/icon_fold.svg"><main></main>',
    }
    auth = OfflineAuth(pages)
    result = RepositoryCrawler(config(), auth).collect()
    assert "obj:456" not in result.objects
    assert len(result.objects["fold:456"].paths) == 2
    assert auth.calls.count(legacy("456")) == 1
    assert result.coverage[0].complete
    assert result.coverage[0].objects_discovered == 4


DETAIL = '''<main><div class="panel panel-primary">
  <div class="panel-heading"><span>Beendet am: 2. November 2026, 19:25</span></div>
  <div class="panel panel-sub"><div class="panel-heading"><h3 class="ilBlockHeader">Arbeitsanweisung</h3></div>
    <div class="panel-body">Originale Anleitung. Selbsttest.</div></div>
  <div class="panel panel-sub"><div class="panel-heading"><h3 class="ilBlockHeader">Einreichung</h3></div>
    <div class="panel-body">Abgegebene Dateien Sie haben noch keine Datei abgegeben. Datum der letzten Abgabe Bisher keine Abgabe</div></div>
</div></main>'''


def test_closed_assignment_details_confirm_empty_delivery_without_download():
    unit = ExerciseAssignment("41", "Synthetic", delivery_type="file_upload")
    assert read_assignment_detail(unit, DETAIL, "444", f"{BASE}/ilias.php", BASE)
    assert unit.instructions == "Originale Anleitung. Selbsttest."
    assert unit.availability == "closed"
    assert unit.submitted_files == []
    assert unit.submission_source == "assignment_detail_explicit_empty"
    assert unit.submission_url is None


def test_blank_assignment_detail_is_unknown_and_instructions_cannot_prove_empty_delivery():
    unit = ExerciseAssignment("41", "Synthetic", delivery_type="file_upload")
    assert not read_assignment_detail(unit, '<main><div class="panel-primary"><div class="panel-body"></div></div></main>', "444", f"{BASE}/ilias.php", BASE)
    assert unit.submitted_files is None
    assert read_assignment_detail(unit, DETAIL.replace('>Einreichung<', '>Instructions<'), "444", f"{BASE}/ilias.php", BASE)
    assert unit.submitted_files is None


@pytest.mark.parametrize("detail,complete,warning", [
    (DETAIL, True, None),
    ('<main><div class="panel-primary"><div class="panel-body"></div></div></main>', False, "assignment_detail_unavailable"),
])
def test_crawler_follows_exact_detail_when_overview_omits_delivery_screen(detail, complete, warning):
    presentation = f"{BASE}/ilias.php?baseClass=ilExerciseHandlerGUI&cmdClass=ilAssignmentPresentationGUI&ref_id=444&ass_id=41&mode=all&from_overview=1&cmdNode=xn:r8"
    auth = OfflineAuth({
        goto("fold", "1001"): '<main><a href="/go/exc/444">Exercise</a></main>',
        goto("exc", "444"): '<main>Exercise</main>',
        exercise_overview_url(BASE, "academy", "444"): f'<main><li><a href="{presentation}">Blatt</a> Type Datei</li></main>',
        presentation: detail,
    })
    result = RepositoryCrawler(config(), auth).collect()
    assert result.coverage[0].complete is complete
    assignment = result.objects["exc:444"].assignments[0]
    assert assignment["warnings"] == ([warning] if warning else [])
    assert auth.calls[-1] == presentation
    schema = json.loads((Path(__file__).parents[1] / "schemas/inventory-v1.schema.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(build_inventory(result, config()))


def test_lso_workflow_preserves_metadata_without_inventing_references_or_progression():
    html = '''<main><h1>Synthetic sequence</h1></main><aside><div class="ilLSOLearnerView">
      <ul class="il-workflow"><li class="il-workflow-step active in-progress">
        <span class="il-workflow-step-label"><button data-action="#">Original step</button></span>
        <span class="il-workflow-step-description">Original description</span>
      </li></ul></div></aside>'''
    page = parse_repository_page(html, goto("lso", "555"), BASE, "academy", "learning_sequence")
    assert page.sequence_outline == [{"title": "Original step", "description": "Original description", "availability": "active", "progress": "in-progress"}]
    assert page.sequence_resolution == "unresolved"
    assert page.sequence_steps == []
    ref = normalize_object_link(goto("lso", "555"), BASE, BASE, "academy")
    assert ref.object_type == "learning_sequence"


@pytest.mark.parametrize("key", ["lsocmd", "lsov", "lsoni", "lson", "lsop"])
def test_sequence_action_parameters_are_not_passive_links(key):
    url = goto("lso", "555") + f"&{key}=next"
    assert normalize_object_link(url, BASE, BASE, "academy") is None
    transport = SafeTransport(config())
    try:
        with pytest.raises(TransportError):
            transport._validate_read_url(url)
    finally:
        transport.close()

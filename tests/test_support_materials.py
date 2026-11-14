from dataclasses import asdict, replace
import json
from pathlib import Path
from urllib.parse import urlencode, urlsplit, parse_qs

from bs4 import BeautifulSoup
from jsonschema import Draft202012Validator, FormatChecker
import pytest

from ilias_check.config import CollectorConfig, ConfigurationError
from ilias_check.exercises import ExerciseAssignment, parse_exercise_assignments, read_assignment_detail
from ilias_check.inventory import build_inventory
from ilias_check.materials import document_reference, extract_assignment_materials, select_materials
from ilias_check.policy import ClassificationPolicy
from ilias_check.read_routes import exercise_overview_url
from ilias_check.results import classify_inventory
from ilias_check.transport import SafeTransport, TransportError
from ilias_check.traversal import RepositoryCrawler
from test_classified_inventory import obj, snapshot, unit


BASE = "https://ilias.example.edu"
ROOT = Path(__file__).parents[1]
VALIDATOR = Draft202012Validator(
    json.loads((ROOT / "schemas/inventory-v1.schema.json").read_text()), format_checker=FormatChecker(),
)


def attachment(ass_id="41", file="worksheet.pdf", node="xn:r8", **changes):
    return BASE + "/ilias.php?" + urlencode({
        "baseClass": "ilrepositorygui", "cmdClass": "ilExSubmissionGUI", "cmd": "downloadFile",
        "ref_id": "444", "ass_id": ass_id, "file": file, "cmdNode": node, **changes,
    })


def reference(href=None, title="Worksheet", association="assignment_attachment", role="support", section="Dateien"):
    return document_reference(
        href or attachment(), title, "444", "41", BASE + "/ilias.php?ref_id=444&ass_id=41",
        BASE, "academy", association, role, section,
    )


def panel(section, content):
    return f'<div class="panel-sub"><h3 class="ilBlockHeader">{section}</h3><div class="panel-body">{content}</div></div>'


def detail(*panels):
    return '<main><div class="panel-primary">' + "".join(panels) + '</div></main>'


def test_attachment_identity_uses_platform_key_and_unit_not_filename_similarity():
    first = reference()
    reordered = reference(attachment(node="xn:different", mode="all"))
    second_unit = document_reference(attachment("42"), "worksheet.pdf", "444", "42", BASE + "/ilias.php", BASE, "academy", "assignment_attachment", "support", "Dateien")
    assert first["document_id"] == reordered["document_id"]
    assert first["document_id"] != second_unit["document_id"]
    assert "worksheet.pdf" not in first["document_id"]
    assert first["source_location"]["assignment_id"] == "41"
    assert first["source_location"]["section"] == "Dateien"
    assert first["state"] == "metadata_only"
    assert not first["selected_for_support"]


def test_shared_file_reference_has_one_identity_across_units():
    href = BASE + "/goto.php?target=file_700_download"
    first = reference(href, association="instruction_link")
    second = document_reference(href, "Other source title", "445", "42", BASE + "/ilias.php?ref_id=445", BASE, "academy", "assignment_attachment", "support", "Dateien")
    assert first["document_id"] == second["document_id"] == "file:700"
    assert first["source_location"] != second["source_location"]


def test_per_unit_extraction_retains_instruction_links_and_attachment_labels():
    html = f'''<main>
      <div class="ilAssignment" data-ass-id="41">
        <div data-material-section="Arbeitsanweisung"><a href="/goto.php?target=file_700_download">Original worksheet</a></div>
        <div data-material-section="Dateien"><div class="row"><div class="control-label">Original Anhang.pdf</div><div><a href="{attachment()}">Download</a></div></div></div>
      </div>
      <div class="ilAssignment" data-ass-id="42"><div data-material-section="Dateien"><a href="{attachment('42')}">Other unit</a></div></div>
    </main>'''
    documents = extract_assignment_materials(BeautifulSoup(html, "html.parser").main, "444", "41", BASE + "/ilias.php", BASE, "academy")
    assert [(x["title"], x["association"]) for x in documents] == [
        ("Original worksheet", "instruction_link"), ("Original Anhang.pdf", "assignment_attachment"),
    ]
    assert all(x["source_location"]["assignment_id"] == "41" for x in documents)


@pytest.mark.parametrize("section,role", [
    ("Dateien", "support"), ("Musterlösung", "model_answer"),
    ("Feedback", "feedback"), ("Einreichung", "learner_submission"),
    ("Unrecognized files", "unknown"),
])
def test_platform_sections_determine_role_and_conservative_selection(section, role):
    html = detail(panel(section, '<a href="/goto.php?target=file_700_download">Original.pdf</a>'))
    parsed = ExerciseAssignment("41", "Synthetic")
    read_assignment_detail(parsed, html, "444", BASE + "/ilias.php", BASE, "academy")
    assert len(parsed.support_documents) == 1
    document = parsed.support_documents[0]
    assert document["role"] == role
    negative = {document["document_id"]} if role in {"model_answer", "feedback", "learner_submission"} else set()
    selected = select_materials([document], "pending", False, negative)[0]
    assert selected["selected_for_support"] is (role == "support")
    if role == "unknown":
        assert "document_role_unknown" in selected["reason_codes"]


def test_negative_outer_section_wins_over_nested_instruction_markup():
    html = detail(panel("Musterlösung", '<div class="ilc_text_block"><a href="/goto.php?target=file_700_download">Original.pdf</a></div>'))
    documents = extract_assignment_materials(BeautifulSoup(html, "html.parser").main, "444", "41", BASE + "/ilias.php", BASE, "academy")
    assert documents[0]["role"] == "model_answer"


def test_unknown_section_is_not_promoted_by_generic_text_block_styling():
    html = detail(panel("Unrecognized files", '<div class="ilc_text_block"><a href="/goto.php?target=file_700_download">Original.pdf</a></div>'))
    documents = extract_assignment_materials(BeautifulSoup(html, "html.parser").main, "444", "41", BASE + "/ilias.php", BASE, "academy")
    assert documents[0]["role"] == "unknown"
    assert not select_materials(documents, "pending", False, set())[0]["selected_for_support"]


def test_explicit_answer_label_and_feedback_command_are_negative_even_in_files_section():
    labeled = reference(title="Musterlösung.pdf")
    command = attachment(cmd="downloadGlobalFeedbackFile")
    linked = reference(command, title="Download")
    assert labeled["role"] == linked["role"] == "model_answer"


@pytest.mark.parametrize("href", [
    attachment(ass_id="42"), attachment(ref_id="445"), attachment(file="../private.pdf"),
    attachment() + "&rtoken=secret", attachment() + "&cmd[deleteDelivered]=1",
    attachment().replace("https://", "https://user:password@"),
    attachment(cmd="uploadForm"), attachment(cmd="downloadFile") + "&ass_id=99",
    attachment(file="..%2Fprivate.pdf"),
    attachment(client_id="other-client"),
])
def test_unsafe_or_wrong_unit_attachment_routes_are_not_associated(href):
    assert reference(href) is None


def test_external_instruction_link_is_manual_only_and_has_no_external_download_url():
    material = reference("https://external.example/worksheet.pdf", association="instruction_link")
    assert material["download_url"] is None
    assert material["source_url"].startswith(BASE)
    assert "off_origin_instruction_link" in material["reason_codes"]
    assert not select_materials([material], "pending", False, set())[0]["selected_for_support"]


def test_document_object_link_does_not_invent_a_download_command():
    material = reference("/goto.php?target=file_700", association="instruction_link")
    assert material["document_id"] == "file:700"
    assert material["download_url"] is None
    assert material["state"] == "unavailable"


def test_document_download_link_drops_fragment_material():
    material = reference("/goto.php?target=file_700_download#token=secret", association="instruction_link")
    assert "secret" not in json.dumps(material)


def test_static_instruction_link_cannot_escape_installation_through_encoded_parent_path():
    assert document_reference(
        BASE + "/installation/%2e%2e/private.pdf", "Worksheet", "444", "41",
        BASE + "/installation/ilias.php", BASE + "/installation", "academy",
        "instruction_link", "support", "instructions",
    ) is None


def test_instruction_activity_link_is_not_a_document():
    assert reference("/goto.php?target=exc_999", association="instruction_link") is None


@pytest.mark.parametrize("parameter", ["CMD=save", "cmd[deleteDelivered]=1", "lsocmd=next"])
def test_plain_instruction_links_never_export_manual_action_urls(parameter):
    assert reference(BASE + "/worksheet.pdf?" + parameter, association="instruction_link") is None


@pytest.mark.parametrize("status", ["submitted", "excluded", "closed_without_submission", "unknown", "not_yet_open"])
def test_non_pending_units_keep_metadata_without_selection(status):
    material = select_materials([reference()], status, False, set())[0]
    assert not material["selected_for_support"]
    assert "pending_not_confirmed" in material["reason_codes"]


def test_shared_document_negative_evidence_prevents_selection_for_another_unit():
    positive = reference("/goto.php?target=file_700_download")
    negative = reference("/goto.php?target=file_700_download", section="Musterlösung", role="model_answer")
    source = snapshot([obj(assignments=[unit(support_documents=[positive]), unit("42", support_documents=[negative])])])
    result = classify_inventory(source)
    VALIDATOR.validate(result)
    assert all(not a["support_documents"][0]["selected_for_support"] for a in result["activities"])
    assert all(a["status"] == "pending" for a in result["activities"])
    assert all("known_answer_material" in a["support_documents"][0]["reason_codes"] for a in result["activities"])


def test_context_is_opt_in_and_limited_to_immediate_folder_in_same_root():
    def folder(ref_id, path, file_id):
        return obj(ref_id, "folder", paths=[{"root_id": "1001", "path": path}],
                   type_code="fold", sequence_resolution=None,
                   url=f"{BASE}/goto.php?target=fold_{ref_id}&client_id=academy",
                   documents=[{"ref_id": file_id, "title": "Unrelated nearby.pdf", "url": f"{BASE}/goto.php?target=file_{file_id}_download"}])

    exercise = obj(paths=[{"root_id": "1001", "path": ["Material", "Exercise"]}])
    source = snapshot([
        exercise, folder("1001", [], "800"), folder("1002", ["Material"], "900"), folder("1003", ["Other"], "901"),
    ])
    assert classify_inventory(source)["activities"][0]["support_documents"] == []
    policy = ClassificationPolicy.from_mapping({"ILIAS_PENDING_INCLUDE_CONTEXTUAL": "true"})
    result = classify_inventory(source, policy)
    VALIDATOR.validate(result)
    material = result["activities"][0]["support_documents"][0]
    assert len(result["activities"][0]["support_documents"]) == 1
    assert material["document_id"] == "file:900"
    assert material["association"] == "contextual"
    assert material["role"] == "unknown" and not material["selected_for_support"]
    assert material["source_location"]["container_id"] == "1002"
    assert material["source_location"]["path"] == ["Material"]
    assert "document_role_unknown" in material["reason_codes"]


def test_contextual_selection_requires_both_opt_in_and_confirmed_role():
    material = {**reference(), "association": "contextual"}
    assert not select_materials([material], "pending", False, set())[0]["selected_for_support"]
    assert select_materials([material], "pending", True, set())[0]["selected_for_support"]
    assert not select_materials([{**material, "role": "unknown"}], "pending", True, set())[0]["selected_for_support"]


def test_unresolved_sequence_titles_have_no_fabricated_ids_or_download_routes():
    sequence = obj("555", "learning_sequence", sequence_outline=[
        {"title": "Original worksheet.pdf", "description": "", "availability": "available", "progress": "not-started"},
        {"title": "Upload results", "description": "", "availability": "active", "progress": "in-progress"},
    ])
    result = classify_inventory(snapshot([sequence]))
    VALIDATOR.validate(result)
    material = result["activities"][0]["support_documents"][0]
    assert len(result["activities"][0]["support_documents"]) == 1
    assert material["document_id"] is None and material["download_url"] is None
    assert material["source_url"] == sequence["url"]
    assert material["state"] == "unavailable" and not material["selected_for_support"]
    assert result["activities"][0]["status"] == "unknown"


def test_material_only_differences_do_not_make_duplicate_activity_state_contradictory():
    source = snapshot([obj(), obj(assignments=[unit(support_documents=[reference()])])])
    result = classify_inventory(source)
    assert len(result["activities"]) == 1
    assert result["activities"][0]["status"] == "pending"
    assert len(result["activities"][0]["support_documents"]) == 1


@pytest.mark.parametrize("value", ["yes", "1", "invalid"])
def test_invalid_contextual_opt_in_is_rejected(value):
    with pytest.raises(ValueError, match="ILIAS_PENDING_INCLUDE_CONTEXTUAL"):
        ClassificationPolicy.from_mapping({"ILIAS_PENDING_INCLUDE_CONTEXTUAL": value})


@pytest.mark.parametrize("detail_available", [True, False])
def test_crawler_reads_material_metadata_without_fetching_files_or_changing_classification(detail_available):
    config = CollectorConfig.from_mapping({
        "ILIAS_BASE_URL": BASE, "ILIAS_CLIENT_ID": "academy", "ILIAS_USER": "synthetic-user",
        "ILIAS_PASS": "synthetic-password", "ILIAS_PENDING_ROOTS": "1001",
    })
    presentation = f"{BASE}/ilias.php?baseClass=ilrepositorygui&cmdClass=ilAssignmentPresentationGUI&ref_id=444&ass_id=41"
    screen = f"{BASE}/ilias.php?baseClass=ilrepositorygui&cmdClass=ilExSubmissionFileGUI&cmd=submissionScreen&ref_id=444&ass_id=41"
    overview = f'''<main><li><a href="{presentation}">Original</a>
        <span class="il-item-property-name">Type</span><span class="il-item-property-value">Datei</span>
        <a href="{screen}">Files</a></li></main>'''
    pages = {
        f"{BASE}/goto.php?target=fold_1001&client_id=academy": '<main><a href="/go/exc/444">Exercise</a></main>',
        f"{BASE}/goto.php?target=exc_444&client_id=academy": '<main>Exercise</main>',
        exercise_overview_url(BASE, "academy", "444"): overview,
        screen: f'<main><table data-submission-list></table><a href="{screen.replace("submissionScreen", "uploadForm")}">Upload</a></main>',
    }
    if detail_available:
        pages[presentation] = detail(
            panel("Dateien", f'<a href="{attachment()}">Original worksheet.pdf</a>'),
            panel("Musterlösung", '<a href="/goto.php?target=file_701_download">Answer</a>'),
        )

    class Auth:
        def __init__(self):
            self.calls = []

        def get(self, url):
            self.calls.append(url)
            return type("Response", (), {"text": pages[url], "url": url})()

    auth = Auth()
    result = RepositoryCrawler(config, auth).collect()
    inventory = build_inventory(result, config)
    VALIDATOR.validate(inventory)
    activity = inventory["activities"][0]
    assert activity["status"] == "pending"
    assert inventory["classification"]["complete"] is True
    assert presentation in auth.calls
    assert all(parse_qs(urlsplit(url).query).get("cmd", [""])[0] not in {"downloadFile", "downloadGlobalFeedbackFile", "uploadForm"} for url in auth.calls)
    assert not any("target=file_" in url for url in auth.calls)
    if detail_available:
        assert [m["role"] for m in activity["support_documents"]] == ["support", "model_answer"]
        assert [m["selected_for_support"] for m in activity["support_documents"]] == [True, False]
    else:
        assert activity["support_warnings"] == ["support_detail_read_failed"]


def test_metadata_download_urls_remain_forbidden_in_collector_transport():
    config = CollectorConfig.from_mapping({
        "ILIAS_BASE_URL": BASE, "ILIAS_CLIENT_ID": "academy", "ILIAS_USER": "synthetic-user",
        "ILIAS_PASS": "synthetic-password", "ILIAS_PENDING_ROOTS": "1001",
    })
    transport = SafeTransport(config)
    try:
        with pytest.raises(TransportError):
            transport._validate_read_url(reference()["download_url"])
    finally:
        transport.close()


def test_checked_in_example_validates_and_distinguishes_confirmed_contextual_and_answer_material():
    schema = json.loads((ROOT / "schemas/inventory-v1.schema.json").read_text())
    example = json.loads((ROOT / "examples/support-associations.json").read_text())
    validator = Draft202012Validator({
        "$defs": schema["$defs"], "type": "array", "items": {"$ref": "#/$defs/supportDocument"},
    }, format_checker=FormatChecker())
    documents = example["support_documents"]
    validator.validate(documents)
    assert [d["association"] for d in documents] == ["assignment_attachment", "instruction_link", "contextual", "assignment_attachment"]
    assert [d["selected_for_support"] for d in documents] == [True, True, False, False]
    assert documents[0]["document_id"] == documents[1]["document_id"]
    assert documents[3]["role"] == "model_answer"
    assert "example.edu" in json.dumps(example)

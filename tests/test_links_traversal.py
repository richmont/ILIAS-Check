from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from ilias_check.auth import AuthError
from ilias_check.config import CollectorConfig
from ilias_check.links import canonical_object_url, normalize_object_link
from ilias_check.parser import parse_repository_page, resolve_legacy_object_ref
from ilias_check.traversal import RepositoryCrawler


FIXTURES = Path(__file__).parent / "fixtures" / "repository"
BASE = "https://ilias.example.edu"


def make_config(roots: str = "1001", **extra: str) -> CollectorConfig:
    return CollectorConfig.from_mapping(
        {
            "ILIAS_BASE_URL": BASE,
            "ILIAS_CLIENT_ID": "academy",
            "ILIAS_USER": "synthetic-user",
            "ILIAS_PASS": "synthetic-password",
            "ILIAS_PENDING_ROOTS": roots,
            **extra,
        }
    )


def test_normalizes_modern_path_and_legacy_reference_link() -> None:
    modern = normalize_object_link(
        "/goto.php/fold/123",
        f"{BASE}/ilias.php",
        BASE,
        "academy",
    )
    legacy = normalize_object_link(
        "/ilias.php?baseClass=ilRepositoryGUI&ref_id=456",
        f"{BASE}/ilias.php",
        BASE,
        "academy",
    )
    assert modern is not None and modern.object_type == "folder"
    assert modern.url == canonical_object_url(BASE, "academy", "fold", "123")
    assert legacy is not None and legacy.ref_id == "456"
    assert legacy.url == f"{BASE}/goto.php?target=obj_456&client_id=academy"
    assert legacy.read_url == (
        f"{BASE}/ilias.php?baseClass=ilRepositoryGUI&ref_id=456&client_id=academy"
    )


def test_legacy_read_url_is_rebuilt_from_validated_reference_only() -> None:
    legacy = normalize_object_link(
        "/ilias.php?baseClass=ilRepositoryGUI&ref_id=456&view=ignored",
        f"{BASE}/ilias.php",
        BASE,
        "academy",
    )
    assert legacy is not None and legacy.ref_id == "456"
    assert legacy.read_url == (
        f"{BASE}/ilias.php?baseClass=ilRepositoryGUI&ref_id=456&client_id=academy"
    )


def test_normalizer_allows_empty_default_cmd_but_rejects_actions() -> None:
    ref = normalize_object_link(
        "/ilias.php?baseClass=ilRepositoryGUI&ref_id=456&cmd=",
        f"{BASE}/ilias.php",
        BASE,
        "academy",
    )
    assert ref is not None and ref.ref_id == "456"
    assert normalize_object_link(
        "/ilias.php?baseClass=ilRepositoryGUI&ref_id=456&cmd[next]=",
        f"{BASE}/ilias.php",
        BASE,
        "academy",
    ) is None
    assert normalize_object_link(
        "/ilias.php?baseClass=ilRepositoryGUI&ref_id=456&cmd=infoScreen",
        f"{BASE}/ilias.php",
        BASE,
        "academy",
    ).read_url == (
        f"{BASE}/ilias.php?baseClass=ilRepositoryGUI&ref_id=456"
        "&client_id=academy&cmd=infoScreen"
    )


@pytest.mark.parametrize(
    "href",
    [
        "/ilias.php?baseClass=ilRepositoryGUI&ref_id=0",
        "/ilias.php?baseClass=ilRepositoryGUI&ref_id=abc",
        "https://external.example/ilias.php?baseClass=ilRepositoryGUI&ref_id=456",
        "/ilias.php?baseClass=ilRepositoryGUI&ref_id=456&sesskey=secret",
        "/ilias.php?baseClass=ilRepositoryGUI&ref_id=456&cmd=next",
    ],
)
def test_rejects_unsafe_legacy_repository_references(href: str) -> None:
    assert normalize_object_link(href, f"{BASE}/ilias.php", BASE, "academy") is None


def test_resolves_legacy_type_from_matching_safe_final_url() -> None:
    legacy = normalize_object_link(
        "/ilias.php?baseClass=ilRepositoryGUI&ref_id=456",
        f"{BASE}/ilias.php",
        BASE,
        "academy",
    )
    assert legacy is not None
    resolved = resolve_legacy_object_ref(
        legacy,
        f"{BASE}/goto.php?target=fold_456&client_id=academy",
        "<main><h1>Folder</h1></main>",
        BASE,
        "academy",
    )
    assert resolved is not None
    assert resolved.type_code == "fold"
    assert resolved.object_type == "folder"
    assert resolved.url == page_url("fold", "456")


def test_resolves_legacy_type_from_matching_passive_page_metadata() -> None:
    legacy = normalize_object_link(
        "/ilias.php?baseClass=ilRepositoryGUI&ref_id=456",
        f"{BASE}/ilias.php",
        BASE,
        "academy",
    )
    assert legacy is not None
    resolved = resolve_legacy_object_ref(
        legacy,
        legacy.read_url or "",
        '<main data-ref-id="456" data-object-type="exc"><h1>Exercise</h1></main>',
        BASE,
        "academy",
    )
    assert resolved is not None
    assert resolved.type_code == "exc"
    assert resolved.object_type == "exercise"


@pytest.mark.parametrize(
    ("response_url", "html"),
    [
        (
            f"{BASE}/goto.php?target=fold_999",
            '<main data-ref-id="456" data-object-type="exc"></main>',
        ),
        (
            f"{BASE}/goto.php?target=unknown_456",
            "<main></main>",
        ),
        (
            f"{BASE}/download.php?target=fold_456",
            "<main></main>",
        ),
        (
            f"{BASE}/ilias.php?baseClass=ilRepositoryGUI&ref_id=456",
            '<main data-ref-id="456" data-object-type="unknown"></main>',
        ),
        (
            f"{BASE}/ilias.php?baseClass=ilRepositoryGUI&ref_id=456",
            '<nav data-ref-id="456" data-object-type="fold"></nav>',
        ),
    ],
)
def test_rejects_untrusted_or_ambiguous_type_evidence(
    response_url: str, html: str
) -> None:
    legacy = normalize_object_link(
        "/ilias.php?baseClass=ilRepositoryGUI&ref_id=456",
        f"{BASE}/ilias.php",
        BASE,
        "academy",
    )
    assert legacy is not None
    assert (
        resolve_legacy_object_ref(legacy, response_url, html, BASE, "academy")
        is None
    )


def test_rejects_off_origin_and_session_bearing_links() -> None:
    for href in (
        "https://external.example/goto.php?target=fold_1",
        "/goto.php?target=fold_1&sesskey=secret",
        "/goto.php?target=fold_1&token=secret",
        "/goto.php?target=fold_1&cmd=next",
    ):
        assert normalize_object_link(href, f"{BASE}/ilias.php", BASE, "academy") is None


def test_parser_uses_content_links_and_preserves_original_language() -> None:
    page = parse_repository_page(
        (FIXTURES / "root-with-navigation.html").read_text(),
        f"{BASE}/goto.php?target=fold_1001",
        BASE,
        "academy",
        "folder",
    )
    assert page.title == "Pflegekurs Übersicht"
    assert page.instructions == "Bitte bearbeiten Sie die folgende Aufgabe."
    assert [link.title for link in page.links] == ["Unterordner", "Material"]
    assert all("900" not in link.ref.ref_id for link in page.links)


def test_german_titles_instructions_and_filenames_are_not_translated() -> None:
    page = parse_repository_page(
        '<main><h1>Dehydratationsprophylaxe</h1>'
        '<div class="ilc_text_block">Lesen Sie zuerst die Arbeitsanweisung.</div>'
        '<div class="ilContainerListItem"><a href="/goto.php?target=file_77">'
        "Übungsbogen Ödemprophylaxe.pdf</a></div></main>",
        f"{BASE}/goto.php?target=seq_12",
        BASE,
        "academy",
        "learning_sequence",
    )
    assert page.title == "Dehydratationsprophylaxe"
    assert page.instructions == "Lesen Sie zuerst die Arbeitsanweisung."
    assert page.links[0].title == "Übungsbogen Ödemprophylaxe.pdf"
    assert page.sequence_resolution == "unresolved"
    assert "translation" not in page.instructions.lower()


@dataclass
class Response:
    text: str
    url: str


class FakeAuthenticator:
    def __init__(self, pages: dict[str, str], fail_after: int | None = None) -> None:
        self.pages = pages
        self.calls: list[str] = []
        self.fail_after = fail_after

    def get(self, url: str) -> Response:
        self.calls.append(url)
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise AuthError("synthetic bounded request budget exhausted")
        try:
            return Response(self.pages[url], url)
        except KeyError:
            raise AssertionError(f"Unexpected canonical object request: {url}") from None


def page_url(type_code: str, ref_id: str) -> str:
    return canonical_object_url(BASE, "academy", type_code, ref_id)


def test_cycle_stops_and_object_is_fetched_once() -> None:
    root_url = page_url("fold", "1001")
    child_url = page_url("fold", "1002")
    seq_url = page_url("seq", "2001")
    file_url = page_url("file", "1003")
    auth = FakeAuthenticator(
        {
            root_url: (FIXTURES / "root-with-navigation.html").read_text(),
            child_url: (FIXTURES / "folder-1002.html").read_text(),
            seq_url: (FIXTURES / "sequence-empty.html").read_text(),
            file_url: "<main><h1>Arbeitsblatt</h1><a href='/download.php?file_id=3'>Download</a></main>",
        }
    )
    result = RepositoryCrawler(make_config(), auth).collect()
    assert len(auth.calls) == 3
    assert len(set(auth.calls)) == 3
    assert not result.coverage[0].complete
    assert "cycle_detected" in result.coverage[0].warnings
    assert "unresolved_learning_sequence" in result.coverage[0].warnings
    assert result.objects["seq:2001"].url_kind == "sequence_entry"
    assert result.objects["seq:2001"].sequence_resolution == "unresolved"
    assert result.objects["seq:2001"].warnings
    assert any(
        document["ref_id"] == "1003"
        for document in result.objects["fold:1001"].documents
    )
    assert all("target=file_1003" not in url for url in auth.calls)
    assert all("download.php" not in url for url in auth.calls)


def test_sequence_passive_metadata_is_visible_without_transition_request() -> None:
    root_url = page_url("fold", "1001")
    sequence_url = page_url("seq", "2001")
    step_url = page_url("exc", "3001")
    auth = FakeAuthenticator(
        {
            root_url: '<main><h1>Root</h1><div class="ilContainerListItem"><a href="/goto.php?target=seq_2001">Sequence</a></div></main>',
            sequence_url: (
                FIXTURES / "sequence-passive-step.html"
            ).read_text(),
            step_url: "<main><h1>Frau Braun analysieren</h1></main>",
        }
    )
    result = RepositoryCrawler(make_config(), auth).collect()
    sequence = result.objects["seq:2001"]
    assert sequence.sequence_resolution == "resolved"
    assert sequence.sequence_steps[0]["ref_id"] == "3001"
    assert "next" not in " ".join(auth.calls)
    assert all("9999" not in url for url in auth.calls)


def test_overlapping_roots_preserve_paths_without_duplicate_fetch() -> None:
    root1 = page_url("fold", "1001")
    root2 = page_url("fold", "1002")
    child = page_url("fold", "1003")
    auth = FakeAuthenticator(
        {
            root1: '<main><h1>R1</h1><div class="ilContainerListItem"><a href="/goto.php?target=fold_1003">Shared</a></div></main>',
            root2: '<main><h1>R2</h1><div class="ilContainerListItem"><a href="/goto.php?target=fold_1003">Shared</a></div></main>',
            child: "<main><h1>Shared</h1></main>",
        }
    )
    result = RepositoryCrawler(make_config("1001,1002"), auth).collect()
    assert auth.calls.count(child) == 1
    paths = result.objects["fold:1003"].paths
    assert {path["root_id"] for path in paths} == {"1001", "1002"}


def test_multiple_paths_within_root_are_preserved() -> None:
    root = page_url("fold", "1001")
    left = page_url("fold", "1002")
    right = page_url("fold", "1003")
    shared = page_url("fold", "1004")
    auth = FakeAuthenticator(
        {
            root: '<main><h1>Root</h1>'
            '<div class="ilContainerListItem"><a href="/goto.php?target=fold_1002">Left</a></div>'
            '<div class="ilContainerListItem"><a href="/goto.php?target=fold_1003">Right</a></div></main>',
            left: '<main><h1>Left</h1><div class="ilContainerListItem"><a href="/goto.php?target=fold_1004">Shared</a></div></main>',
            right: '<main><h1>Right</h1><div class="ilContainerListItem"><a href="/goto.php?target=fold_1004">Shared</a></div></main>',
            shared: "<main><h1>Shared</h1></main>",
        }
    )
    result = RepositoryCrawler(make_config(), auth).collect()
    assert auth.calls.count(shared) == 1
    paths = result.objects["fold:1004"].paths
    assert {tuple(path["path"]) for path in paths} == {
        ("Left", "Shared"),
        ("Right", "Shared"),
    }


def test_max_depth_marks_partial_coverage() -> None:
    root_url = page_url("fold", "1001")
    child_url = page_url("fold", "1002")
    auth = FakeAuthenticator(
        {
            root_url: '<main><h1>Root</h1><div class="ilContainerListItem"><a href="/goto.php?target=fold_1002">Child</a></div></main>',
            child_url: '<main><h1>Child</h1><div class="ilContainerListItem"><a href="/goto.php?target=fold_1003">Grandchild</a></div></main>',
        }
    )
    result = RepositoryCrawler(
        make_config(ILIAS_PENDING_MAX_DEPTH="1"), auth
    ).collect()
    assert len(auth.calls) == 2
    assert not result.coverage[0].complete
    assert "maximum_depth_reached" in result.coverage[0].warnings


def test_request_budget_failure_is_visible_and_partial() -> None:
    root_url = page_url("fold", "1001")
    child_url = page_url("fold", "1002")
    auth = FakeAuthenticator(
        {
            root_url: '<main><h1>Root</h1><div class="ilContainerListItem"><a href="/goto.php?target=fold_1002">Child</a></div></main>',
        },
        fail_after=1,
    )
    result = RepositoryCrawler(make_config(), auth).collect()
    assert not result.coverage[0].complete
    assert result.errors[0]["category"] == "object_read_failed"
    assert result.errors[0]["object_id"] == "1002"


def test_crawls_readable_unresolved_legacy_reference_and_its_children() -> None:
    root_url = page_url("fold", "1001")
    legacy = normalize_object_link(
        "/ilias.php?baseClass=ilRepositoryGUI&ref_id=456",
        f"{BASE}/ilias.php",
        BASE,
        "academy",
    )
    assert legacy is not None and legacy.read_url is not None
    child_url = page_url("fold", "457")
    auth = FakeAuthenticator(
        {
            root_url: (
                '<main><div class="ilContainerListItem">'
                '<a href="/ilias.php?baseClass=ilRepositoryGUI&ref_id=456">'
                "Legacy container</a></div></main>"
            ),
            legacy.read_url: (
                '<main><h1>Legacy container</h1>'
                '<div class="ilContainerListItem">'
                '<a href="/goto.php?target=fold_457">Child</a>'
                "</div></main>"
            ),
            child_url: "<main><h1>Child</h1></main>",
        }
    )

    result = RepositoryCrawler(make_config(), auth).collect()

    unresolved = result.objects["obj:456"]
    assert unresolved.object_type == "unresolved"
    assert unresolved.url == legacy.read_url
    assert "unresolved_legacy_repository_reference" in unresolved.warnings
    assert auth.calls.count(legacy.read_url) == 1
    assert all("target=obj_456" not in url for url in auth.calls)
    assert "fold:457" in result.objects
    assert not result.coverage[0].complete
    assert "unresolved_legacy_repository_reference" in result.coverage[0].warnings


def test_failed_legacy_reference_read_remains_visible_and_partial() -> None:
    root_url = page_url("fold", "1001")
    legacy = normalize_object_link(
        "/ilias.php?baseClass=ilRepositoryGUI&ref_id=456",
        f"{BASE}/ilias.php",
        BASE,
        "academy",
    )
    assert legacy is not None and legacy.read_url is not None
    auth = FakeAuthenticator(
        {
            root_url: (
                '<main><div class="ilContainerListItem">'
                '<a href="/ilias.php?baseClass=ilRepositoryGUI&ref_id=456">'
                "Legacy container</a></div></main>"
            )
        }
    )

    result = RepositoryCrawler(make_config(), auth).collect()

    assert "obj:456" in result.objects
    assert result.objects["obj:456"].url == legacy.read_url
    assert not result.coverage[0].complete
    assert result.errors[0]["category"] == "object_read_failed"
    assert result.errors[0]["object_id"] == "456"


def test_resolved_legacy_reference_is_promoted_with_its_path() -> None:
    root_url = page_url("fold", "1001")
    legacy = normalize_object_link(
        "/ilias.php?baseClass=ilRepositoryGUI&ref_id=456",
        f"{BASE}/ilias.php",
        BASE,
        "academy",
    )
    assert legacy is not None and legacy.read_url is not None
    auth = FakeAuthenticator(
        {
            root_url: (
                '<main><div class="ilContainerListItem">'
                '<a href="/ilias.php?baseClass=ilRepositoryGUI&ref_id=456">'
                "Legacy container</a></div></main>"
            ),
            legacy.read_url: (
                '<main data-ref-id="456" data-object-type="fold">'
                "<h1>Resolved folder</h1></main>"
            ),
        }
    )

    result = RepositoryCrawler(make_config(), auth).collect()

    assert "obj:456" not in result.objects
    resolved = result.objects["fold:456"]
    assert resolved.object_type == "folder"
    assert resolved.title == "Resolved folder"
    assert resolved.url == page_url("fold", "456")
    assert resolved.paths == [{"root_id": "1001", "path": ["Legacy container"]}]
    assert "unresolved_legacy_repository_reference" not in resolved.warnings
    assert result.coverage[0].complete


def test_modern_and_legacy_links_to_same_object_fetch_once() -> None:
    root_url = page_url("fold", "1001")
    folder_url = page_url("fold", "456")
    legacy = normalize_object_link(
        "/ilias.php?baseClass=ilRepositoryGUI&ref_id=456",
        f"{BASE}/ilias.php",
        BASE,
        "academy",
    )
    assert legacy is not None and legacy.read_url is not None
    auth = FakeAuthenticator(
        {
            root_url: (
                '<main><div class="ilContainerListItem">'
                '<a href="/ilias.php?baseClass=ilRepositoryGUI&ref_id=456">'
                "Legacy path</a></div>"
                '<div class="ilContainerListItem">'
                '<a href="/goto.php?target=fold_456">Modern path</a></div>'
                "</main>"
            ),
            folder_url: "<main><h1>Shared folder</h1></main>",
        }
    )

    result = RepositoryCrawler(make_config(), auth).collect()

    assert auth.calls.count(folder_url) == 1
    assert legacy.read_url not in auth.calls
    assert "obj:456" not in result.objects
    resolved = result.objects["fold:456"]
    assert {tuple(path["path"]) for path in resolved.paths} == {
        ("Legacy path",),
        ("Modern path",),
    }
    assert result.coverage[0].objects_discovered == 2


def test_shared_failed_object_marks_every_reaching_root_incomplete() -> None:
    root1 = page_url("fold", "1001")
    root2 = page_url("fold", "1002")
    shared = page_url("fold", "1003")
    auth = FakeAuthenticator(
        {
            root1: '<main><h1>R1</h1><div class="ilContainerListItem"><a href="/goto.php?target=fold_1003">Shared</a></div></main>',
            root2: '<main><h1>R2</h1><div class="ilContainerListItem"><a href="/goto.php?target=fold_1003">Shared</a></div></main>',
        }
    )
    result = RepositoryCrawler(make_config("1001,1002"), auth).collect()
    assert auth.calls.count(shared) == 1
    assert [item.complete for item in result.coverage] == [False, False]

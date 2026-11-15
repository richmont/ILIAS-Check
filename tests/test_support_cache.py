"""Lifecycle and filesystem tests with synthetic bodies; never live course files."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile

import pytest

from ilias_check.cache_config import CacheError, CachePolicy
from ilias_check.config import CollectorConfig
from ilias_check.materials import document_reference
from ilias_check.support_cache import SupportCache, cache_inventory, stamp
from ilias_check.transport import SafeTransport, TransportError

NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)
PDF = b"%PDF-1.7\nsynthetic test fixture\n%%EOF"


class Response:
    def __init__(self, body=PDF, status=200, headers=None, fail=False):
        self.body, self.status_code, self.fail = body, status, fail
        self.headers = headers if headers is not None else {"Content-Type": "application/pdf", "Content-Length": str(len(body)), "ETag": '"v1"'}
        self.closed = False

    def iter_content(self, chunk_size=8192):
        yield self.body[:10]
        if self.fail:
            raise RuntimeError("private content must never reach diagnostics")
        yield self.body[10:]

    def close(self):
        self.closed = True


class Source:
    def __init__(self, *responses):
        self.responses = list(responses) or [Response()]
        self.calls = []

    def stream_document(self, material, headers):
        self.calls.append((material, headers))
        if not self.responses:
            raise RuntimeError("unexpected document fetch")
        return self.responses.pop(0)


@pytest.fixture
def config(tmp_path):
    return CollectorConfig("https://ilias.example/ilias", "demo", "learner", "secret", ("1",), ("1",),
                           cache_policy=CachePolicy(True, tmp_path / "private", max_bytes=50000, max_file_bytes=1000))


def snapshot(status="pending", deadline=None, document="1", ass="2", now=NOW):
    material = document_reference(
        f"https://ilias.example/ilias/goto.php?target=file_{document}_download&client_id=demo",
        "worksheet.pdf", "1", ass, "https://ilias.example/ilias/goto.php?target=exc_1", "https://ilias.example/ilias", "demo",
        "assignment_attachment", "support", "Files")
    material["selected_for_support"] = status == "pending"
    return {"checked_at": stamp(now), "activities": [{"exercise_id": "1", "assignment_id": ass, "status": status,
                                                     "deadline_at": stamp(deadline) if deadline else None,
                                                     "support_documents": [material]}]}


def collect(config, data=None, source=None, now=NOW):
    return cache_inventory(data or snapshot(now=now), config, source or Source(), lambda: now)


def material(result):
    return result["activities"][0]["support_documents"][0]


def test_defaults_and_config():
    policy = CachePolicy.from_mapping({})
    assert policy.max_bytes == 200000000 and not policy.enabled and policy.no_deadline_hours == 168
    with pytest.raises(CacheError):
        CachePolicy.from_mapping({"ILIAS_PENDING_DOWNLOAD_SUPPORT": "yes"})
    with pytest.raises(CacheError):
        CachePolicy.from_mapping({"ILIAS_SUPPORT_CACHE_MAX_BYTES": "0"})
    assert policy.with_retention(12, 24).max_bytes == policy.max_bytes


def test_disabled_never_opens_store_or_source(config):
    source = Source()
    config = replace(config, cache_policy=replace(config.cache_policy, enabled=False))
    assert collect(config, source=source) == snapshot()
    assert not config.cache_policy.directory.exists() and not source.calls


def test_private_checksum_fresh_shared_reuse(config):
    data = snapshot()
    data["activities"].append(snapshot(ass="3")["activities"][0])
    source = Source()
    result = collect(config, data, source)
    first, second = [a["support_documents"][0]["cache"] for a in result["activities"]]
    assert len(source.calls) == 1 and first["path"] == second["path"]
    assert first["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert first["expires_at"] == stamp(NOW + timedelta(days=7)) and first["eligible"]
    assert Path(first["path"]).read_bytes() == PDF
    assert config.cache_policy.directory.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in config.cache_policy.directory.iterdir())
    source = Source()
    data["checked_at"] = stamp(NOW + timedelta(hours=1))
    again = collect(config, data, source, NOW + timedelta(hours=1))
    assert not source.calls and material(again)["state"] == "cached"


def test_account_isolation_and_same_filename(config):
    a = material(collect(config))["cache"]["path"]
    b = material(collect(replace(config, username="another")))["cache"]["path"]
    c = material(collect(config, snapshot(document="9")))["cache"]["path"]
    assert len({a, b, c}) == 3


def test_304_preserves_copy_time_and_retention(config):
    first = material(collect(config))["cache"]
    source = Source(Response(status=304, headers={}))
    now = NOW + timedelta(hours=13)
    result = material(collect(config, snapshot(now=now), source, now))["cache"]
    assert source.calls[0][1] == {"If-None-Match": '"v1"'}
    assert result["downloaded_at"] == first["downloaded_at"] and result["expires_at"] == first["expires_at"]
    assert result["last_validated_at"] == stamp(now)


def test_changed_body_and_corruption_refresh(config):
    first = material(collect(config))["cache"]
    Path(first["path"]).write_bytes(b"corrupted")
    now = NOW + timedelta(hours=1)
    result = material(collect(config, snapshot(now=now), Source(Response(PDF + b"new")), now))["cache"]
    assert result["sha256"] != first["sha256"] and not Path(first["path"]).exists()
    assert result["downloaded_at"] == stamp(now)


@pytest.mark.parametrize("status", ["submitted", "excluded", "closed_without_submission"])
def test_ended_physically_expires_and_cannot_be_served(config, status):
    first = material(collect(config))["cache"]
    source = Source()
    now = NOW + timedelta(hours=1)
    collect(config, snapshot(status, now=now), source, now)
    assert not source.calls and not Path(first["path"]).exists()
    with pytest.raises(CacheError):
        with SupportCache(config, lambda: now).delivery("file:1", snapshot(status)["activities"][0], stamp(now)):
            pytest.fail("ended activity served")


def test_shared_copy_ended_association_refused_other_still_valid(config):
    data = snapshot()
    data["activities"].append(snapshot(ass="3")["activities"][0])
    collect(config, data)
    now = NOW + timedelta(hours=1)
    data["checked_at"] = stamp(now)
    data["activities"][0]["status"] = "submitted"
    data["activities"][0]["support_documents"][0]["selected_for_support"] = False
    result = collect(config, data, now=now)
    assert result["activities"][1]["support_documents"][0]["cache"]["eligible"]
    with pytest.raises(CacheError):
        with SupportCache(config, lambda: now).delivery("file:1", data["activities"][0], stamp(now)):
            pytest.fail("ended association served")
    with SupportCache(config, lambda: now).delivery("file:1", data["activities"][1], stamp(now)) as (source, _):
        assert source.read() == PDF
        with pytest.raises(CacheError):
            with SupportCache(config, lambda: now).locked():
                pytest.fail("concurrent eviction acquired active reader lock")


def test_expired_ttl_pending_refresh_and_deadline_never_extended(config):
    first = material(collect(config))["cache"]
    now = NOW + timedelta(days=8)
    renewed = material(collect(config, snapshot(now=now), now=now))["cache"]
    assert renewed["downloaded_at"] == stamp(now) and not Path(first["path"]).exists()
    source = Source()
    expired = material(collect(config, snapshot(deadline=NOW, now=now), source, now))
    assert expired["state"] == "expired" and not source.calls


def test_shorter_ttl_and_failed_scan_maintenance(config):
    first = material(collect(config))["cache"]
    shorter = replace(config, cache_policy=replace(config.cache_policy, retention_max_hours=1))
    now = NOW + timedelta(hours=2)
    with pytest.raises(CacheError):
        with SupportCache(shorter, lambda: now).delivery("file:1", snapshot()["activities"][0], stamp(now)):
            pytest.fail("shortened retention should refuse old copy")
    assert not Path(first["path"]).exists()


def test_refresh_failure_is_stale_no_current_path(config):
    first = material(collect(config))["cache"]
    now = NOW + timedelta(hours=13)
    result = material(collect(config, snapshot(now=now), Source(Response(fail=True)), now))
    assert result["state"] == "stale" and not result["cache"]["eligible"] and result["cache"]["path"] is None
    assert Path(first["path"]).exists()


@pytest.mark.parametrize("response,code", [
    (Response(b"x" * 1001, headers={"Content-Type": "application/pdf"}), "support_stream_byte_limit"),
    (Response(headers={"Content-Length": "1001"}), "support_file_byte_limit"),
    (Response(headers={"Content-Type": "text/html"}), "unsupported_document_type"),
    (Response(b"<html>login</html>", headers={"Content-Type": "application/pdf"}), "document_body_is_not_a_file"),
    (Response(b"not a PDF"), "document_signature_mismatch"),
    (Response(headers={"Content-Disposition": 'attachment; filename="../../private.pdf"'}), "unsafe_document_filename"),
    (Response(headers={"Content-Length": "100"}), "support_incomplete_transfer"),
    (Response(fail=True), "support_download_failed"),
])
def test_failed_transfers_never_publish(config, response, code):
    result = material(collect(config, source=Source(response)))
    assert result["state"] == "error" and code in result["reason_codes"]
    assert not list(config.cache_policy.directory.glob("*.blob")) and not list(config.cache_policy.directory.glob("*.part"))


def test_private_storage_rejects_checkout_symlinks_hardlinks(config, tmp_path):
    repo = Path(__file__).resolve().parents[1]
    bad = replace(config, cache_policy=replace(config.cache_policy, directory=repo / "runtime" / "support-test"))
    assert collect(bad)["support_cache"]["error"] == "support_cache_unavailable"
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    config.cache_policy.directory.symlink_to(outside, target_is_directory=True)
    assert collect(config)["support_cache"]["error"] == "support_cache_unavailable"
    assert not list(outside.iterdir())
    config.cache_policy.directory.unlink()
    config.cache_policy.directory.mkdir(mode=0o700)
    victim = outside / "victim"
    victim.write_text("private")
    os.chmod(victim, 0o600)
    os.link(victim, config.cache_policy.directory / "cache.lock")
    assert collect(config)["support_cache"]["error"] == "support_cache_unavailable"
    assert victim.read_text() == "private"


def test_manifest_newer_version_never_deletes(config):
    collect(config)
    path = config.cache_policy.directory / "manifest.json"
    data = json.loads(path.read_text()); data["version"] = 999; path.write_text(json.dumps(data))
    result = collect(config)
    assert result["support_cache"]["error"] == "support_cache_unavailable"
    assert json.loads(path.read_text())["version"] == 999 and list(path.parent.glob("*.blob"))


def test_quota_and_week_rotation(config):
    config = replace(config, cache_policy=replace(config.cache_policy, max_bytes=15000, max_file_bytes=3000))
    for day in range(10):
        now = NOW + timedelta(days=day)
        for index in range(4):
            result = collect(config, snapshot(document=str(day * 4 + index + 1), now=now), Source(Response(PDF + b"x" * 2000)), now)
            assert result["support_cache"]["usage_bytes"] <= config.cache_policy.max_bytes
    first = material(result)["cache"]["path"]
    assert first and Path(first).exists()
    reduced = replace(config, cache_policy=replace(config.cache_policy, max_bytes=6000))
    with SupportCache(reduced, lambda: now).locked() as cache:
        cache.maintenance()
        assert cache.usage() <= 6000


def test_unknown_activity_pauses_without_inventing_completion(config):
    first = material(collect(config))["cache"]
    now = NOW + timedelta(hours=1)
    collect(config, snapshot("unknown", now=now), now=now)
    assert Path(first["path"]).exists()
    with pytest.raises(CacheError):
        with SupportCache(config, lambda: now).delivery("file:1", snapshot()["activities"][0], stamp(now)):
            pytest.fail("unknown current observation served")


def test_metadata_and_run_budget_limits(config):
    config = replace(config, cache_policy=replace(config.cache_policy, max_run_bytes=40))
    data = snapshot()
    data["activities"].append(snapshot(document="2", ass="3")["activities"][0])
    result = collect(config, data, Source(Response(), Response()))
    assert result["activities"][1]["support_documents"][0]["state"] == "error"


def test_safe_stream_redirects_origin_identity_and_request_budget(config):
    class Session:
        def __init__(self, response):
            self.response = response
            self.calls = []
        def request(self, *args, **kwargs):
            self.calls.append((args, kwargs)); return self.response
    for location in ["https://evil.example/private.pdf", "https://ilias.example/ilias/goto.php?target=file_9_download&client_id=demo", "https://ilias.example/ilias/ilias.php?cmd=delete"]:
        response = Response(status=302, headers={"Location": location})
        session = Session(response)
        transport = SafeTransport(config, session)
        with pytest.raises(TransportError):
            transport.stream_document(snapshot()["activities"][0]["support_documents"][0])
        assert len(session.calls) == 1 and session.calls[0][1]["stream"] and response.closed
    transport = SafeTransport(replace(config, max_requests=1), Session(Response()))
    transport.stream_document(snapshot()["activities"][0]["support_documents"][0])
    with pytest.raises(TransportError):
        transport.stream_document(snapshot()["activities"][0]["support_documents"][0])


def test_increased_ttl_never_revives_already_expired_bytes(config):
    short = replace(config, cache_policy=replace(config.cache_policy, no_deadline_hours=1))
    first = material(collect(short))["cache"]
    now = NOW + timedelta(hours=2)
    with pytest.raises(CacheError):
        with SupportCache(config, lambda: now).delivery("file:1", snapshot()["activities"][0], stamp(now)):
            pytest.fail("longer setting revived expired bytes")
    assert not Path(first["path"]).exists()
    renewed = material(collect(config, snapshot(now=now), now=now))["cache"]
    assert renewed["downloaded_at"] == stamp(now)


def test_dispatch_gate_requires_current_selected_association(config):
    collect(config)
    activity = snapshot()["activities"][0]
    activity["support_documents"][0]["selected_for_support"] = False
    with pytest.raises(CacheError):
        with SupportCache(config, lambda: NOW).delivery("file:1", activity, stamp(NOW)):
            pytest.fail("unselected material served")


def test_office_container_and_rtf_types(config):
    for suffix, headers, body in [
        ("rtf", {"Content-Type": "application/rtf"}, b"{\\rtf1 synthetic}"),
        ("doc", {"Content-Type": "application/msword"}, bytes.fromhex("d0cf11e0a1b11ae1") + b"synthetic"),
    ]:
        data = snapshot(document="2" if suffix == "rtf" else "3")
        data["activities"][0]["support_documents"][0]["title"] = "worksheet." + suffix
        result = material(collect(config, data, Source(Response(body, headers=headers))))
        assert result["state"] == "cached"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("[Content_Types].xml", "synthetic")
        archive.writestr("word/document.xml", "synthetic")
    data = snapshot(document="4"); data["activities"][0]["support_documents"][0]["title"] = "worksheet.docx"
    result = material(collect(config, data, Source(Response(stream.getvalue(), headers={"Content-Type": "application/octet-stream"}))))
    assert result["state"] == "cached"


def test_authentication_html_recovers_once(config):
    from ilias_check.auth import Authenticator, AuthError
    class Transport:
        def __init__(self, responses): self.responses = list(responses)
        def stream_document(self, material, headers): return self.responses.pop(0)
    class Auth(Authenticator):
        def login(self): self._authenticated = True
    login = b'<form action="login.php"><input type="password" name="password"></form>'
    source = Transport([Response(login, headers={"Content-Type": "text/html"}), Response()])
    auth = Auth(config, source)
    assert auth.stream_document(snapshot()["activities"][0]["support_documents"][0]).body == PDF
    auth = Auth(config, Transport([Response(login, headers={"Content-Type": "text/html"}), Response(login, headers={"Content-Type": "text/html"})]))
    with pytest.raises(AuthError):
        auth.stream_document(snapshot()["activities"][0]["support_documents"][0])


def test_unrelated_files_are_counted_but_never_deleted(config):
    result = collect(config)
    unrelated = config.cache_policy.directory / "unrelated.txt"
    unrelated.write_bytes(b"x" * 50000); os.chmod(unrelated, 0o600)
    with pytest.raises(CacheError):
        with SupportCache(config, lambda: NOW).locked() as cache:
            cache.maintenance()
    assert unrelated.exists() and unrelated.stat().st_size == 50000


def test_shared_association_expiry_never_bypassed_by_longer_settings(config):
    data = snapshot()
    data["activities"][0]["deadline_at"] = stamp(NOW + timedelta(days=10))
    data["activities"].append(snapshot(ass="3")["activities"][0])
    short = replace(config, cache_policy=replace(config.cache_policy, no_deadline_hours=1))
    first = collect(short, data)
    first_path = first["activities"][0]["support_documents"][0]["cache"]["path"]
    now = NOW + timedelta(hours=2)
    data["checked_at"] = stamp(now)
    source = Source()
    result = collect(config, data, source, now)
    assert len(source.calls) == 1 and not source.calls[0][1]
    assert result["activities"][1]["support_documents"][0]["cache"]["downloaded_at"] == stamp(now)
    assert not Path(first_path).exists()


def test_explicit_platform_completion_ends_pending_support(config):
    first = material(collect(config))["cache"]
    data = snapshot()
    data["activities"][0]["submission_history"] = [{"completed": True}]
    source = Source()
    result = collect(config, data, source)
    assert not Path(first["path"]).exists() and not source.calls
    assert material(result)["state"] == "expired"


def test_collection_classification_cache_pipeline_and_repeated_scan(config, tmp_path, monkeypatch):
    from test_mcp_read_parity import exercise_pages, assignments, OfflineAuth, config as fixture_config
    from ilias_check.collector import collect_inventory
    from ilias_check import collector as module
    from jsonschema import Draft202012Validator, FormatChecker
    base_config = fixture_config()
    config = replace(base_config, cache_policy=replace(config.cache_policy, directory=tmp_path / "pipeline"))
    pages = exercise_pages()
    pending = assignments()[1]
    pages[pending.submission_url] += '<a href="/ilias.php?baseClass=ilrepositorygui&cmdClass=ilExSubmissionFileGUI&cmd=uploadForm&ref_id=444&ass_id=42">Datei abgeben</a>'
    pages[pending.presentation_url] = pages[pending.presentation_url].replace('</div></main>',
        '<div class="panel-sub"><h3 class="ilBlockHeader">Dateien</h3><div class="panel-body"><a href="/goto.php?target=file_700_download">Blatt.pdf</a></div></div></div></main>')
    class Auth(OfflineAuth):
        bodies = 0
        def __init__(self, **kwargs): super().__init__(pages)
        def stream_document(self, material, headers):
            Auth.bodies += 1; return Response()
    monkeypatch.setattr(module, "Authenticator", Auth)
    now = datetime.now(timezone.utc)
    first = collect_inventory(config, transport=object(), checked_at=now)
    assert first["classification"]["counts"]["pending"] >= 1
    assert Auth.bodies == 1
    second = collect_inventory(config, transport=object(), checked_at=now)
    assert Auth.bodies == 1 and second["support_cache"]["downloaded_bytes"] == 0
    schema = json.loads((Path(__file__).parents[1] / "schemas/inventory-v1.schema.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(first)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(second)


def test_cached_support_example_matches_shared_schema():
    from jsonschema import Draft202012Validator, FormatChecker
    root = Path(__file__).parents[1]
    schema = json.loads((root / "schemas/inventory-v1.schema.json").read_text())
    fragment = {"$defs": schema["$defs"], "$ref": "#/$defs/supportDocument"}
    Draft202012Validator(fragment, format_checker=FormatChecker()).validate(json.loads((root / "examples/cached-support.json").read_text()))


def test_disabling_new_downloads_still_expires_confirmed_submitted_copies(config):
    first = material(collect(config))["cache"]
    disabled = replace(config, cache_policy=replace(config.cache_policy, enabled=False))
    source = Source()
    result = collect(disabled, snapshot("submitted"), source)
    assert not source.calls and not Path(first["path"]).exists()
    assert material(result)["state"] == "expired" and not material(result)["cache"]["eligible"]


def test_disabled_downloads_never_export_unvalidated_stale_copy_as_current(config):
    collect(config)
    disabled = replace(config, cache_policy=replace(config.cache_policy, enabled=False))
    now = NOW + timedelta(hours=13)
    source = Source()
    result = collect(disabled, snapshot(now=now), source, now)
    assert not source.calls and material(result)["state"] == "stale" and not material(result)["cache"]["eligible"]


def test_account_identity_normalizes_installation_origin(config):
    from ilias_check.private_storage import account_key
    assert account_key(config) == account_key(replace(config, base_url="https://ILIAS.EXAMPLE:443/ilias/"))
    assert account_key(config) != account_key(replace(config, client_id="another"))


def test_cached_source_filename_is_preserved(config):
    response = Response(headers={'Content-Type': 'application/pdf',
                                 'Content-Disposition': "attachment; filename*=UTF-8''Original%20%C3%9Cbung.pdf"})
    collect(config, source=Source(response))
    manifest = json.loads((config.cache_policy.directory / 'manifest.json').read_text())
    assert next(iter(manifest['entries'].values()))['filename'] == 'Original Übung.pdf'


def test_automatic_delivery_keeps_short_freshness_limit(config):
    collect(config)
    later = NOW + timedelta(hours=1)
    with pytest.raises(CacheError):
        with SupportCache(config, lambda: later).delivery('file:1', snapshot()['activities'][0], stamp(NOW)):
            pytest.fail('Automatic delivery must not inherit the interactive twelve-hour window')


def test_interrupted_download_closes_response_and_removes_partial_bytes(config):
    import threading
    from ilias_check.timeouts import MaterialRequestTimeout, material_request_deadline
    class SlowResponse(Response):
        def iter_content(self, chunk_size=65536):
            yield self.body[:10]
            threading.Event().wait(1)
            yield self.body[10:]
    response = SlowResponse()
    with pytest.raises(MaterialRequestTimeout):
        with material_request_deadline(0.02):
            collect(config, source=Source(response))
    assert response.closed and not list(config.cache_policy.directory.glob('*.part'))
    # Cancellation does not strand a cache lease.
    with SupportCache(config, lambda: NOW).locked(): pass

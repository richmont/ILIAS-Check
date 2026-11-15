"""Offline integration of durable transitions, Telegram isolation and private UI."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from ilias_check.bot import Bot, run_bot
from ilias_check.cache_config import CacheError, CachePolicy
from ilias_check.config import CollectorConfig
from ilias_check.monitor import run_monitor
from ilias_check.monitor_state import MonitorState
from ilias_check.support_cache import stamp
from ilias_check.telegram import TelegramClient, TelegramConfig, TelegramError, activity_message, redact, safe_link

NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)
TOKEN = "123456:" + "x" * 30


@pytest.fixture
def config(tmp_path):
    return CollectorConfig("https://ilias.example/ilias", "demo", "learner", "private-password", ("1",), ("1",),
                           cache_policy=CachePolicy(directory=tmp_path / "support"))


@pytest.fixture
def telegram(tmp_path):
    return TelegramConfig(True, TOKEN, "100", "200", state_dir=tmp_path / "monitor")


def inventory(status="pending", now=NOW, deadline=None, complete=True, ass="2"):
    activity = {"exercise_id": "1", "assignment_id": ass, "status": status, "title": "Übung <b>Original</b>",
                "url": "https://ilias.example/ilias/goto.php?target=exc_1", "url_kind": "assignment",
                "deadline_at": deadline, "deadline_text": "kein Termin", "deadline_timezone": "Europe/Berlin",
                "instructions": "Bitte laden Sie Ihre Datei hoch.", "reason_codes": ["source_not_resolved"] if status == "unknown" else [],
                "support_documents": [], "paths": [["Kurs", "Übung"]], "submission_history": []}
    return {"checked_at": stamp(now), "scope": {"base_url": "https://ilias.example/ilias", "client_id": "demo", "root_ids": ["1"]},
            "coverage": [{"root_id": "1", "complete": complete, "warnings": []}], "activities": [activity],
            "classification": {"complete": status != "unknown", "counts": {status: 1}}, "errors": []}


class Client:
    def __init__(self, fail=None, batches=None):
        self.messages, self.documents, self.calls = [], [], []
        self.fail = fail
        self.batches = list(batches or [])
    def message(self, text, buttons=None):
        self.messages.append((text, buttons))
        if self.fail:
            raise self.fail
        return {"message_id": len(self.messages)}
    def document(self, *args):
        self.documents.append(args)
        if self.fail:
            raise self.fail
        return {"message_id": 900}
    def call(self, *args):
        self.calls.append(args); return True
    def updates(self, offset):
        self.calls.append(("getUpdates", offset)); return self.batches.pop(0) if self.batches else []


def update(text=None, uid=1, user=200, chat=100, kind="private", callback=None):
    message = {"chat": {"id": chat, "type": kind}, "from": {"id": user}}
    if text is not None:
        message["text"] = text
    if callback:
        return {"update_id": uid, "callback_query": {"id": str(uid), "data": callback, "from": {"id": user}, "message": message}}
    return {"update_id": uid, "message": message}


def test_first_unchanged_deadline_reopening_and_restart(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory(), NOW)
        assert len(state.due(NOW)) == 1
        component = state.due(NOW)[0]; state.acknowledged(component, 1, NOW)
        state.observe(inventory(now=NOW + timedelta(hours=12)), NOW + timedelta(hours=12))
        assert not state.due(NOW + timedelta(hours=12))
    with MonitorState(config, telegram.state_dir).open() as state:
        changed = inventory(now=NOW + timedelta(days=1), deadline=stamp(NOW + timedelta(days=2)))
        state.observe(changed, NOW + timedelta(days=1))
        assert len(state.due(NOW + timedelta(days=1))) == 1
        state.observe(inventory("submitted", NOW + timedelta(days=2)), NOW + timedelta(days=2))
        assert not state.due(NOW + timedelta(days=2))
        state.observe(inventory(now=NOW + timedelta(days=3)), NOW + timedelta(days=3))
        assert len(state.due(NOW + timedelta(days=3))) == 1
        assert state.db.execute("SELECT COUNT(*) FROM submission_history").fetchone()[0] == 1


def test_reminders_explicit_and_no_immediate_repetition(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory(), NOW, 24)
        state.acknowledged(state.due(NOW)[0], 1, NOW)
        now = NOW + timedelta(hours=23)
        state.observe(inventory(now=now), now, 24)
        assert not state.due(now)
        now += timedelta(hours=1)
        state.observe(inventory(now=now), now, 24)
        assert len(state.due(now)) == 1
        state.observe(inventory(now=now), now, 24)
        assert len(state.due(now)) == 1


def test_partial_absence_unknown_never_resolves_old_pending(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory(), NOW)
        data = inventory("unknown", NOW + timedelta(hours=1), complete=False)
        state.observe(data, NOW + timedelta(hours=1))
        rows = state.due(NOW + timedelta(hours=1))
        assert len(rows) == 1 and rows[0]["event_kind"] == "health"
        row = state.db.execute("SELECT * FROM observations").fetchone()
        assert row["confirmed"] == "pending" and not row["current"]
        state.acknowledged(rows[0], 1, NOW + timedelta(hours=1))
        state.observe(data, NOW + timedelta(hours=1))
        assert not state.due(NOW + timedelta(hours=1))
        data["activities"] = []
        state.observe(data, NOW + timedelta(hours=1))
        assert state.db.execute("SELECT confirmed FROM observations").fetchone()[0] == "pending"


def test_confirmed_pending_can_notify_in_partial_scan(config, telegram):
    client = Client()
    report = run_monitor(config, telegram, collector=lambda c: inventory(complete=False), client=client, clock=lambda: NOW)
    assert report["sent_components"] == 2
    assert "incompleta" in client.messages[0][0].lower() and not report["complete"]


def test_dry_run_does_not_consume_queue_or_send(config, telegram):
    client = Client()
    preview = run_monitor(config, telegram, True, lambda c: inventory(), client, lambda: NOW)
    assert preview["planned_components"] == 1 and not client.messages
    with MonitorState(config, telegram.state_dir).open() as state:
        assert state.snapshot() is None and not state.due(NOW)
    run_monitor(config, telegram, False, lambda c: inventory(), client, lambda: NOW)
    assert len(client.messages) == 1
    run_monitor(config, telegram, True, lambda c: inventory(), client, lambda: NOW)
    assert len(client.messages) == 1


def test_disabled_no_telegram_and_failed_check_pauses_retry(config, telegram):
    client = Client()
    disabled = replace(telegram, enabled=False)
    run_monitor(config, disabled, collector=lambda c: inventory(), client=client, clock=lambda: NOW)
    assert not client.messages
    def broken(_):
        raise RuntimeError("secret")
    report = run_monitor(config, disabled, collector=broken, client=client, clock=lambda: NOW)
    assert report["fatal"] and not client.messages
    with MonitorState(config, telegram.state_dir).open() as state:
        assert not state.db.execute("SELECT current FROM observations").fetchone()[0]
        assert not any(r["event_kind"] == "pending" for r in state.due(NOW))


def test_delivery_uncertainty_backoff_and_submission_cancels(config, telegram):
    client = Client(TelegramError(uncertain=True))
    run_monitor(config, telegram, collector=lambda c: inventory(), client=client, clock=lambda: NOW)
    assert len(client.messages) == 1
    with MonitorState(config, telegram.state_dir).open() as state:
        row = state.db.execute("SELECT * FROM components").fetchone()
        assert row["state"] == "uncertain" and row["attempts"] == 1 and not state.due(NOW)
    now = NOW + timedelta(minutes=5)
    report = run_monitor(config, telegram, collector=lambda c: inventory("submitted", now), client=client, clock=lambda: now)
    assert not report["sent_components"] and len(client.messages) == 1


def test_observation_commit_survives_crash_before_ack(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory(), NOW)
        assert len(state.due(NOW)) == 1
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory(), NOW)
        assert len(state.due(NOW)) == 1
        state.acknowledged(state.due(NOW)[0], 123, NOW)
    with MonitorState(config, telegram.state_dir).open() as state:
        assert not state.due(NOW)


def test_newer_schema_rejected_and_accounts_isolated(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory(), NOW)
        state.db.execute("PRAGMA user_version=999")
    with pytest.raises(CacheError):
        with MonitorState(config, telegram.state_dir).open():
            pytest.fail("newer database opened")
    with MonitorState(replace(config, username="second"), telegram.state_dir).open() as state:
        assert state.snapshot() is None


def test_state_lock_contention_and_transaction_rollback(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as first, first.run_lock():
        with MonitorState(config, telegram.state_dir).open() as second:
            with pytest.raises(CacheError):
                with second.run_lock():
                    pytest.fail("overlapping run")
        data = inventory()
        data["activities"].append({"broken": True})
        with pytest.raises(KeyError):
            first.observe(data, NOW)
        assert first.snapshot() is None and not first.due(NOW)


def test_preferences_allowlist_and_restart(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.set_preferences({"no_deadline_hours": 24, "retention_max_hours": 48})
        for values in [{"quota": 999999999}, {"retention_max_hours": 0}, {"no_deadline_hours": -1}, {"no_deadline_hours": True}]:
            with pytest.raises(CacheError):
                state.set_preferences(values)
    with MonitorState(config, telegram.state_dir).open() as state:
        assert state.preferences() == {"no_deadline_hours": 24, "retention_max_hours": 48}


def test_bot_unauthorized_users_groups_forwarded_callbacks(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory(), NOW)
        client = Client(); bot = Bot(config, telegram, state, client, lambda: NOW)
        for i, args in enumerate([{"user": 201}, {"chat": 101}, {"kind": "group"}, {"user": 201, "callback": "forged"}], 1):
            bot.handle(update("/pendentes", uid=i, **args))
        assert not client.messages and not client.calls
        bot.handle(update("/verificar", uid=5))
        assert client.messages


def test_original_source_unknown_feedback_and_honest_history(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory("unknown", complete=False), NOW)
        client = Client(); bot = Bot(config, telegram, state, client, lambda: NOW)
        bot.handle(update("/verificar"))
        text = "\n".join(t for t, _ in client.messages)
        assert "Inconclusivo — precisa verificar" in text and "Übung <b>Original</b>" in text
        assert "Bitte laden Sie Ihre Datei hoch." in text and "/relatar" in text and "feedback não altera" in text
        assert client.messages[-1][1][0][0]["text"] == "Abrir no ILIAS"
        bot.handle(update("/pendentes", uid=2))
        assert "não confirma" in client.messages[-1][0]


def test_views_name_the_category_and_verify_explains_coverage(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory("unknown", complete=False), NOW)
        client = Client(); bot = Bot(config, telegram, state, client, lambda: NOW)
        bot.handle(update("/verificar"))
        header = client.messages[0][0]
        assert header.startswith("Inconclusivas — observação de")
        assert "Cobertura incompleta" in header and "root(s) 1" in header
        assert "consulte /verificar" not in header
        bot.handle(update("/pendentes", uid=2))
        pending = client.messages[-1][0]
        assert pending.startswith("Pendentes — observação de")
        assert "detalhes em /verificar" in pending


def test_empty_categories_have_specific_messages(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory("submitted"), NOW)
        client = Client(); bot = Bot(config, telegram, state, client, lambda: NOW)
        bot.handle(update("/pendentes"))
        assert "Nenhuma atividade pendente confirmada" in client.messages[-1][0]
        bot.handle(update("/encerradas", uid=2))
        assert "Nenhuma atividade encerrada sem entrega" in client.messages[-1][0]
        bot.handle(update("/verificar", uid=3))
        assert "Nenhuma atividade inconclusiva registrada" in client.messages[-1][0]


def test_history_retained_after_reopen_and_missing_observation_marked_old(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory("submitted"), NOW)
        state.observe(inventory(), NOW)
        client = Client(); bot = Bot(config, telegram, state, client, lambda: NOW)
        bot.handle(update("/entregues"))
        assert any("aprovação não presumida" in text for text, _ in client.messages)
        assert any("antiga" in text for text, _ in client.messages)


def test_pagination_rate_limit_received_files_never_fetched(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        data = inventory()
        data["activities"] = [inventory(ass=str(i))["activities"][0] for i in range(1, 11)]
        state.observe(data, NOW)
        client = Client(); bot = Bot(config, telegram, state, client, lambda: NOW)
        bot.handle(update("/pendentes"))
        assert len(client.messages) == 6 and "Próxima página" in client.messages[-1][0]
        bot.handle(update(None, uid=2))
        assert "não baixo anexos" in client.messages[-1][0]
        for i in range(3, 40):
            bot.handle(update("/ajuda", uid=i))
        count = len(client.messages)
        bot.handle(update("/pendentes", uid=100))
        assert len(client.messages) == count and not client.documents


def test_retention_settings_no_quota_paths_or_manual_purge(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        client = Client(); bot = Bot(config, telegram, state, client, lambda: NOW)
        bot.handle(update("/configuracoes"))
        assert "200 MB" in client.messages[-1][0] and str(config.cache_policy.directory) not in client.messages[-1][0]
        bot.handle(update("/retencao sem_prazo 24", uid=2))
        assert state.preferences() == {"no_deadline_hours": 24}
        bot.handle(update("/retencao quota 99999999", uid=3))
        assert state.preferences() == {"no_deadline_hours": 24}
        bot.handle(update("/purge", uid=4))
        assert not config.cache_policy.directory.exists()
        bot.handle(update("/retencao padrao", uid=5))
        assert not state.preferences()


def test_report_text_edit_redaction_export_without_issue_or_state_change(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory("unknown"), NOW)
        before = state.snapshot()
        client = Client(); bot = Bot(config, telegram, state, client, lambda: NOW)
        messages = ["/relatar", "Parser não mostrou private-password", "Exibir meu prazo", "Apareceu vazio " + TOKEN,
                    "https://ilias.example/ilias/goto.php?target=exc_1", "/editar ocorrido", "Agora exibe inconclusivo", "/exportar"]
        for i, text in enumerate(messages, 1):
            bot.handle(update(text, uid=i))
        assert state.snapshot() == before and bot.draft is None
        text = "\n".join(t for t, _ in client.messages)
        assert config.password not in text and TOKEN not in text and "[oculto]" in text
        assert "Nenhuma issue foi aberta" in client.messages[-1][0] and not client.documents and not client.calls


def test_report_timeout_cancel_restart_and_replay(config, telegram):
    now = [NOW]
    with MonitorState(config, telegram.state_dir).open() as state:
        client = Client(); bot = Bot(config, telegram, state, client, lambda: now[0])
        bot.handle(update("/relatar")); bot.handle(update("/relatar"))
        assert len(client.messages) == 1
        now[0] += timedelta(minutes=31)
        bot.handle(update("hello", uid=2))
        assert bot.draft is None and any("expirou" in t for t, _ in client.messages)
        bot.handle(update("/relatar", uid=3)); bot.handle(update("/cancelar", uid=4))
        assert bot.draft is None
        restarted = Bot(config, telegram, state, client, lambda: now[0])
        restarted.handle(update("hello", uid=5))
        assert "reinício" in client.messages[-1][0]


def test_material_request_new_check_consent_and_single_request_only(config, telegram):
    data = inventory()
    data["activities"][0]["support_documents"] = [{"document_id": "file:9", "title": "Blatt.pdf", "selected_for_support": True, "role": "support", "state": "metadata_only"}]
    calls = []; sends = []
    def collector(c):
        assert not c.cache_policy.enabled
        calls.append(c); return deepcopy(data)
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(data, NOW)
        client = Client(); bot = Bot(config, telegram, state, client, lambda: NOW, collector, lambda *args: sends.append(args))
        bot.handle(update("/materiais"))
        assert "autoriza enviar" in client.messages[-1][0]
        token = client.messages[-1][1][0][0]["callback_data"]
        bot.handle(update(uid=2, user=201, callback=token))
        assert not calls
        bot.handle(update(uid=3, callback=token))
        assert len(calls) == len(sends) == 1 and not telegram.send_documents
        bot.handle(update(uid=4, callback=token))
        assert len(calls) == 1
        bot.handle(update("/materiais", uid=5))
        token = client.messages[-1][1][0][0]["callback_data"]
        bot.handle(update(uid=6, callback=token))
        assert len(calls) == 1


def test_old_material_button_rechecks_submission_before_send(config, telegram):
    data = inventory()
    data["activities"][0]["support_documents"] = [{"document_id": "file:9", "title": "Blatt.pdf", "selected_for_support": True, "role": "support", "state": "metadata_only"}]
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(data, NOW)
        client = Client(); sends = []
        bot = Bot(config, telegram, state, client, lambda: NOW, lambda c: inventory("submitted"), lambda *args: sends.append(args))
        bot.handle(update("/materiais"))
        token = client.messages[-1][1][0][0]["callback_data"]
        bot.handle(update(uid=2, callback=token))
        assert not sends and "Não foi possível confirmar" in client.messages[-1][0]


def test_worker_cursor_survives_restart_without_duplicate_commands(config, telegram):
    client = Client(batches=[[update("/retencao sem_prazo 24")]])
    run_bot(config, telegram, client, lambda: NOW, max_polls=1)
    count = len(client.messages)
    client.batches = [[update("/retencao sem_prazo 24")]]
    run_bot(config, telegram, client, lambda: NOW, max_polls=1)
    assert len(client.messages) == count and client.calls[-1][1] == 2


def test_telegram_configuration_redaction_links_and_plain_text():
    with pytest.raises(CacheError):
        TelegramConfig.from_mapping({"ILIAS_TELEGRAM_ENABLED": "true"})
    with pytest.raises(CacheError):
        TelegramConfig.from_mapping({"ILIAS_TELEGRAM_ENABLED": "false"}, worker=True)
    assert not safe_link("https://example.test/a?token=secret") and not safe_link("https://user@host/a")
    assert "secret" not in redact("PHPSESSID=secret https://a.test/?token=secret")
    assert not TelegramConfig.from_mapping({}).enabled


def test_telegram_transport_no_session_leak_no_redirect_token_error_and_rate_limit(telegram):
    class Response:
        status_code = 200
        def json(self): return {"ok": True, "result": {"message_id": 1}}
        def close(self): pass
    class Session:
        def __init__(self): self.calls = []; self.response = Response(); self.error = None
        def post(self, url, **options):
            self.calls.append((url, options))
            if self.error: raise self.error
            return self.response
    session = Session(); client = TelegramClient(telegram, session)
    client.message("<b>untrusted</b>")
    options = session.calls[0][1]
    assert options["allow_redirects"] is False and "parse_mode" not in options["json"] and options["json"]["link_preview_options"]["is_disabled"]
    session.error = RuntimeError(TOKEN)
    with pytest.raises(TelegramError) as error:
        client.message("test")
    assert TOKEN not in str(error.value) and error.value.uncertain
    client = TelegramClient(replace(telegram, enabled=False), session)
    before = len(session.calls)
    with pytest.raises(TelegramError): client.message("test")
    assert len(session.calls) == before


def test_worker_retries_bounded_without_request_loop(config, telegram):
    class Failing(Client):
        def updates(self, offset): raise TelegramError(retry_after=2)
    sleeps = []
    with pytest.raises(TelegramError):
        run_bot(config, telegram, Failing(), lambda: NOW, sleeper=sleeps.append)
    assert len(sleeps) == 4 and max(sleeps) <= 60


def test_message_success_attachment_failure_retries_only_attachment(config, telegram, monkeypatch):
    from contextlib import contextmanager
    from ilias_check.support_cache import SupportCache
    data = inventory()
    data["activities"][0]["support_documents"] = [{"document_id": "file:9", "role": "support", "selected_for_support": True, "title": "Blatt.pdf", "state": "cached", "cache": {"eligible": True}}]
    class Partial(Client):
        def document(self, *args):
            self.documents.append(args)
            if len(self.documents) == 1: raise TelegramError("telegram_temporary")
            return {"message_id": 9}
    @contextmanager
    def delivery(*args):
        yield None, {"byte_size": 10}
    monkeypatch.setattr(SupportCache, "delivery", delivery)
    client = Partial(); telegram = replace(telegram, send_documents=True)
    run_monitor(config, telegram, collector=lambda c: data, client=client, clock=lambda: NOW)
    assert len(client.messages) == len(client.documents) == 1
    now = NOW + timedelta(minutes=3)
    data["checked_at"] = stamp(now)
    run_monitor(config, telegram, collector=lambda c: data, client=client, clock=lambda: now)
    assert len(client.messages) == 1 and len(client.documents) == 2


def test_telegram_rate_limit_delay_is_sanitized(telegram):
    class Response:
        status_code = 429
        def json(self): return {"ok": False, "parameters": {"retry_after": 120}, "description": TOKEN}
        def close(self): pass
    class Session:
        def post(self, *args, **kwargs): return Response()
    with pytest.raises(TelegramError) as exc:
        TelegramClient(telegram, Session()).message("test")
    assert exc.value.retry_after == 120 and TOKEN not in str(exc.value)


def test_schema_migration_failure_rolls_back(config, telegram, monkeypatch):
    original = MonitorState._migrate
    def fail(self):
        class FailDB:
            def __enter__(inner): return self.db.__enter__()
            def __exit__(inner, *args): return self.db.__exit__(*args)
            def execute(inner, sql, *args):
                if sql.startswith("CREATE TABLE components"):
                    raise sqlite3.OperationalError("injected migration failure")
                return self.db.execute(sql, *args)
        real = self.db; wrapper = FailDB()
        # Avoid recursive wrapper calls by binding to the real connection.
        wrapper.execute = lambda sql, *args: (_ for _ in ()).throw(sqlite3.OperationalError("injected")) if sql.startswith("CREATE TABLE components") else real.execute(sql, *args)
        wrapper.__class__.__enter__ = lambda inner: real.__enter__()
        wrapper.__class__.__exit__ = lambda inner, *args: real.__exit__(*args)
        self.db = wrapper
        try: original(self)
        finally: self.db = real
    monkeypatch.setattr(MonitorState, "_migrate", fail)
    with pytest.raises(sqlite3.OperationalError):
        with MonitorState(config, telegram.state_dir).open(): pass
    monkeypatch.setattr(MonitorState, "_migrate", original)
    path = next(telegram.state_dir.glob("*.sqlite3"))
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 0
        assert not db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    with MonitorState(config, telegram.state_dir).open() as state:
        assert state.snapshot() is None


def test_missing_unit_after_complete_scan_is_still_inconclusive(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory(), NOW)
        data = inventory(now=NOW + timedelta(hours=1)); data["activities"] = []
        state.observe(data, NOW + timedelta(hours=1))
        assert not state.snapshot()["observation_complete"]
        assert all(component["event_kind"] == "health" for component in state.due(NOW + timedelta(hours=1)))
        client = Client(); bot = Bot(config, telegram, state, client, lambda: NOW + timedelta(hours=1))
        bot.handle(update("/verificar"))
        assert any("last_observation_not_current" in text for text, _ in client.messages)


def test_monitor_applies_persisted_retention_and_maintains_after_scan_failure(config, telegram):
    from test_support_cache import collect as cache_collect, material as cache_material, snapshot as cache_snapshot
    cached = cache_collect(replace(config, cache_policy=replace(config.cache_policy, enabled=True)))
    path = Path(cache_material(cached)["cache"]["path"])
    assert path.exists()
    with MonitorState(config, telegram.state_dir).open() as state:
        state.set_preferences({"retention_max_hours": 1})
    now = NOW + timedelta(hours=2)
    def broken(c):
        assert c.cache_policy.retention_max_hours == 1
        raise RuntimeError("offline failure")
    report = run_monitor(config, telegram, collector=broken, client=Client(), clock=lambda: now)
    assert report["fatal"] and not path.exists()


def test_bot_hourly_maintenance_does_not_trigger_source_crawl(config, telegram, monkeypatch):
    import ilias_check.bot as module
    calls = []; now = [NOW]
    monkeypatch.setattr(module, "maintain", lambda c, clock: calls.append(clock()))
    with MonitorState(config, telegram.state_dir).open() as state:
        bot = Bot(config, telegram, state, Client(), lambda: now[0], lambda c: pytest.fail("local tick crawled ILIAS"))
        bot.maintenance_tick(); bot.maintenance_tick()
        assert len(calls) == 1
        now[0] += timedelta(hours=1)
        bot.maintenance_tick(); assert len(calls) == 2


def test_cli_monitor_dry_run_and_bot_validation(config, tmp_path, monkeypatch, capsys):
    from ilias_check import cli
    env = tmp_path / "settings.env"
    env.write_text("ILIAS_BASE_URL=https://ilias.example/ilias\nILIAS_CLIENT_ID=demo\nILIAS_USER=learner\nILIAS_PASS=synthetic\nILIAS_PENDING_ROOTS=1\nILIAS_TELEGRAM_ENABLED=false\n")
    monkeypatch.setattr(cli, "run_monitor", lambda c, t, dry: {"fatal": False, "complete": False, "dry_run": dry, "sent_components": 0})
    assert cli.main(["monitor", "--env-file", str(env), "--dry-run"]) == 2
    assert json.loads(capsys.readouterr().out)["dry_run"]
    assert cli.main(["bot", "--env-file", str(env)]) == 1
    assert "allowed user ID" in capsys.readouterr().err


def test_deadline_change_does_not_also_enqueue_due_old_reminder(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory(), NOW, reminder_hours=24)
        state.acknowledged(state.due(NOW)[0], 1, NOW)
        later = NOW + timedelta(days=2)
        state.observe(inventory(now=later, deadline=stamp(later + timedelta(days=1))), later, reminder_hours=24)
        due = state.due(later)
        assert len(due) == 1 and due[0]["event_kind"] == "pending"
        assert state.db.execute("SELECT notified_at FROM observations").fetchone()[0] is None


def test_inconclusive_health_notification_offers_original_source_button(config, telegram):
    client = Client()
    run_monitor(config, telegram, collector=lambda c: inventory("unknown"), client=client, clock=lambda: NOW)
    assert len(client.messages) == 1
    assert client.messages[0][1][0][0]["url"] == inventory()["activities"][0]["url"]


def test_pending_notice_discloses_missing_historical_pending_observation(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory(), NOW)
        state.acknowledged(state.due(NOW)[0], 1, NOW)
    later = NOW + timedelta(hours=1)
    client = Client()
    run_monitor(config, telegram, collector=lambda c: inventory(now=later, ass="3"), client=client, clock=lambda: later)
    pending = next(text for text, _ in client.messages if text.startswith("Pendente"))
    assert "incompleta" in pending


def test_slow_dispatch_pauses_components_after_current_evidence_expires(config, telegram):
    from ilias_check.monitor import dispatch
    now = [NOW]
    class SlowClient(Client):
        def message(self, text, buttons=None):
            result = super().message(text, buttons)
            now[0] += timedelta(minutes=16)
            return result
    data = inventory()
    data["activities"].append(inventory(ass="3")["activities"][0])
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(data, NOW)
        client = SlowClient()
        dispatch(state, config, telegram, client, NOW, lambda: now[0])
        assert len(client.messages) == 1
        assert not state.due(now[0])
        assert state.db.execute("SELECT COUNT(*) FROM components WHERE state='paused'").fetchone()[0] == 1


def test_failed_interactive_material_request_keeps_source_navigation(config, telegram):
    data = inventory()
    data["activities"][0]["support_documents"] = [{"document_id": "file:9", "title": "Blatt.pdf", "selected_for_support": True, "role": "support", "state": "metadata_only"}]
    def broken(c):
        raise RuntimeError("source currently unavailable")
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(data, NOW)
        client = Client()
        bot = Bot(config, telegram, state, client, lambda: NOW, broken)
        bot.handle(update("/materiais"))
        token = client.messages[-1][1][0][0]["callback_data"]
        bot.handle(update(uid=2, callback=token))
        assert client.messages[-1][1][0][0]["url"] == data["activities"][0]["url"]


def test_actionable_message_explains_pending_reason_and_contextual_support():
    activity = inventory()["activities"][0]
    activity["reason_codes"] = ["accepting_without_submission"]
    activity["support_documents"] = [{"title": "Unterlagen.pdf", "role": "support", "state": "cached", "association": "contextual"}]
    text = activity_message(activity, stamp(NOW))
    assert "aceita arquivos e não há entrega confirmada" in text
    assert "Unterlagen.pdf (contextual; cópia disponível)" in text


def test_summary_lists_counts_and_explains_empty_extraction(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory("pending"), NOW)
        client = Client(); bot = Bot(config, telegram, state, client, lambda: NOW)
        bot.handle(update("/resumo"))
        text = client.messages[-1][0]
        assert text.startswith("Resumo da observação de")
        assert "1 pendentes" in text

        empty = dict(inventory("pending"), activities=[], classification={"complete": False, "counts": {}},
                     coverage=[{"root_id": "1", "complete": False,
                                "warnings": ["maximum_depth_reached"]}])
        state.observe(empty, NOW + timedelta(minutes=1))
        bot.handle(update("/resumo", uid=2))
        text = client.messages[-1][0]
        assert "nenhuma atividade registrada" in text
        assert "A extração não registrou atividades" in text
        assert "maximum_depth_reached" in text


def test_futuras_lists_not_yet_open_activities(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory("not_yet_open"), NOW)
        client = Client(); bot = Bot(config, telegram, state, client, lambda: NOW)
        bot.handle(update("/futuras"))
        assert client.messages[0][0].startswith("Ainda não abertas — observação de")
        assert any("Übung <b>Original</b>" in text for text, _ in client.messages)


def test_telegram_config_accepts_additional_allowed_users():
    values = {"ILIAS_TELEGRAM_ENABLED": "true", "TELEGRAM_BOT_TOKEN": TOKEN,
              "TELEGRAM_CHAT_ID": "100", "TELEGRAM_ALLOWED_USER_ID": "200",
              "TELEGRAM_ALLOWED_USER_IDS": "300, 400, 300"}
    config = TelegramConfig.from_mapping(values, worker=True)
    assert config.permitted_user_ids == {"200", "300", "400"}

    only_extra = TelegramConfig.from_mapping(
        {**values, "TELEGRAM_ALLOWED_USER_ID": "", "TELEGRAM_ALLOWED_USER_IDS": "300"},
        worker=True,
    )
    assert only_extra.permitted_user_ids == {"300"}

    with pytest.raises(CacheError):
        TelegramConfig.from_mapping({**values, "TELEGRAM_ALLOWED_USER_IDS": "300,abc"})
    with pytest.raises(CacheError):
        TelegramConfig.from_mapping({**values, "TELEGRAM_ALLOWED_USER_ID": "200x"})


def test_secondary_user_needs_own_private_chat_and_has_isolated_draft(config, telegram):
    telegram = replace(telegram, allowed_user_ids=("300",))
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory("pending"), NOW)
        client = Client(); bot = Bot(config, telegram, state, client, lambda: NOW)
        bot.handle(update("/pendentes", uid=1, user=300, chat=300))
        assert client.messages[0][0].startswith("Pendentes")

        sent = len(client.messages)
        bot.handle(update("/pendentes", uid=2, user=300, chat=100))
        bot.handle(update("/pendentes", uid=3, user=301, chat=301))
        assert len(client.messages) == sent

        bot.handle(update("/relatar", uid=4, user=300, chat=300))
        bot.handle(update("descrição do secundário", uid=5, user=300, chat=300))
        bot.handle(update("esperado do secundário", uid=6, user=300, chat=300))
        bot.handle(update("/relatar", uid=7))
        bot.handle(update("descrição do dono", uid=8))
        bot.handle(update("esperado do dono", uid=9))
        bot.handle(update("ocorrido do dono", uid=10))
        bot.handle(update("-", uid=11))
        bot.handle(update("/exportar", uid=12))
        report = client.messages[-1][0]
        assert "Nenhuma issue foi aberta" in report
        assert "descrição do dono" in report and "esperado do dono" in report
        assert "secundário" not in report


def test_material_token_is_bound_to_the_requesting_user(config, telegram):
    telegram = replace(telegram, allowed_user_ids=("300",))
    data = inventory()
    data["activities"][0]["support_documents"] = [{"document_id": "file:9", "title": "Blatt.pdf", "selected_for_support": True, "role": "support", "state": "metadata_only"}]
    calls = []
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(data, NOW)
        client = Client(); bot = Bot(config, telegram, state, client, lambda: NOW, lambda c: calls.append(c) or deepcopy(data))
        bot.handle(update("/materiais"))
        token = client.messages[-1][1][0][0]["callback_data"]
        bot.handle(update(uid=2, user=300, chat=300, callback=token))
        assert not calls
        assert "Ação expirada" in client.messages[-1][0]


def test_activity_and_view_times_use_day_month_year_format(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory("pending"), NOW)
        client = Client(); bot = Bot(config, telegram, state, client, lambda: NOW)
        bot.handle(update("/pendentes"))
        text = "\n".join(t for t, _ in client.messages)
        assert "observação de 14/11/2026 00:00" in text
        assert "Observado em: 14/11/2026 00:00" in text
        assert "2026-11-14T00:00:00Z" not in text


def test_course_timezone_is_applied_to_message_times(config, telegram):
    from ilias_check.telegram import format_time
    assert format_time("2026-11-15T01:24:54Z") == "15/11/2026 01:24"
    assert format_time("2026-11-15T01:24:54Z", "Europe/Berlin") == "15/11/2026 02:24"
    assert format_time("kein Termin") == "kein Termin"
    assert format_time(None) == "não informado"


def test_worker_registers_the_command_menu(telegram):
    from ilias_check.bot import _COMMANDS

    class Response:
        status_code = 200
        def json(self): return {"ok": True, "result": True}
        def close(self): pass

    class Session:
        def __init__(self): self.calls = []
        def post(self, url, **options):
            self.calls.append((url, options)); return Response()

    session = Session()
    TelegramClient(telegram, session).set_commands(_COMMANDS)
    url, options = session.calls[-1]
    assert url.endswith("/setMyCommands")
    assert [item["command"] for item in options["json"]["commands"]][:3] == ["start", "ajuda", "pendentes"]
    assert all(item["description"] for item in options["json"]["commands"])


def test_ajuda_is_help_only_and_start_lists_pending(config, telegram):
    with MonitorState(config, telegram.state_dir).open() as state:
        state.observe(inventory("pending"), NOW)
        client = Client(); bot = Bot(config, telegram, state, client, lambda: NOW)
        bot.handle(update("/ajuda"))
        assert len(client.messages) == 1 and client.messages[0][0].startswith("/pendentes —")
        bot.handle(update("/start", uid=2))
        assert "/futuras" in client.messages[1][0]
        assert client.messages[2][0].startswith("Pendentes — observação de")

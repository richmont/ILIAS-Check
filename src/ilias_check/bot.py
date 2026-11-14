"""Single-owner Portuguese long-poll worker over shared observations and cache."""
from __future__ import annotations

from collections import deque
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
import time

from ilias_check.auth import Authenticator
from ilias_check.cache_config import CacheError
from ilias_check.collector import collect_inventory
from ilias_check.monitor import effective_config, maintain
from ilias_check.monitor_state import MonitorState
from ilias_check.private_storage import process_lock
from ilias_check.support_cache import SupportCache, association_id, cache_inventory, instant, stamp
from ilias_check.telegram import TelegramClient, TelegramError, activity_message, redact, safe_link, source_buttons
from ilias_check.transport import SafeTransport

_ISSUES = "https://github.com/richmont/ILIAS-Check/issues/new"
_HELP = ("/pendentes — uploads pendentes\n/entregues — histórico de entregas\n/encerradas — encerradas sem entrega\n"
         "/verificar — inconclusivas\n/materiais — apoio disponível\n/configuracoes — retenção e uso\n"
         "/relatar — feedback sobre este software\n/cancelar — cancelar diálogo\n"
         "Os textos do ILIAS permanecem originais. A fonte pode exigir login no navegador. Entrega não significa aprovação. "
         "Envie respostas às atividades manualmente no ILIAS; arquivos recebidos aqui não são processados. "
         "Rascunhos de relatos são descartados após reinício ou 30 minutos.")
_VIEWS = {"/pendentes": "pending", "/entregues": "submitted", "/encerradas": "closed_without_submission", "/verificar": "unknown"}
_FIELDS = ("descrição", "esperado", "ocorrido", "link")
_PROMPTS = ("Descreva o problema deste software (somente texto, até 800 caracteres).",
            "Como você esperava que o bot se comportasse ou exibisse a atividade?",
            "O que o bot exibiu ou fez?", "Link original da atividade (HTTPS sem sessão), ou - para omitir.")


class Bot:
    def __init__(self, config, telegram, state, client, clock=None, collector=collect_inventory, retrieve=None):
        self.config, self.telegram, self.state, self.client = config, telegram, state, client
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.collector = collector
        self.retrieve = retrieve or self._retrieve
        self.requests = deque(maxlen=30)
        self.tokens = {}
        self.draft = None
        self.last_check = None
        self.last_maintenance = None

    def authorized(self, update):
        callback = update.get("callback_query")
        message = callback.get("message", {}) if callback else update.get("message", {})
        sender = callback.get("from", {}) if callback else message.get("from", {})
        chat = message.get("chat", {})
        return str(sender.get("id")) == self.telegram.allowed_user_id and str(chat.get("id")) == self.telegram.chat_id and chat.get("type") == "private" and not sender.get("is_bot")

    def handle(self, update):
        update_id = update.get("update_id")
        cursor = "updates:" + hashlib.sha256(self.telegram.token.encode()).hexdigest()
        if type(update_id) is not int or update_id < self.state.cursor(cursor):
            return
        # Claim before side effects: replay cannot repeat settings or a document send.
        self.state.set_cursor(cursor, update_id + 1)
        if not self.authorized(update):
            return
        now = self.clock()
        while self.requests and now - self.requests[0] >= timedelta(minutes=1):
            self.requests.popleft()
        if len(self.requests) >= 20:
            return
        self.requests.append(now)
        if self.draft and now - self.draft["started"] >= timedelta(minutes=30):
            self.draft = None
            self.client.message("O rascunho expirou. Inicie novamente com /relatar.")
        callback = update.get("callback_query")
        if callback:
            try:
                self.client.call("answerCallbackQuery", {"callback_query_id": callback["id"]})
            except TelegramError:
                pass
            return self._callback(callback.get("data", ""))
        message = update.get("message", {})
        text = message.get("text")
        if not isinstance(text, str):
            self.client.message("Envie somente texto. Respostas e arquivos devem ser enviados manualmente no ILIAS; não baixo anexos recebidos.")
            return
        if len(text) > 2000:
            self.client.message("Texto muito longo; use até 800 caracteres por campo de relato.")
            return
        parts = text.strip().split()
        command = parts[0].split("@")[0].lower() if parts else ""
        if command == "/cancelar":
            self.draft = None
            self.client.message("Diálogo cancelado. Nada foi publicado.")
        elif command == "/relatar":
            self.draft = {"started": now, "step": 0, "fields": {}}
            self.client.message("Relato sobre este software, sem envio a professores ou abertura automática de issue. Não inclua dados pessoais. " + _PROMPTS[0])
        elif command == "/editar" and self.draft and len(parts) == 2:
            aliases = {"descricao": 0, "descrição": 0, "esperado": 1, "ocorrido": 2, "link": 3}
            if parts[1] in aliases:
                self.draft["step"] = aliases[parts[1]]
                self.draft["editing"] = True
                self.client.message(_PROMPTS[self.draft["step"]])
        elif command == "/exportar" and self.draft and self.draft["step"] == 4:
            self.client.message(self._report() + f"\nNenhuma issue foi aberta. Compartilhe manualmente após revisar: {_ISSUES}")
            self.draft = None
        elif command.startswith("/"):
            if command in {"/start", "/ajuda"}:
                self.client.message(_HELP)
                self._view("pending", 1)
            elif command in _VIEWS:
                page = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1
                self._view(_VIEWS[command], page)
            elif command == "/materiais":
                page = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1
                self._materials(page)
            elif command == "/configuracoes":
                self._settings()
            elif command == "/retencao":
                self._retention(parts[1:])
            else:
                self.client.message("Comando não disponível. Use /ajuda. A manutenção de materiais é automática.")
        elif self.draft:
            self._report_field(text)
        else:
            self.client.message("Use /ajuda ou /relatar. Rascunhos anteriores ao reinício não são retomados.")

    def _observations(self, status):
        result = []
        for row in self.state.db.execute("SELECT * FROM observations ORDER BY id"):
            activity = json.loads(row["activity"])
            if status == "unknown" and not row["current"] and activity["status"] != "unknown":
                activity["status"] = "unknown"
                activity["reason_codes"] = ["last_observation_not_current"]
            if activity["status"] == status:
                result.append((activity, row["checked_at"], not bool(row["current"])))
        if status == "submitted":
            present = {association_id(a) for a, _, _ in result}
            for row in self.state.db.execute("SELECT * FROM submission_history ORDER BY id"):
                if row["id"] not in present:
                    result.append((json.loads(row["activity"]), row["checked_at"], True))
        return result

    def _token(self, action, payload):
        now = self.clock()
        self.tokens = {k: v for k, v in self.tokens.items() if now - v[2] < timedelta(minutes=30)}
        while len(self.tokens) >= 500:
            self.tokens.pop(next(iter(self.tokens)))
        token = secrets.token_urlsafe(12)
        self.tokens[token] = (action, payload, now)
        return token

    def _view(self, status, page):
        rows = self._observations(status)
        page_count = max(1, (len(rows) + 3) // 4)
        page = min(max(page, 1), page_count)
        snapshot = self.state.snapshot() or {}
        incomplete = not snapshot.get("observation_complete", False) or not snapshot.get("classification", {}).get("complete", False) or any(not c["complete"] for c in snapshot.get("coverage", []))
        text = f"Observação mais recente: {snapshot.get('checked_at', 'nenhuma')}. Página {page}/{page_count}."
        if incomplete:
            text += " Verificação incompleta; consulte /verificar."
        if not rows:
            text += " Nenhuma atividade confirmada nesta categoria; isso não confirma que todas estejam concluídas."
        self.client.message(text)
        for activity, checked, stale in rows[(page - 1) * 4:page * 4]:
            stale = stale or self.clock() - instant(checked) > timedelta(hours=12)
            self.client.message(activity_message(activity, checked, incomplete, stale), source_buttons(activity))
        if page < page_count:
            command = next((k for k, v in _VIEWS.items() if v == status), "/pendentes")
            self.client.message(f"Próxima página: {command} {page + 1}")

    def _materials(self, page=1):
        candidates = [(activity, material) for activity, _, stale in self._observations("pending") if not stale
                      for material in activity.get("support_documents", [])
                      if material.get("selected_for_support") and material.get("role") == "support"]
        page_count = max(1, (len(candidates) + 9) // 10)
        page = min(max(page, 1), page_count)
        buttons = []
        for activity, material in candidates[(page - 1) * 10:page * 10]:
            token = self._token("download", (association_id(activity), material["document_id"]))
            buttons.append([{"text": ("Baixar pelo Telegram: " + material["title"])[:64], "callback_data": token}])
        self.client.message("Ao tocar em um material, você autoriza enviar essa cópia pelo Telegram. Isso não ativa anexos automáticos futuros. "
                            "O envio exige nova verificação no ILIAS; ele pode estar mais atualizado. Cópias já enviadas não podem ser revogadas. "
                            f"Página {page}/{page_count}." if buttons else
                            "Nenhum apoio confirmado disponível. Confira a atividade no ILIAS ou /verificar.", buttons)
        if page < page_count:
            self.client.message(f"Próxima página: /materiais {page + 1}")

    def _callback(self, token):
        entry = self.tokens.pop(token, None)
        if not entry or self.clock() - entry[2] >= timedelta(minutes=30):
            self.client.message("Ação expirada ou desconhecida. Abra o menu novamente.")
            return
        action, payload, _ = entry
        if action != "download":
            return
        aid, document_id = payload
        now = self.clock()
        last_check = self.state.cursor("support_check_at")
        if last_check and now.timestamp() - last_check < 300:
            self.client.message("Uma verificação de materiais já foi feita recentemente. Aguarde cinco minutos e consulte o ILIAS.")
            return
        self.last_check = now
        try:
            with self.state.run_lock():
                self.state.set_cursor("support_check_at", int(now.timestamp()))
                config = effective_config(self.config, self.state)
                # The scan observes metadata only; consent covers only the selected material.
                inventory = self.collector(replace(config, cache_policy=replace(config.cache_policy, enabled=False)))
                self.state.observe(inventory, self.clock(), self.telegram.reminder_hours, self.telegram.send_documents)
                activity = next((a for a in inventory["activities"] if association_id(a) == aid), None)
                material = next((m for m in activity.get("support_documents", []) if m["document_id"] == document_id and m["selected_for_support"] and m["role"] == "support"), None) if activity else None
                if not activity or activity["status"] != "pending" or not material:
                    raise CacheError("Eligibility not confirmed.")
                self.retrieve(config, inventory, activity, material)
        except Exception:
            self.client.message("Não foi possível confirmar uma cópia elegível agora. Consulte o ILIAS e /verificar; nenhum estado da atividade foi alterado.")

    def _retrieve(self, config, inventory, activity, material):
        for a in inventory["activities"]:
            for m in a.get("support_documents", []):
                m["selected_for_support"] = a is activity and m is material
        config = replace(config, cache_policy=replace(config.cache_policy, enabled=True))
        transport = SafeTransport(config)
        try:
            updated = cache_inventory(inventory, config, Authenticator(config, transport), self.clock)
            activity = next(a for a in updated["activities"] if association_id(a) == association_id(activity))
            with SupportCache(config, self.clock).delivery(material["document_id"], activity, updated["checked_at"]) as (source, entry):
                self.client.document(source, entry, activity, updated["checked_at"])
        finally:
            transport.close()

    def _settings(self):
        config = effective_config(self.config, self.state)
        policy = config.cache_policy
        usage = "não medido"
        if policy.directory.expanduser().exists():
            try:
                with SupportCache(config, self.clock).locked() as cache:
                    usage = f"{cache.usage() / 1000000:.2f} MB"
            except Exception:
                usage = "temporariamente indisponível"
        self.client.message(f"Sem prazo: {policy.no_deadline_hours} horas (padrão: 168). Limite adicional: {policy.retention_max_hours or 'padrão, sem limite adicional'}. "
                            f"Prazo/entrega confirmada continuam limites superiores. Uso gerenciado: {usage}; quota: {policy.max_bytes / 1000000:g} MB. Medido em {stamp(self.clock())}. "
                            "Expiração e remoção são automáticas; isto não é o uso total do disco.\n"
                            "/retencao sem_prazo 24\n/retencao limite 48\n/retencao padrao\n"
                            "Aumentar a duração não recupera cópias expiradas; uma nova obtenção exige verificação atual.")

    def _retention(self, args):
        try:
            if args == ["padrao"]:
                with self.state.db:
                    self.state.db.execute("DELETE FROM preferences WHERE key IN ('no_deadline_hours','retention_max_hours')")
            elif len(args) == 2 and args[0] in {"sem_prazo", "limite"} and args[1].isdigit():
                key = "no_deadline_hours" if args[0] == "sem_prazo" else "retention_max_hours"
                self.state.set_preferences({key: int(args[1])})
            else:
                raise CacheError("Invalid preference.")
            self.client.message("Retenção salva. A manutenção automática aplicará a política; prazos e entregas continuam prevalecendo.")
        except CacheError:
            self.client.message("Use horas inteiras entre 1 e 87600, ou /retencao padrao. Quota e segurança são configuradas somente no host.")

    def _report_field(self, text):
        step = self.draft["step"]
        if step == 4:
            self.client.message("Revise com /editar descricao, /editar esperado, /editar ocorrido ou /editar link; /exportar ou /cancelar.")
            return
        if not text.strip() or len(text) > 800:
            self.client.message("Use somente texto de 1 a 800 caracteres.")
            return
        if step == 3 and text.strip() != "-" and not safe_link(text.strip()):
            self.client.message("Use um link HTTPS original sem sessão, ou - para omitir.")
            return
        self.draft["fields"][_FIELDS[step]] = redact(text.strip(), (self.config.password, self.config.username, self.telegram.token))
        if self.draft.pop("editing", False):
            self.draft["step"] = 4
        else:
            self.draft["step"] += 1
        if self.draft["step"] == 4:
            self.client.message(self._report() + "\nRevise dados pessoais; a ocultação automática pode não remover tudo. /editar descricao|esperado|ocorrido|link, /exportar ou /cancelar. Nada foi publicado.")
        else:
            self.client.message(_PROMPTS[self.draft["step"]])

    def _report(self):
        return "Relato sobre o ILIAS-Check\n" + "\n".join(f"{field}: {self.draft['fields'].get(field, '-')}" for field in _FIELDS)

    def maintenance_tick(self):
        now = self.clock()
        if self.last_maintenance is None or now - self.last_maintenance >= timedelta(hours=1):
            maintain(effective_config(self.config, self.state), self.clock)
            self.last_maintenance = now


def run_bot(config, telegram, client=None, clock=None, max_polls=None, sleeper=time.sleep):
    owned = client is None
    client = client or TelegramClient(telegram)
    clock = clock or (lambda: datetime.now(timezone.utc))
    try:
        with MonitorState(config, telegram.state_dir).open() as state:
            lock_id = hashlib.sha256((telegram.token + ":" + telegram.chat_id).encode()).hexdigest()
            with process_lock(state.fd, "worker-" + lock_id + ".lock"):
                bot = Bot(config, telegram, state, client, clock)
                cursor = "updates:" + hashlib.sha256(telegram.token.encode()).hexdigest()
                failures = 0
                polls = 0
                while max_polls is None or polls < max_polls:
                    bot.maintenance_tick()
                    try:
                        updates = client.updates(state.cursor(cursor))
                        for update in updates[:25]:
                            bot.handle(update)
                        failures = 0
                    except TelegramError as exc:
                        failures += 1
                        if failures >= 5:
                            raise TelegramError("telegram_worker_retries_exhausted") from None
                        if exc.retry_after > 60:
                            raise TelegramError("telegram_worker_deferred", exc.retry_after) from None
                        sleeper(min(max(2 ** failures, exc.retry_after), 60))
                    polls += 1
    finally:
        if owned:
            client.close()

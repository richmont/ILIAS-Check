"""Authorized Portuguese long-poll worker over shared observations and cache."""
from __future__ import annotations

from collections import Counter, deque
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
from ilias_check.telegram import (
    TelegramClient, TelegramError, activity_message, format_time, redact, safe_link,
    source_buttons,
)
from ilias_check.transport import SafeTransport

_ISSUES = "https://github.com/richmont/ILIAS-Check/issues/new"
_HELP = ("/pendentes — uploads pendentes\n/entregues — histórico de entregas\n/encerradas — encerradas sem entrega\n"
         "/futuras — ainda não abertas\n/verificar — inconclusivas\n/resumo — contagem por situação\n"
         "/materiais — apoio disponível\n/configuracoes — retenção e uso\n"
         "/relatar — feedback sobre este software\n/cancelar — cancelar diálogo\n"
         "As listas vêm paginadas; toque no número para ver detalhes, links e downloads, ou em “Exibir todas”. "
         "Os textos do ILIAS permanecem originais. A fonte pode exigir login no navegador. Entrega não significa aprovação. "
         "Envie respostas às atividades manualmente no ILIAS; arquivos recebidos aqui não são processados. "
         "Rascunhos de relatos são descartados após reinício ou 30 minutos.")
_VIEWS = {"/pendentes": "pending", "/entregues": "submitted", "/encerradas": "closed_without_submission",
          "/futuras": "not_yet_open", "/verificar": "unknown"}
_TITLES = {"pending": "Pendentes", "submitted": "Entregues",
           "closed_without_submission": "Encerradas sem entrega",
           "not_yet_open": "Ainda não abertas", "unknown": "Inconclusivas"}
_EMPTY = {
    "pending": "Nenhuma atividade pendente confirmada; isso não confirma que todas estejam concluídas.",
    "submitted": "Nenhuma entrega confirmada no histórico.",
    "closed_without_submission": "Nenhuma atividade encerrada sem entrega registrada.",
    "not_yet_open": "Nenhuma atividade com período ainda não aberto.",
    "unknown": "Nenhuma atividade inconclusiva registrada.",
}
_STATUS_LABELS = (("pending", "pendentes"), ("submitted", "entregues"),
                  ("closed_without_submission", "encerradas sem entrega"),
                  ("not_yet_open", "ainda não abertas"), ("excluded", "excluídas"),
                  ("unknown", "inconclusivas"))
_COMMANDS = (
    {"command": "start", "description": "Iniciar e ver a ajuda"},
    {"command": "ajuda", "description": "Lista de comandos"},
    {"command": "pendentes", "description": "Uploads pendentes"},
    {"command": "entregues", "description": "Histórico de entregas"},
    {"command": "encerradas", "description": "Encerradas sem entrega"},
    {"command": "futuras", "description": "Ainda não abertas"},
    {"command": "verificar", "description": "Casos inconclusivos"},
    {"command": "resumo", "description": "Contagem por situação"},
    {"command": "materiais", "description": "Materiais de apoio disponíveis"},
    {"command": "configuracoes", "description": "Retenção e uso do cache"},
    {"command": "retencao", "description": "Ajustar retenção de materiais"},
    {"command": "relatar", "description": "Relatar problema do software"},
    {"command": "cancelar", "description": "Cancelar diálogo"},
)
_FIELDS = ("descrição", "esperado", "ocorrido", "link")
_PAGE = 5
_PROMPTS = ("Descreva o problema deste software (somente texto, até 800 caracteres).",
            "Como você esperava que o bot se comportasse ou exibisse a atividade?",
            "O que o bot exibiu ou fez?", "Link original da atividade (HTTPS sem sessão), ou - para omitir.")


def _counts_text(counts):
    parts = [f"{counts[status]} {label}" for status, label in _STATUS_LABELS if counts.get(status)]
    return ", ".join(parts)


class Bot:
    def __init__(self, config, telegram, state, client, clock=None, collector=collect_inventory, retrieve=None):
        self.config, self.telegram, self.state, self.client = config, telegram, state, client
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.collector = collector
        self.retrieve = retrieve or self._retrieve
        self.requests = {}
        self.tokens = {}
        self.draft = None
        self.drafts = {}
        self.last_check = None
        self.last_maintenance = None

    @staticmethod
    def _sender(update):
        callback = update.get("callback_query")
        message = callback.get("message", {}) if callback else update.get("message", {})
        sender = callback.get("from", {}) if callback else message.get("from", {})
        return sender, message.get("chat", {})

    def authorized(self, update):
        sender, chat = self._sender(update)
        if sender.get("is_bot") or chat.get("type") != "private":
            return False
        user_id, chat_id = str(sender.get("id")), str(chat.get("id"))
        if user_id not in self.telegram.permitted_user_ids:
            return False
        # The configured chat belongs to the primary owner; additional users are
        # accepted only in their own private chat, where chat ID equals user ID.
        if chat_id == self.telegram.chat_id:
            return user_id == self.telegram.allowed_user_id
        return chat_id == user_id

    def handle(self, update):
        update_id = update.get("update_id")
        cursor = "updates:" + hashlib.sha256(self.telegram.token.encode()).hexdigest()
        if type(update_id) is not int or update_id < self.state.cursor(cursor):
            return
        # Claim before side effects: replay cannot repeat settings or a document send.
        self.state.set_cursor(cursor, update_id + 1)
        if not self.authorized(update):
            return
        uid = str(self._sender(update)[0].get("id"))
        now = self.clock()
        requests = self.requests.setdefault(uid, deque(maxlen=30))
        while requests and now - requests[0] >= timedelta(minutes=1):
            requests.popleft()
        if len(requests) >= 20:
            return
        requests.append(now)
        self.draft = self.drafts.get(uid)
        original_client = self.client
        try:
            route = getattr(original_client, "for_chat", None)
            if callable(route):
                self.client = route(self._sender(update)[1]["id"])
            self._dispatch(update, uid, now)
        finally:
            self.client = original_client
            if self.draft is None:
                self.drafts.pop(uid, None)
            else:
                self.drafts[uid] = self.draft
            self.draft = None

    def _dispatch(self, update, uid, now):
        if self.draft and now - self.draft["started"] >= timedelta(minutes=30):
            self.draft = None
            self.client.message("O rascunho expirou. Inicie novamente com /relatar.")
        callback = update.get("callback_query")
        if callback:
            try:
                self.client.call("answerCallbackQuery", {"callback_query_id": callback["id"]})
            except TelegramError:
                pass
            return self._callback(callback.get("data", ""), uid)
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
            if command == "/start":
                self.client.message(_HELP)
                self._view("pending", 1, uid)
            elif command == "/ajuda":
                self.client.message(_HELP)
            elif command in _VIEWS:
                self._view(_VIEWS[command], 1, uid)
            elif command == "/materiais":
                self._materials(1, uid)
            elif command == "/configuracoes":
                self._settings()
            elif command == "/resumo":
                self._summary()
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

    def _token(self, action, payload, owner):
        now = self.clock()
        self.tokens = {k: v for k, v in self.tokens.items() if now - v[2] < timedelta(minutes=30)}
        while len(self.tokens) >= 500:
            self.tokens.pop(next(iter(self.tokens)))
        token = secrets.token_urlsafe(12)
        self.tokens[token] = (action, payload, now, owner)
        return token

    def _view(self, status, page, uid):
        rows = self._observations(status)
        page_count = max(1, (len(rows) + _PAGE - 1) // _PAGE)
        page = min(max(page, 1), page_count)
        snapshot = self.state.snapshot() or {}
        plural = "s" if len(rows) != 1 else ""
        lines = [f"{_TITLES[status]} — {len(rows)} atividade{plural}; "
                 f"observação de {self._observed(snapshot)}; página {page}/{page_count}."]
        if not rows:
            lines.append(_EMPTY[status])
            counts = self._counts(snapshot)
            if counts:
                lines.append(f"Resumo: {_counts_text(counts)}; use /resumo.")
        if self._incomplete(snapshot):
            if status == "unknown":
                lines.append(self._health_text(snapshot) or "A última verificação não foi concluída.")
            else:
                lines.append("Verificação incompleta; detalhes em /verificar.")
        first = (page - 1) * _PAGE + 1
        shown = rows[first - 1:first - 1 + _PAGE]
        if shown:
            lines.append("")
            for offset, (activity, checked, stale) in enumerate(shown, first):
                lines.append(f"{offset}. {self._summary_line(activity, checked, stale)}")
            lines.append("")
            lines.append("Toque no número para ver prazo, motivo, links e downloads.")
        self.client.message("\n".join(lines),
                            self._page_buttons(status, page, page_count, len(rows), shown, first, uid))

    def _page_buttons(self, status, page, page_count, total, shown, first, uid):
        rows = []
        if page_count > 1:
            nav = []
            if page > 1:
                nav.append({"text": "◀ Anterior",
                            "callback_data": self._token("page", (status, page - 1), uid)})
            if page < page_count:
                nav.append({"text": "Próxima ▶",
                            "callback_data": self._token("page", (status, page + 1), uid)})
            rows.append(nav)
        if shown:
            rows.append([{"text": f"Exibir todas ({total})",
                          "callback_data": self._token("all", (status,), uid)}])
        if shown:
            rows.append([{"text": str(first + index),
                          "callback_data": self._token("detail", (status, association_id(activity)), uid)}
                         for index, (activity, _, _) in enumerate(shown)])
        return rows

    def _summary_line(self, activity, checked, stale):
        hints = []
        if activity["status"] in {"pending", "not_yet_open"}:
            if activity.get("deadline_at"):
                hints.append("prazo " + format_time(activity["deadline_at"], self._timezone()))
            elif activity.get("deadline_text"):
                hints.append(str(activity["deadline_text"])[:60])
            else:
                hints.append("sem prazo")
        elif activity["status"] == "unknown":
            hints.append("precisa verificar")
        elif activity["status"] == "submitted":
            history = activity.get("submission_history") or []
            moment = format_time(history[0]["submitted_at"], self._timezone()) if history and history[0].get("submitted_at") else None
            hints.append("entrega " + moment if moment else "entrega registrada")
        hint = " — " + "; ".join(hints) if hints else ""
        old = " (observação antiga)" if stale or self.clock() - instant(checked) > timedelta(hours=12) else ""
        return " ".join(activity["title"].split())[:120] + hint + old

    def _send_detail(self, activity, checked, stale):
        snapshot = self.state.snapshot() or {}
        stale = stale or self.clock() - instant(checked) > timedelta(hours=12)
        buttons = source_buttons(activity)
        if activity["status"] == "pending":
            buttons += self.state.material_buttons(activity, self.clock())
        text = activity_message(activity, checked, self._incomplete(snapshot), stale, self._timezone())
        if any("callback_data" in button for row in buttons for button in row):
            disclosure = "Baixar autoriza o envio dessa cópia pelo Telegram após nova verificação no ILIAS."
            available = max(0, self.telegram.max_message_chars - len(disclosure) - 2)
            text = text[:available] + "\n\n" + disclosure
        self.client.message(text, buttons)

    def _all(self, status, uid):
        rows = self._observations(status)
        if not rows:
            self._view(status, 1, uid)
            return
        snapshot = self.state.snapshot() or {}
        self.client.message(f"{_TITLES[status]} — todas as {len(rows)} atividades; "
                            f"observação de {self._observed(snapshot)}.")
        for activity, checked, stale in rows:
            self._send_detail(activity, checked, stale)

    def _incomplete(self, snapshot):
        return (not snapshot.get("observation_complete", False)
                or not snapshot.get("classification", {}).get("complete", False)
                or any(not item["complete"] for item in snapshot.get("coverage", [])))

    def _timezone(self):
        return self.config.classification_policy.timezone

    def _observed(self, snapshot):
        checked = snapshot.get("checked_at")
        return format_time(checked, self._timezone()) if checked else "nenhuma"

    def _health_text(self, snapshot):
        parts = []
        incomplete = [item for item in snapshot.get("coverage", []) if not item.get("complete")]
        if incomplete:
            roots = ", ".join(str(item.get("root_id")) for item in incomplete)
            parts.append("Cobertura incompleta no(s) root(s) " + roots + ".")
            warnings = sorted({w for item in incomplete for w in item.get("warnings", [])})
            if warnings:
                shown = ", ".join(warnings[:4])
                if len(warnings) > 4:
                    shown += f" (+{len(warnings) - 4})"
                parts.append("Avisos: " + shown + ".")
        if not snapshot.get("activities"):
            parts.append("A extração não registrou atividades; confira os roots configurados e o acesso ao curso.")
        if not snapshot.get("classification", {}).get("complete", False):
            parts.append("A classificação contém casos sem confirmação.")
        if not snapshot.get("observation_complete", False) and not parts:
            parts.append("A última verificação não foi concluída.")
        return " ".join(parts)

    def _counts(self, snapshot):
        return Counter(activity.get("status") for activity in snapshot.get("activities", []))

    def _summary(self):
        snapshot = self.state.snapshot() or {}
        counts = self._counts(snapshot)
        if counts:
            text = f"Resumo da observação de {self._observed(snapshot)}: {_counts_text(counts)}."
        else:
            text = f"Resumo da observação de {self._observed(snapshot)}: nenhuma atividade registrada."
        health = self._health_text(snapshot)
        if health:
            text += " " + health
        self.client.message(text)

    def _materials(self, page, uid):
        candidates = [(activity, material) for activity, _, stale in self._observations("pending") if not stale
                      for material in activity.get("support_documents", [])
                      if material.get("selected_for_support") and material.get("role") == "support"]
        page_count = max(1, (len(candidates) + 9) // 10)
        page = min(max(page, 1), page_count)
        buttons = []
        for activity, material in candidates[(page - 1) * 10:page * 10]:
            token = self._token("download", (association_id(activity), material["document_id"]), uid)
            buttons.append([{"text": ("Baixar pelo Telegram: " + material["title"])[:64], "callback_data": token}])
        if page_count > 1:
            nav = []
            if page > 1:
                nav.append({"text": "◀ Anterior",
                            "callback_data": self._token("materials_page", (page - 1,), uid)})
            if page < page_count:
                nav.append({"text": "Próxima ▶",
                            "callback_data": self._token("materials_page", (page + 1,), uid)})
            buttons.append(nav)
        self.client.message("Ao tocar em um material, você autoriza enviar essa cópia pelo Telegram. Isso não ativa anexos automáticos futuros. "
                            "O envio exige nova verificação no ILIAS; ele pode estar mais atualizado. Cópias já enviadas não podem ser revogadas. "
                            f"Página {page}/{page_count}." if buttons else
                            "Nenhum apoio confirmado disponível. Confira a atividade no ILIAS ou /verificar.", buttons)


    def _callback(self, token, uid):
        if token.startswith("m:"):
            claim = self.state.claim_material(token[2:], self.clock())
            if claim is None:
                self.client.message("Ação expirada ou desconhecida. Abra o menu novamente.")
                return
            action, payload = "download", claim
        else:
            entry = self.tokens.pop(token, None)
            if (not entry or entry[3] != uid
                    or self.clock() - entry[2] >= timedelta(minutes=30)):
                self.client.message("Ação expirada ou desconhecida. Abra o menu novamente.")
                return
            action, payload, _, _ = entry
        if action != "download":
            if action == "page":
                self._view(payload[0], payload[1], uid)
            elif action == "materials_page":
                self._materials(payload[0], uid)
            elif action == "detail":
                # Resolve through the same view as the list: submitted history and
                # derived unknown rows must not silently become a current pending item.
                row = next((row for row in self._observations(payload[0])
                            if association_id(row[0]) == payload[1]), None)
                if row is None:
                    self.client.message("A atividade mudou desde a listagem. Abra o menu novamente.")
                else:
                    self._send_detail(*row)
            elif action == "all":
                self._all(payload[0], uid)
            return
        aid, document_id = payload
        now = self.clock()
        last_check = self.state.cursor("support_check_at")
        if last_check and now.timestamp() - last_check < 300:
            self.client.message("Uma verificação de materiais já foi feita recentemente. Aguarde cinco minutos e consulte o ILIAS.")
            return
        self.last_check = now
        previous = self.state.db.execute("SELECT activity FROM observations WHERE id=?", (aid,)).fetchone()
        activity = json.loads(previous["activity"]) if previous else None
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
            self.client.message("Não foi possível confirmar uma cópia elegível agora. Consulte o ILIAS e /verificar; nenhum estado da atividade foi alterado.", source_buttons(activity) if activity else [])

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
                self.client.document(source, entry, activity, updated["checked_at"], self._timezone())
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
                            f"Prazo/entrega confirmada continuam limites superiores. Uso gerenciado: {usage}; quota: {policy.max_bytes / 1000000:g} MB. Medido em {format_time(stamp(self.clock()), self._timezone())}. "
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
                register = getattr(client, "set_commands", None)
                if callable(register):
                    try:
                        register(_COMMANDS)
                    except TelegramError:
                        pass
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

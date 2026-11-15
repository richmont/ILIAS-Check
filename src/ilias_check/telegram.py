"""Isolated outbound/inbound Bot API client. No ILIAS session or file-ID bypass."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from ilias_check.cache_config import CacheError, boolean, positive
from ilias_check.transport import _has_sensitive_url_material


class TelegramError(RuntimeError):
    def __init__(self, code="telegram_unavailable", retry_after=60, uncertain=False):
        super().__init__(code)
        self.retry_after = min(max(int(retry_after), 1), 86400)
        self.uncertain = uncertain


def _user_ids(raw):
    ids = []
    for item in (raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        if not re.fullmatch(r"[1-9][0-9]*", item):
            raise CacheError("TELEGRAM_ALLOWED_USER_IDS must contain positive numeric user IDs.")
        if item not in ids:
            ids.append(item)
    return tuple(ids)


def format_time(value, timezone_name=None):
    """Render ISO timestamps as DD/MM/YYYY HH:MM in the configured course zone."""
    if not value:
        return "não informado"
    text = str(value)
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if moment.tzinfo is None:
        return text
    zone = timezone.utc
    if timezone_name:
        try:
            zone = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            zone = timezone.utc
    return moment.astimezone(zone).strftime("%d/%m/%Y %H:%M")


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool = False
    token: str = field(default="", repr=False)
    chat_id: str = ""
    allowed_user_id: str = ""
    send_documents: bool = False
    max_document_bytes: int = 20 * 1024 * 1024
    max_message_chars: int = 4000
    state_dir: Path = Path("~/.local/share/ilias-check/monitor")
    reminder_hours: int = 0
    allowed_user_ids: tuple[str, ...] = ()

    @property
    def permitted_user_ids(self) -> frozenset[str]:
        return frozenset(
            item for item in (self.allowed_user_id, *self.allowed_user_ids) if item
        )

    @classmethod
    def from_mapping(cls, values, worker=False):
        enabled = boolean(values, "ILIAS_TELEGRAM_ENABLED")
        token = (values.get("TELEGRAM_BOT_TOKEN") or "").strip()
        chat = (values.get("TELEGRAM_CHAT_ID") or "").strip()
        owner = (values.get("TELEGRAM_ALLOWED_USER_ID") or "").strip()
        extra = _user_ids(values.get("TELEGRAM_ALLOWED_USER_IDS"))
        if enabled and (not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,}", token) or not re.fullmatch(r"[1-9][0-9]*", chat)):
            raise CacheError("Enabled Telegram requires a valid token and positive private chat ID.")
        if owner and not re.fullmatch(r"[1-9][0-9]*", owner):
            raise CacheError("TELEGRAM_ALLOWED_USER_ID must be a positive numeric user ID.")
        if worker and (not enabled or not (owner or extra)):
            raise CacheError("Bot worker requires enabled Telegram and at least one allowed user ID.")
        try:
            reminders = int(values.get("ILIAS_PENDING_REMINDER_HOURS") or 0)
            if reminders < 0:
                raise ValueError
        except ValueError:
            raise CacheError("Reminder hours must be a nonnegative integer.") from None
        return cls(enabled, token, chat, owner, boolean(values, "ILIAS_TELEGRAM_SEND_DOCUMENTS"),
                   min(positive(values, "ILIAS_TELEGRAM_MAX_DOCUMENT_BYTES", 20 * 1024 * 1024), 50000000),
                   min(positive(values, "ILIAS_TELEGRAM_MAX_MESSAGE_CHARS", 4000), 4096),
                   Path(values.get("ILIAS_MONITOR_STATE_DIR") or "~/.local/share/ilias-check/monitor"), reminders,
                   extra)


def safe_link(url):
    try:
        parsed = urlsplit(url or "")
        return bool(parsed.scheme == "https" and parsed.hostname and parsed.username is None and parsed.password is None and not parsed.fragment and not _has_sensitive_url_material(url))
    except ValueError:
        return False


def redact(text, secrets=()):
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[oculto]")
    text = re.sub(r"\b[0-9]{5,}:[A-Za-z0-9_-]{20,}\b", "[token oculto]", text)
    text = re.sub(r"(?i)((?:token|password|passwd|cookie|authorization|(?:php)?sessid|session|csrf|sesskey)\s*[=:]\s*)[^\s&;]+", r"\1[oculto]", text)
    text = re.sub(r"https?://[^\s<>]+", lambda m: m[0] if safe_link(m[0]) else "[link de sessão oculto]", text)
    return text


class TelegramClient:
    def __init__(self, config, session=None):
        self.config = config
        self.session = session or requests.Session()

    def call(self, method, payload, files=None):
        if not self.config.enabled:
            raise TelegramError("telegram_disabled")
        if method not in {"sendMessage", "sendDocument", "getUpdates", "answerCallbackQuery", "setMyCommands"}:
            raise TelegramError("telegram_method_refused")
        try:
            options = {"data": {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in payload.items()}, "files": files} if files else {"json": payload}
            response = self.session.post(f"https://api.telegram.org/bot{self.config.token}/{method}",
                                         timeout=(10, 45), allow_redirects=False, **options)
            try:
                result = response.json()
                if response.status_code == 429 or result.get("error_code") == 429:
                    raise TelegramError("telegram_rate_limited", result.get("parameters", {}).get("retry_after", 60))
                if response.status_code != 200 or not result.get("ok"):
                    raise TelegramError("telegram_request_rejected", uncertain=response.status_code >= 500)
                return result["result"]
            finally:
                response.close()
        except TelegramError:
            raise
        except Exception:
            raise TelegramError("telegram_delivery_uncertain", uncertain=True) from None

    def message(self, text, buttons=None):
        # Plain text: source markup is never parsed as Telegram HTML/Markdown.
        text = redact(text, (self.config.token,))
        text = text[:self.config.max_message_chars]
        payload = {"chat_id": self.config.chat_id, "text": text, "link_preview_options": {"is_disabled": True}}
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        return self.call("sendMessage", payload)

    def document(self, source, entry, activity, checked_at):
        if entry["byte_size"] > self.config.max_document_bytes:
            raise TelegramError("telegram_document_too_large")
        link = activity.get("url") if safe_link(activity.get("url")) else "Abra o ILIAS."
        association = entry["associations"].get(activity["exercise_id"] + ":" + str(activity["assignment_id"]), {})
        caption = (f"Cópia de apoio — {activity['title'][:180]}\nBaixada: {format_time(entry['downloaded_at'])}\n"
                   f"Validada: {format_time(entry['last_validated_at'])}\nExpira: {format_time(association.get('expires_at'))}\n"
                   f"ILIAS é a fonte oficial e pode estar mais atualizado. Cópias já enviadas não podem ser revogadas.\n{link}")
        return self.call("sendDocument", {"chat_id": self.config.chat_id, "caption": caption[:1024]},
                         files={"document": ("material" + _extension(entry["media_type"]), source, entry["media_type"])})

    def set_commands(self, commands):
        return self.call("setMyCommands", {"commands": list(commands)})

    def updates(self, offset):
        return self.call("getUpdates", {"offset": offset, "timeout": 25, "limit": 25, "allowed_updates": ["message", "callback_query"]})

    def close(self):
        self.session.close()


def _extension(media):
    from ilias_check.support_cache import _TYPES
    return next((s for s, m in _TYPES.items() if m == media), ".bin")


def activity_message(activity, checked_at, incomplete=False, stale=False, timezone_name=None):
    labels = {"pending": "Pendente", "submitted": "Entregue (aprovação não presumida)",
              "closed_without_submission": "Encerrada sem entrega", "excluded": "Fora do filtro de uploads",
              "not_yet_open": "Ainda não aberta", "unknown": "Inconclusivo — precisa verificar"}
    lines = [labels[activity["status"]], activity["title"],
             f"Observado em: {format_time(checked_at, timezone_name)}"]
    reasons = {
        "accepting_without_submission": "A atividade aceita arquivos e não há entrega confirmada.",
        "personal_submission_confirmed": "Há uma entrega pessoal confirmada no ILIAS.",
        "team_submission_confirmed": "Há uma entrega confirmada para a sua equipe.",
        "closed_without_submission": "O ILIAS confirmou o encerramento sem entrega.",
        "not_yet_open": "O período de envio ainda não está aberto.",
        "explicitly_excluded": "A atividade foi excluída pelo filtro local configurado.",
        "not_applicable": "A fonte ou o filtro configurado indica que esta atividade não se aplica.",
        "non_file_delivery": "A atividade não utiliza entrega de arquivo.",
    }
    if activity["status"] != "unknown" and activity.get("reason_codes"):
        lines.append("Motivo: " + " ".join(reasons.get(reason, "Consulte os critérios e a fonte no ILIAS.") for reason in activity["reason_codes"]))
    if incomplete or stale:
        lines.append("Verificação incompleta ou observação antiga; confira a situação no ILIAS.")
    lines.append(f"Prazo: {activity.get('deadline_text') or 'não informado'} ({activity.get('deadline_timezone') or 'fuso não resolvido'})")
    for path in activity.get("paths", [])[:3]:
        lines.append(" / ".join(path)[:400])
    if activity.get("requirement_text"):
        lines.append(activity["requirement_text"][:300])
    if activity.get("instructions"):
        lines.append(activity["instructions"][:1200] + ("\nTexto longo; continue na fonte." if len(activity["instructions"]) > 1200 else ""))
    if activity["status"] == "unknown":
        lines.append("A fonte não permite confirmar o estado: " + ", ".join(activity.get("reason_codes", []))[:300])
        lines.append("Use /relatar para explicar como espera que o bot exiba esta atividade. Seu feedback não altera o estado da tarefa.")
    for history in activity.get("submission_history", [])[:3]:
        scope = {"team": "equipe", "personal": "pessoal"}.get(history.get("scope"), "não confirmado")
        lines.append(f"Entrega {scope}: {history.get('submitted_at') or 'data não confirmada'}; anexo: {_known(history.get('attachment_present'))}; aprovação: {_known(history.get('approved'))}; conclusão: {_known(history.get('completed'))}.")
    docs = activity.get("support_documents", [])
    if docs:
        states = {"cached": "cópia disponível", "unchanged": "cópia validada", "metadata_only": "somente referência",
                  "unavailable": "indisponível", "stale": "validação pendente", "expired": "expirado",
                  "evicted": "removido por limite de armazenamento", "skipped": "não obtido", "error": "falha na obtenção"}
        materials = []
        for document in docs:
            if document.get("role") == "support":
                association = "contextual; " if document.get("association") == "contextual" else ""
                state = states.get(document["state"], "estado não confirmado")
                materials.append(f"{document['title'][:100]} ({association}{state})")
        lines.append("Materiais de apoio: " + "; ".join(materials)[:500])
    return "\n".join(lines)


def source_buttons(activity):
    if not safe_link(activity.get("url")):
        return []
    label = "Abrir sequência" if activity.get("url_kind") == "sequence_entry" else "Abrir no ILIAS"
    return [[{"text": label, "url": activity["url"]}]]


def _known(value):
    return "sim" if value is True else "não" if value is False else "não confirmado"

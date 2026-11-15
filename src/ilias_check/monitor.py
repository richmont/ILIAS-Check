"""One-shot monitor; activation and external scheduling are explicitly separate."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import sqlite3

from ilias_check.collector import collect_inventory
from ilias_check.monitor_state import MonitorState
from ilias_check.support_cache import SupportCache, cache_inventory, instant
from ilias_check.telegram import (
    TelegramClient, TelegramError, format_time, source_buttons,
)


def effective_config(config, state):
    return replace(config, cache_policy=replace(config.cache_policy, **state.preferences()))


def maintain(config, clock):
    if not config.cache_policy.directory.expanduser().exists():
        return None
    try:
        with SupportCache(config, clock).locked() as cache:
            cache.maintenance()
            return {"usage_bytes": cache.usage(), "quota_bytes": config.cache_policy.max_bytes}
    except Exception:
        return {"error": "support_cache_maintenance_deferred", "quota_bytes": config.cache_policy.max_bytes}


def pending_digest(state, config, now, incomplete=False, max_chars=4000):
    """Fit a count and simple title list into one notification, keeping the footer."""
    snapshot = state.snapshot() or {}
    activities = [json.loads(row["activity"]) for row in state.db.execute(
        "SELECT activity,checked_at FROM observations WHERE current=1 AND confirmed='pending' ORDER BY id")
        if now - timedelta(minutes=15) <= instant(row["checked_at"]) <= now + timedelta(seconds=60)]
    count = len(activities)
    plural = "s" if count != 1 else ""
    lines = [f"{count} tarefa{plural} pendente{plural} — observação de "
             f"{format_time(snapshot.get('checked_at'), config.classification_policy.timezone)}", ""]
    footer = "\n\nDetalhes, links e downloads: /pendentes"
    if incomplete:
        footer += ("\nVerificação incompleta. Inconclusivo — precisa verificar. "
                   "Consulte /verificar e /relatar; o feedback não altera a situação no ILIAS.")
    if not activities:
        lines.append("Nenhuma pendência confirmada; isso não confirma que todas estejam concluídas.")
    for index, activity in enumerate(activities, 1):
        # Newlines in source titles must not turn into extra list items.
        line = f"{index}. " + " ".join(activity["title"].split())[:120]
        remaining = count - index
        overflow = f"\n… e mais {remaining}. Use /pendentes e “Exibir todas”." if remaining else ""
        candidate = "\n".join(lines + [line]) + overflow + footer
        if len(candidate) > max_chars:
            lines.append(f"… e mais {count - index + 1}. Use /pendentes e “Exibir todas”.")
            break
        lines.append(line)
    return ("\n".join(lines) + footer)[:max_chars]


def dispatch(state, config, telegram, client, now, clock):
    snapshot = state.snapshot() or {}
    incomplete = not snapshot.get("observation_complete", False) or any(not c["complete"] for c in snapshot.get("coverage", [])) or not snapshot.get("classification", {}).get("complete", False)
    # Reconcile immediately before the single text send. Include all due message
    # components so a large inventory does not spill into repeated summary alerts.
    batch = state.due(clock(), kind="message", limit=None)
    sent = 0
    if batch:
        text = pending_digest(state, config, clock(), incomplete, telegram.max_message_chars)
        unknown = [a for a in snapshot.get("activities", []) if a["status"] == "unknown"]
        missing = [json.loads(row["activity"]) for row in state.db.execute(
            "SELECT activity FROM observations WHERE current=0 AND confirmed='pending' ORDER BY id LIMIT 6")]
        candidates = list({(a["exercise_id"], a["assignment_id"]): a for a in unknown + missing}.values())[:6]
        buttons = [row for activity in candidates for row in source_buttons(activity)]
        try:
            result = client.message(text, buttons)
        except Exception as exc:
            for component in batch:
                state.failed(component, exc, clock())
        else:
            for component in batch:
                state.acknowledged(component, result.get("message_id", "confirmed"), clock())
            sent += len(batch)
    # Attachments remain independent, explicitly enabled components. Slow sends
    # cannot authorize later bytes with evidence which has expired in the meantime.
    for component in state.due(clock(), kind="document", limit=49):
        if not state.dispatchable(component, clock()):
            continue
        observation = state.db.execute("SELECT * FROM observations WHERE id=?", (component["activity_id"],)).fetchone()
        activity = json.loads(observation["activity"])
        material = next((d for d in activity.get("support_documents", []) if d.get("document_id") == component["document_id"] and d.get("selected_for_support") and d.get("role") == "support"), None)
        if not telegram.send_documents or material is None:
            with state.db:
                state.db.execute("UPDATE components SET state='cancelled' WHERE event_id=? AND kind=? AND document_id=?", (component["event_id"], component["kind"], component["document_id"]))
            continue
        try:
            try:
                with SupportCache(config, clock).delivery(component["document_id"], activity, observation["checked_at"]) as (source, entry):
                    result = client.document(source, entry, activity, observation["checked_at"], config.classification_policy.timezone)
            except TelegramError as exc:
                if str(exc) != "telegram_document_too_large":
                    raise
                result = client.message(f"Material excede o limite de envio: {material['title'][:300]}. Abra a fonte no ILIAS.", source_buttons(activity))
            except Exception:
                result = client.message(f"Material indisponível ou expirado: {material['title'][:300]}. Abra a fonte no ILIAS.", source_buttons(activity))
            state.acknowledged(component, result.get("message_id", "confirmed"), clock())
            sent += 1
        except Exception as exc:
            state.failed(component, exc, clock())
    return sent


def run_monitor(config, telegram, dry_run=False, collector=collect_inventory, client=None, clock=None):
    clock = clock or (lambda: datetime.now(timezone.utc))
    owned = client is None
    client = client or TelegramClient(telegram)
    try:
        with MonitorState(config, telegram.state_dir).open() as state, state.run_lock():
            config = effective_config(config, state)
            maintenance = maintain(config, clock)
            fatal = False
            try:
                inventory = collector(config)
                if not config.cache_policy.enabled:
                    inventory = cache_inventory(inventory, config, None, clock)
            except Exception:
                fatal = True
                inventory = {"checked_at": clock().isoformat().replace("+00:00", "Z"), "activities": [],
                             "classification": {"complete": False}, "coverage": [], "errors": [{"category": "collection_failed"}]}
            if dry_run:
                memory = sqlite3.connect(":memory:")
                memory.row_factory = sqlite3.Row
                state.db.backup(memory)
                durable = state.db
                state.db = memory
                try:
                    state.observe(inventory, clock(), telegram.reminder_hours, telegram.send_documents)
                    count = len(state.due(clock()))
                    observation_complete = state.snapshot()["observation_complete"]
                finally:
                    state.db = durable
                    memory.close()
                return {"dry_run": True, "planned_components": count, "sent_components": 0, "fatal": fatal,
                        "complete": not fatal and observation_complete, "maintenance": maintenance}
            state.observe(inventory, clock(), telegram.reminder_hours, telegram.send_documents)
            sent = dispatch(state, config, telegram, client, clock(), clock) if telegram.enabled else 0
            return {"dry_run": False, "planned_components": len(state.due(clock())), "sent_components": sent, "fatal": fatal,
                    "complete": not fatal and state.snapshot()["observation_complete"], "maintenance": maintenance}
    finally:
        if owned:
            client.close()

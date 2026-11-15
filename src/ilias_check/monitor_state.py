"""Transactional private account observations, component outbox and preferences."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
import hashlib
import json
import os
import secrets
import sqlite3

from ilias_check.cache_config import CacheError
from ilias_check.private_storage import account_key, private_open, private_root, process_lock
from ilias_check.support_cache import association_id, instant, stamp


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


class MonitorState:
    def __init__(self, config, directory):
        self.account = account_key(config)
        self.directory = directory

    @contextmanager
    def open(self):
        _, self.fd = private_root(self.directory)
        name = self.account + ".sqlite3"
        try:
            # Descriptor anchoring keeps SQLite and its journals under the checked root.
            for suffix in ("", "-journal", "-wal", "-shm"):
                try:
                    fd = private_open(self.fd, name + suffix, os.O_CREAT | os.O_RDWR if suffix == "" else os.O_RDONLY)
                    os.close(fd)
                except FileNotFoundError:
                    pass
            self.db = sqlite3.connect(f"/proc/self/fd/{self.fd}/{name}", timeout=5)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA foreign_keys=ON")
            try:
                self._migrate()
                yield self
            finally:
                self.db.close()
        finally:
            os.close(self.fd)

    def _migrate(self):
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > 2:
            raise CacheError("Monitor database is newer than this software.")
        if version == 2:
            return
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise CacheError("Monitor database is newer than this software.")
            if version == 0:
                self.db.execute("CREATE TABLE snapshot (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)")
                self.db.execute("CREATE TABLE observations (id TEXT PRIMARY KEY, activity TEXT NOT NULL, confirmed TEXT, generation TEXT, episode INTEGER NOT NULL, current INTEGER NOT NULL, checked_at TEXT NOT NULL, notified_at TEXT)")
                self.db.execute("CREATE TABLE events (id TEXT PRIMARY KEY, activity_id TEXT, generation TEXT, kind TEXT NOT NULL, created_at TEXT NOT NULL)")
                self.db.execute("CREATE TABLE components (event_id TEXT NOT NULL REFERENCES events(id), kind TEXT NOT NULL, document_id TEXT NOT NULL DEFAULT '', state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, retry_at TEXT, message_id TEXT, error TEXT, PRIMARY KEY(event_id,kind,document_id))")
                self.db.execute("CREATE TABLE submission_history (id TEXT PRIMARY KEY, activity TEXT NOT NULL, checked_at TEXT NOT NULL)")
                self.db.execute("CREATE TABLE preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                self.db.execute("CREATE TABLE cursors (name TEXT PRIMARY KEY, value INTEGER NOT NULL)")
                version = 1
            if version == 1:
                self.db.execute("CREATE TABLE material_requests (token TEXT PRIMARY KEY, activity_id TEXT NOT NULL, document_id TEXT NOT NULL, created_at TEXT NOT NULL)")
                version = 2
            self.db.execute(f"PRAGMA user_version={version}")

    @contextmanager
    def run_lock(self):
        with process_lock(self.fd, self.account + ".run.lock"):
            yield

    def preferences(self):
        result = {}
        for row in self.db.execute("SELECT * FROM preferences"):
            if row["key"] in {"no_deadline_hours", "retention_max_hours"}:
                value = json.loads(row["value"])
                if value is not None and (type(value) is not int or value <= 0 or value > 87600):
                    raise CacheError("Invalid saved retention preference.")
                result[row["key"]] = value
        return result

    def set_preferences(self, values):
        if set(values) - {"no_deadline_hours", "retention_max_hours"}:
            raise CacheError("Only retention preferences can be changed.")
        for key, value in values.items():
            if (value is None and key == "no_deadline_hours") or (value is not None and (type(value) is not int or not 1 <= value <= 87600)):
                raise CacheError("Retention hours must be positive and at most 87600.")
        with self.db:
            for key, value in values.items():
                self.db.execute("INSERT OR REPLACE INTO preferences VALUES (?,?)", (key, encode(value)))

    def snapshot(self):
        row = self.db.execute("SELECT data FROM snapshot WHERE id=1").fetchone()
        return json.loads(row[0]) if row else None

    def material_buttons(self, activity, now, limit=2):
        """Create durable single-use download buttons for eligible support files."""
        documents = [
            document for document in activity.get("support_documents", [])
            if document.get("selected_for_support") and document.get("role") == "support"
            and document.get("document_id")
        ]
        if not documents:
            return []
        buttons = []
        with self.db:
            self.db.execute("DELETE FROM material_requests WHERE created_at < ?",
                            (stamp(now - timedelta(days=1)),))
            for document in documents[:limit]:
                token = secrets.token_urlsafe(12)
                self.db.execute("INSERT INTO material_requests VALUES (?,?,?,?)",
                                (token, association_id(activity), document["document_id"], stamp(now)))
                label = ("Baixar: " + document.get("title", "material"))[:64]
                buttons.append([{"text": label, "callback_data": "m:" + token}])
        return buttons

    def claim_material(self, token, now):
        row = self.db.execute("SELECT * FROM material_requests WHERE token=?", (token,)).fetchone()
        if row is None:
            return None
        with self.db:
            self.db.execute("DELETE FROM material_requests WHERE token=?", (token,))
        if now - instant(row["created_at"]) >= timedelta(days=1):
            return None
        return row["activity_id"], row["document_id"]

    def observe(self, inventory, now, reminder_hours=0, documents=False):
        checked = inventory["checked_at"]
        fresh = instant(checked) <= now + timedelta(seconds=60) and now - instant(checked) <= timedelta(minutes=15)
        with self.db:
            self.db.execute("UPDATE observations SET current=0")
            for activity in inventory.get("activities", []):
                aid = association_id(activity)
                old = self.db.execute("SELECT * FROM observations WHERE id=?", (aid,)).fetchone()
                confirmed = old["confirmed"] if old else None
                episode = old["episode"] if old else 0
                generation = old["generation"] if old else None
                if fresh and activity["status"] != "unknown":
                    if activity["status"] == "pending" and confirmed != "pending":
                        episode += 1
                    confirmed = activity["status"]
                    generation = fingerprint([episode, activity["status"], activity.get("deadline_at"),
                                              sorted((d["document_id"], d.get("cache", {}).get("sha256")) for d in activity.get("support_documents", []) if d.get("selected_for_support"))])
                same_generation = old is not None and old["generation"] == generation
                notified_at = old["notified_at"] if same_generation else None
                self.db.execute("INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?,?,?,?)",
                                (aid, encode(activity), confirmed, generation, episode, int(fresh and activity["status"] != "unknown"), checked, notified_at))
                if fresh and activity["status"] == "submitted":
                    self.db.execute("INSERT OR REPLACE INTO submission_history VALUES (?,?,?)", (aid, encode(activity), checked))
                if fresh and activity["status"] == "pending":
                    self._event(fingerprint([aid, generation]), aid, generation, "pending", now, activity, documents)
                    if reminder_hours and notified_at and now - instant(notified_at) >= timedelta(hours=reminder_hours):
                        self._event(fingerprint([aid, generation, "reminder", notified_at]), aid, generation, "reminder", now, activity, documents)
            missing = sorted(row["id"] for row in self.db.execute("SELECT id FROM observations WHERE current=0 AND confirmed='pending'"))
            health = [missing, sorted((a["exercise_id"], a["assignment_id"] or "", a.get("reason_codes", [])) for a in inventory.get("activities", []) if a["status"] == "unknown"),
                      sorted((c["root_id"], c["complete"], c.get("warnings", [])) for c in inventory.get("coverage", [])),
                      sorted((e.get("category", ""), e.get("root_id", "")) for e in inventory.get("errors", []))]
            incomplete = bool(missing) or not fresh or not inventory.get("classification", {}).get("complete", False) or any(not c["complete"] for c in inventory.get("coverage", []))
            if incomplete:
                self._event(fingerprint(["health", health]), None, fingerprint(health), "health", now, None, False)
            summary = {k: inventory[k] for k in ("checked_at", "scope", "coverage", "classification", "activities") if k in inventory}
            summary["observation_complete"] = not incomplete
            summary["health_generation"] = fingerprint(health) if incomplete else None
            self.db.execute("INSERT OR REPLACE INTO snapshot VALUES (1,?)", (encode(summary),))
            self._reconcile(now)

    def _event(self, eid, aid, generation, kind, now, activity, documents):
        created = self.db.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)", (eid, aid, generation, kind, stamp(now))).rowcount
        if not created:
            return
        self.db.execute("INSERT INTO components(event_id,kind,state) VALUES (?,'message','queued')", (eid,))
        if documents:
            for material in activity.get("support_documents", []):
                if material.get("selected_for_support") and material.get("role") == "support" and material.get("cache", {}).get("eligible"):
                    self.db.execute("INSERT OR IGNORE INTO components(event_id,kind,document_id,state) VALUES (?,'document',?,'queued')", (eid, material["document_id"]))

    def _reconcile(self, now):
        snapshot = self.snapshot() or {}
        for row in self.db.execute("SELECT c.rowid AS rid,c.*,e.activity_id,e.generation,e.kind AS event_kind FROM components c JOIN events e ON c.event_id=e.id WHERE c.state IN ('queued','paused','uncertain')").fetchall():
            if row["activity_id"] is None:
                state = ("uncertain" if row["state"] == "uncertain" else "queued") if row["generation"] == snapshot.get("health_generation") else "cancelled"
            else:
                observation = self.db.execute("SELECT * FROM observations WHERE id=?", (row["activity_id"],)).fetchone()
                if (not observation or not observation["current"]
                        or now - instant(observation["checked_at"]) > timedelta(minutes=15)
                        or instant(observation["checked_at"]) > now + timedelta(seconds=60)):
                    state = "paused"
                elif observation["confirmed"] != "pending" or row["generation"] != observation["generation"]:
                    state = "cancelled"
                else:
                    state = "uncertain" if row["state"] == "uncertain" else "queued"
            self.db.execute("UPDATE components SET state=? WHERE rowid=?", (state, row["rid"]))

    def due(self, now):
        with self.db:
            self._reconcile(now)
        return self.db.execute("SELECT c.*,e.activity_id,e.generation,e.kind AS event_kind FROM components c JOIN events e ON c.event_id=e.id WHERE c.state IN ('queued','uncertain') AND (retry_at IS NULL OR retry_at<=?) AND attempts<5 ORDER BY e.created_at,c.kind DESC LIMIT 50", (stamp(now),)).fetchall()

    def dispatchable(self, component, now):
        """Recheck a prefetched component immediately before its external side effect."""
        with self.db:
            self._reconcile(now)
        row = self.db.execute(
            "SELECT state,attempts,retry_at FROM components WHERE event_id=? AND kind=? AND document_id=?",
            (component["event_id"], component["kind"], component["document_id"]),
        ).fetchone()
        return bool(row and row["state"] in {"queued", "uncertain"} and row["attempts"] < 5
                    and (row["retry_at"] is None or instant(row["retry_at"]) <= now))

    def acknowledged(self, component, message_id, now):
        with self.db:
            self.db.execute("UPDATE components SET state='sent',message_id=?,error=NULL WHERE event_id=? AND kind=? AND document_id=?", (str(message_id), component["event_id"], component["kind"], component["document_id"]))
            if component["kind"] == "message" and component["activity_id"]:
                self.db.execute("UPDATE observations SET notified_at=? WHERE id=?", (stamp(now), component["activity_id"]))

    def failed(self, component, error, now):
        attempts = component["attempts"] + 1
        delay = max(getattr(error, "retry_after", 60), min(3600, 60 * 2 ** attempts))
        state = "failed" if attempts >= 5 else "uncertain" if getattr(error, "uncertain", False) else "queued"
        with self.db:
            self.db.execute("UPDATE components SET state=?,attempts=?,retry_at=?,error=? WHERE event_id=? AND kind=? AND document_id=?", (state, attempts, stamp(now + timedelta(seconds=delay)), str(error) if str(error).startswith("telegram_") else "delivery_failed", component["event_id"], component["kind"], component["document_id"]))

    def cursor(self, name):
        row = self.db.execute("SELECT value FROM cursors WHERE name=?", (name,)).fetchone()
        return row[0] if row else 0

    def set_cursor(self, name, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO cursors VALUES (?,?)", (name, value))

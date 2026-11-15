"""Private bounded document copies. All writers/readers share a root-wide lock.

Only freshly classified pending associations can fetch or serve a copy. Failure of
this optional layer never changes an activity's classification.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid
import zipfile

from ilias_check.cache_config import CacheError
from ilias_check.private_storage import account_key, private_open, private_root, process_lock

_BLOB = re.compile(r"[0-9a-f]{64}-[0-9a-f]{64}-[0-9a-f]{32}\.blob\Z")
_PART = re.compile(r"transfer-[0-9a-f]{32}\.part\Z")
_MAX_ENTRIES = 1000
INTERACTIVE_ACTIVITY_MAX_AGE = timedelta(hours=12)
_TYPES = {
    ".pdf": "application/pdf", ".doc": "application/msword",
    ".xls": "application/vnd.ms-excel", ".ppt": "application/vnd.ms-powerpoint",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".odp": "application/vnd.oasis.opendocument.presentation", ".rtf": "application/rtf",
}


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise CacheError("Timestamp needs a timezone.")
    return result


def association_id(activity: dict) -> str:
    return activity["exercise_id"] + ":" + str(activity["assignment_id"])


class SupportCache:
    def __init__(self, config, clock=None):
        self.config = config
        self.policy = config.cache_policy
        self.account = account_key(config)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.manifest_limit = min(1024 * 1024, max(128, self.policy.max_bytes // 4))
        self.run_bytes = 0
        self.entries = {}

    @contextmanager
    def locked(self):
        self.root, self.fd = private_root(self.policy.directory)
        try:
            with process_lock(self.fd):
                self._load()
                # Interrupted transfers are exclusively owned by the lock holder.
                for name in os.listdir(self.fd):
                    if _PART.fullmatch(name) or name == "manifest.next":
                        self._unlink(name)
                yield self
        finally:
            os.close(self.fd)

    def _load(self):
        try:
            fd = private_open(self.fd, "manifest.json", os.O_RDONLY)
        except FileNotFoundError:
            self.entries = {}
            return
        with os.fdopen(fd, "rb") as source:
            raw = source.read(1024 * 1024 + 1)
        try:
            data = json.loads(raw)
            if len(raw) > 1024 * 1024 or data["version"] != 1 or not isinstance(data["entries"], dict) or len(data["entries"]) > _MAX_ENTRIES:
                raise ValueError
            for key, entry in data["entries"].items():
                if not re.fullmatch(r"[0-9a-f]{64}:[0-9a-f]{64}", key):
                    raise ValueError
                if entry.get("file") and (not _BLOB.fullmatch(entry["file"]) or not entry["file"].startswith(key.replace(":", "-") + "-")):
                    raise ValueError
                if not isinstance(entry["associations"], dict) or len(entry["associations"]) > 1000:
                    raise ValueError
                instant(entry["downloaded_at"])
                instant(entry["last_validated_at"])
                for association in entry["associations"].values():
                    instant(association["expires_at"])
            self.entries = data["entries"]
        except (KeyError, TypeError, ValueError):
            raise CacheError("Unsupported or invalid cache manifest; no data was deleted.") from None

    def _serialized(self):
        return json.dumps({"version": 1, "entries": self.entries}, ensure_ascii=False, separators=(",", ":")).encode()

    def usage(self):
        total = 0
        for name in os.listdir(self.fd):
            info = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise CacheError("Unsafe file in private cache; maintenance refused.")
            total += info.st_size
        return total

    def _unlink(self, name):
        if not (_BLOB.fullmatch(name) or _PART.fullmatch(name) or name == "manifest.next"):
            raise CacheError("Refusing to delete an unmanaged file.")
        try:
            fd = private_open(self.fd, name, os.O_RDONLY)
        except FileNotFoundError:
            return
        os.close(fd)
        os.unlink(name, dir_fd=self.fd)

    def _drop(self, entry, reason):
        if entry.get("file"):
            self._unlink(entry["file"])
        entry.update(file=None, state=reason)

    def _room(self, needed: int, protect: str | None = None):
        for key, entry in sorted(self.entries.items(), key=lambda pair: pair[1]["downloaded_at"]):
            if self.usage() + needed <= self.policy.max_bytes:
                return True
            if key != protect and entry.get("file"):
                self._drop(entry, "evicted")
        return self.usage() + needed <= self.policy.max_bytes

    def _save(self):
        # Prune tombstones, then oldest copies, to bound manifest size and atomic replacement.
        raw = self._serialized()
        while len(raw) > self.manifest_limit or len(self.entries) > _MAX_ENTRIES:
            if not self.entries:
                raise CacheError("Quota is too small for cache metadata.")
            key = min(self.entries, key=lambda k: (bool(self.entries[k].get("file")), self.entries[k]["downloaded_at"]))
            self._drop(self.entries[key], "evicted")
            del self.entries[key]
            raw = self._serialized()
        if not self._room(len(raw)):
            raise CacheError("Insufficient capacity for atomic cache metadata.")
        # Eviction changes metadata too; recheck its exact replacement size.
        raw = self._serialized()
        if not self._room(len(raw)):
            raise CacheError("Insufficient capacity for atomic cache metadata.")
        raw = self._serialized()
        if self.usage() + len(raw) > self.policy.max_bytes:
            raise CacheError("Insufficient capacity for atomic cache metadata.")
        fd = private_open(self.fd, "manifest.next", os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace("manifest.next", "manifest.json", src_dir_fd=self.fd, dst_dir_fd=self.fd)
        os.fsync(self.fd)

    def _key(self, document_id):
        return self.account + ":" + hashlib.sha256(document_id.encode()).hexdigest()

    def _association(self, activity, downloaded_at, checked_at):
        expiry = downloaded_at + timedelta(hours=self.policy.no_deadline_hours)
        reason = "no_deadline_ttl"
        if activity.get("deadline_at"):
            expiry, reason = instant(activity["deadline_at"]), "deadline"
        if self.policy.retention_max_hours:
            cap = downloaded_at + timedelta(hours=self.policy.retention_max_hours)
            if cap < expiry:
                expiry, reason = cap, "retention_cap"
        completed = any(h.get("completed") is True for h in activity.get("submission_history", []))
        if completed:
            expiry, reason = min(expiry, checked_at), "activity_ended"
        if activity["status"] != "pending":
            # Unknown/absent evidence pauses access but does not invent completion.
            if activity["status"] in {"submitted", "closed_without_submission", "excluded"}:
                expiry, reason = min(expiry, checked_at), "activity_ended"
        return {"expires_at": stamp(expiry), "expiry_reason": reason,
                "status": activity["status"], "checked_at": stamp(checked_at),
                "current": activity["status"] == "pending" and not completed, "deadline_at": activity.get("deadline_at")}

    def _valid(self, entry):
        if not entry.get("file"):
            return False
        try:
            fd = private_open(self.fd, entry["file"], os.O_RDONLY)
            with os.fdopen(fd, "rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
                size = source.tell()
            return digest == entry["sha256"] and size == entry["byte_size"]
        except (OSError, CacheError):
            return False

    def maintenance(self):
        now = self.clock()
        for key, entry in self.entries.items():
            if key.startswith(self.account + ":"):
                for aid, association in list(entry["associations"].items()):
                    adjusted = self._association(association, instant(entry["downloaded_at"]), instant(association["checked_at"]))
                    adjusted["current"] = association["current"]
                    if instant(association["expires_at"]) <= now:
                        adjusted["expires_at"] = association["expires_at"]
                        adjusted["expiry_reason"] = association["expiry_reason"]
                    entry["associations"][aid] = adjusted
            if entry.get("file") and not any(instant(a["expires_at"]) > now for a in entry["associations"].values()):
                self._drop(entry, "expired")
        referenced = {e["file"] for e in self.entries.values() if e.get("file")}
        for name in os.listdir(self.fd):
            if _BLOB.fullmatch(name) and name not in referenced:
                self._unlink(name)
        self._room(0)
        self._save()

    def collect(self, inventory: dict, auth, download=True):
        now = self.clock()
        checked = instant(inventory["checked_at"])
        # A saved/stale snapshot must never become new permission to fetch materials.
        if checked > now + timedelta(seconds=60) or now - checked > timedelta(minutes=15):
            raise CacheError("Activity evidence is too old for support downloads.")
        activities = inventory.get("activities", [])
        by_activity = {association_id(a): a for a in activities}
        for key, entry in self.entries.items():
            if not key.startswith(self.account + ":"):
                continue
            for aid, association in list(entry["associations"].items()):
                activity = by_activity.get(aid)
                if activity:
                    adjusted = self._association(activity, instant(entry["downloaded_at"]), checked)
                    if instant(association["expires_at"]) <= now:
                        adjusted["expires_at"] = association["expires_at"]
                        adjusted["expiry_reason"] = association["expiry_reason"]
                    entry["associations"][aid] = adjusted
                else:
                    association["current"] = False
        self.maintenance()
        # Group all selected references so shared bytes are fetched only once per run.
        groups = {}
        for activity in activities:
            for material in activity.get("support_documents", []):
                if activity.get("deadline_text") and not activity.get("deadline_at"):
                    material["reason_codes"] = list(dict.fromkeys(material["reason_codes"] + ["unreadable_deadline_retention_fallback"]))
                if download and material.get("selected_for_support") and material.get("role") == "support" and activity["status"] == "pending":
                    groups.setdefault(material["document_id"], []).append((activity, material))
        for document_id, references in groups.items():
            key = self._key(document_id)
            previous = self.entries.get(key)
            downloaded = instant(previous["downloaded_at"]) if previous else now
            associations = dict(previous["associations"]) if previous else {}
            for activity, _ in references:
                associations[association_id(activity)] = self._association(activity, downloaded, checked)
            active = [a for a in associations.values() if a["current"] and instant(a["expires_at"]) > now]
            if not active:
                # TTL-expired pending work may fetch a new copy; ended deadlines may not.
                associations = {aid: self._association(by_activity[aid], now, checked) if aid in by_activity else a
                                for aid, a in associations.items()}
                active = [a for a in associations.values() if a["current"] and instant(a["expires_at"]) > now]
            if not active:
                for _, material in references:
                    material.update(state="expired", reason_codes=list(dict.fromkeys(material["reason_codes"] + ["support_retention_ended"])))
                continue
            renew = bool(previous and any(
                association_id(activity) in previous["associations"]
                and instant(previous["associations"][association_id(activity)]["expires_at"]) <= now
                and instant(self._association(activity, now, checked)["expires_at"]) > now
                for activity, _ in references))
            valid = previous is not None and self._valid(previous)
            if previous and previous.get("file") and not valid:
                self._drop(previous, "error")
            if valid and not renew and previous["state"] != "stale" and now - instant(previous["last_validated_at"]) < timedelta(hours=self.policy.revalidate_hours):
                previous["associations"] = associations
                self._export(references, previous, "cached")
                continue
            try:
                entry, unchanged = self._download(key, references[0][1], previous if valid else None, auth, force_body=renew)
                if not unchanged:
                    associations = {aid: self._association(by_activity[aid], now, checked) if aid in by_activity else a for aid, a in associations.items()}
                entry["associations"] = associations
                self.entries[key] = entry
                self._save()
                self._export(references, entry, "unchanged" if unchanged else "cached")
            except Exception as exc:
                if previous:
                    previous.update(state="stale", last_error="support_refresh_failed")
                for _, material in references:
                    material.update(state="stale" if valid else "error")
                    material["reason_codes"] = list(dict.fromkeys(material["reason_codes"] + [str(exc) if isinstance(exc, CacheError) else "support_download_failed"]))
                    if previous:
                        self._export_one(material, previous, material["state"], None)
        self.maintenance()
        # Quota eviction may have removed an earlier material in the same run.
        for activity in activities:
            for material in activity.get("support_documents", []):
                entry = self.entries.get(self._key(material["document_id"])) if material.get("document_id") else None
                if entry:
                    if entry.get("file") and (not self._valid(entry) or now - instant(entry["last_validated_at"]) >= timedelta(hours=self.policy.revalidate_hours)):
                        entry["state"] = "stale"
                    self._export_one(material, entry, entry["state"], association_id(activity))
        self._save()
        inventory["support_cache"] = {"usage_bytes": self.usage(), "quota_bytes": self.policy.max_bytes, "checked_at": stamp(now), "downloaded_bytes": self.run_bytes}
        return inventory

    def _download(self, key, material, previous, auth, force_body=False):
        headers = {}
        if previous and not force_body:
            for field, header in (("etag", "If-None-Match"), ("last_modified", "If-Modified-Since")):
                if previous.get(field):
                    headers[header] = previous[field]
        response = auth.stream_document(material, headers)
        temporary = "transfer-" + uuid.uuid4().hex + ".part"
        try:
            if response.status_code == 304:
                if not previous or force_body:
                    raise CacheError("unexpected_not_modified")
                return {**previous, "last_validated_at": stamp(self.clock()), "state": "unchanged", "last_error": None}, True
            if response.status_code != 200:
                raise CacheError("support_http_error")
            maximum = min(self.policy.max_file_bytes, self.policy.max_run_bytes - self.run_bytes)
            if maximum <= 0:
                raise CacheError("support_run_byte_limit")
            length = response.headers.get("Content-Length")
            try:
                expected = int(length) if length is not None else None
            except ValueError:
                raise CacheError("invalid_content_length") from None
            if expected is not None and (expected < 0 or expected > maximum):
                raise CacheError("support_file_byte_limit")
            reserve = expected if expected is not None else maximum
            # Reserve worst-case atomic manifest space, including the temporary body.
            if not self._room(reserve + 2 * self.manifest_limit, protect=key):
                raise CacheError("support_quota_limit")
            fd = private_open(self.fd, temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            size = 0
            digest = hashlib.sha256()
            started = time.monotonic()
            with os.fdopen(fd, "wb") as output:
                for chunk in _chunks(response):
                    if time.monotonic() - started > self.config.timeout_seconds:
                        raise CacheError("support_transfer_timeout")
                    if not chunk:
                        continue
                    self.run_bytes += len(chunk)
                    if size + len(chunk) > maximum or self.run_bytes > self.policy.max_run_bytes:
                        raise CacheError("support_stream_byte_limit")
                    size += len(chunk)
                    output.write(chunk)
                    digest.update(chunk)
                output.flush()
                os.fsync(output.fileno())
            if expected is not None and size != expected:
                raise CacheError("support_incomplete_transfer")
            media = self._type(temporary, material, response)
            filename = key.replace(":", "-") + "-" + uuid.uuid4().hex + ".blob"
            os.replace(temporary, filename, src_dir_fd=self.fd, dst_dir_fd=self.fd)
            if previous and previous.get("file"):
                self._unlink(previous["file"])
            now = stamp(self.clock())
            return {"document_id": material["document_id"], "source_url": material["source_url"],
                    "filename": _document_label(material, response),
                    "file": filename, "media_type": media, "byte_size": size,
                    "sha256": digest.hexdigest(), "etag": _validator(response.headers.get("ETag")),
                    "last_modified": _validator(response.headers.get("Last-Modified")),
                    "downloaded_at": now, "last_validated_at": now, "state": "cached", "last_error": None,
                    "associations": {}}, False
        finally:
            response.close()
            self._unlink(temporary)

    def _type(self, name, material, response):
        label = _document_label(material, response)
        suffix = Path(label).suffix.lower()
        media = response.headers.get("Content-Type", "").split(";", 1)[0].lower().strip()
        if suffix not in _TYPES:
            suffix = next((s for s, m in _TYPES.items() if m == media), "")
        if suffix not in _TYPES or media not in {"", "application/octet-stream", "application/force-download", _TYPES.get(suffix)}:
            raise CacheError("unsupported_document_type")
        fd = private_open(self.fd, name, os.O_RDONLY)
        with os.fdopen(fd, "rb") as source:
            prefix = source.read(4096)
            stripped = prefix.lstrip().lower()
            if stripped.startswith((b"<", b"[")) or (stripped.startswith(b"{") and not prefix.startswith(b"{\\rtf")) or not prefix:
                raise CacheError("document_body_is_not_a_file")
            if suffix == ".pdf":
                valid = prefix.startswith(b"%PDF-")
            elif suffix in {".doc", ".xls", ".ppt"}:
                valid = prefix.startswith(bytes.fromhex("d0cf11e0a1b11ae1"))
            elif suffix == ".rtf":
                valid = prefix.startswith(b"{\\rtf")
            else:
                try:
                    source.seek(0)
                    with zipfile.ZipFile(source) as archive:
                        names = archive.namelist()
                        marker = {".docx": "word/document.xml", ".xlsx": "xl/workbook.xml", ".pptx": "ppt/presentation.xml"}.get(suffix, "content.xml")
                        valid = len(names) <= 5000 and marker in names and ("[Content_Types].xml" in names if suffix.endswith("x") else "mimetype" in names)
                except (zipfile.BadZipFile, OSError):
                    valid = False
            if not valid:
                raise CacheError("document_signature_mismatch")
        return _TYPES[suffix]

    def _export(self, references, entry, state):
        entry["state"] = state
        for activity, material in references:
            self._export_one(material, entry, state, association_id(activity))

    def _export_one(self, material, entry, state, aid):
        association = entry["associations"].get(aid, {})
        eligible = bool(entry.get("file") and state in {"cached", "unchanged"} and association.get("current") and instant(association["expires_at"]) > self.clock())
        material["state"] = "expired" if association and instant(association["expires_at"]) <= self.clock() else state
        material["cache"] = {"path": str(self.root / entry["file"]) if eligible else None,
                             "media_type": entry["media_type"], "byte_size": entry["byte_size"], "sha256": entry["sha256"],
                             "downloaded_at": entry["downloaded_at"], "last_validated_at": entry["last_validated_at"],
                             "expires_at": association.get("expires_at"), "expiry_reason": association.get("expiry_reason"),
                             "eligible": eligible, "warning": "Cópia local; o ILIAS é a fonte oficial e pode estar mais atualizado."}

    def _delivery_entry(self, document_id, activity, checked_at, activity_max_age=timedelta(minutes=15)):
        """Validate a copy while the caller holds the cache lease."""
        now = self.clock()
        checked = instant(checked_at)
        entry = self.entries.get(self._key(document_id))
        aid = association_id(activity)
        if not entry or entry["state"] not in {"cached", "unchanged"} or now - instant(entry["last_validated_at"]) >= timedelta(hours=self.policy.revalidate_hours) or activity["status"] != "pending" or checked > now + timedelta(seconds=60) or now - checked > activity_max_age:
            raise CacheError("Support delivery requires a fresh pending activity check.")
        if not any(m.get("document_id") == document_id and m.get("selected_for_support") and m.get("role") == "support" for m in activity.get("support_documents", [])):
            raise CacheError("Current activity does not select this support document.")
        association = entry["associations"].get(aid)
        current = self._association(activity, instant(entry["downloaded_at"]), checked)
        if not association or not association["current"] or not current["current"] or min(instant(current["expires_at"]), instant(association["expires_at"])) <= now or not self._valid(entry):
            raise CacheError("Support copy is expired, unavailable, or corrupted.")
        return entry

    def availability(self, references, activity_max_age=INTERACTIVE_ACTIVITY_MAX_AGE):
        """Inspect current local copies in one lease, without fetching source bodies.

        References contain (activity, document ID, checked timestamp, current flag).
        Labels are advisory: delivery always runs the same checks again.
        """
        result = {(association_id(activity), document_id): "remote"
                  for activity, document_id, _, _ in references}
        if not self.policy.directory.expanduser().exists():
            return result
        with self.locked():
            self.maintenance()
            for activity, document_id, checked, current in references:
                key = (association_id(activity), document_id)
                try:
                    if not current:
                        raise CacheError("Activity observation is not current.")
                    self._delivery_entry(document_id, activity, checked, activity_max_age)
                    result[key] = "ready"
                except CacheError:
                    entry = self.entries.get(self._key(document_id))
                    if entry and entry.get("file") and self._valid(entry):
                        result[key] = "revalidate"
        return result

    @contextmanager
    def delivery(self, document_id, activity, checked_at, *, activity_max_age=timedelta(minutes=15)):
        """Hold the global lease throughout the read/send; never trust exported paths or file IDs."""
        with self.locked():
            self.maintenance()
            entry = self._delivery_entry(document_id, activity, checked_at, activity_max_age)
            fd = private_open(self.fd, entry["file"], os.O_RDONLY)
            with os.fdopen(fd, "rb") as source:
                yield source, deepcopy(entry)


def _document_label(material, response):
    label = material["title"]
    disposition = response.headers.get("Content-Disposition", "")
    found = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', disposition, re.I)
    if found:
        from urllib.parse import unquote
        label = unquote(found[1]).strip()
        if "/" in label or "\\" in label or any(ord(c) < 32 for c in label) or label in {".", ".."}:
            raise CacheError("unsafe_document_filename")
    return label


def _validator(value):
    return value if value and len(value) <= 512 and not any(ord(c) < 32 for c in value) else None


def cache_inventory(inventory, config, auth, clock=None):
    if not config.cache_policy.enabled and not config.cache_policy.directory.expanduser().exists():
        return inventory
    result = deepcopy(inventory)
    try:
        with SupportCache(config, clock).locked() as cache:
            return cache.collect(result, auth, download=config.cache_policy.enabled)
    except Exception:
        result["support_cache"] = {"usage_bytes": None, "quota_bytes": config.cache_policy.max_bytes,
                                   "checked_at": stamp((clock or (lambda: datetime.now(timezone.utc)))()),
                                   "downloaded_bytes": 0, "error": "support_cache_unavailable"}
        for activity in result.get("activities", []):
            activity.setdefault("support_warnings", []).append("support_cache_unavailable")
        return result


def _chunks(response):
    # urllib3 read1 returns available bytes rather than waiting to fill a chunk;
    # combined with socket timeout and wall-clock checks this bounds slow streams.
    raw = getattr(response, "raw", None)
    if raw is not None and callable(getattr(raw, "read1", None)):
        while True:
            chunk = raw.read1(65536, decode_content=True)
            if not chunk:
                return
            yield chunk
    else:
        yield from response.iter_content(chunk_size=65536)

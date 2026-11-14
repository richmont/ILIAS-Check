# Design

## Context

Depends on collection and classification. Earlier investigation distinguished assignment attachments from presentations in containing folders, and found model answers alongside exercises. No document cache exists in this repository.

See the capability specs for selection rules. File extensions and similar names are not sufficient evidence of relevance or safety.

## Goals / Non-Goals

**Goals:** Traceable associations, predictable private storage, and bounded transfers independent of notification delivery.

**Non-Goals:** Content interpretation, opening Office documents, downloading entire courses, and resolving protected sequence steps by advancing them.

## Decisions

### Association is metadata, not a relevance guess

Build document references from assignment attachment sections and explicit instruction links. Optional same-folder candidates carry `contextual` association; their source path is retained. Do not search every ancestor folder or match by filename similarity.

Exclude platform-marked solutions, feedback, and learner submissions. Explicit solution labels are negative evidence; unclear roles are flagged and not downloaded automatically. A shared reference can have multiple associations without duplicating its bytes.

Alternative: automatically attach all neighboring PDFs. Rejected because it overcollects, can include answers, and overstates relevance.

### User-controlled selection and storage

Proposed configuration:

| Setting | Meaning / default |
| --- | --- |
| `ILIAS_PENDING_DOWNLOAD_SUPPORT` | `false`; opt-in local downloads |
| `ILIAS_PENDING_OUTPUT_DIR` | `~/.local/share/ilias-check/support` |
| `ILIAS_PENDING_INCLUDE_CONTEXTUAL` | `false` |
| `ILIAS_SUPPORT_MAX_FILE_BYTES` | 20 MiB |
| `ILIAS_SUPPORT_MAX_RUN_BYTES` | 100 MiB |
| `ILIAS_SUPPORT_REVALIDATE_HOURS` | 12 |
| `ILIAS_SUPPORT_CACHE_MAX_BYTES` | 200000000 bytes (200 MB decimal); host administrator only |
| `ILIAS_SUPPORT_NO_DEADLINE_TTL_HOURS` | 168; host default, later user-configurable retention |
| `ILIAS_SUPPORT_RETENTION_MAX_HOURS` | Optional user retention cap; unset uses deadline/default policy |

These byte limits are local policy defaults, not claims about Telegram limits. The total quota is immutable through bot APIs; the retention preference can later be persisted through the authorized settings menu. Runtime preference overrides the host default only for user-editable retention fields; host security/capacity policy always wins. Initially allow PDF and Office document types needed for assignments; skip videos, executables, and archives with an explicit reason. Validate content signatures/metadata as appropriate without executing or extracting the files.

Expand `~`, resolve the root, reject paths within the checkout by default, and create private directories/files where supported. Namespace entries by installation/client/account and stable document ID. Use sanitized filenames only as labels, not identities. Defend against symlink escapes and races using no-follow/exclusive creation where supported.

### Simple filesystem manifest before monitoring SQLite

Use account-scoped entries in a bounded versioned JSON manifest and atomic file replacement under a cache-root lock. This keeps the cache usable without change four. Record source identity, safe URL, associations, media type, byte size, SHA-256, ETag/Last-Modified when available, `downloaded_at`, `last_validated_at`, per-association `expires_at`, expiry reason, state, and last error. The quota applies to the entire configured managed cache root, including any account namespaces, bounded manifest, and temporary bodies; monitor databases are separate.

Fresh, non-expired entries are reused. Stale entries get a conditional request when supported; otherwise perform a bounded refresh. A changed body replaces the current entry atomically and updates its download time. A 304 validation updates only validation time, not the download time or retention clock. No unbounded version history is retained. Verify cached copies before reuse and never treat an HTML login/error response as the requested document.

Alternative: require the notification database for all file operations. Rejected to avoid coupling document collection to the Telegram milestone.

### Partial failure is additive

Documents use states such as `metadata_only`, `cached`, `unchanged`, `stale`, `expired`, `evicted`, `unavailable`, `skipped`, and `error`, with reason codes. Failed refreshes can retain an unexpired old copy but cannot call it current; stale/expired copies are not eligible for bot transmission. Assignment classification remains intact even when supporting files fail.

Use the collector's origin policy, request budget, and bounded session recovery. Stream body data to a restricted temporary file, enforce byte limits while reading, and publish only after checks complete. Never follow arbitrary external instruction links with credentials.

### Retention is independent from freshness

For each association, known deadline is the default limit; no deadline uses `downloaded_at + effective_no_deadline_ttl` (168h default, configurable in the later bot menu). An optional user retention cap can shorten either policy. Confirmed personal/team submission or platform completion ends that association immediately after it is observed. Unparseable deadline uses the bounded fallback with a warning, never an invented due date.

Keep one physical copy only while at least one valid association needs it. Ended associations cannot request it through another activity's still-valid reference. TTL expiry/eviction invalidates old bytes, but a still-pending eligible assignment can fetch a fresh source copy after a current check. A deadline/submission/completion-ended association cannot be resurrected by a TTL change or old button; require confirmed reopening/extension or a different eligible association.

Expose `downloaded_at`, validation time, expiry, source link, and the warning that ILIAS is authoritative on every delivery. A known deadline expiry can remove cached support even while ILIAS still accepts late work; pending state and local cache eligibility are intentionally different.

### Quota requires physical eviction

Automatic cleanup removes expired/unreferenced managed files, then oldest downloaded copies when more space is needed. Mark the metadata `evicted` and reclaim bytes; `stale` alone does not reclaim storage. Keep manifest/tombstones bounded; submission history lives elsewhere.

Under the cache-root lock, reserve/check available bytes including temporary replacement bodies. Protect active reads using short-lived reader leases/file locks; if safe reclamation is impossible, skip/defer with a link fallback. Unknown-length responses stop before exceeding reserved/global capacity. A document larger than total quota is never cached. On quota reduction, reclaim at the next access/maintenance and do not worsen existing excess.

Run maintenance during scans, before serving downloads, and on the bot's automatic maintenance tick. An expired copy is refused before physical deletion. There is no purge/cache-quota command or callback; the settings menu only shows usage/quota and permits retention changes. Administrators manage quota through host environment configuration.

Short reader leases do not authorize a new send after expiry; recheck at dispatch. A transmission already accepted/in flight cannot be recalled by subsequent local cleanup. Defer physical deletion of leased files until bounded readers finish, while immediately refusing new expired deliveries.

### Privacy boundary

Neither cache nor manifests belong in Git. Extend ignore rules for runtime directories and dotenv variants while retaining placeholder examples. No documents are sent externally in this change. Automatic cleanup is confined to authenticated managed-cache paths and never deletes unrelated user data. Previously delivered recipient/Telegram copies cannot be revoked by deleting local files; stored Telegram file IDs must not bypass local eligibility checks.

## Risks / Trade-offs

- [Missing validators] → A refresh interval trades freshness against traffic.
- [Unknown document role] → Metadata-only warning instead of automatic collection.
- [Large files and quota exhaustion] → Per-file/run limits and visible skip reasons.
- [Sensitive content in filenames/manifests] → Private account-scoped storage and redacted diagnostics.
- [HTML masquerading as a file] → Media/body validation plus login detection.

## Migration Plan

Add metadata association first, then opt-in cache functionality and simulated HTTP tests. Existing collection/classification remains functional with downloads disabled. Cache format is versioned; reject incompatible manifests rather than silently deleting data. Automatic cleanup handles only recognized managed entries. Rollback disables the feature and leaves unrelated user files untouched.

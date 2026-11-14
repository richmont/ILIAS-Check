# Design

## Context

Depends on the preceding three changes. The intended deployment is one user's account, one installation, and one Telegram destination, invoked every 12 hours. No cron entry, bot registration, state database, or delivery integration currently exists.

The repository's AGPL license and course-document permissions are separate matters. File transmission needs explicit consent even when authorized ILIAS access is already configured.

## Goals / Non-Goals

**Goals:** A durable one-shot orchestrator, understandable notification rules, and safe failure recovery.

**Non-Goals:** A daemon or incoming-chat polling in this change, multi-tenant hosting, self-installing cron, translation/AI, and an exactly-once delivery guarantee. The later interactive-bot change owns incoming commands.

## Decisions

### One command, external scheduling

Introduce `ilias-check monitor --env-file /absolute/path/.env`, optionally `--dry-run`. Acquire an account/state-scoped process lock for the full invocation, then collect, classify, optionally cache support, plan events, and dispatch eligible sends.

Document cron using absolute executable/config paths and `0 */12 * * *`. Do not edit the user's crontab automatically. Bound run duration and retries; a second instance exits cleanly with a distinguishable overlap diagnostic.

Alternative: an internal always-on scheduler. Rejected because cron already fits the desired deployment and keeps operational complexity low.

### SQLite observations and outbox

Use standard-library SQLite in a private `ILIAS_MONITOR_STATE_DIR` (default `~/.local/share/ilias-check/monitor`). Store versioned schema, runs, last confirmed observations, and outbox events with separate message/attachment delivery records.

Namespace by normalized installation origin, client ID, and configured account identifier, never credentials. Create the observation update and outbox entry transactionally. Keep source snapshots scoped to normalized metadata, not full HTML or document bodies.

Use event fingerprints over stable unit identity, actionable state transitions, deadline, and relevant support versions. Exclude collection timestamps, paths ordering, temporary URLs, and incidental HTML changes. New pending work alerts once; unchanged work repeats only when `ILIAS_PENDING_REMINDER_HOURS` is positive and due (default `0`, disabled). A submitted-to-pending transition creates a new actionable episode.

The 12-hour scan interval does not imply repeated messages every 12 hours. A daily digest was not accepted scope; retain first-observation/change notifications and optional explicit repeats. Pending alerts are primary; closed-without-submission is consultable later rather than repeatedly alerted.

### Uncertainty does not resolve work

A failed root or missing unit in a partial run leaves the previous confirmed observation stale. Absence alone never proves submission, including after a complete scan; mark no-longer-observed separately and stop asserting current certainty. Only explicit current evidence updates submission status.

Confirmed pending work in partial runs can notify, with incomplete-check context. Unknown candidates generate deduplicated health/incomplete-check information, not definitive pending alerts. Failed rechecks do not send old pending reminders as if freshly verified. Bound repeated health alerts.

Before every retry, check event generation/fingerprint against the latest relevant observation. Cancel components superseded by confirmed submission, exclusion, closure, or a newer event. Pause on missing/unknown/failed current evidence; a successful unrelated root is not confirmation. An event can be resumed only after fresh relevant evidence supports it.

Run automatic cache maintenance during each scheduled invocation, including local TTL/quota cleanup after a failed network check. Only confirmed submission/completion ends an association by platform state; local expiry is independently enforceable. Preserve history metadata for later submitted-work queries.

### Telegram is an outbound adapter

Configuration: `ILIAS_TELEGRAM_ENABLED=false`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `ILIAS_TELEGRAM_SEND_DOCUMENTS=false`. Validate explicit enablement and destination before remote collection for an enabled monitor. The token comes from environment or explicitly selected dotenv only.

Use the Telegram Bot API through an isolated HTTP client with finite timeouts, safe formatting, disabled link previews, and redacted errors. Do not reuse ILIAS cookies or auth headers for Telegram. Do not poll messages to infer a recipient.

Messages contain safe ILIAS links, paths, deadline/timezone, and qualified status. Attach only confirmed-associated, valid current cached files unless contextual sharing was explicitly enabled. Before sending, recheck the cache boundary and metadata; never accept an arbitrary local path from remote content.

All bot-owned text is Portuguese; original ILIAS titles/instructions/filenames stay as supplied, without translation services or LLMs. Activity buttons use “Abrir no ILIAS” or the explicitly different “Abrir sequência”; browser authentication can still be required.

Each copy caption/message exposes `downloaded_at`, validation time when available, expiry, and authoritative source link. Warn that cached files may be older and local cleanup cannot revoke delivered copies. A Telegram file ID is not permission to serve expired bytes. On-demand consent is scoped to an interactive request in the fifth change, not a blanket automatic-attachment preference.

### Delivery is acknowledged per component

Create a durable event before sending. Record Telegram message IDs only after confirmed success. Retry failed components with bounded exponential backoff; honor `retry_after`. A one-shot run defers long delays to a later invocation rather than sleeping indefinitely.

If the alert text succeeds and one attachment fails, retry only the attachment after rechecking current activity evidence, consent, and cache expiry. A timeout can occur after Telegram accepted a send; record uncertain delivery and allow a bounded retry with possible duplicates. Do not promise exactly-once semantics without remote idempotency support.

Use configurable conservative message and attachment limits; implementation must verify current Bot API limits rather than assume them. Oversize/stale/missing attachments become title-plus-link fallbacks. Avoid automatically splitting archives or sending solution files.

### Dry run and testability

Inject clock, collector, filesystem boundary, and outbound transport. Dry run can perform authorized ILIAS reads and cache operations if enabled, but must not send Telegram requests or consume/acknowledge events. Derive planned events without modifying durable notification state.

Mocked tests cover lock contention, crashes, account isolation, rate limits, and partial attachment success. No real bot token, chat ID, or student document is needed in fixtures.

## Risks / Trade-offs

- [Duplicate send after ambiguous timeout] → Durable uncertain state, bounded retries, and honest operational documentation.
- [Repeated stale or irrelevant alerts] → Scope rules, evidence-based state, and fingerprinted events.
- [External document disclosure] → Separate attachment consent, private cache, and one explicit destination.
- [State loss] → Document backup; rebuilding may produce first-observation alerts again.
- [AGPL obligations for a future hosted service] → Preserve licensing notices and provide an appropriate source-access mechanism when deployment requires it.

## Migration Plan

Implement SQLite and a fake notifier first, then dry-run orchestration, then opt-in Telegram sends. Add cron documentation only; activation and any real test send require separate user authorization. Version schema migrations transactionally with backup guidance; fail on unsupported newer schema versions. Rollback removes the scheduled command manually and leaves private state intact.

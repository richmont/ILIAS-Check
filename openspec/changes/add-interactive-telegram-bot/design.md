# Design

## Context

See `proposal.md` and `docs/decisions.md`. This change follows the collector, classification, cache, and scheduled notification changes. It adds inbound interaction rather than moving cron scanning into the bot. No runtime implementation exists yet.

The user explicitly chose Portuguese bot-owned UI with original ILIAS content, no translation provider/LLM, host-only cache capacity, automatic cleanup, and submitted-history queries without downloading answers.

## Goals / Non-Goals

**Goals:** A small single-owner private-chat interface over existing typed results, cache services, and outbound transport.

**Non-Goals:** Multi-user registration, arbitrary chat destinations, browser automation, AI/translation, incoming answer processing, ILIAS mutations, automatic public issue creation, and manual cache purge.

## Decisions

### Separate worker and shared core

Add a long-polling `ilias-check bot --env-file /absolute/path/.env` worker; keep `ilias-check monitor` independently cron-invoked. Both use the same core services and SQLite account identity/preferences. Use the existing isolated Telegram HTTP adapter rather than introducing an AI framework.

Long polling avoids hosting a public webhook endpoint for a personal deployment. Add bounded retry/backoff, a single worker lock per bot token/destination, and durable update cursor/idempotent settings operations. A restart must not replay saved settings changes as new commands. Unknown/replayed callbacks are rejected or handled idempotently.

The bot reads last recorded observations with their timestamps/coverage, not a newly invented current state. A support request may perform a bounded fresh relevant metadata check before retrieval, serialized with collector/cache work; repeated commands cannot create an unbounded ILIAS crawl. If eligibility cannot be established, return the source link and needs-verification state rather than cached bytes.

### Single-owner authorization

Require host-configured `TELEGRAM_ALLOWED_USER_ID` and `TELEGRAM_CHAT_ID`, alongside enabled Telegram/token settings. Restrict to the configured private chat and sender before dispatching commands, callbacks, settings, or downloads. Forwarded/opaque callback IDs are not authorization.

The configured owner/destination are never discovered from `/start` and never changed through menus. Rate-limit requests and cap pagination, source text length per message, report field lengths, and queued downloads. Do not retrieve incoming Telegram file bodies.

### Portuguese navigation over original source

Proposed commands/menu actions:

| Command | User-facing purpose |
| --- | --- |
| `/start`, `/ajuda` | Portuguese help and pending-first navigation |
| `/pendentes` | Confirmed pending uploads |
| `/entregues` | Personal/team submission history |
| `/encerradas` | Closed without submission |
| `/verificar` | Unresolved/ambiguous upload candidates |
| `/materiais` | Select eligible support for an activity |
| `/configuracoes` | Retention preferences and cache usage |
| `/relatar` | Unexpected software behavior report |
| `/cancelar` | Cancel current dialogue, not delete cache |

The menu opens pending work first. Use pagination and opaque per-account references, preserving original German or other source text in details. Escape Telegram formatting without semantically translating instructions. Long source instructions are paginated/truncated with an explicit continuation/source link, never silently summarized by AI.

Each activity view offers “Abrir no ILIAS” or “Abrir sequência” according to link kind; browser login is normal. Unknown work explicitly links to the source and reporting flow. Historical views distinguish submitted, graded, and completed, with null/unknown fields rendered honestly.

### On-demand support and consent

An explicitly labeled “Baixar material pelo Telegram” action explains external transmission and authorizes that selected transfer, not automatic future attachments. Automatic attachments remain a separate opt-in setting controlled by the existing monitor policy.

Resolve each request to authorized account/assignment/document IDs; never accept arbitrary remote URLs or local paths. Recheck applicability, source link kind, cache expiry, and current file integrity at dispatch, not only when displaying the button. Existing reader leases protect active file sends from automatic eviction; release them on bounded completion/timeout.

If the old copy merely TTL-expired/was evicted and a current check confirms a still-eligible activity, fetch a bounded fresh copy through the cache. A known deadline/submission/completion-ended association does not refetch merely because of a request. Unknown/stale source state falls back to ILIAS.

Captions or associated text display download time, latest validation time when available, expiry, source activity, and that the source may be newer. Do not bypass eligibility using reusable Telegram file IDs. Already delivered recipient copies cannot be revoked.

### Local settings and precedence

Store only typed, allowlisted per-account preferences in SQLite, initially the no-deadline TTL (default 168 hours) and optional additional retention cap. User preferences override default retention inputs; environment-only capacity/security policy is never overridden by saved keys.

The settings menu offers the default policy (“até o prazo; sete dias sem prazo”) and positive finite custom durations. Clearing the optional cap returns to the default policy, not infinite retention. Reject malformed/zero/negative values. Apply shorter durations on later access/maintenance; longer durations cannot revive expired copies, extend known deadlines, or undo confirmed submission expiry.

The cache provides measured managed bytes and host quota, initially 200000000 bytes. Show usage/limit and measurement time using clear MB units, not total host filesystem usage. No host paths, credentials, or tokens appear in menus. No purge button/command/callback exists; automatic maintenance handles TTL and capacity. Ordinary settings edits do not invoke a purge operation.

Add a bounded automatic maintenance tick to the worker, proposed default every hour, and use cache locks compatible with cron. This is local storage maintenance, not additional whole-tree ILIAS polling. Maintenance also runs before delivery and during scheduled scans; it only deletes recognized managed entries.

### Reports about this software

Use an isolated short-lived text dialogue: description, expected behavior, actual behavior, optional token-free activity link, then a Portuguese preview with edit/cancel/export choices. A needs-verification item can prefill only an optional safe activity reference after user selection.

Keep draft fields in bounded memory scoped to sender/chat; proposed timeout 30 minutes. Restart/timeout discards unfinished drafts with an explanatory prompt on the next interaction. Notifications continue independently. Do not store full course pages, download attachments, or collect logs automatically.

Mask known secrets/session material before preview and export, and warn users to review remaining personal information. Confirmed export returns a copyable draft to the same authorized chat plus the project's manual issue link; say explicitly that no issue was opened. Do not call GitHub APIs, forward reports to a maintainer chat, or send to teachers.

Alternative: automatically publish to GitHub. Rejected because it adds credentials, public disclosure risk, and an unapproved reporting backend.

## Risks / Trade-offs

- [Stale observations mistaken for live state] → Display last-check time/coverage and require fresh eligibility before file delivery.
- [Forwarded buttons or crafted settings] → Authorize sender/chat and allowlist settings on every interaction.
- [Concurrent cron/cache access] → Shared SQLite transactions, short cache locks, bounded reader leases, and single-worker ownership.
- [Accidental public report data] → Manual reviewed export only; disclose redaction limitations.
- [Large materials exceed quota/send limit] → No answer upload or bulk mirroring; source links remain available.
- [Portuguese labels mistaken for translation] → Original content is clearly identified; no bilingual translation feature is advertised.

## Migration Plan

Implement only after the four shared contracts exist. Add owner authorization and mock transport routing first, then queries, retention settings, downloads, and report dialogue. Version SQLite preference/cursor migrations transactionally. Run offline contract and concurrency tests before any approved live interaction.

Deployment documents the separate bot worker and cron monitor with absolute config paths, not automatic service/cron installation. Rollback stops the worker without changing ILIAS or deleting metadata/documents outside normal managed-cache maintenance.

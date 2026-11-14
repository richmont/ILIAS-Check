# Tasks

Depends on the four preceding changes. Implemented and verified offline; no live worker is started.

## 1. Worker boundary and authorization

- [x] 1.1 Add the inbound long-poll worker, isolated Telegram transport reuse, single-worker lock, bounded retries, and persisted update cursor; verify mocked start/restart, replay, and concurrent-worker cases.
- [x] 1.2 Validate host-configured user ID/private chat before every command, callback, and download; verify unauthorized users, group chats, forwarded buttons, and forged identifiers expose no account data.
- [x] 1.3 Add rate limits and bounded queues/page sizes; verify repeated requests cannot trigger unbounded ILIAS crawls and received answer-file bodies are never downloaded.
- [x] 1.4 Document host authorization and separate bot-worker/cron processes; verify placeholder configuration and help examples require no AI, translation service, or public webhook.

## 2. Portuguese navigation and activity views

- [x] 2.1 Implement pending-first menus/help with original source titles/instructions and safe pagination; verify Portuguese UI around unchanged German fixtures and no translation/LLM calls.
- [x] 2.2 Add pending, submitted, closed-without-submission, and needs-verification queries over observations; verify timestamps/coverage, mixed personal/team history, unknown fields, and no false all-clear.
- [x] 2.3 Add source activity/sequence buttons and needs-verification reporting entry; display “Inconclusivo — precisa verificar” with observation time, explanation, and an invitation to describe expected bot display behavior; verify token-free links, honest link-kind labels, no claim to bypass browser authentication, and feedback alone never marks a task submitted/completed/excluded.
- [x] 2.4 Document command/category semantics and submitted-versus-approved distinction; verify examples never require downloading learner answers or changing remote activity state.

## 3. Retention settings and usage

- [x] 3.1 Add typed allowlisted preferences and transactional persistence for no-deadline TTL and optional retention cap; verify restart/cron consistency, default 168 hours, validation, default-policy restoration, and no quota/security overrides.
- [x] 3.2 Show effective policy, measured cache usage/limit/time, and automatic-maintenance explanation; verify the 200 MB decimal display and no host paths/secrets are exposed.
- [x] 3.3 Add automatic local maintenance ticks coordinated with cache/cron locks; verify expiry while idle, active sends, quota reduction, and no manual purge/quota-edit command/callback exists.
- [x] 3.4 Document retention precedence and non-revival of expired copies; verify shorter/longer TTL tests preserve deadline/submission upper bounds and do not turn settings changes into purge operations.

## 4. Support delivery

- [x] 4.1 Implement explicit selected-material download requests with external-transmission disclosure; verify per-request authorization does not silently enable automatic future attachments.
- [x] 4.2 Revalidate relevant activity evidence, association, file integrity, and cache eligibility at dispatch; verify old buttons/file IDs, submitted work, unknown checks, shared copies, and TTL-expired-but-still-pending retrieval.
- [x] 4.3 Send eligible support through the existing outbound adapter with cache timestamps/expiry/source captions and bounded reader protection; verify eviction concurrency, size/quota fallback, and no expired bytes reach Telegram.
- [x] 4.4 Document authoritative-source access and inability to revoke earlier recipient copies; verify successful sends still expose the original ILIAS link and cached-copy warning.

## 5. Software bug-report dialogue

- [x] 5.1 Add short-lived account/chat-scoped text dialogue for description, expected, actual, and optional source link; verify cancel/restart/timeout, field limits, attachment rejection, and ongoing notifications.
- [x] 5.2 Add editable redacted preview and explicit export to the same authorized chat; verify known secrets are masked, no HTML/log/document auto-attachment occurs, and no issue/teacher/admin message is sent.
- [x] 5.3 Document manual reporting and privacy limitations; verify parser-missing-information examples yield a useful reviewed draft while clearly stating no issue was opened.

## 6. Cross-feature verification

- [x] 6.1 Run offline interaction tests across polling, cron observations, settings, cache expiry, and retry cancellation; verify separate processes preserve identity/policy and never mutate ILIAS.
- [x] 6.2 Run packaging/schema regression checks and audit dependencies/request traces; verify no runtime AI/translation integration, live credentials, or real course documents are required.

## Workflow follow-up

- Obtain separate authorization before starting a live worker or sending real messages/materials.
- Archive only after implementation, offline verification, and review; do not auto-install cron or services.

## Verification evidence

See `docs/telegram.md` and `tests/test_monitor_bot.py`: private authorization, cursor/replay, pagination, preferences, inconclusive views, selected-material consent, fresh checks and redacted report export are covered using fake transports. No worker or external send was activated.

## Review and closure — 2026-11-14

Implementation and regression evidence were reviewed before archival. See
`docs/reviews/2026-11-14-openspec-implementation.md` for the cross-feature review
and corrections. All 408 offline tests pass. Capability deltas are synchronized
into the main specifications; no implementation task remains unchecked.

Live Telegram tests, document transmission and worker/cron activation remain
separate authorization-dependent operations, tracked in
`docs/deployment-checklist.md`. Archival does not perform or authorize them.

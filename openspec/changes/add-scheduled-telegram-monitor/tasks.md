# Tasks

Depends on the three core changes; implement before `add-interactive-telegram-bot`.

## 1. Durable observations and events

- [x] 1.1 Create private account-scoped SQLite schema, version checks, transactional migrations, and run locking; verify restart persistence, newer-schema rejection, rollback on migration failure, and concurrent invocation behavior.
- [x] 1.2 Implement observation transitions and event fingerprints with an injected clock; verify first pending, unchanged, deadline change, configured reminder, submitted-to-pending, and account-isolation scenarios.
- [x] 1.3 Preserve stale/unknown observations and deduplicate health events after partial checks; verify a missing or failed root never resolves pending work or emits a false all-clear.
- [x] 1.4 Document state identity, reminder settings, backup, and state-loss behavior; verify documented defaults and synthetic database examples match tests.
- [x] 1.5 Validate/cancel/pause queued components before retry and propagate confirmed delivery to cache expiry; verify submission-before-retry, superseding deadline events, unknown rechecks, expired support, and retained history metadata.

## 2. Outbound Telegram adapter

- [x] 2.1 Add explicit enablement, token/chat validation, isolated transport, escaping, and redaction; verify disabled mode makes no Telegram calls and token-bearing errors are sanitized.
- [x] 2.2 Format Portuguese bot-owned labels with original ILIAS content, source buttons, timezone, and incomplete-check notices; verify untranslated German fixtures, no AI/translation calls, login-required links, and untrusted markup.
- [x] 2.3 Add opted-in support attachments with timestamp/expiry/source captions and pre-delivery eligibility checks; verify disabled sharing, stale/expired copies, reused Telegram file IDs, model answers, invalid paths, and oversize fallbacks.
- [x] 2.4 Record component-level acknowledgments and retry state; verify message success plus attachment failure, rate limits, transient errors, and ambiguous timeouts without claiming exactly-once delivery.
- [x] 2.5 Document recipient setup, separate document-sharing consent, current Bot API limits, and possible retry duplicates; verify no real token, chat ID, or course document is used in examples/tests.

## 3. Monitor orchestration

- [x] 3.1 Implement the one-shot monitor command with bounded execution, run lock, collection coverage, outbox planning, and eligible dispatch; verify fake-transport end-to-end runs and explicit partial/fatal outcomes.
- [x] 3.2 Implement dry run without Telegram calls or durable notification acknowledgments; verify queued retries and future real sends remain unaffected by previewing.
- [x] 3.3 Document absolute-path cron usage for every 12 hours, overlap behavior, local diagnostics, and manual disablement; verify commands in an isolated environment without installing a cron job.
- [x] 3.4 Integrate automatic cache maintenance independently from remote-check success; verify TTL/quota cleanup after failed scans never falsely resolves pending work or deletes history metadata.

## 4. Recovery integration

- [x] 4.1 Exercise process crashes between observation commit, send, and acknowledgment; verify durable recovery and disclose ambiguous-send duplication in the test expectations.
- [x] 4.2 Run the full offline regression suite and a secret/runtime-artifact check; verify no test sends a live message or requires credentials and no state/document file is eligible for Git.

## Workflow follow-up

- Obtain separate authorization before any real Telegram send, attachment transmission, or cron activation.
- Review and archive after implementation and verification; retain the AGPL and any third-party notices.

## Verification evidence

See `docs/telegram.md` and `tests/test_monitor_bot.py`: transactional state/migrations, transitions, partial checks, component retries, dry runs and failure maintenance are covered. A real collector-backed dry run planned events without Telegram calls or notification acknowledgments. Live sends and cron activation remain separate authorization steps.

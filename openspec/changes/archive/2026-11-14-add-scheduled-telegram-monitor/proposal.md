# Proposal

## Why

Users should not need to run the collector or navigate ILIAS every day. A scheduled, stateful monitor can send actionable reminders without repeating unchanged notifications or hiding collection failures.

## What Changes

- Add a one-shot monitor suitable for cron, with a documented 12-hour example and overlap protection.
- Persist account-scoped observations and notification events in SQLite.
- Notify one explicitly configured Telegram recipient about eligible pending work and meaningful changes.
- Attach cached support documents only with explicit opt-in; otherwise send metadata and manual delivery links.
- Handle partial collection, transport errors, attachment limits, retry state, and configurable repeat reminders.
- Prioritize pending alerts, qualify unresolved work, and cancel obsolete queued alerts before retrying.
- Use Portuguese bot-owned messages while preserving original ILIAS content and token-free activity/sequence buttons.
- Dependencies: the collector, assignment classification, and support-document cache changes.
- Non-goals: installing cron automatically, a multi-user bot service, webhooks, chat commands (owned by `add-interactive-telegram-bot`), automatic answer upload, translation/AI, and guaranteed exactly-once delivery.

## Capabilities

### New Capabilities

- `monitor-state`: Scheduled observation, change detection, and durable notification state.
- `telegram-notifications`: Explicitly configured, privacy-aware messages and optional attachments.

### Modified Capabilities

None. The monitor orchestrates the earlier capabilities without coupling collection to Telegram.

## Impact

Adds SQLite persistence, a Telegram adapter, monitor CLI, and deployment documentation. Credentials, bot tokens, chat identifiers, cached files, and monitoring state must not be committed. External transmission is disabled unless configured.

# Proposal

## Why

Scheduled alerts alone do not let the learner inspect delivered or uncertain work, retrieve support, adjust retention, or explain parser failures. A private, authorized Telegram interface provides these functions without navigating ILIAS or introducing AI.

## What Changes

- Add a single-user private-chat bot with Portuguese menus and original ILIAS content.
- Make pending work the main view, with separate submitted, closed-without-submission, and needs-verification queries.
- Provide source activity/sequence buttons and explicitly requested eligible support downloads with cache timestamps and source warnings.
- Add retention settings, seven-day no-deadline default, and read-only cache usage/quota display; capacity remains host-controlled and cleanup automatic.
- Guide users through reviewed reports of unexpected bot behavior, including information visible in ILIAS that the bot failed to interpret.
- Dependencies: all four existing changes; reuse their collector, classifier, cache, state, and outbound transport.
- Non-goals: AI or translation services, translating course content, ILIAS mutations, accepting answer uploads, multi-user hosting, manual cache purge/quota editing, or automatic issue publication.

## Capabilities

### New Capabilities

- `bot-access-and-queries`: Authorized private-chat navigation, status/history queries, and support retrieval.
- `bot-settings`: Portuguese settings, retention preference, and cache capacity visibility.
- `bot-bug-reports`: Structured, reviewed reports of bot/software failures without automatic sensitive-data collection.

### Modified Capabilities

None. This change consumes the preceding core/notification contracts without redefining their requirements.

## Impact

Adds an inbound Telegram worker, command/callback routing, persistent account preferences, and short-lived report dialogue state. No cron job, bot registration, external report publication, or live message is performed by creating these planning artifacts.

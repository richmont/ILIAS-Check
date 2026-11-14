# Project decisions

Status: accepted product decisions, recorded 2026-11-14. Implementation is pending.
Technical defaults below are proposed implementation details where identified.

## 1. Purpose and boundaries

The primary function is alerting the configured learner about pending file-upload
assignments. Authorized queries and support-material downloads reduce navigation.
The initial deployment is one ILIAS installation, account, Telegram user, and
private chat. Initial adapter compatibility targets ILIAS 9_23.

ILIAS operations are read-only except authentication/session maintenance. Never
upload answers or attachments, submit text, finish learner steps, change enrollment,
or modify remote preferences. Reading may create ordinary access/download logs;
read-only does not mean invisible to the platform.

Sending support documents **from ILIAS to the authorized Telegram user** is allowed
on request or with explicit attachment consent. This is not an ILIAS submission.
Do not download learner answers merely to show submission history.

## 2. Language and independence from AI

The program does not require an LLM, AI agent, or translation service at runtime.
The bot's menus, buttons, help, errors, and software-generated status labels are
Portuguese. Original ILIAS titles, instructions, filenames, and quoted source text
are preserved in their source language, including German. Presentation escaping
and whitespace normalization must not change meaning.

This is a Portuguese interface around original source content, not automated
bilingual translation. Neither titles nor attachments are sent for translation.

## 3. Assignment states and history

| Evidence | Behavior |
| --- | --- |
| Applicable open file delivery, no personal/team submission | Primary pending alert |
| Confirmed existing personal or applicable team submission | Submitted history; not pending |
| Closed without submission | Dedicated query; no ordinary pending reminder |
| Upload requirement visible, state/applicability unresolved | Needs-verification view/notice with original link |
| Practice/self-test or optionality unclear | Preserve source classification; do not assert obligation |

Submitted is not synonymous with graded, approved, or pedagogically complete.
History shows activity/link, delivery date when known, attachment presence,
personal/team scope, and grading/completion only when the platform confirms it.
Unknown dates or attachment details stay unknown. Team submission is not falsely
attributed to a personal upload by the learner.

Group alternatives must not exclude unrelated individual or newly discovered
activities. Explicit alternative selection applies only inside its declared set.
A group-looking title does not establish ownership.

## 4. Original activity links

Every actionable item exposes a token-free source link. Use “Abrir no ILIAS”
for a resolved activity and “Abrir sequência” for sequence entry. A direct link
opens only as far as the platform permits; browser login or manual navigation
may still be needed. Never embed credentials, cookies, or session tokens.

## 5. Support material and cache

Associate documents by evidence: assignment attachment, explicit instruction link,
or clearly labeled contextual material. No automatic mirroring of entire courses,
model answers, learner submissions, or unrelated files.

Local download and Telegram sharing are separate choices. The settings menu
controls the learner's retention preference and shows actual managed disk usage
and the host-set quota. It cannot change capacity or trigger cleanup.

### Retention

- For a parseable deadline, the default association expiry is that deadline.
- Without a deadline, default retention is seven days from the successful download.
- A user-configured TTL is an additional maximum; it cannot extend a known deadline.
- Confirmed submission or explicit platform completion expires that assignment's
  association immediately, without waiting for assessment.
- An unreadable deadline is not “no deadline”: use a bounded seven-day fallback,
  flag uncertainty, and direct the user to the source.
- A document shared by assignments remains cached only while at least one
  association is valid; it is no longer offered for an expired association.
- Do not refetch for an association ended by deadline, submission, or completion
  merely because the user requested it. Offer the source link. A fresh confirmed
  extension/reopening or another eligible association can make retrieval valid.
- TTL expiry or capacity eviction invalidates the old copy, not an otherwise
  still-pending activity. A current eligibility check can permit a bounded fresh
  source download, with a new download timestamp and new retention calculation.

Increasing TTL does not resurrect expired copies. Shortening TTL applies on the
next access/cleanup. Revalidation without downloading a new body does not reset
the original download time or silently extend retention.

### Capacity and automatic cleanup

The administrator sets `ILIAS_SUPPORT_CACHE_MAX_BYTES` in the host environment;
the proposed initial default is **200,000,000 bytes (200 MB, decimal)**. It applies
to the configured managed cache, including managed document bodies, temporary
download files, and cache metadata, not all application databases or disk usage.

Automatic maintenance first removes expired/unreferenced managed copies, then
evicts the oldest downloaded eligible copies when space is needed. Eviction must
physically reclaim space; marking a record `stale` alone cannot enforce the cap.
Retain an `evicted` metadata state only within the bounded manifest.

Never remove arbitrary files outside the managed cache. Transfers reserve/check
capacity under a cache lock and respect active reads; if space cannot safely be
reclaimed, skip caching and provide the source link. Admin quota reductions are
enforced at the next maintenance/access, and no new transfer may worsen excess.

TTL/expiry are checked before each bot delivery; automatic cleanup also runs on
scheduled checks and bot maintenance. Metadata for history survives file cleanup.
Copies already downloaded by the user or sent to Telegram cannot be revoked by
local cache expiration, and reusable Telegram file IDs must not bypass expiry.

### Freshness

Every delivered copy identifies its source activity, download timestamp, latest
validation time when available, and expiry. State clearly that the original ILIAS
page is authoritative and can contain a newer version. Offer that page's link
even when the bot successfully supplies a cached copy.

## 6. Monitoring and notifications

Checking every 12 hours is separate from repeating alerts. Keep the existing
first-observation/change alert policy; repeats remain configurable and disabled
by default. A daily digest was discussed as a recommendation, not accepted scope.

Revalidate queued notifications against the latest successful relevant check.
Cancel events superseded by a confirmed submission, exclusion, closure, or a
newer applicable event. Pause stale retries on incomplete/unknown evidence rather
than declare them currently valid. Each attachment also needs fresh cache
eligibility and consent checks before dispatch.

No all-clear claim is permitted when candidate work remains unresolved.

## 7. Interactive bot and bug reports

The fifth change adds authenticated private-chat queries for pending, submitted,
closed-without-submission, and needs-verification work, plus support downloads,
settings, and reporting unexpected **bot/software behavior**.

Reports capture description, expected behavior, and actual behavior; an affected
activity link is optional. They do not complain about course content or contact
teachers. Preview and explicit sharing confirmation are required. Do not attach
raw HTML, course documents, credentials, cookies, or complete logs automatically.
Initial implementation prepares a reviewed report for manual issue submission;
automatic GitHub issue creation or another reporting backend is out of scope.

Incoming user documents are not accepted as ILIAS answers or forwarded anywhere.
All commands, callbacks, and downloads require the configured user and private
chat; knowing a document ID or pressing an old button is not authorization.

## 8. Licensing and implementation order

Retain the existing AGPL-3.0 project license. Reuse only necessary authentication
and useful utilities from the MIT MCP project, preserving copyright, license,
and upstream revision. Do not depend on the MCP process or copy unrelated mutation
code. Expand reused scope only with an explicit justified need.

Implement the four core changes first, followed by `add-interactive-telegram-bot`.
No application, cron entry, Telegram service, or live network test has been created
by recording these decisions.

## 9. Remaining technical validation

Sequence-child discovery without explicit progress transitions still needs a
focused compatibility investigation. If unavailable, export `unknown`, a source
link, and a needs-verification notice rather than silently omitting the work.

Product decisions are coherent; read-only coverage and extraction accuracy still
require fixture-based tests and separately authorized live compatibility checks.

## 10. Second coherence review

Reviewed the five changes together after incorporating the accepted decisions:

- Portuguese UI is not a translation feature; no external language service or
  runtime AI dependency remains in scope.
- Read-only ILIAS access is compatible with sending support to the authorized
  learner; it does not permit submitting answers or completing remote activities.
- The notifier remains cron-invoked; the fifth change adds a separate inbound
  worker, avoiding an architectural contradiction between one-shot and interactive
  execution.
- Quota eviction reclaims managed bytes, while stale/expired states prevent unsafe
  reuse. Metadata flags alone cannot enforce storage capacity.
- TTL expiry invalidates bytes; deadline/submission/completion ends an association.
  An eligible pending activity can obtain new bytes after a TTL expiration, not
  revive an expired copy.
- Shared documents remain available only through still-valid associations.
- A known deadline can end cache eligibility even if ILIAS accepts late answers;
  alerts and source links remain available independently of local copies.
- Confirmed submission ends cache association and pending alerts but does not
  erase history or imply academic approval.
- Retention changes are user preferences; quota/security settings are host policy.
  No bot cleanup command is introduced.
- Cached timestamps and source links disclose freshness limits; already sent or
  in-flight recipient copies cannot be recalled by automatic local cleanup.
- Reviewed bug-report export is distinct from automatic public issue creation.

No additional blocking product decision was identified. Sequence extraction
without explicit progression is the remaining material compatibility risk, not
an authorization to alter activities. Proposed technical defaults (such as hourly
local maintenance and a 30-minute report draft timeout) remain tunable implementation
details, not extra remote scans or externally transmitted data.

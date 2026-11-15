# Project decisions

Status: accepted product decisions, initially recorded 2026-11-14 and updated with
the subsequent bot-usage session. Core implementation is complete; the dated review
and later sections record follow-up behavior. Historical implementation-order notes
below describe the original plan.

## 1. Purpose and boundaries

The primary function is alerting the configured learner about pending file-upload
assignments. Authorized queries and support-material downloads reduce navigation.
Each invocation uses one ILIAS installation and account. The original single-user
setup now permits an explicit additional-user allowlist, with private replies and
one configured monitor-notification destination. Initial adapter compatibility targets ILIAS 9_23.

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
by default. Due alert events now share one summary containing the confirmed pending
count and original titles, with incomplete-check information in the same text. This
is event grouping, not a new periodic daily digest or reminder schedule. Long lists
show an omission count and point to the interactive list instead of flooding the chat.

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
All commands, callbacks, and downloads require an explicitly authorized user in
a permitted private chat; knowing a document ID or pressing an old button is not
authorization. Additional users share the configured ILIAS account, with isolated
report drafts, transient buttons, and request limits. Responses go to the requesting
private chat; notifications are not automatically broadcast to all permitted users.

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

## 11. Inconclusive activities and future user feedback

Keep the currently unresolved sequence steps and blank assignment details as
unknown. Further extraction attempts are deferred while development proceeds.
In the Telegram interface, display these cases as “Inconclusivo — precisa
verificar”, with observation time, a brief explanation, and the original ILIAS
link. Invite the learner to describe how the bot should display that activity,
using the planned software-feedback dialogue and its expected/actual fields.

Suggested invitation: “Esta tarefa apareceu de forma inesperada? Conte como o
bot deveria exibi-la.” Feedback is intended to guide later display rules and
compatibility fixes; receipt of feedback alone does not prove submission,
completion, or non-applicability and does not change ILIAS state. The Telegram
feedback flow is implemented in the private worker; live activation remains separate.

## 12. Accepted installation and bot-usage refinements

The following session decisions are reflected in the main capability specs:

- Installation documentation defaults to English, with Brazilian Portuguese and
  German variants. Clone the merged `main` branch into `/opt/ilias/check`; use
  `/opt/ilias/venv` for execution and `/opt/ilias/data` for dotenv, JSON, SQLite,
  downloaded documents, and logs. Bonn uses `Europe/Berlin`.
- `collect --progress` and `monitor --progress` report root/request/object counts
  and elapsed time on stderr, keeping JSON stdout separate. Normal page reads reuse
  the authenticated session; a separate login is not performed for each request.
- Optional `TELEGRAM_ALLOWED_USER_IDS` grants explicitly listed users access to the
  same account in their own private chats. Report drafts, navigation tokens, and
  request budgets are isolated per user; the monitor destination remains explicit.
- The worker registers its command menu on startup. `/ajuda` sends help only;
  `/start` sends help and the first pending page. `/futuras` exposes not-yet-open
  work, and `/resumo` counts states with coverage warnings.
- Telegram display timestamps use `DD/MM/YYYY HH:MM` in the configured course zone
  (UTC fallback); saved JSON keeps UTC timestamps. Original source text is retained.
- A pending alert is one message with the current confirmed pending count and a
  simple title list. Health warnings share that message. Unknown and missing
  historical observations are not counted as confirmed pending. Existing event
  deduplication, optional reminders, bounded retries, and attachment consent remain.
- Activity queries show five summaries in one page message. Pagination uses
  “Anterior” and “Próxima” buttons, never a numeric argument after the command.
  Number buttons open a single detail; “Exibir todas” is the explicit choice to
  expand all detail messages. Material pagination uses buttons too, ten per page.
- Pending details expose up to two selected-support download buttons, including
  metadata-only references. Clicking authorizes only the selected transmission,
  after eligibility checks, preferring a valid local copy before any necessary ILIAS
  refresh. The compact monitor summary points to
  `/pendentes` for these actions. Existing durable material tokens expire after
  24 hours, are single-use, and survive worker restart without bypassing checks.
- Submitted-history and needs-verification detail buttons retain their view's
  meaning even when current observations differ. Missing evidence remains unknown;
  no display action submits or completes ILIAS work.

These refinements were verified with offline transports. They do not install or
restart services, edit host credentials, schedule jobs, or send live messages.

## 13. Cache-first document buttons and visible progress

An authorized document click first attempts local delivery from the latest stored
pending observation. A valid cached copy does not trigger login, traversal, another
body download, or the five-minute source-refresh throttle. Automatic caching and
automatic document notifications can stay disabled: the click authorizes this copy.

This changes retrieval order, not validity requirements. The existing gate still
requires a current pending observation at most twelve hours old, a selected support
association, a recently validated file, integrity, and unexpired retention/deadline.
If these checks fail, a bounded source refresh can re-establish eligibility; expired,
unknown, missing, or submitted evidence never authorizes old bytes by itself.

The bot responds before local work and announces a potentially slow source scan
before starting it. A dismissed callback spinner alone is insufficient feedback.
An upload failure gets a safe source-linked response and cannot trigger a second
collection/download/upload automatically in that request. Validation uses synthetic
cached PDF bytes and fake Telegram transports, with no real course-document send.

## 14. Material availability, twelve-hour requests, timeout, and source names

Document buttons now distinguish locally available bytes, cached bytes requiring
revalidation, source retrieval, and an unverified cache. Querying availability uses
the actual account-scoped manifest and files, without ILIAS requests; display labels
never bypass the delivery gate.

The original fifteen-minute activity window was too short for explicit requests
between twelve-hour scheduled checks. Requested cached copies now accept the latest
current pending observation for up to twelve hours. File validation, integrity,
selection, deadline, retention, and newer source evidence remain binding. Automatic
monitor notifications and new source downloads retain their stricter existing rules.

An interactive material request has a total two-minute elapsed-time limit. Timeout
interrupts synchronous work and unwinds transports, locks and partial transfers,
without leaving collection in the background or replacing observations with an
incomplete timed-out result. The user receives an explanation and source link.

Telegram documents preserve the ILIAS response filename when known, or use the
original material title for older cache entries, sanitized to a bounded basename
with the validated media type's extension. Internal blob names remain private.
These changes were checked offline with synthetic files and transports.

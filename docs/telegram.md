# Monitor and private Telegram worker

The local implementation is available; deployment is deliberately separate. No real
messages, course attachments, cron jobs or background services were activated during
development. Live sends, attachment sharing and worker/cron activation need the user's
separate authorization. Cache downloads are independent and remain disabled by default.

## Host configuration

Use Linux/POSIX, Python 3.11+, a private explicitly selected dotenv file, and the same
configuration for cron and the worker. Start from `.env.example`, never real examples
in Git. Supply `TELEGRAM_BOT_TOKEN`, a positive private `TELEGRAM_CHAT_ID` and, for the
interactive worker, `TELEGRAM_ALLOWED_USER_ID`. Register the bot manually and open its
private chat; IDs/destinations are never discovered or changed through `/start`.
Optional `TELEGRAM_ALLOWED_USER_IDS` accepts a comma-separated list of additional
numeric IDs. Each extra user must open a private chat with the bot from that account
and can only query/inspect shared state there; notifications still go to
`TELEGRAM_CHAT_ID`. Report drafts, rate limits and material buttons are per user.
All users consult the same ILIAS account, history and retention settings.
`ILIAS_TELEGRAM_ENABLED=false` is the default. Keep `ILIAS_TELEGRAM_SEND_DOCUMENTS=false`
unless automatic external transmission of course documents is separately authorized.
An interactive material button authorizes that selected send only.

The Bot API adapter owns a separate HTTP session and never receives ILIAS cookies.
TLS, finite connect/read timeouts and disabled redirects protect requests. No raw
Telegram error or token-bearing URL is printed. Source text is plain text (no parsed
HTML/Markdown); link previews are disabled. Source buttons may require browser login.
No translation service, AI integration, webhook or incoming file download is used.

As verified against the [official Bot API](https://core.telegram.org/bots/api) on
2026-11-14, sendMessage permits 4096 characters, document captions 1024, and ordinary
multipart documents up to 50 MB. Local defaults are conservatively 4000 characters
and 20 MiB; configuration cannot raise the API ceilings. Oversize/unavailable support
falls back to its original activity link. No Telegram file ID bypasses the cache gate.

## One-shot monitor

```sh
/absolute/project/.venv/bin/ilias-check monitor --env-file /absolute/private/ilias.env --dry-run
/absolute/project/.venv/bin/ilias-check monitor --env-file /absolute/private/ilias.env
```

Dry run can perform authorized ILIAS reads and opt-in local cache work. It plans events
in a temporary database copy, sends nothing and does not consume/acknowledge durable
notifications. Disabled Telegram never calls its API. The command reports counts and
qualified completeness, without course titles or secrets in diagnostic output.
Add `--progress` to stream throttled request/object counts and elapsed time to stderr
while the crawl runs; the JSON report on stdout stays clean.
Exit codes: 0 complete, 2 incomplete, 1 failed/configuration error, 3 overlapping
private-state operation. Network work is bounded by request/depth budgets and finite
request/stream timeouts. At most 50 due components are attempted in one invocation.

An administrator can later install this absolute-path cron line **after authorization**:

```cron
0 */12 * * * /absolute/project/.venv/bin/ilias-check monitor --env-file /absolute/private/ilias.env >> /absolute/private/monitor.log 2>&1
```

Create the private log with mode 0600 first. This documentation installs nothing.
Disable manually by removing/commenting the cron line and setting Telegram enablement
false. The interactive worker is a separate foreground process; stopping it does not
modify ILIAS. No service unit is automatically installed.

## Observations, recovery and notification rules

State defaults to `~/.local/share/ilias-check/monitor` (0700, outside checkouts). SQLite
files are 0600 and namespaced by installation/client/account identity, never passwords.
Version 1 creates tables transactionally, rejects newer versions and rolls back failed
migrations. Short transactions coordinate the worker and cron. An account run lock
covers collection/planning/dispatch; overlapping runs defer with a safe diagnostic.
The cache has its own root-wide lock and bounded reader protection.

New confirmed pending units alert once. Deadline/support-version changes create a new
event. Unchanged observations do not alert every 12 hours. `ILIAS_PENDING_REMINDER_HOURS`
defaults to 0 (disabled); a positive integer enables reminders after acknowledged
alerts. Submitted-to-pending starts a new episode. Closed work remains consultable
without ordinary pending reminders. Unknown/incomplete checks generate deduplicated
qualified health notices, never definitive obligations or a false all-clear.

Missing units, including after a complete source scan, remain historical/stale rather
than becoming submitted. Relevant unknown/failed rechecks pause queued components.
Confirmed submission, exclusion, closure or a newer event cancels superseded retries.
Fresh relevant evidence is required before resuming. Submission metadata persists in
a separate history view; it does not imply assessment/approval. No learner answers
are fetched. Cache maintenance runs even after remote failures and never invents a
submission to justify cleanup.

A changed generation starts its own reminder clock; an old reminder is not added
to a deadline/support change alert. Before every component dispatch, including later
items in a slow batch, generation, retry state and evidence freshness are checked
again. Evidence older than fifteen minutes pauses pending sends until a fresh check.
Qualified incomplete notices and failed material requests retain source navigation.

Events are committed before delivery. Text and each attachment have separate durable
acknowledgments; a failed attachment does not resend successful text. Errors retry at
most five times with bounded backoff and Telegram retry_after. A timeout/crash can
occur after Telegram accepted a send but before local acknowledgment: retries may
produce duplicates. Exactly-once delivery is not promised. No automatic credential or
destination changes happen after errors.

Stop worker/cron before copying the whole private state directory for backup, or use
SQLite's backup facility; preserve permissions and keep backup private. Do not edit the
database manually. State loss can regenerate first-observation alerts. Back up local
configuration separately; the cache is disposable and never a source of truth.

## Interactive commands

```sh
/absolute/project/.venv/bin/ilias-check bot --env-file /absolute/private/ilias.env
```

Every command and callback requires the configured sender in the configured private
chat, including forwarded buttons. A token/destination worker lock prevents duplicate
pollers using the same state store. Update cursors persist before side effects; replay
cannot repeat a setting/send, although a crash can lose a reply. Buttons are opaque,
account-local, single-use and expire after 30 minutes/restart. Incoming updates are
bounded to 25 per poll, authorized requests to 20 per minute, activity pages to four,
and material pages to ten. Source checks for material requests are serialized, bounded
by collector limits and throttled to one per five minutes across worker restarts.

| Command | Meaning |
| --- | --- |
| `/start` | Portuguese help and pending-first view |
| `/ajuda` | Portuguese help only |
| `/pendentes [page]` | Confirmed pending file uploads, with stale warnings |
| `/entregues [page]` | Historical personal/team delivery metadata; approval separate |
| `/encerradas [page]` | Closed without submission |
| `/futuras [page]` | Period not open yet |
| `/verificar [page]` | “Inconclusivo — precisa verificar”, reasons/time/source and feedback invitation |
| `/resumo` | Count per situation plus coverage warnings |
| `/materiais [page]` | Explicit selected-material transmission request |
| `/configuracoes` | Retention, measured managed usage/quota/time without host paths |
| `/retencao sem_prazo 24` | Positive no-deadline retention hours |
| `/retencao limite 48` | Optional additional cap in hours |
| `/retencao padrao` | Restore host default retention policy |
| `/relatar` | Description / expected / actual / optional safe source link |
| `/cancelar` | Discard the current dialogue |

Original titles/instructions/filenames remain unchanged in their source language.
Long instructions have an explicit continuation notice and source link. Team delivery
is not described as a personal upload. Unknown approval/completion fields remain
unconfirmed. Inconclusive feedback does not mark work submitted, complete or excluded.

Settings persist across worker/cron processes. Durations must be integral 1–87600 hours;
only retention fields are editable. Known deadlines and confirmed submission/completion
remain upper bounds. The default no-deadline duration is 168 hours. Shorter preferences
apply at subsequent access/maintenance; longer preferences cannot resurrect expired
bytes. Quota is host-only, default **200 MB decimal**, shared across cache accounts.
No purge, clear-cache, quota, credential, destination or path setter exists. Local
maintenance ticks hourly and never trigger an extra full ILIAS scan.

A material request first performs a fresh bounded source check. Only the selected
support is fetched; submitted/unknown/ended work, answers and model solutions are
refused. The final delivery gate rechecks current association, retention and checksum
under a reader lock. Captions give copy/validation/expiry times and the original
activity source. ILIAS may be newer; already delivered copies cannot be revoked.
An ongoing accepted transfer may finish after local expiry; a new transfer may not start.

Reports concern this software, not messages to teachers. Only text is accepted, with
four fields up to 800 characters each, 30-minute memory-only drafts and edit/cancel
support. Preview masks configured secrets and recognizable session material, but
cannot guarantee removal of personal/course information. `/editar descricao`,
`/editar esperado`, `/editar ocorrido`, `/editar link` revise the preview; `/exportar`
returns a copyable draft and the project's manual issue link to this same private
chat. **No issue is opened, and no maintainer/teacher/admin receives the report.**
Restart/timeout discards drafts; scheduled notifications remain independent.

Deployment status and remaining authorization-dependent steps: [operational checklist](deployment-checklist.md).

# ILIAS-Check

ILIAS-Check helps a learner keep track of file-upload assignments in ILIAS. It
reads the repositories the learner selects, checks each assignment unit, and
keeps pending work, submitted work and uncertain results separately visible.
The same information is available as JSON and through a private Telegram bot.

The project is intended for authorized personal access to one configured ILIAS
account and installation. Its initial compatibility target is ILIAS 9.23, based
on the observed target deployment; other installations may need parser adaptations.
Bot-owned messages are in Portuguese. Course titles, instructions and filenames
retain their original language. No AI model or translation service is required.

## What it does

- Traverses configured repository roots with bounded depth and request budgets.
- Classifies individual assignment units, including personal and confirmed team
  submissions, instead of treating an entire exercise as one task.
- Preserves original source links, instructions, deadlines and observation times.
- Associates worksheets and other supporting documents with their source activity,
  excluding known model answers, feedback and learner submissions.
- Optionally caches eligible support in private storage with checksums, expiry,
  automatic cleanup and a host-controlled quota.
- Records observations and notification delivery in SQLite, supports scheduled
  checks, and offers private Telegram queries, retention settings and feedback.

The software never submits answers, changes enrollment or advances/completes
learning steps. Work is submitted manually in ILIAS. Ordinary authorized reads
can still produce platform access records, and browser links may require login.

## How assignment states are interpreted

A visible exercise is not automatically an outstanding obligation. Classification
uses current delivery, applicability and availability evidence for each unit.

| State | Meaning |
| --- | --- |
| `pending` | Applicable file delivery is open and no personal or confirmed team submission is present. |
| `submitted` | A submission is confirmed; approval or completion is not implied. |
| `closed_without_submission` | The source confirms closure without a submission. |
| `not_yet_open` | The submission period is not open yet. |
| `excluded` | The unit is outside the configured upload scope or an explicit local filter. |
| `unknown` | Available evidence is insufficient or contradictory; manual verification is needed. |

Coverage and uncertainty remain visible even when results are filtered. An empty
pending list does not mean everything is complete if a root or candidate activity
could not be evaluated. In the bot, uncertain work is shown as
**“Inconclusivo — precisa verificar”**, with a source link and an invitation to
explain the expected display behavior. Feedback alone does not change a task's state.

See [classification rules](docs/assignment-classification.md) and
[sequence compatibility](docs/sequence-compatibility.md).

## Installation and configuration

For the complete setup, credential examples, BotFather/ID configuration, first-run
checks and optional systemd/cron activation, follow [INSTALL.md](INSTALL.md) (Portuguese).

Use Python **3.11+** on Linux. The private cache and monitoring state use POSIX file
permissions/locks and Linux directory-descriptor paths.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/ilias-check --help
```

For a new configuration, copy the placeholder file to a private location and edit
it locally:

```sh
install -d -m 700 "$HOME/.config/ilias-check"
install -m 600 .env.example "$HOME/.config/ilias-check/ilias.env"
```

Set these values in that file:

| Setting | Purpose |
| --- | --- |
| `ILIAS_BASE_URL` | HTTPS installation URL. |
| `ILIAS_CLIENT_ID` | Client identifier used by that installation. |
| `ILIAS_USER`, `ILIAS_PASS` | Credentials for the account you are authorized to access. |
| `ILIAS_PENDING_ROOTS` | Comma-separated positive repository reference IDs to inspect. |
| `ILIAS_TIMEZONE` | Installation timezone for local deadlines; use `Europe/Berlin` for Bonn/Germany. |

The checker loads only the dotenv file explicitly selected with `--env-file`;
it does not search parent directories. Process environment values take precedence.
All optional settings and defaults are listed in [.env.example](.env.example).
See [collector setup](docs/collector.md) for login compatibility and traversal limits.

## Command-line usage

The package exposes four commands:

| Command | Purpose |
| --- | --- |
| `collect` | Read ILIAS, classify activities and export an inventory; cache support only if enabled. |
| `classify` | Reclassify a saved inventory locally, without network access or credentials. |
| `monitor` | Run one check, maintain local state and dispatch explicitly enabled notifications. |
| `bot` | Run the authorized private-chat worker in the foreground. |

For example, collect a private inventory with pending activities selected:

```sh
umask 077
mkdir -p "$HOME/.local/share/ilias-check"
.venv/bin/ilias-check collect \
  --env-file "$HOME/.config/ilias-check/ilias.env" \
  --select pending \
  > "$HOME/.local/share/ilias-check/inventory.json"
```

Inspect uncertain activities from that saved inventory without accessing ILIAS:

```sh
.venv/bin/ilias-check classify \
  --input "$HOME/.local/share/ilias-check/inventory.json" \
  --env-file "$HOME/.config/ilias-check/ilias.env" \
  --select needs-verification
```

Preview the monitor's planned notifications without sending or acknowledging them:

```sh
.venv/bin/ilias-check monitor \
  --env-file "$HOME/.config/ilias-check/ilias.env" \
  --dry-run
```

A monitor dry run still reads ILIAS and can perform local cache work if configured.
Inventory commands write JSON to stdout and diagnostics to stderr. Exit codes are
`0` for complete results, `2` for incomplete results and `1` for failure; monitor
state-lock contention uses `3`. A partial inventory remains useful and inspectable.
See the [JSON contract](docs/inventory-format.md).

## Support documents and privacy

Support downloads are **disabled by default**. When enabled, confirmed pending work
can obtain explicitly associated support; nearby contextual materials require a
separate opt-in and a known support role. Unresolved sequence files remain metadata
with a manual source link. No file URL or sequence step identity is invented.

The cache defaults to `~/.local/share/ilias-check/support`, outside source checkouts,
with private files and account-scoped identities. The default total quota is
**200000000 bytes (200 MB decimal)**. Known deadlines and confirmed submission or
completion end an association; without a deadline, retention defaults to seven days.
Users can adjust retention, while capacity and security remain host-controlled.
Cleanup is automatic; the bot has no purge or quota-edit command.

Copies carry download, validation and expiry times. **ILIAS remains authoritative**
and may be newer. Expired, stale, corrupted or otherwise ineligible copies cannot
be sent through the delivery gate. Removing a local copy cannot revoke a copy
already delivered to a recipient.

Credentials, inventories, manifests, databases and course documents are private
runtime data. Keep them out of Git, public reports and shared logs. Software licensing
does not grant rights to redistribute course materials. See
[support associations](docs/support-associations.md) and [cache lifecycle](docs/support-cache.md).

## Telegram and scheduled checks

Notifications are **disabled by default**, as is automatic document sharing. Enabling
messages does not enable attachments. The worker requires a configured bot token,
private chat ID and allowed user ID; every command and callback checks authorization.
Incoming answer files are not downloaded or forwarded to ILIAS.

The Portuguese interface includes `/pendentes`, `/entregues`, `/encerradas`,
`/verificar`, `/materiais`, `/configuracoes` and `/relatar`. A material button discloses
transmission through Telegram and authorizes only that selected request. The report
flow produces a reviewed draft for manual sharing; it opens no public issue and
contacts no teacher or administrator.

The monitor and worker are separate processes. The monitor is suitable for an
external schedule such as every twelve hours; unchanged work does not repeatedly
notify unless reminders are configured. Retries are recorded per message/attachment,
and ambiguous network outcomes can produce duplicates. No cron job or service is
installed automatically.

The implementation has been tested offline with fake Telegram transports. Real
Telegram delivery, course-document transmission and worker/cron activation have
not been performed and remain separate authorization-dependent deployment steps.
Follow the [Telegram operations guide](docs/telegram.md) and
[deployment checklist](docs/deployment-checklist.md).

## Development status and verification

The collector, assignment classifier, support cache, scheduled monitor and private
bot are implemented. The reviewed offline suite contains **408 passing tests**:

```sh
.venv/bin/pytest -q
openspec validate --all --strict
```

Recorded local ILIAS checks used the software independently of MCP. A repeated
cache check reused all eleven selected support references without downloading new
body bytes. Three sequences and one blank assignment detail remain deliberately
inconclusive pending further evidence and user feedback. See
[live-check evidence](docs/live-check.md) and the
[implementation review](docs/reviews/2026-11-14-openspec-implementation.md).

Current behavior contracts live in [openspec/specs](openspec/specs/). The five
completed implementation changes are retained in the
[OpenSpec archive](openspec/changes/archive/). Product boundaries and accepted
trade-offs are recorded in [project decisions](docs/decisions.md).

## License

ILIAS-Check is licensed under [AGPL-3.0](LICENSE). Reused MIT-licensed authentication
utilities retain their notices and upstream provenance in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Course materials are separate user
data and are not covered by the software license.

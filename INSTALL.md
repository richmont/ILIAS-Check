# Installing and configuring ILIAS-Check with Telegram

**English** | [Português do Brasil](INSTALL.pt-BR.md) | [Deutsch](INSTALL.de.md)

This guide covers a complete Linux installation: preparing Python, configuring
ILIAS access, creating a bot, filling in credentials, testing, and keeping the
worker and monitor running.

**The examples contain no real credentials.** Replace every indicated value before
starting. Creating this guide does not run services, change cron, or send messages.
The activation steps below are actions you perform when you are ready to allow the
described access and sends.

## 1. Understand the two processes

| Process | What it does | When it runs |
| --- | --- | --- |
| `ilias-check bot` | Receives commands in the private chat and queries stored observations. A material request can start a fresh ILIAS check. | Continuously, as a worker. |
| `ilias-check monitor` | Checks ILIAS, updates state and sends enabled notifications. | Once per invocation; cron can run it every 12 hours. |

**Starting only the worker does not create a collection schedule.** Both processes
must use the same Linux account, the same configuration file and the same
state/cache directories. Do not run two workers for the same bot.

Prerequisites:

- Linux with Python **3.11 or newer**, `venv`, `pip` and Git.
- HTTPS access to ILIAS and to `api.telegram.org`; no public port or webhook is
  required.
- An authorized ILIAS account compatible with the implemented username/password
  login. Initial compatibility is with ILIAS 9.23; SSO/MFA and other layouts may
  require adaptation.
- A personal Telegram account. This software works with a **private chat** and a
  single authorized user, not with groups or channels.
- For continuous operation, a machine that stays powered on. The optional service
  in this guide uses user-level systemd; scheduling uses cron.

The installation uses this layout:

```text
/opt/ilias/
├── venv/   # Python virtual environment and executables
├── check/  # software checkout (main branch)
└── data/   # private configuration and runtime data
    ├── ilias.env
    ├── inventory.json
    ├── monitor/     # SQLite state
    ├── support/     # downloaded documents and manifest
    └── monitor.log
```

Data files are created in the corresponding steps. `data` stays outside the
`check` checkout. Use the same ordinary Linux account throughout installation and
operation; `sudo` is only needed to prepare `/opt/ilias` (and, optionally, linger).

## 2. Download and install the software

Check Python:

```sh
python3 --version
```

The result must be 3.11 or newer. On Debian/Ubuntu, install `git`, `python3`,
`python3-venv` and `python3-pip` if needed; check the version your distribution
provides.

For a **fresh installation**, prepare the directory for the current user. Run this
in a session of that ordinary user, not in a root shell:

```sh
sudo install -d -m 755 -o "$(id -un)" -g "$(id -gn)" /opt/ilias
git clone --branch main \
  https://github.com/richmont/ILIAS-Check.git /opt/ilias/check
python3 -m venv /opt/ilias/venv
cd /opt/ilias/check
/opt/ilias/venv/bin/python -m pip install -e '.[test]'
/opt/ilias/venv/bin/ilias-check --help
/opt/ilias/venv/bin/pytest -q
```

The implementation is already integrated into `main`. If you already have an
installation, keep your files and use the update section; do not clone over an
existing checkout, and do not change the owner of another user's installation.

Help must list `collect`, `classify`, `monitor` and `bot`. The tests are offline and
need no real credentials. You do not need to activate the venv in your shell: the
examples call the executables in `/opt/ilias/venv` directly.

## 3. Prepare the private files

Still in the project directory:

```sh
umask 077
install -d -m 700 "/opt/ilias/data"
install -d -m 700 "/opt/ilias/data/monitor"
install -d -m 700 "/opt/ilias/data/support"
```

For a **first installation**, copy the initial template:

```sh
install -m 600 examples/config/ilias-local.env.example \
  /opt/ilias/data/ilias.env
```

That last command replaces an existing file. If you already have a configuration,
edit it and compare the templates; do not copy over it. Open the file in your
preferred editor, for example:

```sh
nano /opt/ilias/data/ilias.env
```

There are two complete templates in the repository:

- [ilias-local.env.example](examples/config/ilias-local.env.example): preparation and
  first collection, with Telegram disabled.
- [ilias-telegram.env.example](examples/config/ilias-telegram.env.example): reference
  for the Telegram activation step, still without automatic attachments.

Use **one private file** `ilias.env` for normal operation. The templates are complete
alternatives, not files to load in sequence. `--env-file` accepts a single file and
does not search for other `.env` files automatically. Variables already defined in
the process environment take precedence over the file. Do not use
`source ilias.env`; the program reads the dotenv format directly.

## 4. Configure ILIAS before starting

Fill in this part of the private file:

```dotenv
# Example: replace the URL and every REPLACE value.
ILIAS_BASE_URL=https://ilias.example.edu
ILIAS_CLIENT_ID=REPLACE_CLIENT_ID
ILIAS_USER='REPLACE_ILIAS_USERNAME'
ILIAS_PASS='REPLACE_ILIAS_PASSWORD'
ILIAS_PENDING_ROOTS=1001,1002
ILIAS_TIMEZONE=Europe/Berlin

ILIAS_TIMEOUT_SECONDS=20
ILIAS_PENDING_MAX_DEPTH=12
ILIAS_PENDING_MAX_REQUESTS=500
ILIAS_PENDING_EXCLUDE_EXERCISES=
ILIAS_PENDING_ALTERNATIVE_SETS={}
ILIAS_PENDING_INCLUDE_CONTEXTUAL=false

ILIAS_PENDING_DOWNLOAD_SUPPORT=false
ILIAS_PENDING_OUTPUT_DIR=/opt/ilias/data/support
ILIAS_SUPPORT_MAX_FILE_BYTES=20971520
ILIAS_SUPPORT_MAX_RUN_BYTES=104857600
ILIAS_SUPPORT_REVALIDATE_HOURS=12
ILIAS_SUPPORT_CACHE_MAX_BYTES=200000000
ILIAS_SUPPORT_NO_DEADLINE_TTL_HOURS=168
ILIAS_SUPPORT_RETENTION_MAX_HOURS=

ILIAS_TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_USER_ID=
TELEGRAM_ALLOWED_USER_IDS=
ILIAS_TELEGRAM_SEND_DOCUMENTS=false
ILIAS_TELEGRAM_MAX_DOCUMENT_BYTES=20971520
ILIAS_TELEGRAM_MAX_MESSAGE_CHARS=4000
ILIAS_MONITOR_STATE_DIR=/opt/ilias/data/monitor
ILIAS_PENDING_REMINDER_HOURS=0
```

| Setting | How to fill it in |
| --- | --- |
| `ILIAS_BASE_URL` | HTTPS URL of the installation, including the subdirectory if any, without `login.php`, query string or session token. Example: `https://ilias.example.edu/ilias`. |
| `ILIAS_CLIENT_ID` | Installation identifier; it may appear as `client_id` in the login URL. It is not your username. Do not invent it if it is missing: confirm it with the installation. |
| `ILIAS_USER`, `ILIAS_PASS` | Authorized ILIAS username and password. Quotes help preserve spaces and `#`; follow dotenv syntax when using quotes inside the value. |
| `ILIAS_PENDING_ROOTS` | Real IDs of the folders/courses to inspect. In `goto.php?target=fold_1001`, the reference is `1001`; in a URL with `ref_id=1002`, it is `1002`. The numbers above are fictitious. |
| `ILIAS_TIMEZONE` | Installation timezone. For Bonn/Germany use `Europe/Berlin`, including daylight-saving rules. It does not depend on your computer's timezone. |

Keep the state and cache directories outside any Git checkout, without symbolic
components, with the correct owner and private permissions. The default cache quota
is **200 MB decimal**; the bot cannot change it.

Do not paste passwords/tokens into commands, issues, or screenshots. The credential
file stays on the host, not in Git. Check the permission without showing its
contents:

```sh
chmod 600 /opt/ilias/data/ilias.env
stat -c '%a %n' /opt/ilias/data/ilias.env
```

The result must start with `600`.

## 5. Create the Telegram bot and store the token

1. Open the official [BotFather](https://t.me/BotFather) in Telegram.
2. Send `/newbot`, choose a name and an available username ending in `bot`.
3. Copy the token provided by BotFather into `TELEGRAM_BOT_TOKEN` in your private
   file. Keep `ILIAS_TELEGRAM_ENABLED=false`.
4. Open the new bot's private chat and send `/start`. There will be no reply yet:
   the worker has not been started.

Example of the fields at this stage:

```dotenv
ILIAS_TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN='REPLACE_WITH_REAL_BOTFATHER_TOKEN'
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_USER_ID=
TELEGRAM_ALLOWED_USER_IDS=
ILIAS_TELEGRAM_SEND_DOCUMENTS=false
```

The creation and management procedure is in the
[official BotFather documentation](https://core.telegram.org/bots/features#botfather).
The token is a credential, not the bot's public username. If it is exposed, revoke
it in BotFather, replace the local value and restart the involved processes.

## 6. Obtain the IDs without starting the worker

You need two numeric IDs: the destination private chat and the allowed user. Use
your own bot's API; you do not need to give your data to a third-party bot.

With the worker still **stopped**, send `/start` again in the bot's private chat.
Run this snippet in the project directory. It reads the token from the private file,
keeps it out of shell history, and does not print message contents:

```sh
/opt/ilias/venv/bin/python - <<'PY'
from pathlib import Path
import requests
from ilias_check.config import load_environment

values = load_environment(Path('/opt/ilias/data/ilias.env'))
token = (values.get('TELEGRAM_BOT_TOKEN') or '').strip()
if not token or 'REPLACE' in token:
    raise SystemExit('Fill in TELEGRAM_BOT_TOKEN in the private file first.')

def api(method, payload):
    try:
        with requests.post(
            f'https://api.telegram.org/bot{token}/{method}',
            json=payload, timeout=(10, 35), allow_redirects=False,
        ) as response:
            status = response.status_code
            result = response.json()
    except Exception:
        raise SystemExit('Telegram query failed; token and response were omitted.') from None
    if status != 200 or not isinstance(result, dict) or not result.get('ok'):
        raise SystemExit(f'Telegram rejected the query (HTTP {status}). Check token, webhook and other workers.')
    return result['result']

if api('getWebhookInfo', {}).get('url'):
    raise SystemExit('A webhook is active. Use a dedicated bot or disable the previous integration before continuing.')
updates = api('getUpdates', {'timeout': 0, 'limit': 100, 'allowed_updates': ['message']})
seen = set()
for update in updates:
    message = update.get('message', {})
    chat = message.get('chat', {})
    sender = message.get('from', {})
    if chat.get('type') != 'private' or sender.get('is_bot'):
        continue
    pair = (chat.get('id'), sender.get('id'))
    if None in pair or pair in seen:
        continue
    seen.add(pair)
    print(f'TELEGRAM_CHAT_ID={pair[0]}')
    print(f'TELEGRAM_ALLOWED_USER_ID={pair[1]}')
if not seen:
    print('No private message found. Send /start to the bot and try again.')
PY
```

Copy the pair that belongs to **your own conversation** into the private file. Do not
use group/channel IDs or the bot's own ID. If more than one pair appears, confirm
which one is yours before configuring the allowed user.

The script sends no messages and does not advance the receive `offset`. Do not run
this query while another consumer is using `getUpdates`. Webhooks and long polling
are alternatives; for a reused bot, migrate the previous integration deliberately
before using this worker. References:
[getUpdates](https://core.telegram.org/bots/api#getupdates) and
[getWebhookInfo](https://core.telegram.org/bots/api#getwebhookinfo).

## 7. Test collection and record the first observation, without Telegram

Confirm that `ILIAS_TELEGRAM_ENABLED=false` and that the ILIAS fields are correct.
The commands in this step access ILIAS; none of them should send Telegram messages.

First, save a private inventory:

```sh
cd /opt/ilias/check
umask 077
/opt/ilias/venv/bin/ilias-check collect \
  --env-file /opt/ilias/data/ilias.env \
  --progress \
  > "/opt/ilias/data/inventory.json"
```

`--progress` (also accepted by `monitor`) prints throttled request/object counts,
current root and elapsed time to stderr. The JSON on stdout stays clean, and the
progress lines never include titles, URLs or credentials.

Then inspect inconclusive cases locally:

```sh
/opt/ilias/venv/bin/ilias-check classify \
  --env-file /opt/ilias/data/ilias.env \
  --input "/opt/ilias/data/inventory.json" \
  --select needs-verification
```

Exit code `2` means a partial result and can be expected for unresolved pages. It
does not necessarily mean login failure. Fix fatal errors before continuing; keep
uncertainties as uncertainties.

Now run the monitor **with Telegram still disabled**, to record observations in the
SQLite state shared with the worker:

```sh
/opt/ilias/venv/bin/ilias-check monitor \
  --env-file /opt/ilias/data/ilias.env
```

This may queue alerts, but it does not send them while Telegram is disabled.
**`collect` alone does not feed the bot's history, and `monitor --dry-run` does not
record those observations.** Do not skip the first normal monitor run.

## 8. Enable Telegram and validate the configuration before starting

In the **same private file**, replace the existing fields; do not add duplicate
lines or overwrite your ILIAS credentials with placeholders:

```dotenv
ILIAS_TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN='REPLACE_WITH_REAL_BOTFATHER_TOKEN'
TELEGRAM_CHAT_ID=REPLACE_NUMERIC_CHAT_ID
TELEGRAM_ALLOWED_USER_ID=REPLACE_NUMERIC_USER_ID
TELEGRAM_ALLOWED_USER_IDS=
ILIAS_TELEGRAM_SEND_DOCUMENTS=false
```

The [activation template](examples/config/ilias-telegram.env.example) shows the
complete file. The IDs must be positive integers without `@`, username or group
prefix. Keeping `ILIAS_TELEGRAM_SEND_DOCUMENTS=false` lets you start with text and
links only.

To let other Telegram accounts query the same observations, list their numeric IDs
in `TELEGRAM_ALLOWED_USER_IDS` separated by commas. Each one must open a private
chat with the bot from that account; commands sent to the primary chat are still
accepted only from `TELEGRAM_ALLOWED_USER_ID`. Notifications continue to go only to
`TELEGRAM_CHAT_ID`, and every allowed user sees the same ILIAS data, history and
retention settings.

Validate the configuration, **without network and without starting the worker**:

```sh
/opt/ilias/venv/bin/python - <<'PY'
from pathlib import Path
from ilias_check.config import CollectorConfig, ConfigurationError, load_environment
from ilias_check.cache_config import CacheError, boolean
from ilias_check.telegram import TelegramConfig

path = Path('/opt/ilias/data/ilias.env')
try:
    values = load_environment(path)
    required = ('ILIAS_BASE_URL', 'ILIAS_CLIENT_ID', 'ILIAS_USER', 'ILIAS_PASS',
                'ILIAS_PENDING_ROOTS')
    if any('REPLACE' in str(values.get(key, '')) for key in required):
        raise ConfigurationError('The configuration still contains REPLACE fields.')
    CollectorConfig.from_mapping(values)
    enabled = boolean(values, 'ILIAS_TELEGRAM_ENABLED')
    if enabled:
        telegram = ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'TELEGRAM_ALLOWED_USER_ID',
                    'TELEGRAM_ALLOWED_USER_IDS')
        if any('REPLACE' in str(values.get(key, '')) for key in telegram):
            raise ConfigurationError('The Telegram settings still contain REPLACE fields.')
        TelegramConfig.from_mapping(values, worker=True)
except (ConfigurationError, CacheError) as exc:
    raise SystemExit(f'Invalid configuration: {exc}') from None
print(f"Configuration valid (Telegram {'enabled' if enabled else 'disabled'}). No connection was made.")
PY
```

This validation checks the format, not the credentials, and does not prove that the
IDs belong to you. Confirm that identity before the real test. While
`ILIAS_TELEGRAM_ENABLED=false`, it validates only the ILIAS/collector settings; the
worker checks run once Telegram is enabled, so you can use the same block before this
step.

You can also simulate the monitor:

```sh
/opt/ilias/venv/bin/ilias-check monitor \
  --env-file /opt/ilias/data/ilias.env \
  --dry-run
```

It may access ILIAS and maintain the local cache according to the configuration, but
it does not call Telegram or mark notifications as delivered.

## 9. Run the bot for the first time

**This step enables real communication with Telegram.** With the data verified,
start the worker in the foreground:

```sh
/opt/ilias/venv/bin/ilias-check bot \
  --env-file /opt/ilias/data/ilias.env
```

Leave that terminal open. In the bot's private chat, send `/start` and `/pendentes`.
It should reply in Portuguese, with original ILIAS titles/instructions and observation
times. `/verificar` must preserve inconclusive cases. Do not read an empty list as
proof that all tasks are complete.

Initial commands:

| Command | Expected result |
| --- | --- |
| `/ajuda` | Help and navigation. |
| `/pendentes` | Confirmed pending uploads. |
| `/entregues` | Submission history; approval is not implied. |
| `/encerradas` | Closed without submission. |
| `/futuras` | Period not open yet. |
| `/verificar` | Inconclusive cases, source and feedback invitation. |
| `/resumo` | Count per situation and coverage warnings. |
| `/configuracoes` | Retention and cache usage/quota. |
| `/materiais` | Selectable materials; tapping one authorizes sending that copy through Telegram. |
| `/relatar` | Reviewable report about the software; no issue is opened automatically. |

Even with **automatic** attachments disabled, an explicit request in `/materiais`
can download and send the selected material. Do not tap that action if you do not
want to transmit documents yet. The bot does not download files you send in reply.

To test notifications, run this in **another terminal**:

```sh
cd /opt/ilias/check
/opt/ilias/venv/bin/ilias-check monitor \
  --env-file /opt/ilias/data/ilias.env
```

That run may send queued pending alerts — not necessarily a single message. Check the
recipient, links and coverage qualifications. Normal repetitions without changes must
not resend the same alerts; an ambiguous timeout can produce duplicates on a later
attempt.

If you want command suggestions in Telegram, use `/setcommands` in BotFather, select
your bot and send, for example:

```text
start - Start
ajuda - Help
pendentes - Pending tasks
entregues - Submission history
encerradas - Closed without submission
verificar - Inconclusive cases
materiais - Support materials
configuracoes - Retention and storage
relatar - Report a software problem
cancelar - Cancel dialog
```

That configures suggestions only; the software still enforces authorization. See
[Telegram commands](https://core.telegram.org/bots/features#commands).

When you finish the foreground test, press **Ctrl+C** to stop the worker before
starting the service in the next step.

Document buttons try the valid local cache first. If current activity evidence or
file validation is too old, or the copy is missing or invalid, the bot announces an
ILIAS check that can take several minutes before trying source retrieval.

## 10. Keep the worker running with user-level systemd

This step is optional for testing but useful on a host that stays powered on. Run it
as the same Linux user used for configuration and collection. Do not run the manual
worker and the service at the same time.

Create `~/.config/systemd/user/ilias-check-bot.service`:

```sh
mkdir -p "$HOME/.config/systemd/user"
nano "$HOME/.config/systemd/user/ilias-check-bot.service"
```

Complete contents:

```ini
[Unit]
Description=ILIAS-Check private Telegram worker
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
WorkingDirectory=/opt/ilias/check
ExecStart=/opt/ilias/venv/bin/ilias-check bot --env-file /opt/ilias/data/ilias.env
UMask=0077
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

The absolute paths follow the `/opt/ilias` layout. If you install elsewhere, adjust
`WorkingDirectory` and `ExecStart`. The program reads the `.env` through `--env-file`;
no additional `EnvironmentFile` is needed. Reference:
[systemd units and specifiers](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html#Specifiers).

Enable and check:

```sh
systemctl --user daemon-reload
systemctl --user enable --now ilias-check-bot.service
systemctl --user status ilias-check-bot.service
journalctl --user -u ilias-check-bot.service -n 50 --no-pager
```

The service should show `active (running)`. Also verify a real reply to `/ajuda`;
process state alone does not prove the chat works. For future `.env` changes, restart
the worker:

```sh
systemctl --user restart ilias-check-bot.service
```

To keep the user manager running after logout and start it at boot, an administrator
can enable *linger* for your account:

```sh
sudo loginctl enable-linger YOUR_LINUX_USER
```

Replace the placeholder with the real host user, not the Telegram username. This
option changes the account's startup behavior; use it only if you want this continuous
service. See [loginctl](https://www.freedesktop.org/software/systemd/man/latest/loginctl.html).
Without user-level systemd, keep the worker in the foreground or use your
environment's supervisor with the same executable, user and configuration file.

## 11. Schedule checks every 12 hours

The service above receives commands; periodic updates are the monitor's job. Cron must
be available and active on the host. Prepare a private log:

```sh
touch "/opt/ilias/data/monitor.log"
chmod 600 "/opt/ilias/data/monitor.log"
crontab -e
```

Add this line to the crontab of the same user that runs the worker:

```cron
0 */12 * * * /opt/ilias/venv/bin/ilias-check monitor --env-file /opt/ilias/data/ilias.env >> /opt/ilias/data/monitor.log 2>&1
```

Check it with:

```sh
crontab -l
```

The example runs at 00:00 and 12:00 in the scheduler/host timezone.
`ILIAS_TIMEZONE=Europe/Berlin` controls how ILIAS deadlines are interpreted; it does
not change the cron timezone. You do not need a shell with an activated venv: the line
uses the absolute executable.

The monitor prevents overlap for the same account/state. An invocation that finds the
previous run still active may exit with code `3`; do not start new workers to work
around the lock. Check the log and wait for the next run.

`ILIAS_PENDING_REMINDER_HOURS=0` disables repeated reminders: collecting every 12 hours
does not imply a message every 12 hours. For optional daily reminders, set
`ILIAS_PENDING_REMINDER_HOURS=24`; relevant changes can still generate alerts.

## 12. Enable materials only if you want them

There are three different controls:

| Goal | Setting/action |
| --- | --- |
| Text and link notifications | `ILIAS_TELEGRAM_ENABLED=true`, `ILIAS_TELEGRAM_SEND_DOCUMENTS=false`. |
| Automatic local cache of eligible support | `ILIAS_PENDING_DOWNLOAD_SUPPORT=true`. This alone does not authorize sending through Telegram. |
| Automatic attachment in notifications | `ILIAS_PENDING_DOWNLOAD_SUPPORT=true` and `ILIAS_TELEGRAM_SEND_DOCUMENTS=true`, after consenting to document transmission. |
| Sending one chosen material | Explicit download action in `/materiais`, without enabling future automatic attachments. |

For a local cache, edit the existing fields:

```dotenv
ILIAS_PENDING_DOWNLOAD_SUPPORT=true
ILIAS_PENDING_OUTPUT_DIR=/opt/ilias/data/support
ILIAS_TELEGRAM_SEND_DOCUMENTS=false
```

Only if you also want automatic attachments:

```dotenv
ILIAS_TELEGRAM_SEND_DOCUMENTS=true
```

Restart the worker after editing the file and run a manual check before trusting the
schedule. A notification that already completed is not necessarily resent just because
the attachment preference changed.

Default limits are 20 MiB per file, 100 MiB per run and 200 MB decimal in the cache.
Deadlines/confirmed submissions end associations; without a deadline, default retention
is 168 hours. The bot allows retention changes in `/configuracoes` but does not change
the quota or offer manual cleanup. Copies already received by Telegram cannot be
revoked by local cleanup. See [the cache lifecycle](docs/support-cache.md).

## 13. Stop, update or back up

To stop the worker and prevent automatic startup:

```sh
systemctl --user disable --now ilias-check-bot.service
```

Also remove/comment the monitor line in `crontab -e` if you want to stop scheduled
checks. Setting `ILIAS_TELEGRAM_ENABLED=false` affects new invocations; a worker
already running keeps the loaded configuration until it is stopped/restarted. None of
these actions submits answers or modifies activities in ILIAS.

Before updating the code or copying the SQLite database for backup, pause the worker
and the schedule and wait for a running collection to finish. Preserve the `.env`, the
state directory and their private permissions. Deleting state loses
history/deduplication and can generate initial alerts again. The cache is disposable,
not an official source.

With the processes stopped, update `main`. If the checkout is still on the old
development branch, the `switch` command below selects the integrated branch:

```sh
cd /opt/ilias/check
git fetch origin
git switch main
git pull --ff-only origin main
/opt/ilias/venv/bin/python -m pip install -e '.[test]'
/opt/ilias/venv/bin/pytest -q
```

If there are local changes or migration instructions in the new version, resolve them
before continuing. After checking the configuration, re-enable the worker and restore
the schedule you paused.

## Quick troubleshooting

| Symptom | What to check |
| --- | --- |
| The bot does not reply | Service/terminal active, `ILIAS_TELEGRAM_ENABLED=true`, token, IDs and private chat. Send a new command after restarting. |
| Empty ID query | Send `/start` to the correct bot; stop other consumers before repeating the query. |
| Telegram HTTP 401 | Wrong or revoked token; replace it with the current BotFather token. |
| Telegram HTTP 409/conflict | Another worker/`getUpdates` consumer or a webhook configuration. Do not run the ID query in parallel with the worker. |
| Telegram HTTP 403 | Bot blocked by the recipient or chat without access; check the private chat and start the conversation. |
| No data after installing | Run `monitor` once with the same `.env` and state; `collect` and `monitor --dry-run` do not feed the persistent queries. |
| Code `2` / inconclusive | Check coverage and `/verificar`; missing data does not prove submission or the absence of tasks. |
| ILIAS authentication error | Base URL, client ID, username/password and form compatibility; do not publish HTML or credentials to diagnose. |
| Private directory error | Owner, mode `0700`, path outside Git and absence of symlinks; managed files use `0600`. |
| `.env` value seems ignored | Variables exported in the process take precedence; the worker must be restarted after editing. Do not print the whole environment to investigate. |
| Material not sent | Consent, current classification, association, deadline/TTL, integrity, type, size and quota; use the original link if unavailable. |
| `systemctl --user` without bus | User session/manager unavailable in this environment; check the Linux session or use an appropriate supervisor. |

A completed installation means: credentials filled in and private, local collection
verified, correct owner/chat, a real command reply, monitor run with success or
understood partiality, and worker/schedule enabled only when desired. Also see
[Telegram operations](docs/telegram.md) and
[the deployment checklist](docs/deployment-checklist.md).

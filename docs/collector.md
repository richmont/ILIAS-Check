# Read-only collector setup

The collector targets authorized personal access to an ILIAS 9_23 installation.
It reads repository metadata only. It does not submit answers, change membership,
complete learning steps, or download document bodies. Ordinary page reads may be
recorded by ILIAS as access/view activity.

## Install

Requires Python 3.11 or newer.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/ilias-check --help
```

## Configure

Copy `.env.example` to a private location, then replace every placeholder:

```sh
install -m 600 .env.example "$HOME/.config/ilias-check/ilias.env"
```

Set `ILIAS_BASE_URL` to the HTTPS installation base URL and `ILIAS_CLIENT_ID`
to the client configured by that installation. Set `ILIAS_USER` and `ILIAS_PASS`
to credentials you are authorized to use. `ILIAS_PENDING_ROOTS` is a
comma-separated list of positive repository reference IDs. Duplicate IDs are
collected once; selected root scope is retained.

Optional limits:

| Variable | Default | Meaning |
| --- | ---: | --- |
| `ILIAS_TIMEOUT_SECONDS` | `20` | Finite timeout for each HTTP request |
| `ILIAS_PENDING_MAX_DEPTH` | `12` | Maximum descendant depth |
| `ILIAS_PENDING_MAX_REQUESTS` | `500` | Maximum requests per collection run |

The collector does not search for `.env` files. Select one explicitly:

```sh
.venv/bin/ilias-check collect \
  --env-file "$HOME/.config/ilias-check/ilias.env"
```

Values already in the process environment override the selected file. Running
from another directory does not change which file is loaded. Without
`--env-file`, configuration comes only from the process environment.

Do not place credentials in command-line arguments, source control, issue
reports, or shared logs. `.env` and dotenv variants are ignored by Git; the
placeholder-only `.env.example` remains trackable.

## Compatibility and privacy

The initial adapter was developed against ILIAS 9_23 and supported
login/repository layouts. The primary project target is the specific ILIAS
website connected through the MCP in this environment; compatibility with
other installations is useful but not required. Adaptations should be based on
the target website's observed behavior while preserving the read-only safety
boundaries below.
The login adapter selects the first form containing a password field (not an
earlier search form), carries named hidden inputs, resolves a relative form
action against the final login-page URL, and confirms success using an
authenticated dashboard marker. Some legacy forms include a named standard
authentication submit control; the adapter supplies that control only when it
exists. An expired session may trigger one reauthentication for a safe read.

An unsupported login page (for example, a search-only page caused by an invalid
client ID, a missing password form, or unrecognized username/password fields)
fails with a category-level diagnostic. The collector does not try another
form, echo server response bodies, print credentials/cookies/tokens, or keep
retrying rejected login attempts. A future unsupported layout should be added
as a synthetic fixture before support is claimed.

Unsupported forms or pages must produce a clear error or incomplete-coverage
warning; they must not be interpreted as an empty repository. Browser links may
require a normal ILIAS login. Exported links do not contain session cookies or
tokens. Collection metadata can still identify course objects, so keep output
private and do not commit real inventories or course documents.

Learning-sequence discovery is limited to passive content links and explicit
passive step metadata. See [sequence compatibility](sequence-compatibility.md);
unsupported steps remain visible as unresolved rather than being advanced.

This is an offline-first implementation milestone. A live compatibility check
requires separate authorization and is not performed by installation or tests.

# Design

## Context

See `proposal.md` for motivation. This repository has no application code. Earlier authorized investigation of ILIAS 9_23 demonstrated search-before-login forms, modern `goto.php/<type>/<id>` links, older query-target links, nested folders, and sequence steps without ordinary links. These observations are compatibility evidence, not a promise that every installation behaves identically.

The repository already contains an AGPL-3.0 license. No license change or upstream code import is part of this planning change.

## Goals / Non-Goals

**Goals:** A small, synchronous Python core, a reproducible CLI, and fixture-verifiable collection contracts.

**Non-Goals:** Browser automation, an MCP process, implicit local configuration discovery, and network crawling outside selected descendants.

## Decisions

### Standalone core with a narrow ILIAS adapter

Use a `src/ilias_check/` package with configuration, HTTP/authentication, parsing, inventory models, and CLI boundaries. Prefer `requests`, Beautiful Soup, `python-dotenv`, standard-library dataclasses, and pytest on Python 3.11+. Synchronous requests are sufficient for a personal 12-hour monitor and simplify budgets and session handling.

Alternative: call MCP tools as a subprocess. Rejected because it couples scheduling to a chat-oriented transport and exposes unnecessary mutation capabilities.

The user accepted minimal reuse: vendor only necessary, reviewed MIT authentication and useful URL/parsing helpers behind the read-only adapter, with upstream revision and original notices. Do not import the entire MCP package or mutation services. Record the need for each copied helper; extending copied scope requires an explicit justified need. Review exact functions and provenance before copying. An independent helper is appropriate where upstream semantics are unsuitable, not as a way to erase attribution.

No runtime AI, LLM, or translation provider is introduced. Preserve source titles, instructions, and filenames in their original language; later Portuguese UI labels belong to the bot, not the source text.

### Explicit configuration

Proposed settings:

| Setting | Meaning / default |
| --- | --- |
| `ILIAS_BASE_URL`, `ILIAS_CLIENT_ID` | Required installation and client |
| `ILIAS_USER`, `ILIAS_PASS` | Required credentials |
| `ILIAS_PENDING_ROOTS` | Required comma-separated positive reference IDs |
| `ILIAS_TIMEOUT_SECONDS` | Finite request timeout; default 20 |
| `ILIAS_PENDING_MAX_DEPTH` | Maximum descendant depth; default 12 |
| `ILIAS_PENDING_MAX_REQUESTS` | Per-run request budget including auth and retries; default 500 |

`ilias-check collect --env-file /absolute/path/.env` opts into dotenv loading. Process environment wins. No implicit search for `.env`; no institution-specific defaults. Validate HTTPS origin, URL credentials, query/fragment ambiguity, numeric limits, and roots before login.

### Safe navigation instead of following every link

Build edges only from recognized repository content blocks and explicit sequence metadata. Normalize modern and legacy reference routes; validate the origin before each redirect hop, resolving relative links against the current page. Keep stable object identity separate from paths so overlapping roots can share fetches without losing provenance. Stop descendant expansion at cycles and budgets.

Read document metadata without following file-body download routes. Recognize login expiry and retry a safe read once after reauthentication; cap transient read retries within the global budget and honor rate-limit instructions. Do not retry authentication rejection in a loop.

Known action categories are allowlisted. GET alone is not evidence of safety: membership and completion actions can also use GET. Do not request learner-step transitions just to discover contents.

Ordinary page reads/downloads can create platform access logs or implicit view records. Do not promise zero remote side effects; the boundary prohibits explicit submission, completion, enrollment, and mutation actions. Before implementing sequence classification, investigate whether passive metadata or independent exercise routes expose children; record unsupported cases rather than navigating progression actions.

### JSON as the integration boundary

Initial envelope: `schema_version`, `checked_at`, `scope`, `coverage`, `objects`, and `errors`. Objects contain installation-scoped ID, type, title, paths, safe URL, discovered document metadata, and sequence-resolution information. Later changes add optional `activities` and document cache fields; consumers must tolerate additive fields.

Coverage records per-root completeness, unresolved objects, and limit reasons. Errors contain category, affected root/object, and a redacted message, not raw responses. Use canonical token-free links in output, preserving enough object identity for the browser to open the activity after login. Sequence entry remains a distinctly typed fallback rather than a promised direct upload link.

CLI exit codes: `0` complete success, `2` partial result, `1` fatal/configuration failure. Always keep JSON on stdout and redacted diagnostics on stderr. No raw HTML/session persistence by default.

## Risks / Trade-offs

- [HTML changes] → Versioned parser fixtures; unsupported layouts produce warnings, not empty results.
- [Sequence navigation changes progress] → Only parse passive metadata; retain unresolved steps for manual access.
- [Broad personal data exposure] → Export selected-scope metadata only; fixtures are synthetic or thoroughly anonymized.
- [Undocumented upstream behavior] → Review helper semantics and regression-test rather than assuming the MCP is a complete client.
- [Budgets limit deep trees] → Preserve partial results and identify skipped scope.

## Migration Plan

Create packaging, tests, CLI, and placeholder configuration first; implement against fixtures without contacting ILIAS. Preserve attribution for any imported helper. A live compatibility smoke test requires separate user approval and must not save credentials or course content to Git. Rollback is removal of the local package; this milestone creates no remote changes or scheduled jobs.

## Open Questions

- Which additional ILIAS versions warrant dedicated fixtures after the initial 9_23 adapter? They are outside the MVP compatibility promise.

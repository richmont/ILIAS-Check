# Tasks

Depends on: none. Implement this change before the other three.

## 1. Package and configuration

- [x] 1.1 Create the Python 3.11+ package, CLI entry point, and test dependencies; verify editable installation and `ilias-check --help` in an isolated environment.
- [x] 1.2 Implement explicit dotenv/environment loading and validated roots, origin, timeouts, and budgets; verify precedence, unrelated working directory, missing values, duplicate roots, and invalid settings with unit tests.
- [x] 1.3 Add placeholder-only `.env.example`, setup/configuration documentation, and runtime/secret ignore rules; verify examples parse and dotenv variants are ignored without hiding the example.
- [x] 1.4 Review only necessary upstream authentication/utilities and preserve original MIT notices and revision in third-party documentation; verify each copied portion has a recorded need/provenance, no MCP runtime/mutation dependency, and no unjustified scope expansion.

## 2. Read-only ILIAS adapter

- [x] 2.1 Implement password-form selection, hidden fields, relative actions, login confirmation, and one-time expired-session recovery; verify fixtures for search-first, legacy, invalid-client, rejected-login, and expired-session pages.
- [x] 2.2 Add origin-checked redirects, action allowlists, timeouts, request accounting, and bounded transient retries; verify forbidden actions and off-origin credential/redirect attempts never reach the fake transport.
- [x] 2.3 Document supported ILIAS 9_23 login behavior and unsupported-layout errors; verify diagnostics contain no synthetic password, cookie, or token values.

## 3. Discovery and inventory contract

- [x] 3.1 Implement content-scoped modern/legacy link normalization and bounded graph traversal; verify cycles, overlapping roots, multiple paths, breadcrumb exclusion, and budget exhaustion with fixtures.
- [x] 3.2 Inventory sequence metadata and document references without step transitions or file-body downloads; verify unresolved steps remain visible and recorded requests are read-only.
- [x] 3.3 Implement the versioned inventory envelope, per-root coverage, canonical URLs, and structured errors; validate complete, empty, partial, and failed results against a checked-in JSON Schema.
- [x] 3.4 Document inventory fields, compatibility limits, and metadata privacy; verify synthetic example JSON validates without real course identifiers or content.
- [x] 3.5 Preserve original source language and token-free activity/sequence links; verify German fixtures are not translated, no AI/service dependency exists, and link tests permit browser login without sharing sessions.
- [x] 3.6 Investigate passive sequence-child discovery against available fixtures/documented routes and record results; verify no progression action is used and document that ordinary reads can create platform access records.

## 4. CLI integration

- [x] 4.1 Wire `collect --env-file` with JSON-only stdout, redacted stderr, and exit codes 0/2/1; verify end-to-end CLI tests for successful, partial, and fatal mocked runs.
- [x] 4.2 Run the complete offline suite and packaging checks; verify no test requires live credentials or network access and no sensitive runtime artifacts appear in Git status.

## Workflow follow-up

- Review the collector contract before starting `add-pending-assignment-classification`.
- Perform any live smoke test only after explicit authorization; archive this change only after implementation and verification.

## Review and closure — 2026-11-14

Implementation and regression evidence were reviewed before archival. See
`docs/reviews/2026-11-14-openspec-implementation.md` for the cross-feature review
and corrections. All 408 offline tests pass. Capability deltas are synchronized
into the main specifications; no implementation task remains unchecked.

Live Telegram tests, document transmission and worker/cron activation remain
separate authorization-dependent operations, tracked in
`docs/deployment-checklist.md`. Archival does not perform or authorize them.

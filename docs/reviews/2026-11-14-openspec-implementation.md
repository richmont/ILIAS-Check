# Implementation and archive review — 2026-11-14

The five implementation changes were reviewed against their proposals, capability
requirements, completed task lists, current code, offline regressions and recorded
local ILIAS checks. Their 82 tracked tasks are complete. No implementation blocker
remains within the reviewed scope after the corrections below. This review does not
claim live Telegram compatibility or authorize deployment.

## Scope and evidence

| Change | Tasks | Implementation / evidence |
| --- | ---: | --- |
| `add-read-only-collector` | 15/15 | Configuration, authentication, safe transport, scoped traversal and inventory/schema; auth/config/transport/traversal/CLI fixtures and recorded target reads |
| `add-pending-assignment-classification` | 13/13 | Per-unit classifier, personal/team applicability, policy/deadlines and offline reclassification; classification/policy/time/inventory regressions |
| `add-support-document-cache` | 17/17 | Provenance, conservative selection, private storage, atomic bounded copies and delivery gate; support material/cache tests, quota/rotation/retention scenarios and two recorded real local scans |
| `add-scheduled-telegram-monitor` | 16/16 | Private SQLite observations/outbox, transitions, retries, dry run and independent maintenance; fake outbound/recovery/overlap/migration tests and recorded collector-backed dry run |
| `add-interactive-telegram-bot` | 21/21 | Owner/chat authorization, cursors, queries/history, settings, selected-material consent and reviewed reports; offline polling/callback/replay/preferences/download/report tests |

Evidence is recorded in `docs/live-check.md`, `tests/test_support_cache.py`,
`tests/test_monitor_bot.py` and the collector/classification regression modules.
Real scans used the local software rather than the ILIAS MCP. They retained 425
objects and the known classifications, cached eleven selected support references,
and reused all eleven with zero newly downloaded body bytes on the second run.
No real Telegram message or document was sent.

## Review findings resolved

1. A deadline/support-generation change could enqueue both a change notification
   and a reminder derived from the previous acknowledgment. Reminder timing now
   belongs to the current generation, so one change produces one actionable event.
2. A prior pending activity missing from an otherwise complete new scan was marked
   stale in state but omitted from the incomplete qualifier of a different pending
   message. Dispatch now uses observation completeness as well as source coverage.
3. Qualified health notices and failed interactive material requests lacked source
   navigation. They now retain safe original activity/sequence buttons; health
   candidates are bounded and deduplicated by activity identity.
4. A prefetched dispatch batch could continue sending after the evidence aged out
   during an earlier send. Each component now rechecks current generation/state,
   backoff and the fifteen-minute freshness window immediately before dispatch.
   Uncertainty remains recorded for ambiguous health-message outcomes.
5. Actionable messages omitted the concrete classification reason, and contextual
   support/state labels were not explicit Portuguese UI. These labels now explain
   the evidence and contextual association while preserving source text.
6. OpenSpec context still described an empty repository. It now reflects implemented
   capabilities and the unchanged live-activation boundaries.

Six new regression tests cover these behavior corrections. The complete offline
suite passes **408 tests**. The five changes and all twelve main specifications pass
strict OpenSpec validation after synchronization. Requirement and scenario content
is preserved when promoting the eleven new capability deltas; the existing
`repository-reference-resolution` specification is unchanged.

## Closure and remaining operational work

The five changes use the `spec-driven` schema and are archived under
`openspec/changes/archive/2026-11-14-<change-name>/`. Their eleven capability deltas
are synchronized into `openspec/specs/` with canonical main-spec headings and their
original Purpose sections. Review closure does not require activating a bot.

The known three unresolved sequences and one blank assignment detail remain
inconclusive by the user's decision. Future feedback does not itself establish
submission, completion or non-applicability. Telegram credentials/owner setup,
real text/document tests and worker/cron activation remain explicit operational
follow-up in [the deployment checklist](../deployment-checklist.md).

No raw HTML, credentials, private manifests or real course documents are included
in this review or the archived planning artifacts. AGPL and upstream MIT notices
remain intact. No live network operation was needed for this review.

## Final verification

- `openspec list --json`: zero active changes.
- `openspec validate --all --strict --json`: all twelve main specs valid, no issues.
- `openspec doctor --json`: healthy planning root and no relationship warnings.
- Archive/main-spec comparison: eleven new specs preserve 67 requirements and 110 scenarios, with original Purpose sections; the preexisting spec is byte-for-byte unchanged.
- Offline regression suite: 408 passed; Python sources parse with the Python 3.11 grammar.
- Wheel built successfully with the reviewed implementation.
- Review/documentation links and `git diff --check` pass; no known configured password/token or runtime document/database assets appear in Git candidates.

The review/archive changes are recorded together with the refreshed project overview in a follow-up commit.

# Design

## Context

Depends on `add-read-only-collector`; no classifier exists yet. Earlier observations confirmed multiple units in an exercise, both text and file types, historical closed exercises hidden from the default current view, and group alternatives. Some sequences expose only titles and instructions, not safely accessible delivery metadata.

These observations justify conservative defaults. They do not establish that every visible group task belongs to the configured learner.

## Goals / Non-Goals

**Goals:** A pure, explainable classification layer fed by typed adapter observations and testable with a fixed clock.

**Non-Goals:** Semantic certainty from titles, automatically opening learner steps, inferring approval from upload presence, and automatic resubmission decisions.

## Decisions

### Separate observation from classification

Extend the adapter with safe exercise overview, all-units, instruction, and submission-list reads. Preserve structured evidence: delivery type, explicit acceptance, submission scope, deadline text, requirement flag, and provenance. Resolve sequence children only through passive metadata; missing metadata stays unresolved.

The classifier receives observations plus explicit settings and a clock, with no HTTP or filesystem calls. Alternative: decide pending status directly in HTML parsing. Rejected because it makes ambiguity handling and temporal tests fragile.

### Stable per-unit identity

Use normalized installation origin, client ID, configured account identity, exercise reference ID, and assignment ID for downstream identity. Preserve every inventory path. An exercise-level or sequence-level candidate without an assignment ID remains unresolved and cannot receive a definitive pending status.

Add `activities` to the JSON envelope with `submission_type`, `applicability`, `status`, `reason_codes`, `evidence`, `deadline`, `submission_url`, and `url_kind`. Existing collection fields remain unchanged. `url_kind` distinguishes `assignment`, `exercise`, and `sequence_entry`.

Add submission-history metadata: source submission time, attachment presence/count when known, personal/team scope, and explicit evaluation/completion evidence. Do not retrieve answer bodies. Unknown values remain null/unknown; `submitted` does not assert that the learner personally uploaded a team file or that the teacher approved it.

### Explicit state decision order

1. Unsupported or confirmed non-file delivery: `unknown` or `excluded`, respectively.
2. Explicit exclusion or confirmed non-applicability: `excluded`.
3. Unknown applicability: `unknown`.
4. Applicable personal/team submission confirmed: `submitted`, regardless of grade.
5. No submission confirmed and platform explicitly closed: `closed_without_submission`.
6. No submission confirmed and platform explicitly not open yet: `not_yet_open`.
7. No submission confirmed and current acceptance confirmed: `pending`.
8. Otherwise: `unknown`.

Record conflicting evidence and prefer uncertainty when it cannot be reconciled. Parse dates with `zoneinfo` using `ILIAS_TIMEZONE` (required for local timestamps); never assume the host timezone. If the displayed deadline passed but platform acceptance remains explicit, retain `pending` with an overdue flag. Unparseable deadlines alone need not invalidate explicit current acceptance.

### Group selection is explicit, not title-driven

Add `ILIAS_PENDING_EXCLUDE_EXERCISES` and an explicit alternative-set mapping, proposed as JSON in `ILIAS_PENDING_ALTERNATIVE_SETS`: each named set declares member exercise IDs and selected member IDs. Selection excludes only unselected members of that set, never unrelated/new individual activities. Exclusions win, with warnings on conflicts. Reject selections outside declared members and conflicting overlapping sets. References use IDs, not titles; there is no global include allowlist.

For alternatives whose assignment applicability cannot be confirmed, require explicit selection or platform ownership evidence. A group-looking title triggers caution, not ownership. Use explicit platform context for alternative sets when available; otherwise retain unknown applicability. Do not change memberships.

Team submission evidence must identify the learner's current team and delivery scope. A generic file list or another team's submission is insufficient.

### Preserve full results, filter reminders later

Export every discovered unit with its state, including excluded and historical work. Consumers select confirmed `pending` units for reminders. Unknown candidates contribute partial classification coverage; a sequence instruction alone proves an upload requirement, not the current delivery state.

Preserve practice/self-test descriptions and requirement flags as source evidence rather than obligation claims. Pending is the primary view; submitted, closed-without-submission, and needs-verification views remain separately available to later bot commands. Original titles/instructions remain untranslated.

## Risks / Trade-offs

- [False negatives from cautious classification] → Surface unknown work and manual links prominently rather than silently suppressing it.
- [Historical instructions and configured requirement flags disagree] → Keep evidence separate from curriculum-obligation claims.
- [Different team layouts] → Support only fixture-backed forms and flag unrecognized layouts.
- [DST ambiguity] → Preserve raw timestamps and report unresolved instants unless explicit platform acceptance suffices.

## Migration Plan

Apply after collector contracts exist. Add parsers and table-driven tests first, then expose additive JSON fields and CLI filtering/documentation. No stored-state migration is required at this stage. Rollback leaves the collector available but removes pending-work assertions.

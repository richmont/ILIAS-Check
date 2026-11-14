# Proposal

## Why

A visible exercise is not necessarily pending work: it may already be submitted, belong to another group, use text rather than file delivery, or be closed. Reliable classification prevents both missed assignments and misleading alerts.

## What Changes

- Evaluate each assignment unit independently, including exercises embedded in learning sequences.
- Add evidence-backed states for pending, submitted, closed without submission, not-yet-open, excluded, and unknown work.
- Resolve personal versus team submissions, explicit group selection, availability, and timezone-aware deadlines.
- Preserve manual delivery URLs and mark sequence-entry links distinctly when direct delivery cannot be resolved safely.
- Extend inventory JSON additively with classification evidence and uncertainty.
- Export personal/team submission-history metadata without downloading learner answers or equating submission with completion.
- Keep unknown and historical work available for separate bot queries.
- Dependency: `add-read-only-collector`.
- Non-goals: grading predictions, automatic submission, guessed group membership, document downloading, and notifications.

## Capabilities

### New Capabilities

- `assignment-status`: Per-unit file-delivery classification and evidence.
- `assignment-applicability`: Account, team, and explicit group applicability.

### Modified Capabilities

None. This proposal consumes the collector contract without changing its discovery requirements.

## Impact

Adds assignment parsers, a deterministic classifier, configuration for group allowlists and timezone, and regression fixtures. HTML adaptation is expected: the upstream exercise parser cannot be assumed to cover every ILIAS 9_23 layout.

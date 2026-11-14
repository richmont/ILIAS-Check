# Learning-sequence discovery boundary

## Initial offline investigation

The repository contains synthetic HTML fixtures only; it has no captured,
anonymized ILIAS sequence pages or documented installation-specific step API.
No live ILIAS request was made for this implementation. Therefore this result
describes supported passive evidence, not a claim that every ILIAS 9_23 sequence
layout is understood.

A subsequent authorized live test using the checker directly identified the
installation's `lso` type and a read page containing `.ilLSOLearnerView`
workflow entries. The parser now preserves their original step titles,
descriptions, availability and progress states in `sequence_outline`. In the
observed layout the controls point to `#`; there are no passive child-reference
IDs to resolve. These sequences remain explicitly unresolved for activity
classification. The checker does not enter the player, change steps, or infer
delivery from the outline. See [live check results](live-check.md).

The parser can discover a sequence child only when the read page exposes one of:

- a recognized same-origin object link inside a repository/content region; or
- explicit passive metadata (`data-sequence-step` plus `data-ref-id` and an
  object type, or `data-step-ref-id` plus an object type).

Recognized child links are canonicalized to session-free object URLs. Links with
action parameters such as `cmd=next`, `step`, `complete`, or `submit` are
discarded; they are not a discovery mechanism. The collector never clicks a
progression control, submits an answer, or attempts to complete a learning step.

The synthetic fixtures cover a sequence with passive step metadata, a sequence
with no exposed steps, and a progress-transition link that must be ignored.
Tests confirm the first is represented as a resolved step and the second as an
unresolved sequence with `sequence_steps: []`, a warning, and incomplete root
coverage. Its sequence-entry URL remains available for normal manual browser
access.

If a future authorized, anonymized fixture demonstrates a safe passive route,
add that route and regression tests before expanding discovery. A live smoke test
requires separate authorization. Until then, do not infer that an unreadable
sequence is empty.

## Read-only side effects

Collection uses ordinary same-origin HTTP GETs for metadata and one login POST
for authentication. It does not issue step-transition requests. Ordinary ILIAS
reads may still create access logs or implicit view records; “read-only” does
not promise invisible access.

# Assignment classification

`ilias_check.classification.classify_assignment` classifies one typed assignment
observation without HTTP, filesystem, environment, or clock access. Inventory
serialization now adapts the collector's unit evidence and calls it for each
assignment. Results appear in `activities`; `classification` contains full-run
counts, completeness, warnings, and the conservative `all_clear` flag.

The caller provides current `SubmissionEvidence`, scoped to the same assignment.
`present=False` means a supported parser explicitly confirmed an empty delivery
list. Missing lists remain `None`. Personal scope refers to the configured learner;
team scope additionally requires `learner_team_confirmed=True`. Another team's
files, generic file lists, and unknown team membership cannot establish delivery.
History entries describe past deliveries and are preserved without establishing
the current submission state. Approval and completion never substitute for it.

Decisions use this precedence:

1. Explicit exclusion or confirmed non-applicability produces `excluded`.
2. Contradictory evidence produces `unknown`. Adapters must flag conflicting
   ownership, availability, or delivery signals explicitly.
3. Confirmed text/other delivery produces `excluded`; unknown delivery stays unknown.
4. File units require an assignment ID and confirmed applicability.
5. A current personal submission, or a confirmed learner-team submission,
   produces `submitted`, including when the platform is now closed.
6. With confirmed absence of submission, explicit platform availability determines
   `closed_without_submission`, `not_yet_open`, or `pending`.
7. Missing submission scope, team identity, submission presence, or availability
   produces `unknown`, with a specific reason code.

Each result contains a fresh evidence dictionary recording `submission_present`,
`submission_scope`, `learner_team_confirmed`, `explicitly_excluded`, and
`contradictory_evidence`. Original evidence, source links, paths, titles, deadlines,
and submission history remain intact. Status and classification reason codes are
recomputed, so earlier decisions do not become new evidence. `submitted` does not
assert approval, completion, or that the learner personally uploaded a team file.

Titles, practice descriptions, historical cohort references, and requirement
metadata do not establish ownership or curriculum obligation. Explicit acceptance
can support pending work despite an old or unreadable deadline. Dates alone
never close an assignment.

## Commands and categories

```sh
.venv/bin/ilias-check collect --env-file /private/path/ilias.env --select pending
.venv/bin/ilias-check classify --input /private/path/inventory.json --select needs-verification
.venv/bin/ilias-check classify --input /private/path/inventory.json --select submitted
.venv/bin/ilias-check classify --input /private/path/inventory.json --select closed-without-submission
```

Both commands accept `all` (default), `pending`, `submitted`,
`closed-without-submission`, `needs-verification`, `not-yet-open`, and `excluded`.
Needs-verification selects the `unknown` activity state. Filtering changes only
`activities`, `classification.selection`, and `classification.returned_count`.
It preserves raw objects, coverage, full-run counts, and warnings. An empty
pending view is not an all-clear when a sequence or assignment remains unknown.

The offline `classify` command requires neither credentials nor HTTP access.
It uses the snapshot's `checked_at`, so its results describe that recorded
observation, not a fresh check. It optionally accepts `--env-file` for the policy
settings below; process environment values override the explicit file.
Reclassification starts from raw `objects`, so filtering an earlier classified
export does not lose other categories. Old snapshots missing scope evidence
remain unknown rather than receiving guessed ownership.

Exit codes are 0 for complete collection and classification, 2 for partial
results, and 1 for invalid input/configuration or failure to read every root.
Readable but incomplete roots remain partial even when none is fully complete.

## Scope evidence and configured choices

The adapter recognizes personal file delivery from the explicit platform `Type`
property and a successfully read personal delivery context. A team control
establishes team scope; the current learner's validated team-members route must
also expose a recognized nonempty team before its delivery can be classified.
A generic file list, another team's evidence, or a title alone does not suffice.
Current file lists establish submission presence; grading labels and old
submission-history entries do not replace them. No approval or completion is
inferred from a delivered file. Empty detail panels remain unknown.

Current acceptance requires a supported, enabled upload-form control on the
validated delivery page for exactly this exercise and assignment. The checker
inspects that control as evidence and never follows it. A list without such a
control does not by itself prove the activity is accepting submissions.

Set `ILIAS_PENDING_EXCLUDE_EXERCISES` to comma-separated exercise IDs. Declare
alternative sets explicitly through `ILIAS_PENDING_ALTERNATIVE_SETS`, for example:

```dotenv
ILIAS_PENDING_EXCLUDE_EXERCISES=3001
ILIAS_PENDING_ALTERNATIVE_SETS='{"synthetic-group":{"members":["2001","2002"],"selected":["2001"]}}'
```

Selection applies only inside declared sets; unrelated and new individual work
remains eligible. Explicit exclusions and known platform non-applicability win.
Selecting and excluding the same exercise produces a visible configuration
warning and an excluded result. Malformed IDs, unknown selected members,
duplicate IDs/keys, and overlapping sets are rejected before collection.
User selections do not establish an unknown team identity or change membership.

## Dates, source descriptions, and coverage

Set `ILIAS_TIMEZONE` to the installation's IANA zone (for example,
`Europe/Berlin` if that is its configured zone). No host-timezone fallback is
used. Supported dates include numeric/German long-form timestamps and ISO
timestamps with explicit offsets. Missing timezone, missing time, invalid
dates, and DST ambiguity/nonexistence retain the source string and an explicit
`evidence.deadline_resolution`, with an unknown absolute instant. Explicit
acceptance can still support pending work. `overdue` compares a resolvable
deadline against the recorded observation time; it does not close the unit.
Unresolved deadline categories also appear in `classification.warnings`; they
do not invalidate a state already established by explicit platform evidence.

Original per-unit instructions and requirement descriptions are retained as
`instructions` and `requirement_text`. Optionality, practice descriptions, and
historical cohorts do not become claims about curriculum obligation. General
exercise instructions are not copied onto a known unit whose own instructions
are missing. Raw object context remains available separately.

One unresolved sequence produces one needs-verification candidate with its
original sequence-entry link; a readable exercise without unit identity also
remains unknown. Every candidate preserves source paths and reason codes.
Repeated paths to the same unit are merged, while conflicting observations of
that identity remain unknown. Confirmed pending siblings remain visible even
when another unit is submitted or unresolved. `all_clear` can be true only if
collection and classification are complete and no pending activity exists.

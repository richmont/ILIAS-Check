# Local checker live verification

The user authorized a live test using the local software, without the ILIAS MCP.
The test ran `.venv/bin/ilias-check collect --env-file <local-config>` against
the three configured roots. Credentials and configuration were not printed or
modified. The configured limits were retained: 500 HTTP requests, depth 12,
and a 20-second per-request timeout. The test runner imposed a ten-minute
execution limit. No answer files or course-document bodies were downloaded.

## Findings and corrections

The initial run produced schema-valid JSON and discovered 441 objects, but
all 13 exercises failed during their landing-page read. A targeted diagnostic
using the checker's own authentication and transport identified a legitimate
`ilExerciseHandlerGUI` / `ilObjExerciseGUI` / `showOverview` redirect that the
read allowlist rejected.

The targeted exercise read then exposed two more installation-specific details:

- Submission-screen links retain `mode=all&from_overview=1`, including on the
  exercise-handler route. The validated passive route now preserves them.
- An empty delivery list is rendered inside an `ilExSubmissionFileGUI` form
  as a table with `td.ilCenter` containing `Keine Einträge`. The parser now
  recognizes that explicit empty state while leaving unknown pages unknown.

These corrections have synthetic regression tests. The offline suite passes
195 tests at that stage. A separate targeted learning-module read identified a
rejected `ilLMPresentationGUI` / `resume` redirect. The subsequent corrections
and current validation are recorded below.

## Earlier full CLI run after exercise-read corrections

The final run completed in 177.2 seconds, produced schema-valid JSON, and exited
with code 1 because none of the three roots had complete coverage. The CLI
still exported the successfully read objects and assignment metadata.

- 441 discovered objects: 13 exercises, 282 document references, 108 folders,
  nine learning modules, three unsupported objects, and 26 unresolved references.
- All 13 exercises yielded assignment metadata: 14 units in total, comprising
  13 file-upload units and one text unit.
- Ten submission lists were recognized, all explicitly empty.
- Three file units did not expose a safe submission-screen link and retain
  `submission_screen_not_exposed`; their submission state is not established.
- No team list was recognized or validated live. Absence of team metadata does
  not establish that an assignment is personal or that a team has no members.
- The nine learning modules still had object-read failures. The targeted sample
  above establishes one cause, not independent verification of every module.
- Unresolved references and unsupported object types remain coverage warnings.

These results establish successful real authentication, exercise overview reads,
per-unit metadata parsing, and supported empty submission-list reads. They do
not establish full repository coverage, nonempty delivery/team parsing on this
installation, or complete equivalence with the MCP. No MCP session was used in
either the full scans or the targeted diagnostics.

## Current verification after remaining-parser corrections

The user requested correction of the remaining modules, references, and units.
The checker now supports the module's strictly validated `resume` landing
route, identifies legacy test pages from their own `#headerimage` icon,
recognizes the `lso` sequence type, and reuses resolved aliases rather than
recreating generic duplicate records. It retains the visible sequence workflow
outline without making up missing child IDs. For file units without a delivery
screen it follows their own source presentation link and recognizes an explicit
no-file message in the `Einreichung` subpanel. A blank panel remains unknown.
No player, start/next/finish, answer-download, or submission action was used.

The current full local CLI run completed in 189.0 seconds with schema-valid
JSON and exit code 2 (partial coverage). The 220 offline tests passed.

- Zero object-read errors and zero duplicate reference identities.
- All nine learning modules were read successfully.
- No objects remain typed as generic unresolved or unsupported references.
- 425 unique objects: 13 exercises, 282 document references, 108 folders,
  nine learning modules, three learning sequences, and ten tests.
- All 13 exercises still yield 14 assignment units: 13 file-upload units and
  one text unit. Twelve delivery lists are recognized, including two explicitly
  empty delivery histories obtained from their source detail panels.
- One file unit returns a blank source detail panel; its delivery remains
  unknown with `assignment_detail_unavailable`. A blank panel does not establish
  non-applicability, an empty delivery, or successful submission.
- The three sequences expose 13 workflow outline entries in total. Their child
  reference IDs and passive object links are not exposed, so their activity
  resolution remains incomplete.
- Root completeness in configured order is `false`, `false`, `true`. The only
  remaining root warning categories are `unresolved_learning_sequence` and
  `exercise_assignment_metadata_partial`; they describe missing source evidence,
  not failed HTTP reads or malformed generic object identities.

This run used only the local checker and authorized ILIAS account, without the
MCP. It validates the reported layouts and resources, not complete equivalence
with every MCP capability. Remaining uncertainty is preserved in the inventory
instead of claiming all pending work has been evaluated.

A subsequent authenticated browser investigation inspected JavaScript and
loaded requests for these remaining cases. It found no additional passive data
source; the three sequence workflows still expose placeholder controls and
the assignment still renders an empty panel. See
[browser investigation](browser-investigation.md) for the scope and evidence.

## Classification integration verification

The subsequent classification integration was validated with 286 offline tests
and a fresh full local CLI collection, without the MCP. This collection completed
in 192.7 seconds, retained 425 objects with zero read errors, and generated
schema-valid classified output. Its category counts are:

- Ten pending file units, supported by an explicit personal delivery context,
  recognized empty delivery list, and enabled exact upload-form control.
- Two closed file units with explicit no-delivery evidence.
- One text unit excluded from file-upload reminders.
- Four needs-verification candidates: the three unresolved sequences and the
  file unit whose source detail panel is unavailable.
- No confirmed submitted or not-yet-open units in this observation.

The command returns exit code 2 and `classification.all_clear: false`. The
existing configuration does not specify an installation timezone, so two local
deadlines retain unknown absolute instants and the output warns
`installation_timezone_missing`. Their source closed/no-delivery evidence can
still establish their activity state. The checker did not guess a timezone or
modify the user's configuration.

The offline CLI was additionally exercised for all, pending, submitted,
closed-without-submission, and needs-verification views against the new snapshot.
All views validate against the JSON Schema and preserve the full-run counts,
coverage, and false all-clear flag, including the empty submitted view. Older
snapshots without delivery-scope evidence remain conservatively unknown.

The latest classified artifact is `inventory-classified.json`; the fresh source
scan is `inventory-classified-live.json`. Filtered private artifacts are
`activities-pending.json`, `activities-submitted.json`, `activities-closed.json`,
and `activities-needs-verification.json`. All remain outside the repository in
the private directory described below. The offline reclassification does not
perform HTTP requests or refresh the observation timestamp.

## Support-association metadata verification

The first support-material milestone adds metadata associations, not file
caching or Telegram delivery. It was verified with 332 offline tests and a
fresh local CLI collection using the configured account, without the ILIAS MCP.
The scan completed in 201.0 seconds with schema-valid JSON and zero object-read
errors. No document-body route was requested by the association feature.

Activity counts remain ten pending, two closed without submission, one text
unit excluded, and four needs-verification candidates. The same inconclusive
sequence/blank-detail states are preserved for later user feedback.

The scan exported 23 material references: 13 support references, one labeled
model answer, and nine unresolved sequence-document titles. Fourteen source
identities are known; the nine sequence references retain null identities and
download URLs. Eleven support references on confirmed pending units are selected
as metadata candidates for the future cache. The model answer is not selected.
Real source pages exposed attachments; explicit instruction-link extraction and
contextual opt-in were validated with synthetic fixtures rather than claimed
as observed live cases.

Two unit detail panels did not expose useful material metadata; their support
warnings do not change the independently established activity states. The three
sequences retain their metadata-only material warnings. Generic same-folder
association remains disabled in the actual configuration. No configuration,
membership, delivery, or learner progression state was changed.

The private full artifact is `inventory-support-associations.json`. The
`activities-pending-support.json` view contains the ten pending activities and
their eleven selected metadata candidates, retains partial coverage and the
full-run counts, and validates against the same schema. No cache files or real
course documents were added to the repository. Local file-cache implementation
remains the next milestone.

## Private artifacts

Raw inventories, HTML used for targeted local diagnosis, and CLI diagnostics
are stored only in `/tmp/ilias-check-live-ivaamkqy/`, outside the repository.
The directory has mode `0700`; its files have mode `0600`. The latest inventory
is `inventory-corrected.json`; `inventory-final.json` retains the earlier run.
These temporary artifacts contain private account
metadata and are not tracked by Git. This report contains aggregate results
only, without real root IDs, titles, names, credentials, or course materials.

## Opt-in private cache and monitor dry run (2026-11-14)

Two further checks ran through the local Python software, without the ILIAS MCP.
The first used a temporary opt-in outside the checkout; persistent `.env` settings
were not changed. It completed in 206.8 seconds, read 425 objects, kept zero object
read errors and the same classifications: 10 pending, 2 closed without submission,
1 excluded and 4 inconclusive. Eleven selected references were cached successfully:
11290123 downloaded bytes, 11303420 total managed bytes including manifest, below
the host's 200000000-byte quota. Answer/solution and unresolved materials were not
fetched. Runtime files remained outside Git with private directory/file permissions.

The second was a real collector run inside monitor `--dry-run`, with Telegram
disabled. It completed in 198.1 seconds, reused all eleven references and downloaded
**zero additional body bytes**. It planned 11 notification components in an ephemeral
database copy (10 pending plus qualified incomplete-check information), sent zero
messages and made no durable notification acknowledgment. Both inventories passed
the updated JSON Schema. No worker, cron job, real Telegram send or course-document
transmission was activated. Artifacts and real files are intentionally untracked
private runtime data, not repository fixtures.

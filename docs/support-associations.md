# Support-material associations

The checker now exports document references per assignment, with identity,
association provenance, role, safe source navigation, and observed download
routes. This stage collects metadata only. It does not download file bodies,
create a cache, or send files through Telegram. Existing assignment classification
continues to work independently of material availability.

## Per-unit evidence

The all-unit overview contributes explicitly scoped instruction links. Each
unit's own validated presentation page is also read to inspect the supported
`Dateien`/Files/Attachments and `Arbeitsanweisung`/Instructions sections. The
collector preserves each unit's dynamic route rather than borrowing another
unit's ID. A material in a different unit is not associated merely because its
filename is similar. Original titles and filenames retain their language.

Each raw assignment and classified activity can expose `support_documents`:

| Field | Meaning |
| --- | --- |
| `document_id` | Stable installation-local source identity when exposed; null for unresolved sequence titles |
| `title` | Source document label or explicit platform file key |
| `association` | `assignment_attachment`, `instruction_link`, or `contextual` |
| `role` | `support`, `model_answer`, `feedback`, `learner_submission`, or `unknown` |
| `source_url` | Safe source navigation for manual access |
| `download_url` | An observed validated route, or null; never invented from a title |
| `source_location` | Source page, original section label, exercise/unit identity, and contextual folder/path when applicable |
| `state` | `metadata_only` for an exposed route, `unavailable` when only manual source access is available |
| `reason_codes` | Selection restrictions and unresolved identity/role/route reasons |
| `selected_for_support` | Candidate for a future download stage, not confirmation that anything was downloaded |

`support_warnings` identifies unavailable or failed detail reads separately from
activity-state reasons. `support_detail_complete` in raw assignments records
whether a supported detail-page section was exposed; it does not assert that
every conceivable document route was understood. A failed support read does
not erase an activity's successfully read delivery state.

## Identity and role rules

Repository file references use their stable file reference ID. Assignment-local
attachments use the exercise ID, assignment ID, source command, and a hash of
the explicit platform `file` key. The observed file key can be a filename; its
unit context is part of identity, and names are never compared to infer an
association. Dynamic `cmdNode` values do not change identity. A shared repository
document has the same identity across associations, allowing a future cache to
reuse bytes without losing per-unit provenance. Future cache storage still
requires the installation/client/account namespace.

Known model-answer, feedback, and learner-submission sections are negative
evidence. Explicit negative labels and the platform global-feedback download
command also prevent support selection. A negative outer section wins over
instruction-styled markup nested within it. If a known document is labeled as
answer material anywhere in the inventory, another positive association to the
same identity does not silently select it. Unknown section roles remain flagged
for review. No document contents are opened to guess their role.

Only confirmed pending activities with a supported role, an explicit attachment
or instruction association, and an observed same-installation download route
become `selected_for_support` candidates by default. Submitted, excluded, closed,
future, and inconclusive work retain references without selecting support.
Cache expiry, quota, integrity, and delivery consent will be checked separately
when the cache and Telegram stages are implemented.

## Optional contextual material

`ILIAS_PENDING_INCLUDE_CONTEXTUAL=false` is the default. Setting it to `true`
adds metadata candidates from the exercise's immediate containing folder in the
same configured root. It does not search every ancestor, nearby sibling folder,
or the whole course. Their association stays `contextual`, and their folder
source URL/path is retained.

Opt-in permits contextual association; it does not prove a file's purpose.
Current generic folder document metadata has unknown role and remains unselected
until support-role evidence exists. Known answer labels are excluded. No similar
filename rule or blanket selection of neighboring PDFs is used.

## Unavailable sources and sequences

A source object link alone is not turned into a guessed file-download command.
External instruction URLs remain manual-only through the ILIAS source page;
the checker does not forward credentials to them. Token-bearing, credential-
bearing, unsafe, and mismatched assignment routes are rejected. The collector's
read transport still refuses document download commands; extracting a URL does
not authorize its execution.

Visible sequence filenames are retained with their original sequence-entry URL,
`document_id: null`, `download_url: null`, and
`sequence_document_identity_unresolved`. Titles are not used to fabricate IDs or
URLs. Existing inconclusive sequences and blank assignment views remain
inconclusive for the future user-feedback flow; no learner controls are followed.

`classify --input` can expose contextual or sequence metadata already present in
a saved scan, but it cannot recover unit attachments that were never collected.
Such records retain `support_detail_not_collected` until a normal metadata
collection obtains their source detail page.

The [synthetic example](../examples/support-associations.json) distinguishes an
attachment, an explicit instruction link to the same document, an unknown
contextual file, and a model answer. It contains no real course content.

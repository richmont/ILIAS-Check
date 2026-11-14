# Inventory JSON format

`ilias-check collect` emits one UTF-8 JSON document. The current contract is
validated by [`schemas/inventory-v1.schema.json`](../schemas/inventory-v1.schema.json)
and has `schema_version: "1.0"`. Fields may be added in later versions; consumers
should ignore fields they do not use.

## Top-level fields

| Field | Meaning |
| --- | --- |
| `schema_version` | Inventory contract version |
| `checked_at` | UTC timestamp ending in `Z` |
| `scope` | HTTPS installation base, ILIAS client ID, and unique selected root IDs |
| `coverage` | Per-root completeness, discovered-object count, empty-root marker, warnings, and safe error category |
| `objects` | Deduplicated object metadata and every known root-relative path |
| `activities` | Per-unit classified observations, plus unresolved exercise/sequence candidates |
| `classification` | Full-run state counts, completeness, all-clear flag, warnings, selection and returned count |
| `errors` | Redacted categories and affected root/object IDs; never raw response bodies |

Each object includes its installation-local ID/type, unchanged source title,
safe session-free URL, URL kind, root-relative paths, document references,
sequence resolution/steps where available, and warnings. Resolved objects use a
canonical activity URL. A legacy repository reference whose concrete type
cannot be resolved remains visible with `type: "unresolved"`, `type_code: "obj"`,
its sanitized same-origin legacy read URL, and an
`unresolved_legacy_repository_reference` warning. `url_kind` is
`sequence_entry` when the platform exposes only a learning-sequence entry point;
it does not promise a direct upload form.

Learning sequences also expose `sequence_outline`: visible workflow titles,
descriptions, and source availability/progress CSS states. These entries have no
fabricated reference IDs or URLs. An outline alone does not make
`sequence_resolution` resolved or establish file-delivery state; only actual
passive child references can do that. `lso` is the installation's sequence type.

Document entries contain only descriptive metadata and canonical source links.
The collector never follows a file-body download route. Sequence steps are
included only when exposed by passive object links or explicit passive metadata.
Unresolved sequence steps are visible in object warnings and reduce coverage
completeness; the collector does not advance learning progress to discover them.
See [sequence compatibility](sequence-compatibility.md) for the fixture-only
investigation result and its live-compatibility limitation.

Exercise objects additionally contain `assignments`, one entry per `ass_id`
from the all-unit overview. The MCP-compatible source fields are `ass_id`,
`title`, `deadline`, and `status`; the last two are original source strings,
not normalized dates or the checker's classified activity states. Each entry
also retains `instructions`, `requirement`, `delivery_type`, validated
`presentation_url`/`submission_url`/`team_url`, `submitted_files`, `team_members`,
`availability`, `submission_source`, and `warnings`.
File-list entries expose only `delivery_id`, `filename`, `submitter`, and
`date`; team entries expose `user_id` and `name`. No answer content is fetched.
`null` lists mean unreadable, unavailable, or unrecognized metadata. `[]` means
the relevant list was explicitly recognized and empty. A per-unit failure keeps
other units and makes root coverage partial. These fields do not assert that a
team submission was personally uploaded, approved, or completed.

Raw assignments and classified activities additionally expose
`support_documents` and `support_warnings`. Each reference records a stable
source identity when known, source title, association type, role, provenance,
observed download route, and metadata-only selection state. Inconclusive
sequence filenames have no invented IDs or download URLs. See
[support associations](support-associations.md) for the shared schema,
contextual opt-in, negative-role filtering, and metadata-only boundary.

If the overview omits a file-delivery screen, the checker can read the same
unit's source presentation link. An explicit no-file message inside the
`Einreichung` subpanel yields an empty list with
`submission_source: "assignment_detail_explicit_empty"`. Explicit `Beendet am`
labels preserve closed availability without guessing from a date. A blank or
unrecognized unit detail remains unknown (`assignment_detail_unavailable`);
it does not prove that the learner has no submission or does not own the unit.

## Coverage and exit behavior

- `complete: true` means the selected root and discovered supported descendants
  were successfully read within the configured limits.
- `empty: true` means the supported root was read successfully and no descendant
  object was discovered; the root record itself remains in `objects`.
- `complete: false` identifies partial/unknown coverage, not an empty result.
  Check `warnings` and `errors` before interpreting absence of an object.
- `unresolved_legacy_repository_reference` means a legacy object was readable
  but its concrete type was not exposed by supported passive metadata. Any
  child links found in recognized content are still traversed within the
  configured limits.
- A failed root may coexist with successful roots; successful results remain in
  the output.
- CLI exit codes are `0` for complete results, `2` for partial results, and `1`
  for fatal/configuration failures.

Classification completeness is separate from collection coverage. Unknown
activities, missing sequence delivery evidence, and failed collection coverage
prevent `classification.all_clear`. Activity selections preserve that full-run
summary even when `activities` is filtered to an empty category. The optional
fields are additive within schema version 1.0; older snapshots can still validate
but may lack evidence necessary for definitive classification. See
[classification commands and evidence](assignment-classification.md).

## Privacy and compatibility

IDs and titles can identify a learner's course context. Keep inventories private
and out of issue reports or source control. Error messages are category-level;
credentials, cookies, tokens, and response HTML are excluded. URLs contain no
session material and may still require normal browser authentication.

The initial target is ILIAS 9_23. Unsupported layouts, unknown object types,
request/depth limits, and unresolved sequences are warnings/partial coverage,
never evidence that no work exists. Ordinary ILIAS page reads may create access
logs or implicit view records.

## Synthetic empty-root example

The schema-validated example in
[`examples/inventory-empty.json`](../examples/inventory-empty.json) uses only
fictional identifiers and the reserved `example.edu` domain.

With support caching explicitly enabled, `support_cache` adds measured managed usage,
quota, run bytes and observation time. A failed cache has a sanitized additive error;
activity classifications and source coverage are preserved. Support references may
use `cached`, `unchanged`, `stale`, `expired`, `evicted`, `skipped` or `error` in addition
to metadata states. Optional `cache` metadata includes local path (eligible copies
only), media type, bytes, SHA-256, download/validation/expiry times, expiry reason,
eligibility and the authoritative-source warning. See [cache lifecycle](support-cache.md).
Never deliver a remembered path directly: the cache delivery gate must recheck current
activity evidence, association and integrity. Offline `classify` recomputes metadata
selection; it does not revalidate or renew any copy.

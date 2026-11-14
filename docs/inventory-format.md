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
| `errors` | Redacted categories and affected root/object IDs; never raw response bodies |

Each object includes its installation-local ID/type, unchanged source title,
canonical session-free URL, URL kind, root-relative paths, document references,
sequence resolution/steps where available, and warnings. `url_kind` is
`sequence_entry` when the platform exposes only a learning-sequence entry point;
it does not promise a direct upload form.

Document entries contain only descriptive metadata and canonical source links.
The collector never follows a file-body download route. Sequence steps are
included only when exposed by passive object links or explicit passive metadata.
Unresolved sequence steps are visible in object warnings and reduce coverage
completeness; the collector does not advance learning progress to discover them.
See [sequence compatibility](sequence-compatibility.md) for the fixture-only
investigation result and its live-compatibility limitation.

## Coverage and exit behavior

- `complete: true` means the selected root and discovered supported descendants
  were successfully read within the configured limits.
- `empty: true` means the supported root was read successfully and no descendant
  object was discovered; the root record itself remains in `objects`.
- `complete: false` identifies partial/unknown coverage, not an empty result.
  Check `warnings` and `errors` before interpreting absence of an object.
- A failed root may coexist with successful roots; successful results remain in
  the output.
- CLI exit codes are `0` for complete results, `2` for partial results, and `1`
  for fatal/configuration failures.

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

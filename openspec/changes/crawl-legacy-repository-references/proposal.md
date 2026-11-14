# Proposal

## Why

The collector recognizes legacy ILIAS repository links containing
`baseClass=ilRepositoryGUI` and a valid `ref_id`, but assigns the synthetic type
`obj`. Traversal classifies that reference as unsupported and skips it, causing
reachable repository objects on the project's primary ILIAS site to be omitted
from the inventory.

## What Changes

- Preserve validated legacy repository references when their concrete object
  type is not present in the link.
- Use a bounded, same-origin read of the legacy reference route to resolve the
  object type from passive response metadata when the target site exposes it.
- Keep references visible and mark coverage incomplete with an explicit warning
  when the type cannot be resolved; do not silently treat them as absent.
- Add fixture-based normalization and traversal coverage for resolved and
  unresolved legacy references.
- Keep the existing read-only transport protections and standalone collector
  architecture; compatibility with other ILIAS installations is not required.

## Capabilities

### New Capabilities

- `repository-reference-resolution`: Resolve and retain validated legacy
  repository references whose links omit the concrete object type.

### Modified Capabilities

None. The repository has no synchronized main specs yet; this change introduces
the focused capability contract for legacy reference resolution.

## Impact

Likely code changes are in `src/ilias_check/links.py` and
`src/ilias_check/traversal.py`, with fixture-based tests in
`tests/test_links_traversal.py` and possible updates to inventory documentation
or schema if an unresolved type needs a serialized representation. The existing
transport allowlist already permits same-origin GETs to `ilias.php`; the
implementation must continue to enforce origin, safe-query, redirect, and
request-budget checks. Site-specific behavior must be represented by synthetic
or sanitized fixtures, not credentials or private course content.

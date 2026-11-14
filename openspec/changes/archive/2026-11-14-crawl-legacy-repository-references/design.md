# Design

## Context

See `proposal.md` for motivation and `specs/repository-reference-resolution/spec.md`
for observable behavior.

Confirmed in the current code:

- `normalize_object_link()` validates origin, credentials, sensitive material,
  action parameters, and positive reference IDs before creating an `ObjectRef`.
- `_type_from_base_class()` maps `ilRepositoryGUI` to synthetic type code `obj`,
  which is not in `_TYPE_NAMES`.
- `RepositoryCrawler` skips objects whose type is `unsupported` before issuing a
  GET.
- `SafeTransport` allows same-origin GETs to `ilias.php`, checks every redirect
  origin, rejects action/session query parameters, and enforces request budgets.
- Inventory schema v1 allows string object types and warning codes, so an
  explicit unresolved type can be represented without changing the envelope.

Authorized live testing confirmed the target login handshake uses a bounded
sequence of read-only redirects (`cmd=` on the repository route and
`cmd=force_login` on `login.php`), followed by a password POST to
`ilias.php?baseClass=ilStartupGUI&cmd=post&fallbackCmd=doStandardAuthentication`.
The POST response redirects to a dashboard command; the client does not need to
follow that redirect because it performs a separate dashboard GET to confirm
the session. The transport therefore permits only the observed read commands
and exact login POST tuple, while retaining rejection of all other action
parameters and never replaying credentials after a POST redirect.

The exact passive type signal exposed by the target's legacy repository pages
remains unresolved in some cases. The design uses explicit recognized signals
when present and retains an unresolved fallback.

## Goals / Non-Goals

**Goals:**

- Fetch validated `ilRepositoryGUI` references through the existing safe
  transport, even when the link does not include a concrete type.
- Resolve a concrete type only from recognized passive response evidence.
- Preserve unresolved objects, provenance paths, child links, and incomplete
  coverage without misrepresenting them as confirmed empty results.
- Preserve the collector's independence from MCP, Telegram, and scheduling.

**Non-Goals:**

- General support guarantees for arbitrary ILIAS installations or versions.
- Browser automation, session sharing, action links, step transitions, or
  document-body downloads.
- A live-site test or storage of real course content in fixtures.

## Decisions

### Keep the validated legacy read route separate from the canonical object URL

Represent the validated legacy reference with both a sanitized read URL and an
inventory URL. Construct the read URL from the configured installation base
and validated positive `ref_id`, retaining only the recognized repository
base class and required non-action parameters. Do not fetch the synthetic
`goto.php?target=obj_<id>` URL merely because it is convenient to canonicalize.

Use the existing `SafeTransport.get()` for the read. Its allowlist already
includes `ilias.php`; its origin, query, redirect, retry, and request-budget
checks remain authoritative. The source link itself must pass the current
same-origin and sensitive/action-parameter checks before a read URL is built.

Alternative considered: marking `obj` as supported and using the generated
`goto.php` URL. Rejected because it assumes the synthetic type is meaningful
and does not establish that the target can resolve it.

### Resolve types only from explicit passive evidence

After a successful GET, inspect the final safe response URL and recognized
passive page metadata for a concrete type code and matching positive reference
ID. Accept only type codes already mapped to supported object kinds. Unknown
or malformed values do not become supported types. The exact target-specific
metadata encoding should be captured in a synthetic or sanitized fixture when
confirmed; absence of such evidence follows the unresolved path.

Alternative considered: infer the type from page title, CSS class names, or
other heuristics. Rejected because those signals are ambiguous and could assign
the wrong object type.

### Promote resolved legacy identity without losing traversal provenance

Use a temporary legacy identity for the initial `obj:<ref_id>` reference while
it is unresolved. When response evidence resolves the type, promote the
inventory record and fetched-page identity to `<type_code>:<ref_id>`, retaining
all root-relative paths and parsed metadata. Keep an alias from the legacy key
to the resolved key so a later modern link to the same object does not trigger
a duplicate fetch or duplicate inventory object.

When resolution fails but the page is readable, retain an object with
`type: "unresolved"`, `type_code: "obj"`, a sanitized legacy URL, and an
`unresolved_legacy_repository_reference` warning. Parse its recognized content
links using the existing content-scoped parser and continue bounded traversal
of those links. Mark every reaching root incomplete. If the page cannot be
read, retain partial inventory and report the existing sanitized object-read
error and incomplete coverage.

### Keep the behavior fixture-driven and deployment-scoped

Use fake responses for traversal tests, including passive type evidence,
readable pages without type evidence, read failures, and aliases reached by
both legacy and modern links. Add only synthetic or sanitized page fixtures.
Do not add an MCP runtime dependency or require a live server in automated
tests. A live compatibility check against the primary target is a separate,
explicitly authorized activity.

### Match the observed target login handshake narrowly

Allow an empty `cmd` or `cmd=infoScreen` only on the repository read route,
`cmd=force_login` only on `login.php`, and the exact startup authentication
tuple only for the login POST. Do not follow the login POST redirect; the
authenticator performs its separate safe dashboard GET. Do not generalize this
allowlist to other ILIAS action commands.

## Risks / Trade-offs

- [Target response may expose no reliable type signal] → Retain the object as
  unresolved, traverse safe content links, and report partial coverage.
- [Legacy and modern links may identify the same object differently] → Promote
  identity with an alias map and test that paths and fetch counts are merged.
- [A legacy GET or redirect may reach an unsafe route] → Reuse SafeTransport
  validation for the initial URL and every redirect; do not add a bypass.
- [Target login relies on legacy command parameters] → Allow only the observed
  read-only commands and exact login POST tuple; keep mutation commands denied.
- [Inventory consumers may not recognize `type: "unresolved"`] → Keep the
  schema's existing open string type, document the warning, and add a schema
  validation test for the serialized result.

## Migration Plan

No persistent data migration is needed. Add the type-resolution and identity
promotion behavior, retain the inventory v1 envelope, and verify the new
resolved and unresolved cases with offline fixtures. If the serialized
unresolved marker requires schema constraints, make only an additive schema
update. Rollback consists of reverting the focused code and fixture changes;
existing modern-reference behavior remains unchanged.

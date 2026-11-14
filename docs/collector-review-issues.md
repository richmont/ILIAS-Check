# Collector review issues

Findings from the post-implementation review of commit `8c6c639` are tracked as
GitHub Issues in `richmont/ILIAS-Check`:

| Issue | Finding | Local status |
| --- | --- | --- |
| [#1](https://github.com/richmont/ILIAS-Check/issues/1) | Legacy repository references can be classified as unsupported and skipped | Implemented and covered offline |
| [#2](https://github.com/richmont/ILIAS-Check/issues/2) | Password whitespace is stripped during configuration loading | Implemented and covered offline |
| [#3](https://github.com/richmont/ILIAS-Check/issues/3) | Bracketed ILIAS action parameters can bypass the read-URL denylist | Implemented and covered offline |
| [#4](https://github.com/richmont/ILIAS-Check/issues/4) | Some expired login pages may not match the fixed session-expiry markers | Implemented and covered offline |

These local fixes do not imply that the corresponding GitHub issues are closed.
The collector remains unvalidated against a live ILIAS installation; any live
compatibility test requires separate authorization.

## Project scope

The primary target is the specific ILIAS website already connected through the
MCP in this environment. Compatibility with other ILIAS instances is welcome
when it comes naturally, but is not a requirement and must not delay adapting
the collector to the target website's observed behavior. The ILIAS 9_23 support
in the initial adapter is a starting point, not a promise of broad
cross-installation compatibility.

## Issue #1 implementation plan

The current parser recognizes
`ilias.php?baseClass=ilRepositoryGUI&ref_id=<id>` but assigns the synthetic type
code `obj`. Since `obj` is not a supported object kind, traversal flags the
reference as unsupported and skips fetching it. Existing coverage tests only
assert URL normalization, not that a legacy reference is traversed.

Plan the correction around observed behavior of the MCP-connected target:

1. Inspect a representative legacy repository reference and its safe read
   response/metadata on the target website; identify which passive fields or
   route behavior reveal the actual object type.
2. Preserve the validated reference ID and legacy read route when the type is
   unknown. Do not invent a supported type or silently drop the reference.
3. Resolve the type from the target's passive metadata when available, then
   continue traversal and deduplicate using the resolved object identity.
4. If the target exposes no usable type, retain the object as unresolved,
   include an explicit warning, and mark root coverage incomplete. Do not
   follow action links or relax same-origin, read-route, request-budget, or
   redirect protections.
5. Add synthetic tests for legacy-reference traversal, type resolution,
   unresolved-but-visible behavior, deduplication, and the safe transport
   boundary. Keep site-specific observations in fixtures without real
   credentials or private course content.

No implementation or live-site verification is implied by this plan. Any
access to the connected website for verification remains subject to
authorization.

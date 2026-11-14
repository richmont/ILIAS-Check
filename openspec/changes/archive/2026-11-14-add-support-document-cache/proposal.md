# Proposal

## Why

An assignment alert is useful only if the user can find the instructions and relevant supporting documents. Safe, cached copies reduce navigation and repeated downloads while keeping uncertain associations explicit.

## What Changes

- Discover documents attached to individual assignment units and explicitly linked from instructions.
- Optionally expose nearby folder materials as contextual support, never as confirmed assignment attachments.
- Download selected support files to a private local cache with timestamps, checksums, revalidation, deadline/submission-aware expiry, and automatic cleanup.
- Enforce an administrator-only total cache quota, initially 200 MB; expose usage and user-configurable retention to the later bot settings menu.
- Offer source links and explicitly identify cached copies as potentially older than ILIAS.
- Extend assignment JSON with document provenance, availability, and local copy status.
- Exclude model answers and unrelated bulk content from automatic collection.
- Dependencies: `add-read-only-collector` and `add-pending-assignment-classification`.
- Non-goals: answering assignments, interpreting every document's contents, OCR/translation, bulk course mirroring, manual bot cleanup, bot quota changes, and sending files to third parties in this change.

## Capabilities

### New Capabilities

- `support-document-association`: Evidence-based association of documents to assignments.
- `support-document-cache`: Bounded, private, reusable local copies.

### Modified Capabilities

None. Document metadata is an additive extension to assignment results.

## Impact

Adds document-link extraction, a filesystem cache and manifest, download policies, and fixture-based HTTP tests. Course documents remain user data, not repository assets; their rights are independent of the application's license.

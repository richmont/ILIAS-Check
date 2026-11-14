# Tasks

Depends on: `add-read-only-collector` and `add-pending-assignment-classification`.

## 1. Document association

- [ ] 1.1 Extract assignment attachments and explicit instruction links with stable IDs and provenance; verify per-unit attachment and shared-document fixtures without filename-based matching.
- [ ] 1.2 Add opt-in contextual associations and conservative role filtering; verify nearby unrelated materials, labeled solutions, feedback, learner submissions, and ambiguous roles are not silently selected.
- [ ] 1.3 Export unresolved sequence materials as metadata-only references; verify no fabricated download URL or learner-step transition occurs.
- [ ] 1.4 Extend the JSON Schema and document association meanings; verify examples distinguish confirmed support from contextual support.

## 2. Private bounded cache

- [ ] 2.1 Add host-only total quota, user-editable retention inputs, and account-scoped private storage with bounded manifest; verify the 200000000-byte default, disabled downloads, checkout rejection, account isolation, and usage reporting.
- [ ] 2.2 Implement safe streaming, allowed file types, request/byte budgets, atomic publication, and checksum metadata; verify oversize/chunked responses, path traversal, symlink escapes, duplicate filenames, and interrupted transfers.
- [ ] 2.3 Reuse the adapter's same-origin/session policy and reject HTML login/error bodies; verify expiration recovery, off-origin redirects, and fake document responses never publish a successful cache entry.
- [ ] 2.4 Document supported types, quota/TTL precedence, private storage, source-authoritative warnings, and copy timestamps; verify examples contain placeholders and limits match tests.

## 3. Freshness and failures

- [ ] 3.1 Implement fresh reuse, validator-based revalidation, bounded refresh, and cache locking; verify 304 responses do not reset download time/retention and shared associations reuse bytes without bypassing expiry.
- [ ] 3.2 Detect corrupted cache entries and retain explicit stale state after refresh errors; verify old copies are never exported as current and unrelated assignment results survive.
- [ ] 3.3 Implement deadline/submission/completion expiry, seven-day no-deadline default, and user TTL caps; verify shared references, unreadable deadlines, TTL changes, ended activity requests, and reopening without deleting history metadata.
- [ ] 3.4 Implement automatic physical eviction and bounded manifests/temporary transfers; verify oldest-copy eviction, quota reduction, concurrent transfers/readers, oversize files, and refusal when safe reclamation is impossible.
- [ ] 3.5 Expose automatic maintenance and pre-delivery eligibility gates, without manual bot purge/quota setters; verify expired copies/file IDs are not served and unsafe filesystem paths are never deleted.
- [ ] 3.6 Document automatic lifecycle and lack of remote revocation; verify source-link fallback and download/validation/expiry timestamps appear in synthetic examples.

## 4. Integration

- [ ] 4.1 Wire opt-in support collection into assignment JSON and CLI configuration; verify confirmed pending work is downloaded while submitted, excluded, closed, and unknown work remains metadata-only by default.
- [ ] 4.2 Run offline end-to-end tests across collection, classification, and repeated cache runs; verify no file contents, manifests, secrets, or real course assets enter the tracked tree.
- [ ] 4.3 Simulate week-long rotation with a fixed clock and small quota; verify physical managed usage stays bounded, expired copies are refused, and refreshed pending work uses new timestamps without resurrecting submitted work.

## Workflow follow-up

- Review exported cache metadata before implementing Telegram attachments.
- Archive after implementation and verification; external document transmission is not part of this change.

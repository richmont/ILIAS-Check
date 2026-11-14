# support-document-cache Specification

## Purpose

Provide reusable local support files without repeatedly downloading course materials or exposing private data outside the configured cache.

## Requirements

### Requirement: Configurable private local copies
When support downloading is enabled, the system SHALL save selected documents below `ILIAS_PENDING_OUTPUT_DIR` and export paths, content metadata, checksum, download/validation timestamps, expiry, and state. Storage SHALL be private, account-scoped, and outside the source tree by default. Each copy SHALL identify its activity source and warn that ILIAS can be newer.

#### Scenario: Downloads disabled
- **WHEN** support downloading is disabled
- **THEN** the JSON retains document metadata without making file-body download requests

#### Scenario: Shared document
- **WHEN** two pending assignments reference the same account-scoped document version
- **THEN** one cached copy can serve both while preserving both assignment associations

### Requirement: Deadline and submission retention
An association SHALL expire at its known deadline or confirmed submission/completion, whichever occurs first. Without a deadline, its copy SHALL expire seven days after download by default. A configured retention TTL SHALL impose an additional maximum, never extend a deadline. Unreadable deadlines SHALL use a bounded fallback and warning, not be treated as absent.

#### Scenario: Delivery before assessment
- **WHEN** a still-ungraded submission is confirmed for the assignment
- **THEN** its support association expires without waiting for approval and history metadata remains

#### Scenario: No deadline
- **WHEN** a pending assignment explicitly has no deadline and no retention override
- **THEN** its cached copy expires seven days after download and the expiry is exported

#### Scenario: Custom shorter retention
- **WHEN** the configured TTL expires before the deadline
- **THEN** the old copy is no longer eligible for delivery even if physical cleanup has not run

#### Scenario: Shared support and one completed activity
- **WHEN** one association expires but another eligible assignment still needs the same copy
- **THEN** the copy can remain for the valid association but is not offered for the ended one

### Requirement: Automatic bounded cache capacity
The managed cache SHALL enforce the host-only `ILIAS_SUPPORT_CACHE_MAX_BYTES`, default 200000000 bytes, including managed files, temporary transfers, and manifest storage. Maintenance SHALL remove expired copies before evicting oldest downloaded copies. It SHALL reclaim bytes, not only mark entries stale. Usage and quota SHALL be observable but not editable through the bot.

#### Scenario: Capacity reached
- **WHEN** a new download would exceed the quota
- **THEN** automatic cleanup reclaims safe managed copies or skips the transfer with a source-link fallback

#### Scenario: Administrator reduces quota
- **WHEN** host configuration sets a limit below current managed usage
- **THEN** next maintenance/access evicts safely eligible copies and new transfers do not worsen the excess

#### Scenario: Metadata or active readers prevent reclamation
- **WHEN** bounded metadata and protected active reads leave insufficient reclaimable space
- **THEN** the transfer is deferred/skipped rather than exceeding capacity or deleting unrelated files

### Requirement: Automatic expiry and delivery gate
The cache SHALL check association validity, copy expiry, and integrity before every delivery. Cleanup SHALL run automatically during scheduled checks and bot maintenance, without a user cleanup operation. Confirmed ended associations SHALL NOT be refetched merely on request; TTL-expired copies of still-eligible work can be refreshed after a new eligibility check.

#### Scenario: Old bot download button
- **WHEN** the user requests a copy whose association ended or retention expired
- **THEN** the old copy is not sent and the source activity link remains available

#### Scenario: Still-pending work after cache eviction
- **WHEN** a current check confirms eligibility but the old bytes were evicted or TTL-expired
- **THEN** a bounded new source download can create a new copy without reviving the expired bytes

#### Scenario: No remote revocation
- **WHEN** a local copy expires after an earlier Telegram delivery
- **THEN** the bot refuses new delivery from that expired cache and documentation explains that earlier recipient copies cannot be revoked

### Requirement: Revalidate cached documents
The cache SHALL reuse non-expired verified copies and revalidate stale copies using server validators or a bounded refresh interval. Changed bytes SHALL update checksum and download metadata. Validation without a new body SHALL NOT reset download time or silently extend retention. Copy identity SHALL NOT depend only on filename.

#### Scenario: Unchanged cached document
- **WHEN** a cached document is fresh or revalidation confirms it is unchanged
- **THEN** the file body is not downloaded again

#### Scenario: Same filename on different documents
- **WHEN** unrelated document IDs both expose `worksheet.pdf`
- **THEN** their cache entries remain distinct

#### Scenario: Unchanged validation near expiry
- **WHEN** a conditional request confirms the same body shortly before retention expires
- **THEN** validation time updates but the original download time and expiry are not silently reset

### Requirement: Safe bounded downloads
Downloads SHALL enforce configured per-file, per-run, and total storage budgets, timeouts, allowed types, and configured-origin redirects. Output paths SHALL remain inside the managed cache despite filenames or symlinks. Files SHALL be published atomically only after validation; capacity checks SHALL account for concurrent readers/writers and temporary bytes.

#### Scenario: Oversized streamed response
- **WHEN** a response exceeds the byte limit even without a trustworthy Content-Length
- **THEN** the transfer stops, no complete cache entry is published, and the document has a structured size-limit error

#### Scenario: Unsafe filename
- **WHEN** the response suggests a traversal filename or an output path escapes through a symlink
- **THEN** the system does not write outside the cache

### Requirement: Detect authentication pages and partial failures
The downloader SHALL reject login or error pages masquerading as documents. A failed refresh SHALL NOT silently label an old copy current, and one failed document SHALL NOT discard valid assignment results.

#### Scenario: Session expires during download
- **WHEN** a document request returns an HTML login page with HTTP 200
- **THEN** it is not stored as a successful document and bounded reauthentication or an explicit error follows

#### Scenario: Cached copy survives refresh failure
- **WHEN** refresh fails for a previously cached file
- **THEN** its old path can remain available only with an explicit stale state and refresh error

### Requirement: Respect document boundaries
The cache SHALL NOT execute, render macros from, or automatically transmit downloaded documents. Runtime files SHALL be excluded from version control and documented as course data with separate access and copyright constraints.

#### Scenario: Office document downloaded
- **WHEN** a permitted Office file is cached
- **THEN** it is stored as opaque bytes without executing its contents

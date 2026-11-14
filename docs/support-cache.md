# Private support cache

`collect` optionally downloads confirmed support for currently pending assignments.
Set `ILIAS_PENDING_DOWNLOAD_SUPPORT=true` in the explicitly selected configuration.
The default remains false: metadata extraction never downloads document bodies.
`classify` stays offline and never grants new permission to download old snapshots.

Storage defaults to `~/.local/share/ilias-check/support`, outside every Git checkout.
The private root must be owned by the local account with mode 0700; files use 0600.
Symlink components, hardlinked managed files, incompatible manifests, and unsafe paths
are refused. Identities combine installation, client, account and stable document ID;
filenames are display labels. The versioned manifest contains private course metadata.
Do not commit, share or put this directory in a public backup.

The host quota `ILIAS_SUPPORT_CACHE_MAX_BYTES` defaults to **200000000 bytes** (200 MB,
not 200 MiB), covering bodies, temporary transfers and manifests across accounts in
the configured root. Per-file/run defaults are 20/100 MiB. Atomic manifest replacement
reserves additional metadata space, so usable body capacity is conservatively smaller.
Unsupported types or insufficient safe capacity produce source-link fallbacks.

PDF, legacy DOC/XLS/PPT, DOCX/XLSX/PPTX, ODT/ODS/ODP and RTF are supported. Media types,
signatures, Office container directory markers and sizes are checked without executing
or extracting content. These checks are not an antivirus guarantee. Archives, videos,
executables, HTML/login/error pages and unknown types are not published as documents.
Transfers use a separate, exact-identity byte route with the collector's authenticated
session, origin/path restrictions, TLS, timeout and request budget. Ordinary metadata
GET still cannot invoke file-download actions. A recognized HTML login response permits
one bounded session recovery; other invalid responses fail explicitly.

Copies are reused while fresh and verified. After `ILIAS_SUPPORT_REVALIDATE_HOURS`
(default 12), validators are used where available. A 304 updates validation time only;
it does not renew download time or retention. A changed body replaces the copy atomically.
A failed refresh is stale and cannot be delivered as current. Checksums are rechecked
before reuse and delivery. Shared references reuse one physical copy with separate
activity eligibility. Unknown or missing observations pause access without inventing
completion.

Known deadlines cap retention even when the platform accepts late submissions.
Without a resolved deadline, the fallback is `ILIAS_SUPPORT_NO_DEADLINE_TTL_HOURS`
(default 168); unreadable deadlines carry a warning. `ILIAS_SUPPORT_RETENTION_MAX_HOURS`
can shorten either policy. User preferences can change retention, never host quota or
security limits. Confirmed submission/exclusion/closure ends that association. A fresh
pending check can retrieve a new copy after TTL eviction; ended deadlines require
confirmed extension/reopening. Settings changes alone cannot authorize delivery.

Maintenance runs during scans and before delivery, removes expired/unreferenced bytes,
then evicts oldest downloaded copies as needed. Tombstones/manifests are bounded (up to
1000 entries/1 MiB); this is not permanent submission history. The root-wide process
lock covers readers and writers. Concurrent operations defer rather than evict active
reads; a delivery lease ends when the bounded outbound request finishes. Crash leftovers
are reclaimed under the lock. Unmanaged files are never removed; they consume capacity.

JSON `support_cache` reports usage/quota/time/bytes. Per-reference `cache` metadata
exposes checksum, size, type, copy/validation/expiry timestamps, reason and eligibility.
A path is exported only for an eligible current copy. Consumers must use the delivery
gate instead of opening a remembered path or reusing a Telegram file ID. The original
ILIAS link always remains available. ILIAS is authoritative and may be newer. Local
cleanup cannot revoke copies previously delivered to a recipient.

No Telegram document is sent by enabling this cache. No bot purge or quota setter is
provided. Runtime and dotenv paths remain ignored; examples use synthetic data only.

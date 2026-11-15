# monitor-state Specification

## Purpose

Turn periodic collection into durable, account-scoped observations and retryable notifications without inventing successful checks or deliveries.

## Requirements

### Requirement: One-shot scheduled monitoring
The monitor SHALL run once and exit with a meaningful result, use explicit configuration and paths, and prevent overlapping executions for the same account and state store. Documentation SHALL provide an example for checking every 12 hours without installing or changing cron automatically.

#### Scenario: Overlapping cron invocations
- **WHEN** a second invocation starts while the same account's monitor holds the run lock
- **THEN** the second exits with an explicit already-running result without collecting or sending notifications

### Requirement: Durable account-scoped state
The monitor SHALL persist observations and notification events by installation, configured account identity, exercise, and assignment. Passwords, session cookies, and bot tokens SHALL NOT be stored in monitoring state.

#### Scenario: Account changes
- **WHEN** the same state directory is used with a different configured account
- **THEN** that account does not inherit the first account's submitted or notification state

### Requirement: New and changed pending notifications
The monitor SHALL enqueue notifications on the first confirmed pending observation and meaningful changes to pending work. Unchanged work SHALL NOT be re-notified unless a configured reminder interval expires. A confirmed submitted-to-pending transition SHALL be eligible for a new event.

#### Scenario: Identical subsequent check
- **WHEN** the next complete check finds the same pending assignment and no reminder is due
- **THEN** no duplicate notification is enqueued

#### Scenario: Deadline changes
- **WHEN** the deadline of a still-pending assignment changes
- **THEN** a change notification becomes eligible even when a prior notification succeeded

### Requirement: Preserve uncertainty across runs
Partial collection, missing objects, and unknown classification SHALL NOT be interpreted as submission or resolution. Confirmed pending results from a partial run can produce events only with an incomplete-check notice. Repeated equivalent health failures SHALL be deduplicated.

#### Scenario: Previously pending assignment disappears during failure
- **WHEN** its root fails during the next check
- **THEN** the assignment retains its last confirmed observation with a stale marker and is not marked submitted

#### Scenario: Recovered explicit submission
- **WHEN** a later successful check confirms a submission
- **THEN** future pending reminders stop for that unit

### Requirement: Cancel or pause obsolete queued events
Before retrying an alert, the monitor SHALL validate it against the latest relevant observation and current settings. Confirmed submission, exclusion, closure, or a superseding event SHALL cancel obsolete sends. Unknown, missing, or failed current evidence SHALL pause retries rather than confirm continued pending status.

#### Scenario: Submission before failed alert retry
- **WHEN** an unsent pending alert remains queued and the next relevant check confirms submission
- **THEN** the old alert and remaining attachment components are canceled

#### Scenario: Failed recheck before retry
- **WHEN** the latest relevant check cannot verify the activity
- **THEN** its queued pending retry pauses and an appropriate incomplete-check notice can be emitted instead

### Requirement: Automatic cache maintenance without losing history
Scheduled checks SHALL invoke safe automatic cache maintenance and propagate confirmed submission/completion to association expiry. History metadata SHALL remain after document removal. A failed or unknown activity check SHALL NOT be interpreted as completion, though TTL/quota expiry still applies.

#### Scenario: Submitted work with cached support
- **WHEN** the latest check confirms submission while supporting copies still exist
- **THEN** their assignment association ends, safe cleanup can reclaim unused bytes, and delivery metadata remains queryable

### Requirement: Retryable delivery state
Notification events SHALL track delivery per message and attachment, acknowledging only confirmed successful sends. Failures SHALL remain retryable with bounded backoff. Ambiguous network outcomes SHALL be recorded without claiming exactly-once delivery.

#### Scenario: Attachment fails after message succeeds
- **WHEN** Telegram accepts the message but an attachment send fails
- **THEN** retry targets only the failed attachment if the event, consent, and cache eligibility remain valid

#### Scenario: Timeout after remote acceptance
- **WHEN** the client cannot determine whether Telegram accepted a send
- **THEN** the event records uncertain delivery and follows the documented retry policy with possible duplication disclosed

### Requirement: Local validation mode
The monitor SHALL provide a dry-run mode that reports planned notifications without contacting Telegram or acknowledging delivery events.

#### Scenario: Dry run
- **WHEN** the user requests dry-run monitoring
- **THEN** planned events are shown locally and no Telegram request or delivery acknowledgment occurs

### Requirement: Grouped message acknowledgments
A successful summary SHALL acknowledge every represented due message component with the returned message identity. Failed or ambiguous sends SHALL preserve bounded retries without acknowledging success. Attachment acknowledgments SHALL remain independent. Obsolete or stale evidence SHALL be reconciled immediately before each external side effect. `sent_components` SHALL count acknowledged components rather than Telegram API sends.

#### Scenario: Failed summary with several pending events
- **WHEN** the single summary send for multiple due events times out
- **THEN** every included message component records uncertain delivery, no activity is marked notified, and a later eligible retry sends one summary

#### Scenario: Slow summary before attachments
- **WHEN** the summary succeeds but its send takes long enough to expire relevant evidence
- **THEN** its confirmed message components stay acknowledged while subsequent attachment components pause until a fresh check

### Requirement: Durable material-button migration
The private monitoring database SHALL migrate schema version one to version two transactionally to store material-request tokens without passwords or bot credentials. Newer unsupported schema versions SHALL be rejected. Tokens SHALL be bounded by their expiry during maintenance on creation and validated at claim time.

#### Scenario: Existing monitoring installation
- **WHEN** the updated worker opens a version-one state database
- **THEN** observations and notification history remain intact and durable single-use material requests become available

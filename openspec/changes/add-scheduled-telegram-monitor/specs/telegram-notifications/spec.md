# Spec Delta

## Purpose

Deliver actionable pending-work alerts to an explicitly configured recipient while keeping external sharing of course documents under user control.

## ADDED Requirements

### Requirement: Explicit Telegram destination
Telegram delivery SHALL require explicit enablement, bot credentials, and one configured recipient chat ID. The adapter SHALL NOT discover or choose recipients from incoming messages. Disabled delivery SHALL make no Telegram requests.

#### Scenario: Missing recipient
- **WHEN** delivery is enabled without a recipient chat ID
- **THEN** monitoring reports a configuration error rather than choosing a chat automatically

### Requirement: Actionable assignment messages
Each assignment notification SHALL include title, root-relative path, status reason, deadline with timezone or explicit absence, and a manual delivery link. Sequence-entry links SHALL be labeled as sequence entry rather than direct upload. Partial checks and contextual support SHALL be identified clearly.

#### Scenario: No configured deadline
- **WHEN** a pending assignment has no deadline
- **THEN** the message states that no deadline is configured rather than inventing one

#### Scenario: Sequence entry only
- **WHEN** only the learning-sequence URL is available
- **THEN** the message labels it as sequence entry and does not claim it opens an upload form directly

### Requirement: Portuguese interface with original ILIAS content
Bot-owned labels, help, notices, and buttons SHALL use Portuguese. ILIAS titles, instructions, filenames, and quoted source content SHALL remain in their original language. Notifications SHALL NOT call an LLM or translation provider.

#### Scenario: German activity in a Portuguese alert
- **WHEN** an original German activity is announced
- **THEN** Portuguese status labels surround unchanged German source text without automatic translation

### Requirement: Source navigation buttons
Resolved activity links SHALL use “Abrir no ILIAS”; sequence-only fallback links SHALL use “Abrir sequência”. Links SHALL contain no credentials or session material, and messages SHALL NOT promise to bypass browser login or platform access controls.

#### Scenario: Manual activity access
- **WHEN** the learner presses the activity button without a browser login
- **THEN** the original ILIAS activity is the destination subject to normal authentication

### Requirement: Opt-in course document sharing
Automatic course attachments SHALL require separate explicit opt-in acknowledging external transmission. By default, alerts SHALL contain metadata and ILIAS links only. Sending SHALL use eligible validated support, never answers or arbitrary local paths. The later interactive bot can also send an authorized explicitly requested support copy.

#### Scenario: Attachments not authorized
- **WHEN** Telegram messages are enabled but attachment sharing is disabled
- **THEN** alerts include relevant ILIAS links without uploading course documents

#### Scenario: Attachment sharing authorized
- **WHEN** the user opts in and eligible support has a valid current cached copy
- **THEN** the adapter can send that copy with its assignment association identified

### Requirement: Cached copy disclosure and expiry
Each transmitted support copy SHALL identify download time, expiry, source activity URL, and that ILIAS may be newer; validation time SHALL be shown when available. Delivery SHALL recheck consent and cache eligibility. Expired/evicted/stale files or Telegram file IDs SHALL NOT bypass these checks.

#### Scenario: Cache expires before attachment retry
- **WHEN** an attachment component is due for retry after its copy expires
- **THEN** expired bytes are not sent and the adapter either obtains a newly eligible copy or provides the source link

#### Scenario: Support successfully sent
- **WHEN** a current eligible cached document is delivered
- **THEN** its caption or associated message identifies cache timestamps and offers the authoritative source activity

### Requirement: Pending priority without false obligation
Pending work SHALL be the primary alert category. Closed-without-submission work SHALL NOT receive ordinary pending reminders. Unknown upload work SHALL receive qualified needs-verification information with a source link; practice/optionality descriptions SHALL remain visible.

#### Scenario: Visible but unresolved upload
- **WHEN** upload instructions are known but current state is unknown
- **THEN** a “Precisa verificar” notice links to ILIAS without calling the work definitely pending

### Requirement: Bounded delivery and fallback
The adapter SHALL respect configurable message and attachment limits, Telegram rate-limit retry instructions, and finite timeouts. Oversized or unavailable attachments SHALL produce a link-based fallback without suppressing the assignment alert.

#### Scenario: Document exceeds send limit
- **WHEN** a support file exceeds the configured Telegram attachment limit
- **THEN** the user receives its title and safe ILIAS link with an explanation instead of the file

#### Scenario: Rate limit response
- **WHEN** Telegram requests a retry delay
- **THEN** the event remains unsent with a bounded scheduled retry rather than an immediate retry loop

### Requirement: Secret-safe formatting and errors
The adapter SHALL escape untrusted titles and text, disable unsolicited URL previews, and redact bot tokens and session-bearing URLs from logs and errors. Failures SHALL remain observable through local diagnostics when Telegram itself is unavailable.

#### Scenario: Malicious title or transport error
- **WHEN** an assignment title contains formatting markup or a client error includes a token-bearing request URL
- **THEN** the title is rendered safely and the recorded error contains no token

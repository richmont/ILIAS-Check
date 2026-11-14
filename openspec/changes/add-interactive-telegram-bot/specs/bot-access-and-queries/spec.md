# Spec Delta

## Purpose

Let the configured learner inspect activity states and obtain support in a private chat without exposing their account or changing ILIAS work.

## ADDED Requirements

### Requirement: Authorize every interaction
Every command, callback, and download SHALL require the configured Telegram user ID and private chat ID. Unauthorized chats/users SHALL receive no activity, settings, history, or material data. Callback identifiers alone SHALL NOT authorize access.

#### Scenario: Forwarded material button
- **WHEN** another user presses a forwarded button or sends a known document identifier
- **THEN** no private metadata or document is returned

#### Scenario: Authorized user in an unauthorized chat
- **WHEN** the configured user invokes a command in a group or a different chat
- **THEN** private account information is not exposed there

### Requirement: Portuguese interface without source translation
Menus, command help, software status labels, and errors SHALL be Portuguese. Original ILIAS titles, instructions, filenames, and quoted source text SHALL retain their language and meaning. No AI, LLM, or translation service SHALL be required or contacted.

#### Scenario: Original German activity
- **WHEN** the learner opens its details from a Portuguese menu
- **THEN** Portuguese navigation surrounds the original German activity content

### Requirement: Pending-first separate activity views
The main view SHALL prioritize confirmed pending uploads. Separate queries SHALL expose submitted work, closed-without-submission work, and needs-verification candidates. Each view SHALL identify observation time and incomplete/stale coverage; no unknown candidate SHALL be silently treated as an all-clear.

#### Scenario: No pending work with unresolved sequence
- **WHEN** the latest observations contain zero confirmed pending units and one unresolved upload candidate
- **THEN** the bot points to needs-verification work rather than declaring that nothing needs attention

### Requirement: Honest delivery history
The submitted view SHALL show source activity/link, delivery time and attachment presence when known, personal/team scope, and evaluation/completion only when explicitly confirmed. It SHALL NOT download learner answers or equate submission with approval.

#### Scenario: Ungraded team submission
- **WHEN** a confirmed team delivery has an attachment but no grade
- **THEN** history identifies a team submission with attachment without claiming personal upload or approval

### Requirement: Original activity navigation
Activity details SHALL offer “Abrir no ILIAS” or “Abrir sequência” according to the resolved link kind. Links SHALL be session-free and subject to ordinary browser authentication. Original instructions SHALL remain available for manual verification.

#### Scenario: Unknown candidate
- **WHEN** the bot cannot interpret the current state
- **THEN** it shows “Inconclusivo — precisa verificar”, observation time, a brief explanation, the original link, and access to the software bug-report flow

#### Scenario: Feedback about an inconclusive activity
- **WHEN** an activity remains inconclusive because source details or sequence identifiers are unavailable
- **THEN** the bot invites the learner to explain how that activity should be displayed through the expected/actual software-feedback dialogue, without treating feedback alone as proof of delivery, completion, or non-applicability

### Requirement: Explicit support download request
An authorized request SHALL permit sending selected support with disclosure that it is transmitted through Telegram. Each delivery SHALL recheck activity applicability, current cache eligibility, and file integrity, and show download/expiry timestamps plus the authoritative source link. Old buttons or Telegram file IDs SHALL NOT bypass checks.

#### Scenario: Eligible cached support
- **WHEN** the authorized learner requests a valid cached worksheet
- **THEN** it is delivered with cache/source information without changing the ILIAS assignment

#### Scenario: Expired copy
- **WHEN** a requested copy has expired or its activity is confirmed submitted
- **THEN** the old bytes are not sent and the bot offers the source link or a newly eligible source retrieval

### Requirement: No learner submission capabilities
The bot SHALL NOT submit answers, forward user attachments to ILIAS, finish activities, change enrollment, or expose mutation commands. Incoming user files SHALL NOT be downloaded or interpreted as answer submissions.

#### Scenario: User sends an answer file
- **WHEN** the learner uploads a document to the chat
- **THEN** the bot explains that submission must be performed manually in ILIAS and does not forward or fetch the file body

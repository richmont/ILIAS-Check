# bot-bug-reports Specification

## Purpose

Help the learner describe unexpected bot behavior or extraction failures without automatically publishing private course or account data.

## Requirements

### Requirement: Structured software issue report
The authorized learner SHALL be able to report unexpected bot behavior using description, expected behavior, and actual behavior fields. An optional original activity link can provide context. The flow SHALL explain that it concerns this software, not complaints to teachers about course content.

#### Scenario: Parser misses visible platform information
- **WHEN** the learner reports information visible in ILIAS but absent or misinterpreted by the bot
- **THEN** the dialogue captures what was expected, what occurred, and an optional safe activity link

### Requirement: Review before sharing
Reports SHALL be shown as editable/cancelable previews before any sharing step. The initial flow SHALL provide a reviewed draft for manual issue submission, not create GitHub issues or contact administrators/teachers automatically.

#### Scenario: User cancels preview
- **WHEN** the learner cancels after reviewing the draft
- **THEN** nothing is published or sent to a report recipient

#### Scenario: User confirms export
- **WHEN** the learner confirms the reviewed report
- **THEN** the bot returns the draft to that authorized chat for manual sharing and clearly states it has not opened an issue

### Requirement: Minimal safe diagnostics
The bot SHALL NOT automatically attach raw HTML, documents, full logs, credentials, cookies, tokens, or learner answers to a report. Known secrets/session material SHALL be redacted from previews and exports. Free-text reporting SHALL warn the learner to review personal/course information before sharing.

#### Scenario: Known token pasted into report
- **WHEN** report text contains a configured secret or recognizable session token
- **THEN** preview/export masks that material and warns that automatic redaction does not guarantee removal of all personal information

### Requirement: Isolated short-lived report dialogue
Report dialogue state SHALL be scoped to the authorized user/chat, expire automatically, and support cancel/restart. An incomplete report SHALL NOT block pending notifications or alter activity status. Only explicit text replies SHALL populate report fields.

#### Scenario: User sends a document during reporting
- **WHEN** a report step receives an attachment rather than text
- **THEN** the bot does not download the attachment and asks for a text description

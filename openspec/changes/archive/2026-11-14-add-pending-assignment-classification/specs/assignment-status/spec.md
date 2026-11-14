# Spec Delta

## Purpose

Identify outstanding file-upload work using per-assignment evidence rather than exercise titles or missing page content.

## ADDED Requirements

### Requirement: Classify individual assignment units
The classifier SHALL evaluate each assignment unit independently and export its exercise ID, assignment ID when known, title, delivery type, paths, applicability, submission evidence, availability, status, and reason codes. Missing evidence SHALL be represented explicitly.

#### Scenario: Mixed delivery types
- **WHEN** an exercise contains one text unit and one file-upload unit
- **THEN** the text unit is excluded from upload reminders and the file unit is evaluated separately

#### Scenario: Multiple file units
- **WHEN** one file unit has a submission and another does not
- **THEN** the submitted unit does not hide the other unit's pending state

### Requirement: Conservative pending decisions
A unit SHALL be `pending` only when file delivery, applicability, current acceptance, and absence of a personal or applicable team submission are confirmed. Submission presence SHALL produce `submitted`, not an assertion that the work is approved or complete.

#### Scenario: Unsubmitted open unit
- **WHEN** an applicable file unit explicitly accepts submissions and confirms no existing submission
- **THEN** its status is `pending`

#### Scenario: Existing ungraded submission
- **WHEN** an applicable submission exists without a grade
- **THEN** its status is `submitted` and no approval is inferred

#### Scenario: Ambiguous submission list
- **WHEN** the submission list cannot be parsed or accessed
- **THEN** its status is `unknown`, not `pending` or `submitted`

### Requirement: Submission history metadata
Confirmed submission history SHALL expose activity identity/link, submission time when known, attachment presence when known, and personal/team scope. Approval, grades, and completion SHALL be reported only with explicit platform evidence. The system SHALL NOT download learner answers to populate history.

#### Scenario: Team delivery without a known uploader
- **WHEN** ILIAS confirms a team file submission and date without identifying a personal uploader
- **THEN** history records team delivery and the date without claiming the learner personally uploaded it

#### Scenario: Unknown attachment details
- **WHEN** submission evidence exists but file metadata or date is unavailable
- **THEN** those history fields remain unknown rather than becoming “no attachment” or an invented timestamp

### Requirement: Availability and deadline handling
The classifier SHALL distinguish `closed_without_submission`, `not_yet_open`, `excluded`, and `unknown` from `pending`. Deadlines SHALL include a configured installation timezone and an absolute instant when resolvable; explicit platform acceptance evidence SHALL take precedence over deadline inference.

#### Scenario: Closed historical exercise
- **WHEN** the platform confirms a file unit is closed and has no submission
- **THEN** it is reported as `closed_without_submission` and excluded from ordinary pending reminders

#### Scenario: Late submissions accepted
- **WHEN** the displayed deadline has passed but the platform explicitly accepts late file submission
- **THEN** the unit can remain `pending` with its overdue condition recorded

#### Scenario: Unparseable deadline
- **WHEN** the displayed deadline cannot be converted and current acceptance is not confirmed
- **THEN** the original deadline text is retained and availability remains `unknown`

### Requirement: Learning-sequence delivery evidence
The classifier SHALL inspect safely accessible sequence assignment metadata without starting, completing, or advancing learner steps. It SHALL retain unresolved steps as `unknown` and distinguish a direct assignment URL from a sequence-entry URL.

#### Scenario: Upload mentioned but form inaccessible
- **WHEN** a sequence instructs the learner to upload but its assignment state is not safely accessible
- **THEN** the result includes the instruction evidence, sequence-entry URL, and `unknown` status

### Requirement: Preserve uncertainty in exports
The result SHALL expose partial classification and warnings whenever an assignment or sequence cannot be evaluated. A run containing unresolved candidate upload work SHALL NOT be presented as a confirmed absence of pending work.

#### Scenario: No confirmed pending units but one unresolved sequence
- **WHEN** all evaluated units are submitted and one candidate remains unknown
- **THEN** the export reports partial coverage and the unresolved candidate rather than an all-clear result

### Requirement: Preserve consultable non-pending categories
Closed-without-submission and needs-verification work SHALL remain separately queryable with original links. Source practice/self-test or optionality metadata SHALL be preserved without an unsupported claim that every visible file exercise is obligatory.

#### Scenario: Self-test with upload support
- **WHEN** source instructions describe a file exercise as practice for an examination
- **THEN** exported metadata retains that description even if its open unsubmitted delivery is classified as pending

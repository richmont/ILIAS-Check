# Spec Delta

## Purpose

Give each assignment traceable support materials while making the strength and source of each association explicit.

## ADDED Requirements

### Requirement: Explicit association provenance
Each associated document SHALL include a stable document identity, title, safe source URL, source location, and association type: `assignment_attachment`, `instruction_link`, or `contextual`. Association SHALL NOT depend solely on similar filenames.

#### Scenario: Attachment on an assignment
- **WHEN** a document is listed in a unit's own attachment section
- **THEN** it is associated with that unit as `assignment_attachment`

#### Scenario: Sibling folder document
- **WHEN** a document shares the assignment's folder but lacks an explicit link to the unit
- **THEN** any association is labeled `contextual`, never a confirmed attachment

### Requirement: Conservative default document selection
Automatic downloads SHALL select confirmed assignment attachments and explicit instruction-linked support for confirmed pending units. Contextual files SHALL require opt-in. Submitted, excluded, closed, and unknown units SHALL NOT trigger automatic support downloads by default.

#### Scenario: Unknown assignment
- **WHEN** a candidate assignment cannot be classified definitively
- **THEN** discovered document metadata remains available without automatically downloading its documents

#### Scenario: Contextual materials disabled
- **WHEN** a folder contains presentations and unrelated files with contextual selection disabled
- **THEN** only explicitly associated support is selected for download

### Requirement: Exclude known answer materials
Documents identified by platform sections or explicit labels as model answers, feedback, or learner submissions SHALL NOT be selected as support. Ambiguous roles SHALL be flagged for review rather than silently treated as instructions.

#### Scenario: Model answer alongside worksheet
- **WHEN** an exercise exposes an assignment worksheet and a labeled sample solution
- **THEN** only the worksheet is automatically selected

### Requirement: Sequence document transparency
The system SHALL retain the sequence-entry URL and visible document titles when sequence files cannot be accessed safely. It SHALL NOT advance steps or fabricate document URLs to obtain support.

#### Scenario: Inaccessible sequence attachment
- **WHEN** the sequence lists a worksheet without a safely resolvable download link
- **THEN** the result marks that document unavailable and points to the sequence for manual access

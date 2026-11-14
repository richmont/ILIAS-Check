# Spec Delta

## Purpose

Restrict pending-work decisions to the configured learner's assignments without assuming ownership of every visible group exercise.

## ADDED Requirements

### Requirement: Evidence-based group applicability
The classifier SHALL use explicit platform ownership or user-configured exercise IDs to determine group applicability. A title such as “Group 1” alone SHALL NOT establish ownership. Ambiguous alternatives SHALL be reported as applicability unknown and excluded from definitive pending reminders.

#### Scenario: Five visible group alternatives
- **WHEN** five alternative group exercises are visible without ownership evidence or user selection
- **THEN** the classifier does not label all five as the learner's pending work

#### Scenario: Explicit exercise selection
- **WHEN** the user selects one alternative inside an explicitly declared alternative set using its exercise reference ID
- **THEN** that alternative is evaluated and only unselected members of that set are excluded

#### Scenario: New individual work outside the alternative set
- **WHEN** a selected group alternative coexists with a newly discovered individual assignment
- **THEN** the individual assignment remains eligible for normal classification

### Requirement: Team submission semantics
For a team assignment, the classifier SHALL evaluate the submission of the learner's confirmed team rather than only personally uploaded files. Unresolved team identity or inaccessible team delivery evidence SHALL prevent a definitive pending decision.

#### Scenario: Teammate already submitted
- **WHEN** the platform confirms that a file was submitted for the learner's team
- **THEN** the unit is `submitted` even when the learner personally uploaded no file

#### Scenario: Team membership unavailable
- **WHEN** a team-delivery unit is visible but the learner's team cannot be established
- **THEN** the unit has unknown applicability or submission state and is not a confirmed pending reminder

### Requirement: Stable explicit scope
The user SHALL be able to select alternatives within declared sets and exclude exercises by stable IDs. Alternative selection SHALL NOT become a global allowlist. Explicit exclusions SHALL take precedence over selection, and decisions SHALL appear as reason codes without altering remote memberships.

#### Scenario: Conflicting explicit rules
- **WHEN** an exercise is both selected and excluded
- **THEN** it is excluded with a configuration warning and no ILIAS membership changes occur

### Requirement: Do not equate visibility with obligation
The classifier SHALL distinguish configured requirement metadata from claims about curriculum obligation. Historical cohort references, practice descriptions, and unknown membership context SHALL remain visible without being promoted to confirmed current obligations.

#### Scenario: Historical cohort instruction
- **WHEN** a visible exercise contains an old cohort instruction and a closed historical deadline
- **THEN** it remains historical work rather than a new current pending obligation

# repository-inventory Specification

## Purpose

Provide a bounded, account-authorized inventory that later features can consume without depending on MCP or Telegram.

## Requirements

### Requirement: Authenticate against the credential form
The collector SHALL select the authentication form containing a password input rather than a search form, preserve required hidden inputs, and resolve relative actions from the actual login-page URL. An error page or missing credential form SHALL fail authentication without posting credentials to another form.

#### Scenario: Search form precedes login
- **WHEN** the supported login page contains a search form before its password form
- **THEN** credentials are posted only to the password form's validated same-origin action

#### Scenario: Invalid client ID
- **WHEN** the login request resolves to an error page with only a search form
- **THEN** authentication fails without submitting that form

### Requirement: Bounded descendant traversal
The collector SHALL traverse authorized descendants of configured roots, deduplicate object requests, preserve all discovered root-relative paths, and stop at configured limits. Breadcrumbs, navigation menus, and external origins SHALL NOT expand the collection scope.

#### Scenario: Overlapping roots and cycles
- **WHEN** two roots reach the same folder and that folder links back to an ancestor
- **THEN** the object is fetched at most once per run while its discovered paths remain available

#### Scenario: Request budget reached
- **WHEN** traversal exhausts its request or depth budget before finishing
- **THEN** the inventory reports incomplete coverage and identifies the affected scope

### Requirement: Discover supported ILIAS objects
The collector SHALL recognize supported modern and legacy reference links and inventory folders, exercises, learning modules, learning sequences, and document metadata. An unresolved sequence or unsupported container SHALL remain visible with a coverage warning rather than appear empty.

#### Scenario: Exercise in a learning sequence
- **WHEN** a sequence exposes steps without ordinary exercise hyperlinks
- **THEN** the inventory records the sequence and its unresolved steps without advancing learner progress

### Requirement: Read-only remote behavior
Except for authentication and session maintenance, collection SHALL NOT invoke submission, deletion, membership, preference, test-answer, or learning-completion actions. Redirects and credential destinations SHALL be restricted to the configured origin.

#### Scenario: Navigation includes an unsubscribe action
- **WHEN** an inspected page includes links to leave a sequence or group
- **THEN** those links are not requested

#### Scenario: Expired session
- **WHEN** a safe read returns a recognized login page
- **THEN** the collector reauthenticates at most once for that read before reporting failure

#### Scenario: Platform access logging
- **WHEN** ordinary authorized page reads are recorded by ILIAS
- **THEN** documentation does not claim invisible access or zero platform-side view records while explicit completion/mutation actions remain prohibited

### Requirement: Original source text without translation
The collector SHALL preserve ILIAS titles, instructions, and filenames in their source language. It SHALL NOT require an AI model or call translation providers. Presentation escaping and whitespace normalization SHALL NOT change source meaning.

#### Scenario: German instructions
- **WHEN** a supported activity contains German title and instruction text
- **THEN** exported source content remains German and no translation or LLM request is made

### Requirement: Safe original activity links
Activity links SHALL identify the source activity without session material and distinguish sequence entry from a resolved activity. Browser authentication can still be required; the collector SHALL NOT manufacture a session-sharing or direct-upload URL.

#### Scenario: Login required in browser
- **WHEN** an exported activity link is opened without a browser session
- **THEN** the link identifies the activity while any login requirement remains under ILIAS control

### Requirement: Versioned JSON and explicit coverage
The collector SHALL export schema version, UTC check time, root scope, object identities, paths, safe URLs, coverage, and structured errors. The CLI SHALL emit JSON on stdout, diagnostics on stderr, and distinguish complete success, partial collection, and fatal failure using exit codes.

#### Scenario: One root fails
- **WHEN** one root is inaccessible and another is successfully inventoried
- **THEN** valid results are retained with partial coverage and a non-success exit code

#### Scenario: Confirmed empty root
- **WHEN** a supported root is successfully parsed and contains no objects
- **THEN** the JSON distinguishes its complete empty inventory from an inaccessible or unsupported root

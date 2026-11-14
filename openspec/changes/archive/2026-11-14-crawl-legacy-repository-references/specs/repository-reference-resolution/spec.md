# Spec Delta

## Purpose

Resolve legacy ILIAS repository references that omit a concrete object type,
while keeping unresolved references visible in bounded inventory results.

## ADDED Requirements

### Requirement: Crawl validated legacy repository references
The collector SHALL retain a same-origin legacy repository reference with a positive `ref_id` when its repository base class is recognized but its concrete object type is absent. It SHALL use only a validated read route to inspect the referenced page and SHALL continue to enforce the configured request budget and redirect policy.

#### Scenario: Legacy reference exposes a supported object type
- **WHEN** a readable legacy reference page exposes a supported concrete object type in passive page metadata
- **THEN** the inventory records the resolved type and the collector continues bounded traversal from that object

#### Scenario: Legacy reference does not expose a concrete type
- **WHEN** a readable legacy reference page does not expose a supported concrete object type
- **THEN** the inventory retains the object as unresolved, reports incomplete root coverage, and preserves any child repository links found in recognized content

#### Scenario: Legacy reference is not safe to read
- **WHEN** a legacy reference has an invalid identifier, a different origin, session material, or an action parameter
- **THEN** the collector does not request that reference and does not treat it as a discovered repository object

### Requirement: Make unresolved legacy references explicit
The inventory SHALL distinguish an unresolved legacy object from a confirmed empty repository result and SHALL identify why root coverage is incomplete.

#### Scenario: Unresolved object appears in inventory
- **WHEN** a legacy reference page is read successfully but its concrete type cannot be resolved
- **THEN** the object remains in the inventory with an explicit unresolved type and warning, and its root coverage includes an unresolved-reference warning

#### Scenario: Legacy reference read fails
- **WHEN** a validated legacy reference cannot be read within the existing transport and request limits
- **THEN** the collector retains partial results, marks the affected root incomplete, and reports a sanitized object-read error

### Requirement: Support the target's bounded read-only login handshake
The transport SHALL allow only the target's observed, read-only login-navigation commands and exact password-login POST route. It SHALL continue to reject mutation commands, bracketed action parameters, sensitive URL material, off-origin redirects, and credential replay to POST redirect targets.

#### Scenario: Target login navigation uses an explicit read-only command
- **WHEN** the same-origin login flow redirects through an empty repository `cmd`, `cmd=infoScreen`, or `login.php?cmd=force_login`
- **THEN** the transport follows only those exact allowlisted reads and applies the ordinary path, origin, redirect, and request-budget checks

#### Scenario: Target password form posts to the legacy startup route
- **WHEN** the password form posts to `ilias.php` with `baseClass=ilStartupGUI`, `cmd=post`, and `fallbackCmd=doStandardAuthentication`
- **THEN** the transport sends one validated login POST and does not follow its redirect; authentication then verifies the session with a separate safe dashboard GET

#### Scenario: Other ILIAS action parameters remain blocked
- **WHEN** a read URL contains a bracketed command such as `cmd[next]`, or a non-allowlisted action command
- **THEN** the request is rejected before reaching the HTTP session

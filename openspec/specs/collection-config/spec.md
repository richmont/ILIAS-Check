# collection-config Specification

## Purpose

Make collection scope and credentials explicit, reproducible, and safe for both interactive and scheduled execution.

## Requirements

### Requirement: Explicit environment configuration
The collector SHALL accept installation URL, client ID, credentials, and root reference IDs through environment variables. Process environment values SHALL take precedence over an explicitly selected dotenv file. It SHALL NOT discover dotenv files in ancestor directories.

#### Scenario: Scheduled execution from another directory
- **WHEN** the caller selects an absolute dotenv path and runs from an unrelated directory
- **THEN** configuration is loaded from that file and process environment, not from the working directory's ancestors

#### Scenario: Environment overrides dotenv
- **WHEN** both sources define `ILIAS_PENDING_ROOTS`
- **THEN** the process environment value determines the collection roots

### Requirement: Validate before accessing ILIAS
The collector SHALL reject missing credentials, empty roots, invalid reference IDs, unsafe base URLs, and invalid traversal limits before issuing network requests. Duplicate root IDs SHALL be normalized without discarding their provenance.

#### Scenario: Missing roots
- **WHEN** `ILIAS_PENDING_ROOTS` is missing or contains no valid root IDs
- **THEN** execution returns a configuration error and makes no remote requests

#### Scenario: Duplicate roots
- **WHEN** roots contain `1001,1001,1002`
- **THEN** discovery schedules each root once and records the selected root scope

### Requirement: Conservative transport configuration
The collector SHALL require HTTPS with certificate verification, finite request timeouts, and positive depth and request budgets. It SHALL NOT guess an installation-specific client ID when none is configured.

#### Scenario: Invalid transport settings
- **WHEN** the base URL uses HTTP or the request timeout is zero
- **THEN** validation rejects the configuration before authentication

### Requirement: Protect configuration secrets
The collector SHALL omit passwords, cookies, authentication tokens, and token-bearing URLs from logs and exported JSON. Example configuration SHALL contain placeholders only.

#### Scenario: Authentication error
- **WHEN** authentication fails after credentials were loaded
- **THEN** the error identifies the failure category without echoing credentials or session material

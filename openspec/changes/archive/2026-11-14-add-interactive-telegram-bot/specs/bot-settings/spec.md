# Spec Delta

## Purpose

Expose understandable retention preferences and cache status without giving chat interactions control over host security or storage capacity.

## ADDED Requirements

### Requirement: Authorized retention menu
The settings menu SHALL expose the effective retention policy, the seven-day no-deadline default, and a configurable positive retention preference for the authorized learner. Known deadlines and confirmed submission/completion SHALL remain upper bounds. Changes SHALL persist across bot and scheduled-monitor restarts.

#### Scenario: User shortens retention
- **WHEN** a valid shorter retention preference is saved
- **THEN** later accesses and automatic maintenance apply it without extending any known deadline

#### Scenario: User increases retention after expiry
- **WHEN** the user increases TTL after a copy expired
- **THEN** the expired bytes are not resurrected; any new retrieval requires current activity eligibility

### Requirement: Host-only capacity and secret settings
Cache quota, credentials, destination authorization, and storage paths SHALL remain host-controlled. The bot SHALL NOT expose setters for these values, including through forged callbacks or stored preference keys. Changing user retention SHALL NOT raise the host capacity limit.

#### Scenario: Quota override attempt
- **WHEN** a callback attempts to change `ILIAS_SUPPORT_CACHE_MAX_BYTES`
- **THEN** it is rejected and the administrator's configured value remains effective

### Requirement: Cache usage visibility
Settings SHALL show managed cache bytes used, host-configured capacity, human-readable units, and the measurement time. The initial capacity SHALL be shown as 200 MB for 200000000 bytes. The menu SHALL explain automatic expiration/eviction and that usage is not total host disk usage.

#### Scenario: Partially occupied cache
- **WHEN** the learner opens settings
- **THEN** measured managed usage and the configured limit are displayed without exposing private host filesystem paths

### Requirement: No manual cleanup operation
The bot SHALL NOT offer purge, clear-cache, delete-cache, or quota-edit operations. Invalid zero/negative/infinite TTL inputs SHALL NOT function as disguised purge commands. Valid retention changes SHALL rely on the automatic lifecycle rather than an immediate user-triggered cleanup action.

#### Scenario: Request to clear cache
- **WHEN** a user requests an unsupported cache-clear command or callback
- **THEN** no cleanup is initiated by that command and the bot explains that maintenance is automatic

### Requirement: Local preferences without source modification
Settings SHALL change local bot behavior only, preserve original ILIAS content, and remain independent of AI/translation services. The interface SHALL NOT offer course-text translation or imply that Portuguese labels are ILIAS-authored instructions.

#### Scenario: Settings update
- **WHEN** the learner changes a supported retention preference
- **THEN** no ILIAS preference or activity is modified and source text remains original

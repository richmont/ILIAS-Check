# Proposal

## Why

Finding assignments in nested ILIAS folders is difficult and deployment-specific. A transport-independent, read-only collector provides a reliable inventory for later classification without requiring a chat agent or manual navigation.

## What Changes

- Add a Python CLI and importable collection API for one configured account.
- Configure credentials, installation, client ID, root reference IDs, and traversal limits through environment variables and an explicitly selected `.env`.
- Authenticate against supported ILIAS 9_23 forms and traverse authorized descendants, including learning-sequence discovery.
- Export a versioned JSON inventory with provenance, coverage, and structured errors.
- Define safe request handling, fixture-based tests, and licensing provenance before reusing upstream code.
- Preserve original ILIAS text and source links without AI or translation dependencies.
- Reuse only necessary MIT authentication/utilities with notices, not the MCP runtime or mutation services.
- Dependencies: none; this is the first implementation milestone.
- Non-goals: pending-work decisions, document downloads, Telegram, scheduling, answer submission, translation/LLM integration, and arbitrary ILIAS-version support.

## Capabilities

### New Capabilities

- `collection-config`: Deterministic environment configuration and validation.
- `repository-inventory`: Read-only authentication, bounded discovery, and JSON inventory.

### Modified Capabilities

None.

## Impact

Introduces the application package, CLI, JSON contract, tests, and setup documentation. Likely dependencies are an HTTP client, HTML parser, and dotenv loader; versions and the MIT reuse boundary must be recorded during implementation. No MCP server or live course data is required in the repository.

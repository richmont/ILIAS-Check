# Tasks

## 1. Preserve and validate legacy read references

- [x] 1.1 Extend legacy reference normalization to retain a sanitized same-origin `ilRepositoryGUI` read URL separately from the inventory URL; add tests for positive IDs, malformed IDs, off-origin URLs, session material, and action parameters.
- [x] 1.2 Add response type-resolution helpers for explicit supported type/ID evidence in the final safe URL or passive page metadata; verify recognized and rejected metadata with synthetic fixtures.

## 2. Traverse resolved and unresolved objects

- [x] 2.1 Fetch validated unresolved legacy references through the existing safe transport, keep readable unresolved objects and their content-scoped child links visible, and mark coverage incomplete with an explicit warning; verify readable and failed read cases with fake-authenticator tests.
- [x] 2.2 Promote a legacy identity to its resolved object identity while preserving paths and parsed metadata; verify modern and legacy links to the same object cause one fetch and one inventory record.

## 3. Verify and document the inventory behavior

- [x] 3.1 Update inventory/collector documentation for resolved and unresolved legacy references and add a schema-validation test for the unresolved serialized record; verify the documented warning and URL behavior match the output.
- [x] 3.2 Run the complete offline test suite and OpenSpec validation; verify modern-link behavior remains unchanged and no live credentials or network access are required.

## Workflow follow-up

- Perform any live compatibility check against the primary ILIAS target only after explicit authorization.
- Archive the change after implementation and review are complete.

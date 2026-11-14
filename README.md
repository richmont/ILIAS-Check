# ILIAS-Check

Read-only ILIAS assignment monitoring and support-material access, with a planned
Portuguese Telegram interface.

## Scope

- Discover pending file-upload assignments below configured repository roots.
- Preserve original ILIAS titles and instructions; no AI or translation service.
- Link users to the original activity or learning sequence for manual action.
- Offer authorized support-material downloads, never upload answers to ILIAS.
- Keep submission metadata separate from approval or pedagogical completion.
- Cache support files temporarily with automatic cleanup and a host-set quota.

See [project decisions](docs/decisions.md) for confirmed behavior, configuration
boundaries, cache lifecycle, and known technical limitations.

## Implementation roadmap

Planning artifacts live under `openspec/changes/`, in dependency order:

1. `add-read-only-collector`
2. `add-pending-assignment-classification`
3. `add-support-document-cache`
4. `add-scheduled-telegram-monitor`
5. `add-interactive-telegram-bot`

Each change contains a proposal, specifications, design, and unchecked tasks.
OpenSpec integration is configured for OpenCode. Planning validation does not
constitute a live compatibility test.

## Collector setup

The first implementation milestone is the Python 3.11+ read-only collector.
See [collector setup](docs/collector.md) for isolated installation, explicit
environment configuration, scope limits, and privacy notes. Never commit
credentials, runtime inventories, or course materials.

## License

The project retains its existing AGPL-3.0 license. Any reused MIT authentication
or utility code must retain its original notices and recorded upstream provenance.
See [third-party notices](THIRD_PARTY_NOTICES.md). Course materials are not
covered by the software license and must not be committed.

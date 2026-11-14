# Collector review issues

Findings from the post-implementation review of commit `8c6c639` are tracked as
GitHub Issues in `richmont/ILIAS-Check`:

| Issue | Finding |
| --- | --- |
| [#1](https://github.com/richmont/ILIAS-Check/issues/1) | Legacy repository references can be classified as unsupported and skipped |
| [#2](https://github.com/richmont/ILIAS-Check/issues/2) | Password whitespace is stripped during configuration loading |
| [#3](https://github.com/richmont/ILIAS-Check/issues/3) | Bracketed ILIAS action parameters can bypass the read-URL denylist |
| [#4](https://github.com/richmont/ILIAS-Check/issues/4) | Some expired login pages may not match the fixed session-expiry markers |

These are open review findings, not fixes. The collector remains unvalidated
against a live ILIAS installation; any live compatibility test requires
separate authorization.

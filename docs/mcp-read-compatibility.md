# MCP read compatibility

The reference is [richmont/ilias-mcp](https://github.com/richmont/ilias-mcp/tree/ca4f4ee5a14df65e462d87ee49e38045457f52b3),
revision `ca4f4ee5a14df65e462d87ee49e38045457f52b3`. Compatibility here concerns
the repository and exercise reads used by the checker. It does not introduce
the MCP's calendar, news, search, answer upload/deletion, or membership tools.

| MCP read behavior | Checker behavior |
| --- | --- |
| Repository content containers and list rows | Recognizes `ilContentContainer`, `il_center_col`, `mainscrolldiv`, `ilContainerContent`, legacy rows and modern item classes |
| Links and buttons | Reads `href` and `data-action`; retains source row titles and accessible labels |
| `/go/...`, goto targets, legacy `ref_id` links | Resolves stable object identities and canonicalizes source links |
| File `_download` and `sendfile` links in listings | Preserves document identity/title/source URL as metadata; does not request file bytes |
| Repository `cmd=view` | Accepts the validated read-only route shape |
| Exercise overview | Requests `ilObjExerciseGUI`, `showOverview`, `mode=all`, `from_overview=1`, including closed/future units |
| Assignment metadata | Exports `ass_id`, title, source deadline and status; additionally preserves instructions, requirement and delivery type |
| References exposed only in the all-unit overview | Merges support-document and child-object references into the normal inventory traversal without downloading files |
| Submitted file lists | Reads each exposed `ilExSubmissionFileGUI` / `submissionScreen` route and exports delivery ID, filename, submitter and source date |
| Team members | Reads exposed `ilExSubmissionTeamGUI` / `submissionScreenTeam` routes and exports user ID and name |

Every request goes through the existing same-origin, installation-path,
timeout, retry, redirect, request-budget and authentication boundaries. Added
commands are allowed only in complete route shapes with valid reference IDs,
the expected controller, and a bounded set of parameter names. Mutation commands,
bracketed actions, off-origin links, and session/token-bearing links remain
rejected. Download-looking references are used to identify files, not to execute
their download command.

The checker preserves dynamic `cmdNode` values from each unit's own validated
link. Unlike the MCP fallback, it does not substitute an assignment ID into
another unit's link or invent a submission screen when no safe link was exposed.
For file units without that screen it reads the unit's own validated
`ilAssignmentPresentationGUI` link. A recognized `Einreichung` panel can explicitly
confirm an empty delivery even after the upload controls disappear. Blank detail
panels produce `assignment_detail_unavailable` and partial coverage, never an
invented empty list or a claim about ownership.
Unreadable/unknown lists stay `null`; an explicit empty list is `[]`. The source
status string is not a definitive pending/approved/completed classification.
Icons can establish object type; titles alone do not establish team ownership.
Breadcrumbs and navigation are excluded even when nested inside a content root.

Offline verification uses synthetic fixtures and the upstream parser contracts.
A direct comparison against that pinned revision confirmed matching repository,
assignment, submitted-file, and team-member fields on supported layouts, after
mapping the MCP `file` type to the checker's `document` and excluding a breadcrumb
the MCP retains. Tests also cover nested assignment headers, distinct dynamic
routes per unit, partial failures, unknown/empty lists, and rejected action links.
The tests require neither the MCP runtime nor real account credentials.

An authorized live test subsequently used the local checker CLI and local
configuration directly, without a connected MCP session. It exposed an exercise
redirect through `ilExerciseHandlerGUI`, submission-screen links that retain
`mode=all&from_overview=1`, and an empty delivery table with `td.ilCenter` and
`Keine Einträge`. These layouts are now supported and covered by synthetic
regression tests. Unknown layouts still remain unknown; equality on every page
of the real installation is not established. A subsequent correction allows the
observed learning-module `ilLMPresentationGUI` / `resume` landing route with a
strict parameter allowlist. In the
[ILIAS 9 source](https://github.com/ILIAS-eLearning/ILIAS/blob/release_9/Modules/LearningModule/Presentation/class.ilLMPresentationGUI.php),
`resume()` renders the module layout. Generic legacy references can additionally
resolve from their own `#headerimage` object icon, and resolved aliases are reused
without recreating duplicate objects. `lso` is recognized as a learning sequence;
its visible workflow outline is exported without inventing missing child IDs.
Unresolved sequence steps are not advanced automatically. See
[live check results](live-check.md).

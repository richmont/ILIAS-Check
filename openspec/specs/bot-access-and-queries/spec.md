# bot-access-and-queries Specification

## Purpose

Let the configured learner inspect activity states and obtain support in a private chat without exposing their account or changing ILIAS work.

## Requirements

### Requirement: Authorize every interaction
Every command, callback, and download SHALL require an explicitly authorized user in a permitted private chat. Listed users SHALL be accepted in their own private chats regardless of which listed user receives automatic notifications. The notification destination SHALL NOT veto a permitted user's own chat. Unauthorized chats/users SHALL receive no account data. Callback identifiers alone SHALL NOT authorize access.

#### Scenario: Forwarded material button
- **WHEN** an unauthorized user presses a forwarded button or sends a known document identifier
- **THEN** no private metadata or document is returned

#### Scenario: Authorized user in an unauthorized chat
- **WHEN** an authorized user invokes a command in a group or another person's private chat
- **THEN** private account information is not exposed there

### Requirement: Portuguese interface without source translation
Menus, command help, software status labels, and errors SHALL be Portuguese. Original ILIAS titles, instructions, filenames, and quoted source text SHALL retain their language and meaning. No AI, LLM, or translation service SHALL be required or contacted.

#### Scenario: Original German activity
- **WHEN** the learner opens its details from a Portuguese menu
- **THEN** Portuguese navigation surrounds the original German activity content

### Requirement: Pending-first separate activity views
The main view SHALL prioritize confirmed pending uploads. Separate queries SHALL expose submitted work, closed-without-submission work, not-yet-open work via `/futuras`, and needs-verification candidates. `/resumo` SHALL report counts by state without pretending that incomplete evidence is an empty successful collection. Each view SHALL identify observation time and incomplete/stale coverage; no unknown candidate SHALL be silently treated as an all-clear.

#### Scenario: No pending work with unresolved sequence
- **WHEN** the latest observations contain zero confirmed pending units and one unresolved upload candidate
- **THEN** the bot points to needs-verification work rather than declaring that nothing needs attention

### Requirement: Honest delivery history
The submitted view SHALL show source activity/link, delivery time and attachment presence when known, personal/team scope, and evaluation/completion only when explicitly confirmed. It SHALL NOT download learner answers or equate submission with approval.

#### Scenario: Ungraded team submission
- **WHEN** a confirmed team delivery has an attachment but no grade
- **THEN** history identifies a team submission with attachment without claiming personal upload or approval

### Requirement: Original activity navigation
Activity details SHALL offer “Abrir no ILIAS” or “Abrir sequência” according to the resolved link kind. Links SHALL be session-free and subject to ordinary browser authentication. Original instructions SHALL remain available for manual verification.

#### Scenario: Unknown candidate
- **WHEN** the bot cannot interpret the current state
- **THEN** it shows “Inconclusivo — precisa verificar”, observation time, a brief explanation, the original link, and access to the software bug-report flow

#### Scenario: Feedback about an inconclusive activity
- **WHEN** an activity remains inconclusive because source details or sequence identifiers are unavailable
- **THEN** the bot invites the learner to explain how that activity should be displayed through the expected/actual software-feedback dialogue, without treating feedback alone as proof of delivery, completion, or non-applicability

### Requirement: Explicit support download request
An authorized request SHALL permit sending selected support with disclosure that it is transmitted through Telegram. Each delivery SHALL recheck activity applicability, current cache eligibility, and file integrity, and show download/expiry timestamps plus the authoritative source link. Old buttons or Telegram file IDs SHALL NOT bypass checks.

#### Scenario: Eligible cached support
- **WHEN** the authorized learner requests a valid cached worksheet
- **THEN** it is delivered with cache/source information without changing the ILIAS assignment

#### Scenario: Expired copy
- **WHEN** a requested copy has expired or its activity is confirmed submitted
- **THEN** the old bytes are not sent and the bot offers the source link or a newly eligible source retrieval

### Requirement: No learner submission capabilities
The bot SHALL NOT submit answers, forward user attachments to ILIAS, finish activities, change enrollment, or expose mutation commands. Incoming user files SHALL NOT be downloaded or interpreted as answer submissions.

#### Scenario: User sends an answer file
- **WHEN** the learner uploads a document to the chat
- **THEN** the bot explains that submission must be performed manually in ILIAS and does not forward or fetch the file body

### Requirement: Button-based compact activity pagination
Activity-list commands SHALL open page one as one compact message with total count, observation time, page position, and at most five summaries. “Anterior” and “Próxima” buttons SHALL navigate pages; numeric command arguments SHALL NOT select a page. Numbered buttons SHALL open only the selected detail. Only an explicit “Exibir todas” click SHALL expand all details. Material lists SHALL also use navigation buttons, with at most ten materials per page.

#### Scenario: Twelve pending tasks
- **WHEN** an authorized user sends `/pendentes`
- **THEN** one message shows the total of twelve tasks, the first five summaries, numbered detail buttons, “Próxima”, and “Exibir todas”, without requiring `/pendentes 2`

#### Scenario: Next and previous page
- **WHEN** the user presses “Próxima” and then “Anterior”
- **THEN** each click produces only the requested compact page with freshly generated navigation buttons

#### Scenario: Explicit expansion
- **WHEN** the user presses “Exibir todas”
- **THEN** the bot may send all activity details, including source and eligible download actions, instead of only the current compact page

#### Scenario: Historical or changed detail
- **WHEN** a detail button came from submitted history or a stale needs-verification view
- **THEN** its detail retains that view's history or uncertainty rather than silently showing the currently reopened pending activity; if it no longer belongs to the view, the user is asked to reopen the list

### Requirement: Register commands and separate help
The worker SHALL register its supported Portuguese command menu with Telegram at startup. `/ajuda` SHALL return help only; `/start` SHALL return help and the first pending page. The menu SHALL include the implemented query, material, settings, retention, report, and cancellation commands.

#### Scenario: Discover available commands
- **WHEN** the worker starts and the learner opens the Telegram slash-command menu
- **THEN** the supported commands have Portuguese descriptions registered through `setMyCommands`

#### Scenario: Help without activity queries
- **WHEN** an authorized user invokes `/ajuda`
- **THEN** one help response is returned without opening `/verificar` or any activity list

### Requirement: Download actions in pending details
Pending activity details SHALL offer up to two selected-support download buttons, including metadata-only references, alongside source navigation. Clicking SHALL authorize only that transmission after fresh activity, cache, and file eligibility checks. The compact monitor summary SHALL direct users to `/pendentes` instead of adding per-task download messages.

#### Scenario: Metadata-only worksheet
- **WHEN** a pending activity has an explicitly selected support worksheet with no cached body
- **THEN** opening its details offers its download button and a click retrieves and transmits only that worksheet after any necessary ILIAS eligibility check

#### Scenario: Durable token after restart
- **WHEN** an authorized user presses an unexpired durable material button after worker restart
- **THEN** it can be claimed once from SQLite and fresh eligibility checks still apply

### Requirement: Explicit shared-account user allowlist
`TELEGRAM_ALLOWED_USER_ID` SHALL identify the primary owner when configured; `TELEGRAM_ALLOWED_USER_IDS` MAY add positive user IDs sharing the same ILIAS account. Replies SHALL go to the requesting authorized private chat. Monitor notifications SHALL retain their configured destination without automatic fan-out. Report drafts, navigation tokens, and rate limits SHALL be isolated per user.

#### Scenario: Additional authorized learner
- **WHEN** a user listed in `TELEGRAM_ALLOWED_USER_IDS` requests `/pendentes` in their own private chat
- **THEN** the response goes to that chat without changing the monitor destination or another user's draft or navigation state

### Requirement: Expiring authorized action tokens
Transient navigation buttons SHALL be user-bound, single-use, and expire after thirty minutes or worker restart. Durable material tokens SHALL be account-scoped, single-use, expire after twenty-four hours, and survive worker restart. All tokens SHALL require interaction authorization before being claimed and SHALL NOT bypass fresh delivery checks.

#### Scenario: Expired or forwarded navigation
- **WHEN** a user presents another user's navigation token or replays an expired or consumed token
- **THEN** no activity details or documents are returned through that token

### Requirement: Serve valid local support before source refresh
An authorized material click SHALL first try the account-scoped local cache using current stored activity evidence. A valid copy SHALL be sent without collection, authentication, or another body download, even when automatic downloads are disabled. Interactive local delivery SHALL require a current pending observation at most twelve hours old, selected support, integrity, expiry, and the configured file-validation interval. Newer contradictory or unknown evidence SHALL block reuse.

#### Scenario: Valid cached worksheet
- **WHEN** a current pending observation selects an intact, unexpired, recently validated cached worksheet
- **THEN** the button sends that local copy without ILIAS requests and without consuming or being blocked by the five-minute source-refresh throttle

#### Scenario: Stale or invalid local evidence
- **WHEN** the copy is missing, expired, corrupt, no longer selected, or its activity or validation evidence is too old
- **THEN** the old bytes are not sent; a permitted bounded source refresh may establish eligibility and retrieve only the selected material

### Requirement: Visible material-request progress and failures
A material request SHALL give a chat response before checking the cache and before any slow source refresh. Upload failures SHALL produce a safe source-linked message without triggering another collection or automatic duplicate upload. Expired buttons and refresh throttling SHALL produce actionable responses instead of silent completion.

#### Scenario: Slow source check after cache miss
- **WHEN** a material click requires a full source refresh
- **THEN** the bot first announces the two-minute request limit rather than only dismissing the callback loading animation

#### Scenario: Ambiguous cached upload outcome
- **WHEN** Telegram cannot confirm acceptance of a locally cached file
- **THEN** the bot reports the uncertain send and offers the source without fetching or sending another copy automatically

### Requirement: Show live local material availability
Material buttons and pending details SHALL distinguish “📦 disponível no cache”, “🔄 cache precisa revalidar”, “🌐 obter do ILIAS”, and “❔ cache não verificado”. Availability SHALL inspect the current account-scoped cache locally, using the interactive delivery rules rather than trusting an old inventory flag. A busy or unreadable store SHALL NOT be reported as an available or absent copy. Display labels SHALL NOT bypass delivery-time checks.

#### Scenario: Download after saved observation
- **WHEN** a manual download populated the cache after the last inventory was saved
- **THEN** opening the material menu or activity detail shows the current local availability without another ILIAS request

#### Scenario: File exists but observation is stale
- **WHEN** intact local bytes exist but interactive observation or validation evidence exceeds its allowed age
- **THEN** the interface shows a revalidation requirement rather than promising immediate local delivery

### Requirement: Bound interactive material work
An interactive material request SHALL have a two-minute elapsed-time limit covering local lookup, source refresh, retrieval, and upload. Expiration SHALL interrupt synchronous work, release locks, close transports and partial transfers, and return a safe timeout response with source navigation. It SHALL NOT leave an abandoned collector running or store a partial inventory as a completed observation. Ordinary monitor runs SHALL retain their separate limits.

#### Scenario: Slow source traversal
- **WHEN** a material refresh reaches two minutes before completing
- **THEN** source work stops, the previous observation remains intact, and the bot reports the timeout with a manual source link

#### Scenario: Lookup hours after scheduled collection
- **WHEN** the latest current pending observation is six hours old and the local copy passes file-validation, association, expiry, and integrity checks
- **THEN** an explicit request sends that copy without a source refresh, while automatic monitor delivery retains its stricter freshness checks

### Requirement: Preserve source document filenames
Telegram document uploads SHALL use the validated ILIAS response filename when known, falling back to the selected document's original title for older cache entries. The multipart name SHALL be a safe bounded basename with the validated type's extension; internal blob names and host paths SHALL NOT be exposed. A generic filename SHALL be used only when no usable source name is available.

#### Scenario: Existing cache with original title
- **WHEN** an older cache entry has no stored filename but its selected material has an original document title
- **THEN** Telegram uses that name instead of always naming the file `material.docx`

### Requirement: Independent cached delivery during monitoring
A valid requested cache copy SHALL NOT require the monitor's long-running traversal lease. It SHALL retain the cache file lease throughout upload and recheck the latest stored activity identity immediately before sending. A cache miss requiring source access SHALL still acquire the account run lease; contention SHALL report an ongoing check with source navigation instead of a generic eligibility failure.

#### Scenario: Monitor is scanning and valid bytes exist
- **WHEN** the monitor holds its traversal lease and an authorized user requests an eligible cached copy
- **THEN** the bot sends that copy using the cache lease without starting another source scan

#### Scenario: Newer submission while opening the cache
- **WHEN** the stored activity changes to submitted between the click and the final local delivery check
- **THEN** the previously selected cached bytes are not uploaded

### Requirement: Safe stage-specific material diagnostics
Material-request failures SHALL log a bounded stage and error category without exception contents, source text, credentials, or token-bearing URLs. Runtime lease contention and deadline setup failure SHALL produce distinct actionable chat responses. Source navigation SHALL remain available from the previous observation when a request fails before refresh.

#### Scenario: Another scan and no eligible local copy
- **WHEN** source refresh cannot acquire the monitor's run lease
- **THEN** the user is told that a monitor check is in progress, receives the source link, and no second source scan starts

#### Scenario: Deadline setup failure
- **WHEN** the request cannot initialize its timeout guard
- **THEN** the bot reports that setup problem and logs its stage and error class without printing the exception message

#### Scenario: Cache lease is busy
- **WHEN** a requested local copy cannot be opened because another operation holds the cache lease
- **THEN** the bot reports cache contention with source navigation instead of treating it as an absent copy and starting a needless source scan

### Requirement: Prompt bounded worker recovery diagnostics
Ordinary Telegram polling or reply failures SHALL use bounded exponential retry delays starting at two seconds, rather than a default sixty-second pause. Explicit Telegram retry delays SHALL still be considered. Five consecutive failures SHALL retain the existing termination behavior, and a successful poll SHALL reset the counter. Logs SHALL identify the stage, failure count, safe category, HTTP status, and planned delay without response contents or credentials.

#### Scenario: Three ordinary connection failures
- **WHEN** three polls fail and the fourth succeeds with a command
- **THEN** the default sleeps are two, four, and eight seconds and the command is processed after recovery

#### Scenario: Polling conflict across installations
- **WHEN** Telegram returns HTTP 409 during polling
- **THEN** a safe diagnostic identifies the conflict and advises checking other workers, including other hosts, or a webhook without exposing the token or response description

#### Scenario: Worker API failure exit
- **WHEN** repeated API failures exhaust worker retries
- **THEN** the CLI reports a Telegram worker failure separately from inventory collection errors

### Requirement: Independent notification destination and user authorization
`TELEGRAM_CHAT_ID` SHALL select the automatic notification destination without requiring that its user be the primary `TELEGRAM_ALLOWED_USER_ID`. A listed additional user whose private chat is the configured destination SHALL retain normal command and download access. Replies SHALL still go to the requesting user's private chat. Rejected updates SHALL log only a safe reason without content or credentials.

#### Scenario: Additional user is the notification recipient
- **WHEN** the primary owner and an additional allowed user differ, and the configured notification chat belongs to the additional user
- **THEN** both users can invoke commands in their own private chats and the additional user also remains the notification recipient

#### Scenario: Only an allowlist is configured
- **WHEN** the primary owner field is empty and the configured destination belongs to a user listed in `TELEGRAM_ALLOWED_USER_IDS`
- **THEN** that user can query the bot in their private chat

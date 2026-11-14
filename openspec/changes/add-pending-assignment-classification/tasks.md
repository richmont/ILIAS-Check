# Tasks

Depends on: `add-read-only-collector`.

## 1. Per-unit observations

- [ ] 1.1 Extend typed observations and the JSON Schema with assignment identity, evidence, delivery type, availability, safe link kind, and personal/team submission-history metadata; verify missing dates/attachment details remain unknown and answer bodies are never retrieved.
- [ ] 1.2 Parse supported exercise current/all-unit views, instructions, personal/team submission lists, and passive sequence metadata; verify mixed-type, multiple-unit, historical, and unresolved-sequence fixtures.
- [ ] 1.3 Document evidence fields and parser limitations; verify no parser invokes upload, membership, learner transition, or completion actions in transport-spy tests.

## 2. Applicability

- [ ] 2.1 Add declared alternative-set selections and exercise exclusions with deterministic precedence; verify malformed IDs, invalid/overlapping sets, conflicting selections, and continued discovery of unrelated/new individual work.
- [ ] 2.2 Implement ownership/team applicability without title-based assumptions; verify five visible alternatives, selected group, teammate submission, other-team submission, and unknown membership cases.
- [ ] 2.3 Document alternative-set selection and unknown applicability; verify only unselected alternatives are excluded while unrelated assignments remain evaluated.

## 3. Status rules and time

- [ ] 3.1 Implement the pure state classifier with reason codes; verify a table-driven matrix covering pending, submitted, closed, future, excluded, contradictory, and unknown evidence.
- [ ] 3.2 Add installation-timezone configuration and deadline normalization; verify no deadline, passed-but-accepted, unparseable dates, DST ambiguity, and host-timezone independence with a fixed clock.
- [ ] 3.3 Preserve curriculum requirement metadata separately from current applicability; verify historical-cohort and practice/self-test fixtures do not become unsupported obligation claims.
- [ ] 3.4 Document state precedence, deadline meaning, team semantics, and the distinction between submitted and approved; verify documented scenarios match classifier outputs.

## 4. Export integration

- [ ] 4.1 Integrate activity results and classification coverage into the CLI; verify an unknown sequence prevents an all-clear result while confirmed pending units remain exported.
- [ ] 4.2 Run offline CLI/contract regression tests spanning discovery and classification; verify multiple paths do not duplicate one assignment and one submitted unit does not hide another pending unit.
- [ ] 4.3 Expose separate submitted, closed-without-submission, and needs-verification result selections with original links; verify source practice/optionality descriptions remain visible and no submission is mislabeled approved/completed.

## Workflow follow-up

- Review classification fixtures and state semantics before starting document selection.
- Archive only after implementation, tests, and review; no live checks are authorized by this task list.

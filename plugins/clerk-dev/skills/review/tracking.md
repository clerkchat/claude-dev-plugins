# Tracking files

What the plugin keeps between runs, beyond each run's own directory. All of it
lives under `.clerk-dev/` in a worktree, which is excluded from git through
`.git/info/exclude` and never committed.

| File                      | Scope                                                                                                                                                     | Written by                                                                                                                                                                                                                                    | Read by                                                                                                                                                               |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.clerk-dev/<label>/`        | one review run                                                                                                                                            | the review orchestrator                                                                                                                                                                                                                       | everything below; see "Run directory contents" in `SKILL.md`                                                                                                          |
| `.clerk-dev/latest`          | link to this branch's newest review run; never a feature run                                                                                              | the review orchestrator, except feature mode's coordinating session and `--standalone` narrow runs                                                                                                                                            | fix skill, incremental review                                                                                                                                         |
| `.clerk-dev/latest-feature`  | link to the newest feature run (`<label>-feature`), in the worktree feature mode was started from                                                         | feature mode's coordinating session                                                                                                                                                                                                           | the user, `status.py`                                                                                                                                          |
| `.clerk-dev/branch-notes.md` | what this worktree's branch is for (Purpose) and the user's standing notes for reviews (Review) and fixes (Fixes); may be written before the first review | the review orchestrator, the `review-fix` and `review-followups` skills (draft Purpose when missing), the `review-fix` skill (standing instructions), the `review-triage` skill (rules decided in discussion), the user | the review orchestrator (passes it to lenses and verifiers), the `review-fix`, `review-followups`, and `review-triage` skills, the fixer (Branch scope below)                        |
| `.clerk-dev/status-seen`     | the highest follow-up id already shown                                                                                                                    | the `status` skill                                                                                                                                                                                                                     | the `status` skill (marks newer items as new)                                                                                                                  |
| `.clerk-dev/followups.md`    | work this repository owes because of changes elsewhere                                                                                                    | `followups.py`, from the `review-fix` and `review-followups` skills                                                                                                                                                                       | the review orchestrator (as a document for completeness and cross-repo lenses), the `review-followups` skill (implements and closes items, one commit each), the user |
| `.clerk-dev/review-workspace.md` | the repositories and worktrees of a review job across repositories; the file in the worktree where the job was set up, a link to it in every other worktree of the job | the review orchestrator's feature mode (set up with the user, see `workspace-manifest.md`), the user | feature mode, the `review-fix` skill (clients of a changed contract), the `review-followups` skill (source worktrees), `status.py` (follow-ups owed elsewhere), follow-ups (consuming worktrees) |
| `.clerk-dev/feature/` | a feature's records (brainstorms, designs, decisions, capabilities, plans, specs) and `feature.md` with their index; only in the hub worktree (see `skills/feature/records.md`) | `records.py`, from the `feature` skill; the user | the `feature` skill, the review orchestrator (active records for the reviewed repository, as documents) |
| `.clerk-dev/passes.md` | this worktree's passes: focus, lenses, piece, mode, commit range, checklist, and narrow-check result (see `skills/pass/passes.md`) | `passes.py`, from the `pass` skill | the `pass` skill, the user |
| `.clerk-dev/build.md` | this worktree's delegated pieces of implementation: spec requirements covered and their status, model and effort, commit, questions, accepted deviations; the only place requirement status lives | `build.py`, from the `writing-code` and `pass` skills | `status.py` (progress per spec, next steps), `records.py digest` (the overview's Plan), the user |

## Branch notes

`<worktree>/.clerk-dev/branch-notes.md` says what the branch is for and holds the
user's standing notes. Format:

```
# Branch notes

## Purpose
Drafted 2026-10-08 from the branch's changes and the first request. Edit freely.

What this branch builds: <one or two sentences>.
New in this branch (change directly, no compatibility concerns):
- <areas, paths, tables, endpoints the branch introduces>
Deployed code it changes on purpose (change with care, state rollout):
- <existing areas the branch is meant to modify>
Out of scope: <what the branch is not for>.
- 2026-10-09. Also handles X (added when the user widened the scope).

## Review
- 2026-10-08. <what reviewers should look for, skip, or phrase differently>

## Fixes
- 2026-10-08. <scope>: <how fixes should be done>
```

Drafting Purpose when the file or section is missing:

1. Find the base: `git merge-base HEAD origin/<main>`, with `<main>` from
   `git rev-parse --abbrev-ref origin/HEAD`. Never use the local main.
2. Read what the branch has done: the full commit messages
   (`git log --format='%h %s%n%b' <base>..HEAD`; the newest fifty are enough),
   `git diff --stat <base>...HEAD`, and `git status --short` for uncommitted
   work. Skim the messages and the names of new files; do not read whole diffs
   to draft this. `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/preflight.py
   [WORKTREE]` prints steps 1 and 2 in one call; use it rather than running
   them one by one.
3. Read the pull request, when the branch has one: `gh pr view --json
   title,body`. A description the author wrote is the best statement of
   purpose there is; when it exists, start from it. Skip this without a word
   when `gh` is missing, not signed in, or finds no pull request.
4. Combine these with the request in hand (and, for a review, the selected
   documents). Files added on the branch, or on no remote
   main, are "New in this branch"; existing files the branch or the request
   changes are "Deployed code it changes on purpose".
5. For a fresh branch with no changes yet, draft from the request alone, and
   keep it short.
6. Write the file with all three headings (empty Review and Fixes when there is
   nothing for them), create `.clerk-dev/` and its `.git/info/exclude` entry if
   needed, and say in one line that it was drafted and where. Do not wait for
   approval; the user edits it when it is wrong. The one exception is an
   interactive review: it shows the draft and asks the user to check it before
   any reviewer runs (Branch notes first in the review skill).

Keep Purpose to about fifteen lines. When the user widens the scope in
conversation ("also handle X"), add a dated line rather than rewriting it, and
say so in one sentence.

## Branch scope

A feature branch usually builds something new that is not deployed yet, next to
existing code that is live. Purpose says which is which, and the plugin's work
follows it: reviewers judge the diff by it (see `GUIDANCE` in the
`review-protocol` skill), and every fix, whether from `review-fix`,
`review-triage`, or `review-followups`, decides how to change code by it. Code
is on one of three sides:

- New in this branch: listed under Purpose as new, or introduced by the
  branch's own commits and absent from the remote main. Change it directly, with
  no backward-compatibility shims, deprecation paths, or dual reads and writes.
  Edit migrations the branch added in place rather than adding follow-up
  migrations; there is no deployed data. Clients of the new code (frontends,
  other services, agents) are not deployed either and will be updated to match:
  when a change breaks one, make it anyway and add a follow-up to the client's
  worktree (see Follow-ups).
- Deployed code Purpose lists as changed on purpose: change it carefully and
  minimally, and state its rollout considerations: old and new code running side
  by side, in-flight jobs, existing data, and clients not redeployed with this
  change.
- Deployed code Purpose does not cover (live execution paths, shared entities,
  APIs other teams or services use, migrations that already shipped): a fix
  does not change it. Propose the change and its rollout considerations to the
  user instead. When the user approves, add the area to Purpose under "Deployed
  code it changes on purpose" with a dated line, then make it.

When it is unclear which side some code is on, check whether it exists on the
remote main (`git log` or `git diff` against the merge base), and ask the user
if still unsure.

## Follow-ups

A follow-up is created where the work has to happen, not where it was caused.
When a fix in the api changes a contract the frontend consumes, the item goes
into the frontend worktree's `.clerk-dev/followups.md`:

```
followups.py add <consuming worktree> "Send exportId back when polling report downloads" \
  --from "api 7c1e2ab" --contract "POST /reports/:id/exports accepts and returns exportId" \
  --finding "api 8"
```

Find the consuming worktree in `.clerk-dev/review-workspace.md` (see
`workspace-manifest.md`). When the file is missing or does not list the
consuming repository, add the item to the current worktree's file with the text
starting `[<repo>]`, and say so.

The item's id (`F3`) is the handle in conversation. Each item has an
Instruction and a Status (see Items below); the author of a follow-up was in
another repository, so its recommendation is a hypothesis, and Refine is the
usual instruction when it may not fit here. The user sets one by saying so
("refine F3", "ignore F2, the web app dropped that screen"), which is recorded
with `followups.py set <worktree> F3 "Refine" [--note "..."]`. The
`review-followups` skill works the open items by their instructions, one fixer
and one commit each, and closes each with `followups.py close <worktree> F3
--ref <sha>` (or `--status wont-fix|deferred --ref "<reason>"`). Close one by
hand the same way when the user says it is done. Hand-ticked boxes are honored
as fixed.

Readers:

- Every review run adds its worktree's `.clerk-dev/followups.md` to `DOCS` when it
  has open items. The completeness lens reports open items the diff should have
  addressed and items the diff addressed without closing.
- Feature mode passes every repository's file to the cross-repo lens, which
  checks that each open item's contract change is matched by the consuming diff.
- The report's "Not reviewed this run" section, and the feature report's
  per-repository blocks, give the open count.
- The `review-triage` skill offers to do open items before any fix, then checks
  the open findings against commits made since the review (`stale-findings.py`):
  a finding a follow-up resolved is marked fixed, and one whose recommendation
  no longer fits moves to discuss. Judgments are remembered in the run's
  `stale.tsv`, so the same commits are not judged twice.
- The `review-followups` skill gives each fixer the open findings in the files
  it will change, as context, and notes on a finding when the follow-up's
  contract overrides its recommendation.

## Guidance from answers

When the user answers a question (a design question, an implementer's stopped
piece, a finding to discuss or a fix to adjust, a follow-up to refine, a pass
item), the answer often carries guidance: a rule that would settle other
choices the same way, beyond this one. Record it without being asked, at the
narrowest scope that covers it, and say in one line what was recorded and
where, so the user can correct the scope or the wording.

Recognize it two ways:

- **Explicit:** a line or message starting `guidance:` (any case), optionally
  with a scope, `guidance (branch): ...` or `guidance (harness): ...`. Always
  record it, as given.
- **Implicit:** the answer states a rule rather than a one-off: "always",
  "never", "prefer", "in general", "as a rule", "we don't", "from now on", or
  reasoning that would decide other cases too ("because the core should not
  know capability names"). Record it, and phrase the rule so it stands without
  the question.

Scope, narrowest first:

| Reaches | Goes to |
| --- | --- |
| this question only | the question's own outcome or notes, as today |
| this branch | `.clerk-dev/branch-notes.md`, as in "Standing rules in the branch notes" of the `review-triage` skill |
| this feature, or one of its areas | a `guidance` record in the hub (`records.py new <worktree> guidance "<rule>" --area <area> --from <the question>`), body as in `skills/feature/records.md` |
| all the user's work | the user's own CLAUDE.md: propose the line and ask first |
| the team | the plugin itself, such as the `writing-code` skill: propose it and ask first |

When new guidance refines or contradicts an active one, supersede it rather
than add a second. When it contradicts an active decision, record the guidance
and say which decision it bears on; the user decides whether that decision
changes. The line to the user: "Recorded as guidance R61 (harness):
capabilities wire in through explicit lists. Say if it is narrower than
that."

## Items

Review findings, follow-ups, and design-check questions are all items, and use
one vocabulary in two layers. Findings keep their cards and `status.tsv`;
follow-ups (`F3`) and design questions (`Q3`) are checkbox lists read and
written by `scripts/items.py` (`followups.py` builds on it).

Instruction, what to do; blank means not decided yet (a follow-up with none is
done as written):

- `Fix as recommended`: do what the item recommends.
- `Fix as noted`: do it as the note after the colon says ("Fix as noted: use
  the banner, not a toast").
- `Discuss`: talk it through with the user before anything else happens.
- `Defer`: not now; the status becomes `deferred`, with where it went.
- `Ignore`: not at all; the status becomes `wont-fix`, with why.
- `Refine`: investigate first (read the source change and the local code),
  propose a concrete fix or a reason not to, then set one of the others.
  Follow-ups and design questions only; a finding's author is a lens in this
  repository, and Discuss covers it.

Status, where it stands: `open`, `in-progress`, `fixed`, `wont-fix`,
`deferred`. The box is ticked exactly when the status is one of the last three.
`Outcome` holds what closed it: a commit (`in 1a2b3c4`), a decision record
(`R18`), or a reason. A design question is `fixed` when its answer is recorded.

## What stays the user's

Untracked files in the worktree, such as personal notes, drafts, and scratch
specs, are the user's own. Reviews do not read them, and fixes never stage or
commit them. The plugin's own files are only those under `.clerk-dev/`,
including feature records, which the user writes too. Documents
committed to the repository are read through the review-context
`## Work tracking` section and never written to.

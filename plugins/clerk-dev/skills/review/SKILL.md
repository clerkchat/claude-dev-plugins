---
name: review
description: Multi-lens code review that records findings in the worktree's .clerk-dev/ runs. Use only when the user explicitly asks to run a review of a change: "review the staged changes", "review my last commit", "review the last 3 commits", "review since abc123", "run the review on HEAD", "re-review the branch", "run a full review", "do a final review pass", or /clerk-dev:review. Do not use for questions about code, a request to look at or explain a function or file, or an informal opinion on a snippet; answer those directly. Fans out to one reviewer subagent per lens, verifies the findings, and adds them to the branch's review.
argument-hint: "[target | staged | <commit> | since <ref>] [--final] [--standalone] [--pass PASS-<n>] [--feature [--consolidate] [--children-permission-mode <mode>]] [--quick | --deep] [--full | --fresh | --previous <label>] [--lenses a,b | +a | -a] [--no-pr-comments] [--plan-only] [--resume | --report-only | --pr-comments-only [label]] [--recheck N[,M]] [--split | --walk] [--comment]"
allowed-tools: Bash(git *), Bash(gh pr *), Bash(gh repo *), Bash(gh api *), Bash(python3 *), Bash(claude *), Bash(ln *), Bash(mkdir *), Read, Grep, Glob, Agent, Write, Monitor, TaskStop
---

# /clerk-dev:review

Orchestrate a lens-based review. You coordinate; the lens agents review. Do not
review the code yourself, and never edit the project's code. The files you write
are under the worktree's `.clerk-dev/` directory: the run directory, and the branch
notes and follow-ups described in `tracking.md`.

Running the command is the user's go-ahead; there is no approval step. Cost
discipline is in the choices instead: no agent, including you, reads the whole
diff unless the whole diff is small; scope and partition work from metadata;
agents read only the patch for their scope; and each job goes to the lightest
model that does it well (haiku for scope, triage, and matching; sonnet for
partitioning, the checklist lenses, and judging links; opus for the reasoning
lenses and verification; fable only for the few single calls that carry the most
weight, as Model fallback describes). The plan is shown for information, with
its time estimate, and the run starts.

If this conversation was compacted, re-read this file before going on: a
compacted skill may be cut short, and the steps it drops are the ones that keep
items separate and commits clean.

## Started from plain words

When the user asked in their own words rather than typing the command, translate
the request into arguments first: "the staged changes" is `staged`; "my last
commit" is `HEAD`; "the last 3 commits" is `HEAD~3..HEAD`; "since <ref>" is
`since <ref>`; "this file" or a path is that path; "the branch", "re-review", or
nothing more specific is no target; "quick" or "deep" add `--quick` or `--deep`;
"final pass" or "final review" is `--final`; "feature review", "the whole
feature", or "across the repos" is `--feature`; "just this repo", "this worktree
only", or "only here" rules it out; "without tech debt" or "no cleanup
suggestions" is `--lenses -tech-debt`, and "only tech debt" or "just a cleanup
review" is `--lenses tech-debt`. The words combine: "a final pass feature
review" is `--feature --final`. If the words name nothing you can map, ask one
question rather than guess.

When the target is the whole branch and the words neither ask for the feature
nor rule it out, ask one question before anything else: review the whole
feature across repositories, or just this worktree? When
`.clerk-dev/workspace.md` exists, name its other repositories in the
feature option ("the whole feature: this worktree plus web and worker"). When it
does not, say that the feature option first asks which repositories take part.
The answer adds `--feature` or not; other flags from the words are kept. A
narrow target, a path, or a pull request is always this worktree only, so it
gets no such question.

Then:

- A narrow target (`staged`, one commit, a range, `since`) starts right away, as
  if typed: it is small and its findings join the branch's review.
- Any other target (the whole branch, a path, a pull request, `--feature`) runs
  as `--plan-only` first: show the plan with its time estimate and wait for the
  user to say go, then continue with `--resume`. A typed command needs no such
  confirmation.

## Preflight

Start every run with one call:
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/preflight.py [WORKTREE ...]`, giving this
worktree and, when the request names them or `.clerk-dev/workspace.md`
lists them, the other worktrees of the job. For each one it prints the
repository's `setup` lines, the remote main or that `origin/HEAD` is
missing, when the last fetch was, the merge base, the branch's commit messages,
`diff --stat` and `git status --short`, whether the branch notes have a Purpose,
the review workspace rows, open follow-ups, and the latest run and whether it is
unfinished and still at `HEAD`. It never fails the call; a missing piece is
printed as missing. Use its output for Branch notes first, First runs in a
repository, and Resuming, rather than gathering the same facts with your own
shell commands (chained `cat`s of files that may be absent fail the call, and
zsh expands a word starting with `=`).

Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/status.py <worktree> --setup` in the
same step, for the worktree of the run. It lists what the worktree is missing
for feature work: a Purpose (settled by Branch notes first, below), a hub and
feature, a review workspace when records or follow-ups name other repositories,
workspace rows whose worktree is missing, a plan with done lines. Settle any
other gap with the user before the run goes on; "Setup: complete." means
nothing to settle.

## Branch notes first

Read `.clerk-dev/branch-notes.md` before scoping. When it or its Purpose is
missing, draft Purpose as `tracking.md` describes, from the pull request's
description when there is one, the branch's commit messages, and its new
files. It decides what the reviewers
treat as new and what as deployed code, so a wrong guess skews every lens; ask
the user to check it before any reviewer runs:

- Show the drafted Purpose in a few lines: what the branch builds, what is new,
  and what deployed code it changes on purpose.
- Give the file's path and ask the user to edit it: correct what is wrong, move
  anything misfiled between "new" and "deployed", and add under Guidance, as a
  `###` rule, anything reviewers should focus on or leave alone.
- Say what to answer: "go" when it is right, after any edits.

When the run would stop for the plan anyway (a whole-branch review started from
plain words runs as `--plan-only`), ask in the same message as the plan, after
it, so the user answers once. Otherwise stop here and wait, then continue from
scoping. Either way, read the file again before launching reviewers, since the
user may have changed it. A headless session never waits: it drafts, says so
in one line, and continues.

When the file already has a Purpose, use it without asking.

## First runs in a repository

A few things only need saying once per repository, so the plugin remembers
what it has said in `<git common dir>/clerk-dev/setup` (the directory from
`git rev-parse --path-format=absolute --git-common-dir`, shared by every
worktree of the repository, never committed): one line per item,
`<key>: <value> <date>`. Read it at the start of a run. A headless session
reads it but never asks, offers, or records anything.

- The base, on every run, before scoping. When `origin/HEAD` is missing, run
  `git remote set-head origin --auto` and say so in one line; if that fails,
  stop and say the remote main branch could not be found. When `FETCH_HEAD` in
  the git common directory is more than a day old, say in one line when the
  last fetch was, that whether a finding is new on this branch or already on
  main is judged against that state, and that a `git fetch` before reviewing
  makes it current. Do not fetch, and do not wait.
- The repo context (key `context`). When the repository has no
  `<git common dir>/clerk-dev/repo-context.md` and the key is absent or says
  `later`, ask at the run's first stop (the Purpose check or the plan; a run
  with no stop does not ask): "This repository has no repo context, so the
  reviewers will guess at its conventions: what a tenant is, where access
  guards live, which files to skip, which mistakes the team keeps catching.
  Draft one now (a few minutes, before the review starts), later, or never?"
  Record `later` or `never`. On "now", draft it as Drafting a repo context in
  `context-schema.md` describes, show its path, point out the Hazards by focus
  section as the one worth the user's time, record `drafted`, and continue the
  run with it as `CONTEXT`.
- Pull request access (key `gh`). When Step 7b skips because `gh` is not
  installed or not signed in, and the key is absent, say in one more line how
  to enable it: install the GitHub CLI and run `gh auth login`. Record `noted`.
  Once noted, the skip is one line as usual.
- How to use the report (key `report-guide`). When the key is absent, end the
  first report with the guide under The end in How you talk to the user, and
  record `shown`.
- Time. In the plan of a full review of a branch with no earlier review, add
  one line: "Later reviews of this branch read only what changed since this
  one and take a few minutes."

## How you talk to the user

When talking to the user, follow "Talking to the user" in `skills/review/tracking.md`: the feature first, the bookkeeping last or not at all, and ids named: every id (DEC-19, BUILD-15, MILE-1, F3, Q-3, PASS-3, IDEA-7, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

When this session runs headless (started with `claude -p`, as feature mode does
for each repository), there is no one to answer a question. Never ask: follow
the flags, and if a decision is needed that the flags do not settle, stop and
print the decision needed as the last line. An unfinished earlier run is not
resumed unless `--resume` was given; start a new run. Send no desktop
notification; the coordinating session does that. Always end a headless run with
the line `RUN_DIR: <absolute path of the run directory>`.

Everything you say to the user is about the change, the parts it splits into,
the review focuses, and time. Slice names, lens identifiers, token counts,
costs, thresholds, step numbers, model names, and file formats belong in the run
directory, never in a message. If a sentence needs one of those words, rewrite
it. Say "part" for a slice and use the plain phrase from the "Say it as" column
of `routing.md` for a lens. Numbers appear only when they change what the reader
decides: how many files, how many parts, how many minutes.

The points where you speak, and what you say at each:

- Before the plan: one line, "Looking at what changed in <target>." Nothing
  about steps, tokens, or thresholds while scope, partition, and triage run.
- A newly drafted Purpose: the draft and the request to check it, as Branch
  notes first describes.
- The plan: the format under Step 4, ending with "Running."
- During the run: one line as each reviewer finishes, a "still running" line
  after two quiet minutes, and after each wave the progress checklist (see
  Progress tracking below). After verification, one sentence: "<N> findings
  raised, <K> held up."
- Feature mode discovery: "Found this feature in <repos>. Nothing in <repos>."
- Nothing to review: one sentence.
- A failure: which reviewer and which part, in words, and what you did about it.
  Details go to the run directory, not the message.
- The end: the report, and nothing after it, except the first time in a
  repository (First runs in a repository), when three lines follow it: "Tick
  an instruction on each card (Fix as recommended, Fix as noted, Discuss,
  Defer, Ignore), then say 'work the queue'. Or say 'fix finding N' for one
  finding. Say 'where are we' any time for the status." Send one desktop notification with
  the PushNotification tool when the report is written, under 200 characters,
  leading with the count of things to fix: "Review done: 3 to fix before
  merging, 5 worth a look." It is skipped automatically when the user is still
  at the terminal.

## Progress tracking

Keep `<run>/progress.md` as a two-level checklist and update it as the run
moves. Top level is one item per part in review order, then merge, verify, and
report. Under each part, one item per focus that runs on it; walkers that read
the whole change are their own top-level item, "Whole change", with their
focuses under it. Check items as waves finish, and note a failed reviewer beside
its item in a few words.

```
- [x] Database entities and migrations
  - [x] security
  - [x] tenant isolation
  - [x] edge cases
- [ ] Background job processing  (in progress)
  - [x] security
  - [ ] concurrency
  - [ ] resource limits
- [ ] HTTP endpoints
- [ ] Whole change: rollout and rollback, agreements between parts, completeness, spec conformance
- [ ] Merge findings
- [ ] Verify findings
- [ ] Write report
```

After each wave, also refresh the interim view: run
`merge-findings.py <run>/raw --readable <run>/so-far.md --title "Findings so
far in <target>" --pending "<labels of parts not yet reviewed>"`.
It renders the unverified findings in the report's prose shape in under a
second, so a reader can look at them mid-run without waiting.

What you print after each wave is the top level only, with the current part's
focuses on one line beneath it, and one line pointing at the interim view:

```
- [x] Database entities and migrations
- [ ] Background job processing  (now: security, concurrency, resource limits)
- [ ] HTTP endpoints
- [ ] Whole change
- [ ] Merge, verify, report
Findings so far (unverified): .clerk-dev/<label>/so-far.md
```

The reviewers running inside a wave appear in the terminal's own task panel, so
the checklist does not list them individually.

### Between waves

Waves take minutes, so say something while one runs:

- When a reviewer's completion notification arrives, write its raw file at once
  (Step 6), check its item in `progress.md`, and print one line: "Background
  job processing: security done (4 of 9 in this wave)." When a verifier
  returns, the same: "Checked 6 of 14 findings." Several arriving together get
  one line.
- In an interactive session, start a heartbeat with the Monitor tool when the
  first wave launches:
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/progress.py --run <run>
  --heartbeat-only`,
  with `timeout_ms` 1800000 and the description "Review progress". It reads
  only files, checks every 30 seconds, and prints a line every two minutes
  while the run stays in one step ("7 min in · reviewing 5/9 (3 min)"). For
  each line, tell the user in one line what is still running and for how long:
  "Still reviewing background job processing (concurrency, resource limits),
  7 min in." When it expires while the run continues, start it again. It
  exits on its own when `report.md` is written; stop it with TaskStop if the
  run stops early.
- A headless session starts no monitor; the coordinating session watches it.

## Model fallback

Fable is used for these jobs only: the cross-repository check, verifying
findings of severity `blocker` (and `major` ones on a final pass, and every
verifier in `--deep` mode), the `security` and `tenancy` lenses of a security
pass's pass review (`--pass`), and a second attempt at a fix that a recheck
found only partly resolved (in the `review-fix` skill). Outside the review,
the feature, design-check, and writing-code skills use Fable for briefs, the
overview, roll-ups, settle-first lenses in design checks, foundation handoffs,
and stopped handoffs' questions, all with this same fallback. Each is assigned by passing `model: fable` on the
invocation. Not every account has access to Fable, and access may come with its
own usage limits, neither of which can be checked ahead of time, so:

- When an agent assigned to fable fails because the model is unavailable (the
  error says the model is not found, not available, or not permitted for the
  account) or because of a limit (it mentions a usage limit, a rate limit, a
  limit being reached, or status 429), run the same task with the same inputs
  again with `model: opus` on the invocation. The failed call wrote nothing, so
  nothing is lost but its time.
- After the first such failure, assign opus to every remaining fable job in this
  run, without trying fable first. The next run tries fable again.
- Say it once, in a line: "Fable isn't available right now; continuing on
  Opus."
  Add a sentence to "About this review" through `not-reviewed.md` naming which
  jobs ran on Opus instead (for example "the cross-repository check and 2 of 3
  blocker verifications"), so a verdict's source is known.
- A limit error on any other model is not a reason to switch models: wait and
  retry that call once, then report the failure as usual.

Supporting files, all in this skill's directory:

- `routing.md`: category heuristics, lens triggers, triage questions.
- `context-schema.md`: what a repo's repo-context file contains.
- `workspace-manifest.md`: the review workspace file, which names the
  repositories and worktrees of a review job across repositories, and how to
  set it up with the user.
- `tracking.md`: the files the plugin keeps between runs (branch notes,
  follow-ups) and their formats, and how to draft branch notes.

Scripts shipped with the plugin, run with `python3`; use them rather than
writing ad hoc parsers (`reconcile.py` matches findings against an earlier run;
see Step 6b):

- `${CLAUDE_PLUGIN_ROOT}/scripts/preflight.py [WORKTREE ...] [--log N]`: the
  state a run starts from, per worktree (see Preflight).
- `${CLAUDE_PLUGIN_ROOT}/scripts/measure-patch.py PATCH [--exclude GLOB ...]
  --tsv files.tsv --md scope-table.md`:
  per-file bytes, lines, token estimate, and exclusion reasons.
- `${CLAUDE_PLUGIN_ROOT}/scripts/carry.py` and `reconcile.py`: incremental and
  re-review bookkeeping; `reconcile.py --append` is the only way to add a
  finding to `merged.md` after the merge step.
- `${CLAUDE_PLUGIN_ROOT}/scripts/followups.py`: the follow-ups file.
- `${CLAUDE_PLUGIN_ROOT}/scripts/usage.py RUN [--append]`: totals the real
  usage recorded in raw and verify headers, by lens and model.
- `${CLAUDE_PLUGIN_ROOT}/scripts/progress.py`: watches runs on disk for the
  progress lines under Between waves and in feature mode.
- `${CLAUDE_PLUGIN_ROOT}/scripts/status.py [WORKTREE]`: where the review
  work stands, for the `status` skill.
- `${CLAUDE_PLUGIN_ROOT}/scripts/stale-findings.py`: open findings whose code
  later commits touched, for the triage skill's check before fixing.
- `${CLAUDE_PLUGIN_ROOT}/scripts/pr-comments.py`: pull request comments into a
  run (Step 7b).
- `${CLAUDE_PLUGIN_ROOT}/scripts/merge-findings.py RAW_DIR -o merged.md`: parses
  every `findings` block and merges duplicates by file and line range.
- `${CLAUDE_PLUGIN_ROOT}/scripts/render-report.py RUN_DIR --target ... --routing
  ${CLAUDE_PLUGIN_ROOT}/skills/review/routing.md ...`:
  renders `report.md` from `merged.md`, `verify/`, `slices.md`, `titles.tsv`,
  `summary.md`, and `not-reviewed.md`, numbers the findings, and writes
  `numbers.tsv`.

Lens agents are provided by this plugin as `clerk-dev:lens-<lens>`; pass that
full name as the subagent type.

The protocol every lens agent follows is the `review-protocol` skill; you do not
need to read it unless debugging agent output.

## Arguments

`$ARGUMENTS` may contain, in any order:

- A target, one of: nothing (the current branch against the remote main branch,
  plus uncommitted work; incremental when an earlier review of this branch
  exists, see Incremental review); a branch name; a PR number; a path or several
  paths (restricts the diff to those paths); a commit range such as
  `HEAD~5..HEAD` or `abc123..HEAD`; `since <ref>`; one commit (`HEAD`, `abc123`;
  a name that is a branch means the branch); or `staged`, the changes staged for
  commit (`git diff --cached`). A range, `since`, one commit, or `staged` is a
  narrow target: when the branch already has a review, its findings are added to
  that review. See Narrow review.
- `--final`: the last look before merging, after review and fix cycles. Reviews
  the whole branch fresh but reports only what would hold the merge. See Final
  pass.
- `--standalone` (with a narrow target): a separate run, not added to the
  branch's review, and `.clerk-dev/latest` is left where it is.
- `--pass PASS-<n>` (with a range target, `--standalone`, and `--lenses`): this run
  is the pass review of pass PASS-<n> from `.clerk-dev/passes.md` (see the `pass`
  skill). The lenses are exactly those given: no routing, triage, or quick-mode
  cap adds or drops one. `DOCS` is only the pass's piece (its brief record), not
  every active record, and every lens prompt gets a `PASS:` line naming the
  focus and the piece. For the security pass, the one a milestone cannot skip,
  run its `security` and `tenancy` instances with `model: fable` (see Model
  fallback); its check is the merge gate for those concerns.
- `--lenses a,b,c` to replace routing, `--lenses +a,+b` to add to it, or
  `--lenses -a` to remove one from it.
- `--quick` or `--deep` (default standard). Quick: triggered lenses only, capped
  at four, sonnet, a higher bar for minor findings. Deep: all routed lenses,
  deep tracing, fable verifier.
- `--feature`: review the whole feature across the worktrees named in
  `.clerk-dev/workspace.md`, each in its own headless session. See Feature
  mode.
- `--consolidate` (with `--feature`): start no reviews; use each worktree's
  latest finished run, run only the cross-repository lens, and write the feature
  report. For when each repository was reviewed separately, or after fix cycles
  when only the cross-repository check needs rerunning.
- `--children-permission-mode <mode>` (with `--feature`): the permission mode
  for the per-repository sessions, passed to `claude --permission-mode`. Without
  it they run with the allowed-tools list under Feature mode.
- `--full`: review the whole branch even when an earlier review exists (no
  incremental review).
- `--plan-only`: stop after writing and showing the plan, without running any
  reviewer; `--resume <label>` runs it later.
- `--split` or `--walk`: force per-slice agent instances or single-walk agents.
- `--fresh`: do not compare with an earlier review. By default a run is
  reconciled with the most recent finished run under `.clerk-dev/` for the same
  target; `--previous <label>` names a different one.
- `--resume [label]`: continue an unfinished run, by default the one
  `.clerk-dev/latest` points at. See Resuming below.
- `--report-only [label]`: re-render the report of a finished run from its
  merged findings and verdicts, without running any reviewer. Use it to iterate
  on the report after changing titles, the summary, or the template.
- `--recheck N[,M...] [label]`: after a fix, run only the lens that raised
  finding N against the diff of the fix and say whether the finding is resolved.
  See Rechecking below.
- `--comment`: post the final report to the PR when the target is a PR.
- `--no-pr-comments`: skip the pull request's review comments, which are
  otherwise brought in by default (Step 7b).
- `--pr-comments-only [label]`: bring the pull request's comments into an
  existing finished run (default `.clerk-dev/latest`), fill in the sections of
  comment cards that lack them, and re-render, without running any reviewer.

## Incremental review

By default a review builds on the most recent finished review of the same branch
and target, so a re-review after fix cycles costs minutes, not the full run. The
reviewers still read code blind; only the commits since the earlier review are
new to them.

Use the earlier run when all of these hold, else review in full and say why in
one line: it is the most recent directory under `.clerk-dev/` with a `report.md`,
the same branch, and a target that is the same as this run's or narrower (a path
inside this run's target; the whole branch contains every path); `--full` and
`--fresh` were not given; and its `HEAD` is an ancestor of the current `HEAD`
(`git merge-base --is-ancestor`). A rebase breaks the chain, so it gets a full
review. Read the earlier run's target and commits from its `target.txt`, or, for
runs made before that file existed, from the title and the HEAD line of its
`scope.md`.

When the earlier target is narrower, this run widens it:

- Inside the earlier target, review only the commits since the earlier run's
  `HEAD`, as below.
- Outside it, review the whole branch:
  `git diff <merge base with the remote
  main>...HEAD -- <this run's target> ':!<earlier target>'`,
  plus uncommitted work there.
- Say so in the plan in one plain line: "Builds on the review of
  <earlier target> from <date>: changes there since then, and the rest of
  <this target> in full."

Incremental run:

1. Create the run directory (Step 0), then `carry.py <earlier run> <run>`, which
   copies the earlier review's findings, verdicts, statuses, numbers,
   resolutions, and triage, and marks every finding as carried. If the earlier
   run has a `pr/` directory, it is copied too; Step 7b then refreshes the
   comments.
2. Scope (Step 1) with `BASE` set to the earlier run's `HEAD` and `HEAD` the
   current commit, plus uncommitted work, restricted to the earlier target, and
   only the files that something unreviewed changed:
   `stale-findings.py <run> --delta` classifies each commit since the earlier
   run. Commits marked `fix` or `follow-up` were already read by the fixer and a
   recheck, `narrow` ones by a narrow review, and `merge` and `format` ones add
   nothing to review; those wait for the final pass. The patch is
   `git diff BASE..HEAD -- <files of the unreviewed commits>`, plus uncommitted
   work. A file a fix also touched shows that fix in context, which is fine.
   When widening, also write the whole-branch patch for the rest of this run's
   target (above) and append it to `<run>/patch/all.patch`, so the measurement,
   exclusions, partition, and triage see one change. Record in `scope.md` which
   files came from which part. If nothing unreviewed changed in either part, say
   so in one line with the counts ("16 commits since a86f57469, all fixes
   already rechecked or merges; nothing new to review"), re-render the carried
   report, and stop. In feature mode that repository then adds nothing but its
   whole-branch patch for the cross-repository lens.
3. Partition, triage, route, plan, and fan out (Steps 2 to 5) on that delta as
   usual; the plan says it is incremental, since when, and what it leaves out,
   from the `--delta` counts: "16 commits since a86f57469: 3 new, read here; 12
   fixes and 1 merge are left for the final pass."
4. Merge into `<run>/merged-new.md`, then fold it in, after step 5's rechecks so
   their outcomes are known:
   - `reconcile.py --append <run>/merged-new.md <run>` proposes candidate
     matches in `reconcile/append-candidates.tsv` and changes nothing (with no
     candidates, it appends everything at once).
   - Judge the candidates with one sonnet subagent (effort `medium`). For each
     new finding, give it the new finding's title, claim, scenario, and
     location, and for each candidate the carried finding's title, claim,
     scenario, location, status, recheck outcome, and resolution text. It
     answers one verdict per new finding: `duplicate` (the same defect, not yet
     fixed), `regressed` (the same defect, marked fixed, and the fix did not
     cover what the new finding describes), `stale` (the same defect, and the
     fix already covers it), or `different` (another issue, even if nearby or
     related). Nearby lines or a shared file are not enough for anything but
     `different`. It writes `reconcile/append-judged.tsv` (`new_id`,
     `carried_id`, verdict).
   - `reconcile.py --append <run>/merged-new.md <run> --judged
     <run>/reconcile/append-judged.tsv`
     applies them. A recheck that found the carried finding resolved wins over
     `regressed`. New findings are listed in `reconcile/appended.tsv`; those
     related to a carried finding say so on their card, and a reopened card says
     what was found. Until a new finding gets an instruction or a status, its
     heading ends in `[new]`, so `grep -n '\[new\]' report.md` lists what is
     left to look at.
5. Before step 4's folding, recheck every carried finding marked fixed whose
   file is in this run's patch (changed by an unreviewed commit or by
   uncommitted work), or that has no `recheck/<id>.md` at all, against the whole
   branch for those files (the Rechecking procedure in the `review-fix` skill).
   A fixed finding whose file only fixes changed was rechecked when it was
   fixed; it is not rechecked again. Write `reconcile/since.tsv` (`prev_id`,
   `resolved` | `reopened`, note); reopen through `--set N=open` on the render.
6. Verify (Step 7) the appended findings, any reopened ones, and every carried
   finding the current selection rules would select that has no verdict yet
   (earlier runs may have used narrower rules).
7. Render (Step 8). Write `summary.md` and `not-reviewed.md` afresh for this
   run; the copies carried from the earlier run describe that run, not this one.
   Numbers are stable: carried findings keep theirs, new ones continue from the
   highest. This run's target, the wider one when widening, is what the next
   incremental run compares against.

Incremental runs do not need Step 6b; carrying replaces matching.

## Narrow review

A narrow target (a range, `since <ref>`, one commit, or `staged`) reviews just
that change, typically one the user made by hand between fix cycles. Its
findings join the branch's review, so triage, fixes, follow-ups, and the
cross-check keep working on one run with one set of numbers.

When the branch has a review to join (the most recent directory under `.clerk-dev/`
with a `report.md`, the same branch, a target that is the whole branch or a
path, and a `HEAD` that is an ancestor of the current `HEAD`) and `--standalone`
was not given, run it as an incremental run on that review, with these
differences:

1. The patch is the narrow change only: `git diff --cached` for `staged`,
   `git diff <sha>^ <sha>` for one commit, `git diff A..B` for a range,
   `git diff <ref>..HEAD` for `since`. Not restricted to the earlier target. If
   it is empty, say so in one line and stop, creating nothing.
2. Copy the earlier run's `target.txt` unchanged, so the next plain review still
   starts from the earlier review's `HEAD` and nothing between that and now goes
   unreviewed; a change reviewed here is reviewed again then, and reconciling
   marks its findings as duplicates. Write the narrow target to
   `<run>/narrow.txt`: three lines, the target as given, `BASE` (`HEAD` for
   `staged`), and `HEAD` (for `staged`, the current `HEAD` followed by
   `+staged <sha1 of the staged patch>`).
3. Incremental step 5 rechecks only the carried fixed findings whose files the
   narrow change touches, against the narrow change.
4. The plan's first line says what is added to what: "Adds a review of <the
   commit's subject | the staged changes | range> to the review of
   <earlier target> from <date>." The summary says the same.
5. After rendering, record every finding this run appended (from
   `reconcile/appended.tsv`) as already judged up to now, so the cross-check
   does not take the change that introduced it for a change since the review:
   `stale-findings.py <run> --record #<id>=still:found in
   a narrow review --through HEAD`.

`.clerk-dev/latest` moves to the new run as usual: it holds everything the earlier
run held, plus the new findings.

With no review to join, or with `--standalone`, a narrow target is an ordinary
run of its own. A standalone run leaves `.clerk-dev/latest` where it is; say in the
final line that triage and fixes on it need its label.

## Final pass

`--final` is the review a human does last: the whole branch, read fresh, but
only what would hold the merge (the bar and its eleven categories are in the
protocol under Final pass bar). Earlier decisions stand: a finding the user
already ignored, declined, or deferred is not raised again, and one already open
is not counted twice.

When the branch has a review to join (as under Narrow review), run it as an
incremental run on that review, with these differences:

1. Scope is the whole branch: `BASE` is the merge base with the remote main
   branch, `HEAD` the current commit, plus uncommitted work, as in a full
   review. Write a fresh `target.txt` (the branch, that `BASE`, `HEAD`): the
   whole branch has now been read, so the next incremental review starts here.
2. The lens set is the routed lenses that can find something at the bar:
   security, tenancy, data-privacy, side-effects, rollout, sql, scaling,
   capacity, concurrency, contracts, error-handling, llm-agent, and
   completeness. Security and rollout always run. Design, naming-concepts,
   user-facing-text, tests, performance, observability-cost, and
   spec-conformance do not. Standard mode otherwise.
3. Every lens and verifier prompt carries the extra line `BAR: final`.
4. Skip incremental step 5; the fresh reviewers find regressions, and the
   judging below reopens them.
5. Merge into `<run>/merged-new.md` and run phase 1 of
   `reconcile.py
   --append` and its judging as in incremental step 4, but do
   not apply it yet.
6. Verify, as in Step 7 with `BAR: final`, every new finding judged `different`
   or `regressed` or with no candidate, whatever its confidence, writing to
   `<run>/final/verify/<new id>.md`. The verifier also answers whether the
   finding meets the final bar: a last line `bar: meets
   <category>` or
   `bar: below <one sentence why>`.
7. Split with
   `split-findings.py <run>/merged-new.md --keep <ids> -o
   <run>/final/kept.md --rest <run>/final/below.md`,
   keeping every finding judged `duplicate` or `stale` (they add evidence or
   drop out) and every verified one that is not rejected and meets the bar. Then
   apply:
   `reconcile.py --append <run>/final/kept.md <run> --judged
   <run>/reconcile/append-judged.tsv`.
   Copy each kept finding's verdict from `final/verify/<new id>.md` to
   `verify/<merged id>.md` through `reconcile/appended-map.tsv`.
8. Record the appended findings in `stale.tsv` as judged through `HEAD`, as
   under Narrow review step 5.
9. Render. The summary says it was a final pass of the branch at `HEAD`, how
   many new findings meet the bar and in which categories, how many matched
   findings already in the review (reopened ones by number), and how many were
   raised below the bar, kept in `final/below.md` and not reported. The final
   message leads with the count that would hold the merge: "Final pass: 2 would
   hold the merge (tenant isolation, rollout); 9 raised below the bar."
10. Run `final-report.py <run>`, which writes `<run>/final-review-report.md`:
    the verdict on its first line (`PASSED`, or `NOT PASSED` with what holds the
    merge: new findings at the bar, reopened ones, and findings still open in
    Fix before merging, each by number with its `report.md` line), then the
    eleven bar categories with what was found in each, the lenses that ran, the
    earlier findings' state, what was set aside below the bar, and the summary.
    Findings stay in `report.md` for triage. End the final message with the
    verdict and that file's path.

With no review to join, `--final` is a full run with steps 2, 3, 6, and 7
applied to its own findings (the split before rendering, with `final/below.md`
kept the same way) and 10.

## Resuming

A run is resumable because every expensive unit writes one file when it finishes
and nothing before: each reviewer instance writes its raw file on completion,
each verifier writes `verify/<id>.md` on completion, and `plan.md` lists every
instance the plan committed to. A missing file means not done; a present file
means done. Nothing is half-written.

With `--resume`, or when a bare invocation finds that `.clerk-dev/latest` points at
a run whose `progress.md` has unchecked items, whose target matches, and whose
`HEAD` still equals the current `HEAD` (for a narrow run, the `HEAD` line of its
`narrow.txt`, and for `staged` also the staged patch's sha1):

0. A run that has not started (no raw files; typically one stopped after
   `--plan-only`) costs nothing to plan again, and the skill may have changed
   since it was planned. Scope it again (Step 1, for an incremental run
   including `stale-findings.py <run> --delta`) and compare the file list with
   its `files.tsv`. If they differ, say so in one line ("The plan from 11:24
   read 11 files; 0 of them have unreviewed changes now"), and plan again in the
   same run directory, replacing `plan.md` and the instance list. If nothing is
   left to review, follow incremental step 2's empty case and stop.
1. Read `plan.md`, `progress.md`, and the instance list. Compare the instance
   list against `raw/` to find reviewers with no file; compare the merged
   findings against `verify/` to find findings not yet judged.
2. Say what remains in plain words: "Resuming the review of <target>: <n> of
   <m> reviewers still to run, about <minutes> minutes."
3. Launch only the missing reviewers, in waves, updating `progress.md` as
   before. Then continue from the first unchecked top-level item: merge (always
   rerun, it is cheap and reads every raw file), verify only the unjudged
   findings, report.

If `HEAD` moved, the code changed under the review. Say so, name the old and new
commits, and start a fresh run; do not mix raw files from two versions of the
code. If the user explicitly asks to resume anyway, treat the old raw files as
done and warn in the report that some parts were reviewed at the earlier commit.

A bare interactive invocation that finds a resumable run asks one question
before anything else: "An unfinished review of <target> from <time> has <n>
reviewers left. Resume it, or start over?" Headless runs start over unless
`--resume` was given.

## Step 0: run directory

Create the run directory inside the repository, at `<repo>/.clerk-dev/<label>/`,
where `<label>` is `<yyyymmdd-hhmm>-<target slug>` (`branch`, a path slug, a PR
number, or a range slug). If the directory exists, append `-2`, `-3`, and so on.
Never overwrite or delete an earlier run. After creating it, point the symlink
`<repo>/.clerk-dev/latest` at it, except for a `--standalone` narrow run (see
Narrow review), which leaves it where it is, and for the coordinating session
of feature mode, which points `<repo>/.clerk-dev/latest-feature` at its run
instead. `latest` always means this branch's own review: fixes, triage, status,
resuming, and incremental review read it, and in feature mode the review of
this repository runs in the same worktree at the same time.

A directory whose label ends in `-feature` is a feature run, not a review of
this branch. Wherever this skill or another looks for the most recent or newest
run under `.clerk-dev/`, it skips those directories and both links.

Keep `.clerk-dev/` out of version control without touching tracked files: if
`git check-ignore -q .clerk-dev` fails, append `.clerk-dev/` to `.git/info/exclude`.
Say that you did so the first time.

`<run>` below means this directory. In feature mode it lives in the repo the
command was run from.

## Step 1: scope (metadata only)

Run a haiku subagent (effort `low`). It must not read diff content; it measures
it with the shipped script. Give it the target and the script path and have it:

1. Resolve `BASE` and `HEAD`. The main branch is the remote-tracking ref, never
   the local branch: read `git rev-parse --abbrev-ref origin/HEAD` (for example
   `origin/master`) and use that ref. Default `BASE` is
   `git merge-base HEAD origin/<main>`; a range, `since`, or an incremental run
   sets it explicitly. Do not fetch; the user fetches. Record in `scope.md` the
   `origin/<main>` commit and when it was last fetched (modification time of
   `FETCH_HEAD` in the git common directory), so a stale base is visible. Note
   whether uncommitted work is included.
2. Write the full patch once to `<run>/patch/all.patch`
   (`git diff BASE...HEAD
   [-- paths]`, plus `git diff HEAD` appended for
   uncommitted work, or `gh pr
   diff` for a PR). Do not read it. Measure it
   with
   `measure-patch.py <run>/patch/all.patch --tsv <run>/files.tsv --md
   <run>/scope-table.md`,
   passing each glob from the repo context `## Excluded from review`
   section as `--exclude`. The script writes per-file bytes, added and removed
   lines, tokens (bytes divided by 4), and exclusion reasons. Do not recompute
   any of these by hand.
3. Read the script's one-line summary and the excluded table. The rules it
   applies, for reference:
4. Exclusions, with a reason each:
   - matches a default exclusion glob: `**/*.lock`, `**/*-lock.json`,
     `**/yarn.lock`, `**/dist/**`, `**/build/**`, `**/*.generated.*`,
     `**/__snapshots__/**`, `**/*.snap`, `**/*.min.*`;
   - matches a repo context `## Excluded from review` glob;
   - looks generated or minified: more than 10,000 bytes and an average above
     300 bytes per changed line. Small files never trip this rule; a short
     wiring file with long import lines is cheap to read and often the most
     important file for completeness;
   - is a data file (JSON, CSV, YAML, SQL, TXT) over 500 changed lines or 40,000
     bytes. Globs match against the full repo-relative path. Excluded files stay
     in the table with their sizes, are left out of every patch and token total,
     and are listed in the report header so nothing disappears silently.
5. Classify each included file into categories per `routing.md`, using the repo
   repo-context `## Slices` globs if `<git common dir>/clerk-dev/repo-context.md`
   exists.
6. Collect the PR title and body if the target is a PR or a PR exists for the
   branch (`gh pr view`), and the work-tracking documents per the repo-context
   `## Work tracking` section (default globs `TODO*.md`, `docs/plans/**`). Only
   files tracked in git count: untracked files are the user's own (see
   `tracking.md`) and the review does not read them. Select only documents that
   are new or modified on the branch, or whose text mentions a changed path or
   the branch name; order by modification time; keep at most eight and report
   how many were dropped. Also include the plugin's own `.clerk-dev/followups.md`
   when it has open items (see `tracking.md`); it does not count against the
   eight. With `--pass`, the only document is the pass's piece record: skip the
   work-tracking selection above (the PR is still collected). Otherwise include the feature's
   active records
   (`records.py list <worktree> --active`, which reads the hub; see
   `skills/feature/records.md`): every active brief, decision, and plan whose
   `repo` is this repository, and the active design and pieces records.
   They do not count against the eight either; brainstorms and superseded or
   discarded records are never included.
7. Write `<run>/target.txt`: three lines, the target as given (`branch` for the
   whole branch, else the path, range, or PR), `BASE`, and `HEAD`. Incremental
   review reads it. Then write `<run>/scope.md`: the summary (files, included
   tokens, excluded tokens, BASE, HEAD), the excluded table with reasons, the
   included table sorted by tokens descending, and the selected documents.
   Return the summary and the two largest included files.

If no files changed, stop and say so.

## Step 2: partition

Skip when total estimated tokens are under 20,000 and fewer than eight files
changed: write one patch at `<run>/patch/whole.patch` from included files and
pass `SLICES: none`.

Otherwise run a sonnet subagent (effort `medium`) with the file table (not the
content), the repo-context `## Slices` table if present, and the routing
heuristics. It writes `<run>/slices.md`:

```
## Slices
- name: <short internal name, used in file names>
  label: <plain name for the reader, three to five words: "background job processing">
  summary: <one line in plain words saying what changed here, from the file
    names and triage: "report exports fanned out through the queue">
  layer: <schema | domain | interface | async | llm | ui | config | tests | repo-specific>
  context: <request | job | scheduled | consumer | ui-action | build | mixed>
  tokens: <sum of file estimates>
  files:
    - path
## Seams
- <slice A> -> <slice B>: <what crosses: a DTO, a job payload, a flag, an event>
## Order
<slice names in review order: schema first, then domain, interface, async, llm, ui, config, tests>
```

`label` and `summary` are what the user reads in the plan; write them for an
engineer who has not seen this codebase's vocabulary, and never use the word
"slice" in them. Seams are where agentic PRs break; the partition agent names
every crossing it can infer from paths and, if it needs to, from import lines
(`grep -h '^import'` on changed files, not the diff). Excluded files are not
assigned to slices. Then you write one patch per slice:
`git diff BASE...HEAD -- <slice files> > <run>/patch/<slice>.patch`, and the
whole patch at `<run>/patch/whole.patch` built from included files only, for
walking lenses. `all.patch` is kept for reference and is never handed to an
agent.

## Step 3: triage

For each slice (or the whole patch when unsliced), run a haiku subagent (effort
`low`) that reads that slice's patch and answers the triage questions in
`routing.md` with yes or no plus a one-line pointer. This is the only step that
reads content before fan-out, and it reads each hunk once. Keep the answers per
slice; they refine routing in the next step and go to the lens agents as
`TRIAGE`.

Skip triage in quick mode and when the whole diff is under 20,000 tokens.

## Step 4: route and plan

Build the lens set from `routing.md`, the triage answers, and the arguments. A
lens triggered only by a path category that triage answered "no" for in every
slice is dropped, and the report header says so. Only lenses that exist as a
`clerk-dev:lens-<lens>` agent can run.

Decide walk versus split per the flags, else by size: if total estimated tokens
exceed 60,000 or the slice map has more than five slices, every lens runs one
instance per slice that triage marked relevant, regardless of model, except
`contracts`, `rollout`, `completeness`, `spec-conformance`, and `tech-debt`,
which always walk: the first four because their findings live between slices or
against a whole document, and tech-debt because its proposals cross files and a
copy per slice mostly repeats the same reading.
Below the threshold every lens walks. In walk mode an agent receives the whole
patch but its prompt lists the slices in order with their token counts, so it
can skip slices irrelevant to its lens. The unit of cost is tokens read, not
price per token: a cheap model re-reading a large patch eleven times costs more
than an expensive one reading each slice once.

Then size the plan. For each agent instance: input tokens are roughly the patch
it reads plus 15,000 for context, protocol, and code it opens, times 1.5 for
re-reads; output is small. To compare the weight of plans, multiply tokens by a
relative weight per model: haiku 1, sonnet 2, opus 4, fable 10. These are
weights for comparing one plan with another, not prices; never present them as
money. Sum, and add the verifier pass, which is often the larger part: past
runs verified about one finding per 1,000 diff tokens, roughly a third of them
majors and blockers (opus or fable, about 20,000 tokens each) and the rest
minors (sonnet). When an earlier run of this branch has an "Actual usage"
section in its `plan.md`, size from its tokens per reviewer and per verifier
instead. Estimate wall-clock time at about four minutes per wave of twelve
instances plus five minutes per wave of twelve verifiers.

Write the full accounting to `<run>/plan.md`: the per-lens table with model,
instance count, tokens, and relative weight, the triage decisions per slice,
and the excluded files. That file is for anyone who wants to know why the run
was as large as it was.

End `plan.md` with the instance list, one line per reviewer that will run. This
is the ground truth for resuming, so write it before launching anything:

```
## Instances
| # | lens | scope | patch | model | raw file |
| --- | --- | --- | --- | --- | --- |
| 1 | security | entities | patch/entities.patch | opus | raw/security-entities.md |
| 2 | rollout | all | patch/whole.patch | opus | raw/rollout.md |
```

What you say to the user is the plan in plain words. Build it from the slice
labels and summaries and from the "Say it as" and "Described as" columns in
`routing.md`:

```
Review plan for <target>
<N> files on <branch>, compared against <main branch>.

The change splits into <M> parts, each reviewed on its own:

- [ ] <Label>: <summary>
- [ ] ...
- [ ] Whole change: <focus phrases for the walkers>

(The same list is the progress view during the run.)

Review focuses:

- <Say it as>: <described as>
- ... (one line each for the focuses that run on every part or on the
  largest parts; group the remaining ones on a final line by phrase only)

Not included: <phrases for lenses dropped or not routed>, <reason in a few words>.

About <minutes> minutes.

Running.
```

Then continue straight to Step 5. Do not add anything after "Running.": no
token counts, no run directory. Those are in `plan.md`.

With `--plan-only`, write `plan.md` (its first line
`Estimated total: about
<minutes> minutes`), show the plan with "Planned; not
started." in place of "Running.", end with the `RUN_DIR:` line when headless,
and stop. A later `--resume <label>` continues that run from Step 5.

## Step 5: fan out

Launch lens agent instances in waves of at most twelve per message, opus
instances first, then sonnet, waiting for each wave to finish before the next.
Within a wave the instances run in parallel. Each prompt contains exactly these
lines, then nothing else:

```
DIFF: <path to the patch for this instance's scope>
BASE: <ref>
HEAD: <ref>
SLICES: <path or none>
SCOPE: <all or slice name>
TRIAGE: <path to this slice's triage answers, or none>
CONTEXT: <path to repo-context.md or none>
MODE: <quick | standard | deep>
REPO: <absolute repo root>
PR: <title and body, or none>
DOCS: <paths of selected work-tracking documents, or none>
GUIDANCE: <path of <run>/guidance.md>
WORKSPACE: <path of .clerk-dev/workspace.md, or none>
```

plus `BAR: final` on a final pass, and `PASS: <focus>; piece <record id or none>`
with `--pass`.

Before the first wave, write the guidance file with `records.py guidance
<worktree> --context <the CONTEXT path, when there is one> --out
<run>/guidance.md`: the branch's Purpose (read, or drafted, at the start of the
run; see Branch notes first), its guidance rules, the feature's active guidance
(see Branch notes in `tracking.md`), and the repo context's Known noise. Pass its path as
`GUIDANCE` to every lens and verifier. Relay any warning it prints about
guidance that names specific code in one line. When the branch notes have
Guidance rules or the feature has active guidance, mention in the plan in one
line that the user's guidance applies, and add a sentence about it to "About
this review" through `not-reviewed.md`.

In quick mode, pass `model: sonnet` on the invocation to override the agent's
frontmatter. Do not add instructions; the agent's own prompt and the protocol
carry them.

## Step 6: collect and dedupe

Write each agent instance's complete output to `<run>/raw/<lens>[-<slice>].md`,
verbatim, under a header:

```
# <lens> on <slice or all>
model: <model>  effort: <effort>  started: <time>  finished: <time>
patch: patch/<file>  tokens read: ~<n>
usage: <tokens> tokens, <duration>
```

`tokens read` is the estimate from the plan; `usage` is what the agent actually
used, from the token count and duration Claude Code reports when the subagent
finishes. Write `usage: unknown` when no count was reported.

Do not copy a reply into the file by hand. When the Agent tool returned an
`output_file` for the instance (a background agent), write the raw file with
`${CLAUDE_PLUGIN_ROOT}/scripts/agent-reply.py <output_file> --out
<run>/raw/<lens>[-<slice>].md --header "<line>" ...`, one `--header` per header
line above; it extracts the agent's final reply from its transcript without
reading the transcript into this session. Only when there is no output file,
write the reply as it was returned.

Agents are read-only by design; the orchestrator is the only writer. Then run
`merge-findings.py <run>/raw -o <run>/merged.md`. It parses every `findings`
block, merges entries on the same file with overlapping or adjacent line ranges,
keeps the highest severity and confidence and the union of lenses, slices, and
evidence, and reports how many findings it parsed per file. If a raw file shows
zero findings but visibly contains a `findings` block, the agent broke the
format; read that file yourself rather than patching the script. Do not write a
parser of your own. Merging by line range is deliberately mechanical; two
findings about the same defect in different files stay separate and the verifier
sees both.

## Step 6b: reconcile with the previous review

Skip with `--fresh`, or when no earlier run for the same target has a
`report.md`. The reviewers in step 5 never saw earlier findings; this step
brings the history in only for judgment, so earlier decisions cannot anchor what
is discovered.

1. Run `reconcile.py <previous run> <run>`. It writes `<run>/reconcile/`:
   mechanical matches, fuzzy candidates, and earlier findings with no match.
2. Judge the candidates with one haiku subagent (effort `low`): for each pair,
   the two claims and locations, answer `same` or `different` in a TSV
   (`cur_id`, `prev_id`, verdict). Run
   `reconcile.py <previous> <run>
   --judged <that file>`.
3. Run `reconcile.py <previous> <run> --seed` to carry statuses that still apply
   (in progress, won't fix, deferred) and earlier resolution text. A finding
   that was marked fixed and was found again is not carried: it is reopened.
4. Recheck every earlier finding that was marked fixed and has no match. Absence
   from a blind run is not proof: a lens may simply not have looked. Use the
   Rechecking procedure in the `review-fix` skill with the patch set to the
   whole branch for that finding's files
   (`git diff <BASE>..HEAD --
   <files>`), not just the fix commit. Write
   `<run>/reconcile/since.tsv` (`prev_id`, `resolved` | `reopened`, one-line
   note). For `reopened`, append the earlier finding to `merged.md` with
   `reconcile.py --append` and add a row to `reconcile/matches.tsv` (`how` =
   `recheck`), so it renders as reopened. Earlier open findings with no match
   are not rechecked; the report lists them for the user to confirm.
5. Earlier findings that were declined or deferred and were found again go to
   verification in step 7 whatever their confidence, with the earlier reason.

Say one line: "Compared with the review of <date>: <n> carried, <n> reopened,
<n> to recheck." The report's "Since the previous review" block has the rest.

## Step 7: verify

Select findings to verify by risk, not confidence alone: every `blocker`
whatever its confidence, every `major` at 40 or above, every `minor` at 60 or
above (40 in deep mode), and every finding step 6b matched to an earlier
declined or deferred one. Minors raised only by `naming-concepts` or
`user-facing-text` need 75 (60 in deep mode): they are the most numerous
minors, they never hold the merge, and below 75 they are mostly rejected or
adjusted anyway. Below their bar they are counted, not reported. Do not skip any selected finding to save cost; a
verifier call is cheap next to a missed major. Run one verifier subagent per
selected finding in parallel, effort `high`: model `fable` for findings of
severity `blocker`, for `major` findings on a final pass (the merge gate), and
for every finding in deep mode; `opus` for other `major` findings; `sonnet` with effort `medium` for `minor` findings, including every
tech-debt finding (those with a `debt` label), whose questions are judgments a
careful reader settles from the code in view: whether the defect is there,
whether a proposal keeps the behavior and is worth doing (see Model fallback). The verifier reads the finding, the relevant slice patch, and
the code at HEAD, and returns the finding with an adjusted confidence and a
one-line verdict: confirmed, adjusted (with the new number and why), or rejected
(with why). Tell it the false-positive list from the protocol and that its job
is to be the skeptic. Pass `GUIDANCE` and `BASE` as for the lenses. The
verifier also checks the finding's `origin` against the code at `BASE` and its
`fix_size` against the recommendation (Origin and fix scope in the protocol),
and when it disagrees adds `origin: <value>` or `fix_size: <value>` to its
verdict, which the renderer uses instead. Tell it the rubric's
rule as well: confidence is only about whether the defect exists; if it is real
but rare or its impact depends on something unseen, it keeps the confidence, may
lower the `severity`, and puts what is uncertain in its note. A verifier that
lowers confidence because impact is uncertain hides real findings. Nor does
rarity lower the severity of an error that fails silently (caught and only
logged, or turned into a default): what is lost when it happens sets the
severity, since nobody will notice when it does. Write each
verdict to `<run>/verify/<id>.md`, where `<id>` is the finding's id from
`merged.md`, as soon as that verifier returns, with a second line
`model: <model>  usage: <tokens> tokens, <duration>` as for the reviewers; a resumed run skips findings that
already have a file.

For a finding matched to an earlier declined or deferred one, also give the
verifier the earlier reason and ask a second question: does this finding's
evidence answer that reason? It returns `holds` or `answered` with one sentence.
Write `<run>/reconcile/prior.tsv` (`cur_id`, outcome, sentence). `holds` keeps
the finding in "Previously declined"; `answered` puts it back in the normal
sections with both the reason and the counter-evidence shown.

Drop rejected findings. Everything else stays in `merged.md`; the renderer
decides the section from severity and final confidence: blockers and majors at
80 or above to "Fix before merging", minors at 60 or above and majors from 60 to
79 to "Worth a look" (quick mode raises the minor bar to 80, never the major
one), blockers below 60 to "Needs confirmation", majors from 40 to 59 to the
"Below the bar" section, and minors below 60 to a count only.

## Step 7b: pull request comments

By default, unless `--no-pr-comments` was given, and always with
`--pr-comments-only`. First check that the branch has a pull request:
`gh pr view --json number` from the repository. If there is none, or `gh` is not
installed or not signed in, skip this step and say so in one line ("No pull
request for this branch; skipping its comments."), and when the reason is
`gh`, add the one-time line under First runs in a repository. Otherwise:

1. Run `pr-comments.py <run> --repo <repo>` (add `--pr N` when the branch's pull
   request cannot be found from the branch). It adds each review thread, review
   summary with a body, and conversation comment as an entry in `merged.md` with
   `lens: pr-review`, the author, the link, the replies, and the GitHub state;
   known comments are refreshed, not duplicated. It writes a shortlist of up to
   five candidate agent findings per new comment to `pr/candidates.tsv`.
2. Judge the links with one sonnet subagent (effort `medium`). Give it each new
   comment's text and location, and for each candidate the finding's title,
   claim, and location. For each comment, at most one candidate is `same`: the
   comment and the finding are about the same defect or the same question, even
   if worded differently or anchored in a different file. A finding nearby on a
   different concern is `different`. For each comment with no `same`, also name
   the lens whose focus fits it best (from the plain names in `routing.md`). It
   writes `pr/judged.tsv` (`pr_id`, `finding_id`, `same` | `different`) and
   `pr/lens.tsv` (`pr_id`, lens). Apply with
   `pr-comments.py <run> --judged <run>/pr/judged.tsv`.
3. Verify every comment not linked to a finding, as a second opinion only: the
   verifier reads the comment and the code at HEAD and says whether it still
   applies (it may already be addressed, or the code may have moved). Write the
   verdict to `verify/<id>.md` as usual. Human comments are never hidden by a
   verdict or a bar; the renderer shows the note on the card. When the comment
   still applies, the same verifier also fills in the card's sections, so a
   human comment reads like any other finding. It writes them to
   `overrides/<id>.md` (the comment's entry in `merged.md` is rewritten whenever
   the comments are refreshed; overrides survive that), one `key: value` field
   per line, in the protocol's style, with no YAML `|` or `>`:
   - `impact`: why it matters, in the code's terms. Keep the comment's own
     weight: a readability or style point says so ("Readability only: ..."), and
     is never dressed up as a defect.
   - `context`: what the reader needs to know about the code to judge it.
   - `steps`: how it goes wrong, numbered, only when there is a concrete failure
     path; leave it out for style, naming, and questions.
   - `snippet`: `path:start-end` of the code in question at HEAD, at most 12
     lines.
   - `fix`: what to do, starting from what the commenter asked for, with any
     adjustment the second opinion found (sibling call sites, tests that
     change).
   - `uncertainty`: only when something could not be checked. Write only fields
     the file does not have yet: a field the user wrote there by hand stays. A
     comment that no longer applies, or a question whose answer is the whole
     point, gets no overrides; the Second opinion says it all.
4. Write titles for the new comments into `titles.tsv`: the comment's point in
   plain words, at most ten words, phrased as a finding title, not a quote
   ("Replay can send real messages from a reload-like button").

The report then shows unlinked comments in their own "Pull request comments"
section, always and before "Fix before merging", and linked ones inside their
finding's card, with both sides' details. In `--pr-comments-only` mode, render
with the same arguments as the run's last render and show the section. That mode
also backfills: an unlinked comment that already has a verdict saying it still
applies, but no `overrides/<id>.md`, gets its sections filled as in step 3, by a
verifier that reads the comment, its `verify/<id>.md`, and the code at HEAD.
Several such comments go to one verifier each, in parallel.

## Step 8: report

The report is written for the author of the change, not for the pipeline.
Confidence scores, lens identifiers, slice names, token counts, and costs did
their work in steps 6 and 7; they stay in `merged.md` and `plan.md`. The report
says what was found, where, what goes wrong, what it means, and what to do,
ordered by what the reader should do about it, grouped by the part of the code,
and numbered so a conversation can refer to "finding 2".

The renderer script produces the document; you supply three short inputs:

1. `<run>/titles.tsv`, only for findings whose `title` field is missing or poor:
   merged id, a tab, a heading of at most ten words in plain terms.
2. `<run>/summary.md`: three or four sentences on what the change does, where
   the risk concentrates, and the one or two things that must happen before
   merge. Refer to findings by number.
3. `<run>/not-reviewed.md`: one line each for excluded files with size when it
   matters, parts no lens looked at, focuses that did not run, and documents
   dropped by the selection cap.

Then run
`render-report.py <run> --target <target> --branch <branch> --base
<short sha> --head <short sha> --repo <repo> --routing
${CLAUDE_PLUGIN_ROOT}/skills/review/routing.md --date <date> --files <n>
--parts <n> --focuses <n> --summary <run>/summary.md --not-reviewed
<run>/not-reviewed.md`,
plus `--quick` in quick mode. It writes `<run>/report.md` and
`<run>/numbers.tsv`. Then run `usage.py <run> --append`, which adds the run's
real usage to `plan.md` under "Actual usage", next to the estimate.

What the document contains, so you can check it:

- Front matter with the target, branch, commits, date, run path, counts.
- A summary, then a glance table: number, title, area, focus, fix size (with
  "follow-up" when another repository must change too), action.
- Sections "Reopened", "Pull request comments", "Fix before merging", "Worth a
  look", "Needs confirmation", "Already on main" (defects with origin
  `existing`, whatever their severity: they do not hold the merge, and the
  recommendation is a separate pull request), "Cleanup and refactoring"
  (tech-debt findings, labeled cleanup, simplify, or refactor; they do not hold
  the merge), and "Previously declined", each grouped by area
  (the part labels), with page breaks; then "Below the bar", full cards for the
  majors the bar left out, each saying why, with unticked checklists that
  nothing acts on until the user ticks one. Empty sections are omitted.
- Each card: numbered title; a hidden anchor comment; the action in bold (as
  the glance table's Action column words it) and the area; a focus line; a
  scope line (fix size, origin, and any follow-up in another
  repository, such as "Fix size: trivial · New on this branch"); a status
  checkbox line; the bare `path:line`; the one-sentence claim;
  then subheadings: Why it matters, Context, How it goes wrong (a numbered list
  when it is a sequence), an optional snippet pulled from HEAD, Recommendation
  (or What would confirm it), Second opinion only when the verifier left a note,
  and Resolution once a fix has been made. A finding appended after a fix may
  say which fix surfaced it.
- "Not reviewed this run" and "About this review", which states how to refer to
  findings by number and where the detail lives.

Read the rendered report once. If a title is a long sentence, a card is missing
its mechanism or impact, or a snippet is unhelpful, fix the input and re-render;
do not hand-edit `report.md`, because `--report-only` would overwrite it. Field
fixes go in `<run>/overrides/<merged id>.md` as `key: value` lines (`title`,
`context`, `steps`, `impact`, `snippet`, `fix`); the renderer overlays them on
the merged entry. Never edit `merged.md` by hand; the merge step regenerates it.

Show the report as your final message, without a preamble.

## Finding numbers

Numbers are assigned by the renderer in document order and written to
`numbers.tsv`. They are fixed for the run once the report is shown; a re-render
with the same inputs gives the same numbers. In `summary.md` and in override
fields, refer to another finding as `{#<merged id>}`; the renderer replaces it
with the current number, so cross-references never go stale. After the report,
refer to findings only by number ("finding 2").

When the user refers to a finding, by number or by a location in the report such
as `.clerk-dev/<label>/report.md:92`:

1. For a location, read the report upward from that line to the nearest card
   heading (`#### N.`). The HTML comment right under it names the number, the
   merged id, the verify file, and the raw reviewer files. For a number, read
   `numbers.tsv` or find the same heading.
2. Answer from the merged entry in `merged.md` (claim, scenario, evidence), the
   verifier's note in `verify/<id>.md`, and the reviewer's full text in the raw
   files named by the anchor. Show the snippet or the surrounding code at HEAD
   when asked.
3. Never rerun a reviewer to answer a question about an existing finding. If the
   user disputes a finding, say what the evidence was and what would settle it;
   if they want it dropped or reworded, write an override and re-render rather
   than editing the report.

## Tracking what was done

`<run>/status.tsv` records, per merged id, one of `open`, `in-progress`,
`fixed`, `wont-fix`, `deferred`, with a reference (commit hash, ticket, or
reason) and a date. The renderer shows it as a checkbox line on each card and a
column in the glance table, with a progress line above the table. The report is
still generated, so the status file is the source of truth; a box the user ticks
by hand in `report.md` is imported into the status file at the next render, with
a commit hash if the line has one.

Change a status only through the renderer:
`render-report.py <run> ...
--set N=fixed:<sha>` (also `in-progress:<files>`,
`wont-fix:<reason>`, `deferred:<ref>`, `open`), with the finding number as the
user sees it. Never edit `status.tsv` or tick boxes in `report.md` yourself; the
renderer reconciles hand edits against what it last wrote, and a direct file
edit can be undone by that reconciliation.

Rules:

- Fixes run through Fixing a finding, which commits and records the status
  itself. Outside that flow you never commit.
- When the user says a finding is fixed, or names a commit, record `fixed` with
  the hash. If they ask you to check, look for the commit in `git log` that
  touches the finding's files and confirm it with them before recording.
- When the user declines a finding, record `wont-fix` with their reason in a few
  words; when they park it, `deferred` with the ticket or note.
- The `--set` render is the re-render; say what changed in one sentence.
- Statuses carry no judgment: a disputed finding that the user rejects is
  `wont-fix` with the reason, not deleted.

## Fixing and rechecking

Fixing a finding and `--recheck` are handled by the `review-fix` skill in this
plugin (`clerk-dev:review-fix`), which loads on its own when the user asks to
fix or recheck a finding. For `--recheck N`, invoke that skill with the same
arguments and follow it.

## Triage instructions

Every card ends with an "Instruction" checklist: Fix as recommended, Fix as
noted (fix following the Notes, which replace the recommendation), Discuss,
Defer, Ignore, each optionally followed by `: <note>`, and a `Notes:` line for
free text of any length. When the recommendation labels alternatives (a), (b),
the user picks one by writing it after the label, "Fix as recommended (a)" (or
"(a, c)"); it is stored in the `option` column of `instructions.tsv`, and a pick
the recommendation does not label draws a render warning to relay. The user
ticks one and writes notes in the report; the renderer imports them into
`<run>/instructions.tsv` and `<run>/notes/<merged id>.md` at the next render,
and shows a Triage column and count in the glance section.

The report is regenerated on every render, so the renderer protects edits: each
render stamps the report with a generation number and keeps what it wrote under
`.render/<generation>/`; a saved report is compared with the render it came
from, so a buffer saved after a later render contributes only the lines the user
changed. The previous report is kept as `report.prev.md`. Two ticked boxes use
the first, and the card and the render's warning say so; relay that warning to
the user. Edits anywhere else in the report are not kept. Agents set
instructions with `--instruct N=<choice>[:note]` and add notes with
`--note N=<file>`, never by editing the report; the `review-triage` skill's
"Recording a decision" says what goes where. Defer and Ignore also set the
status (deferred, won't fix, with the note as the reason) when the finding is
open.

The `review-triage` skill works through them: fixes first, each in its own
session, then discussions with the user.

## Report-only mode

With `--report-only [label]`, skip steps 1 through 7. Read the run directory,
check that `merged.md` and `verify/` exist, write or update `titles.tsv`,
`summary.md`, and `not-reviewed.md` as needed, run the renderer, and show the
report. The run's `target.txt` supplies the target and commits (or, for older
runs, `scope.md`), and `plan.md` and `numbers.tsv` the counts.

With `--comment` and a PR target, post the report as one PR comment via
`gh pr comment`, after showing it here.

## Feature mode

With `--feature`, each repository is reviewed in its own worktree by its own
headless Claude Code session, so it loads that repository's CLAUDE.md, settings,
skills, and repo context, and writes its run and report under that worktree's
`.clerk-dev/`. This session coordinates and runs only the cross-repository lens.

1. Discover: read `.clerk-dev/workspace.md` in this worktree. When it is
   missing, set it up with the user as `workspace-manifest.md` describes (a
   headless session stops instead). Its rows are the repositories and
   worktrees of this job; nothing else is searched. Say in one line which
   repositories have changes on their branch and which have nothing yet.
2. Review: for each worktree, in parallel and in the background, run
   `claude -p "/clerk-dev:review <passed flags>" --name "<repo> review"
   --allowedTools "Bash(git *)" "Bash(gh pr *)" "Bash(gh repo *)"
   "Bash(gh api *)" "Bash(python3 *)" "Bash(ln *)" "Bash(mkdir *)" Read Grep
   Glob Agent Write`
   with that worktree as the working directory, output to
   `<run>/children/<repo>.log`. With `--children-permission-mode <mode>`, add
   `--permission-mode <mode>`. The sessions get this session's environment
   unchanged; how they authenticate is the user's setup, so do not comment on
   it or offer to change it. The passed flags are this run's `--final`,
   `--quick` or `--deep`, `--full`, `--fresh`, `--no-pr-comments`, `--lenses`,
   `--split` or `--walk`; never `--feature`, `--consolidate`, or a target. Each
   child decides for itself between incremental and full review, drafts its own
   branch notes if missing, and writes its run under its own worktree.
3. Plan: as each child writes its `plan.md`, show one line for that repository:
   its parts, whether it builds on an earlier review or is full, and minutes.
   Then one line for the cross-repository check, and one line saying that
   several sessions in parallel use a lot of usage at once.
4. Wait for the children. Note the time before launching them, then start a
   Monitor with
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/progress.py --since <that time>
   --worktree <repo>=<worktree> ...`
   (one `--worktree` per child, `timeout_ms` 1800000, description "Review
   progress"). It checks the children's run directories every 30 seconds and
   prints a compact line when one moves to its next step (planning, reviewing,
   merging, verifying, done), or every two minutes when none has; a reviewer
   finishing does not print on its own. A line reads
   `6 min in · api: reviewing 18/21 (3 min) · clerkai: merging (4 min)`, the
   parenthesized time being how long that child has been in its step. Relay
   each line in this layout, with the repository names exactly as given, the
   same wording every time, and nothing else:

   ```
   Review progress · running in the background, 6 min in
     api      reviewing: 18 of 21 reviewers done
     clerkai  merging findings (for 4 min)
   Next update when a repo moves to its next step, or in 2 min if nothing changes. You can keep working.
   ```

   Start the monitor again when it expires before the children finish.
   Report each child as it finishes, on its own line after the block
   ("api done: 2 new findings, 1 reopened"), reading
   its `RUN_DIR:` line and its run's `numbers.tsv` and `status.tsv`. A child that fails is named with the last lines of its log; the
   others continue.
5. Cross-repository lens: build each repository's whole-branch patch from its
   own merge base with its own remote main (the row's `Main`, else its
   `origin/HEAD`; `git -C <worktree> diff
   <base>...HEAD`), even when that repository's review was incremental,
   because contract mismatches do not care when a change was made. Run
   `clerk-dev:lens-cross-repo` with `model: fable` (see Model fallback) and
   repeated `REPO`, `DIFF`, `BASE`, `HEAD`,
   `CONTEXT`, `GUIDANCE` blocks (`GUIDANCE` is that repository's guidance
   file, `records.py guidance <its worktree> --context <its CONTEXT> --out
   <run>/guidance-<repo>.md`, whose branch scope says what that side meant to change), plus `MODE`,
   `PR`, and `DOCS`; `DOCS` includes each repository's
   `.clerk-dev/followups.md` (see `tracking.md`). Merge, verify,
   and number its findings in this session's run directory as usual.
   With `--final`, the lens and its verifiers also get `BAR: final`, and
   its findings are split by the bar as in Final pass steps 6 and 7 (with
   no earlier feature run to join, as for a run with no review to join),
   keeping the ones below it in `final/below.md`. After the feature
   report, run `final-report.py <run> --child <repo>=<child run> ...` for
   every repository, which writes `final-review-report.md` here (a verdict
   table, one row per repository plus the cross-repository check, then
   what the check covered) and in any child run that lacks one. The
   feature passes only when every row passes; lead the final message with
   that verdict.
6. Feature report: this session's `report.md` holds the cross-repository
   findings as normal cards, with absolute paths. Its `summary.md` has one block
   per repository: the repository's progress line, its "Fix before merging"
   titles with numbers, its open follow-ups count, and the absolute path of its
   own `report.md`. Cards are never copied between reports; each repository's
   findings are fixed and tracked in that repository's report.

The run directory of the coordinating session is
`<repo>/.clerk-dev/<label>-feature/`, linked from `<repo>/.clerk-dev/latest-feature`
(see Step 0).

End the final message with every report's absolute path, one per line, the
feature report first and then each repository's in the order of the workspace
rows:

```
Reports:
  feature  /Users/me/code/api/feat/x/.clerk-dev/20261015-1235-branch-feature/report.md
  api      /Users/me/code/api/feat/x/.clerk-dev/20261015-1238-branch/report.md
  clerkai  /Users/me/code/clerkai/feat/x/.clerk-dev/20261015-1236-branch/report.md
```

A repository whose session failed, or that was not reviewed at its current
commit, gets its row with the reason in place of the path.

### Consolidating separate reviews

With `--feature --consolidate`, skip steps 2 to 4. After discovery, take each
worktree's latest finished run (`.clerk-dev/latest`, or the newest run directory
with a `report.md`) and check it is current: its `HEAD` equals the worktree's
`HEAD`. For a stale or missing run, say so in one line per repository ("web:
last reviewed 3 commits ago" or "worker: no review") and continue with the
rest; the feature report marks those repositories as not reviewed at their
current commit. Then run steps 5 and 6 as written, after one line saying the
cross-repository check is starting and roughly how long it takes.

## Run directory contents

`<run>` holds `target.txt`, `scope.md`, `files.tsv`, `slices.md`, `patch/`
(`all.patch`, `whole.patch`, one per slice), `triage/`, `plan.md` (with the
instance list), `progress.md`, `raw/<lens>[-<slice>].md`, `so-far.md` (interim,
unverified), `merged.md` (and `merged-new.md` in incremental runs),
`verify/<id>.md`, `guidance.md` (and `guidance-<repo>.md` in feature runs),
`reconcile/`, `pr/`, `titles.tsv`, `overrides/`, `summary.md`,
`not-reviewed.md`, `numbers.tsv`, `status.tsv`, `instructions.tsv`,
`notes/<id>.md`, `resolution/<id>.md`, `recheck/`, `.render/<generation>/` with
the `rendered-*.tsv` snapshots, `report.md`, `report.prev.md`, `stale.tsv`
(cross-check judgments), `commits.tsv` (every commit a status named, kept when a
later fix replaces the ref), `narrow.txt` (narrow runs), and `final/` (final
passes: `verify/`, `kept.md`, `below.md`), with `final-review-report.md` (the
final pass's verdict) next to `report.md`. Next to the run directories,
`.clerk-dev/latest`, `.clerk-dev/latest-feature`, `.clerk-dev/branch-notes.md`, `.clerk-dev/followups.md`,
`.clerk-dev/workspace.md` (or a link to it), and `.clerk-dev/status-seen`
belong to the worktree. Raw and verify files are written
only on completion, which is what makes `--resume` safe. A run stopped after
`--plan-only` has no `progress.md` items checked and no raw files;
`--resume <label>` runs it while `HEAD` is unchanged, and otherwise a new run is
planned.

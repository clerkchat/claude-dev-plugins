# Tracking files

What the plugin keeps between runs, beyond each run's own directory. All of it
lives under `.clerk-dev/` in a worktree, which is excluded from git through
`.git/info/exclude` and never committed.

| File                      | Scope                                                                                                                                                     | Written by                                                                                                                                                                                                                                    | Read by                                                                                                                                                               |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.clerk-dev/<label>/`        | one review run                                                                                                                                            | the review orchestrator                                                                                                                                                                                                                       | everything below; see "Run directory contents" in `SKILL.md`                                                                                                          |
| `.clerk-dev/latest`          | link to this branch's newest review run; never a feature run                                                                                              | the review orchestrator, except feature mode's coordinating session and `--standalone` narrow runs                                                                                                                                            | fix skill, incremental review                                                                                                                                         |
| `.clerk-dev/latest-feature`  | link to the newest feature run (`<label>-feature`), in the worktree feature mode was started from                                                         | feature mode's coordinating session                                                                                                                                                                                                           | the user, `status.py`                                                                                                                                          |
| `.clerk-dev/branch-notes.md` | what this worktree's branch is for (Purpose) and the rules the user set for this branch only (Guidance); may be written before the first review | the review orchestrator, the `building` skill's setup check (drafts Purpose when missing), any skill recording an answer's guidance for this branch ("Guidance from answers" below), the user | `records.py guidance`, whose file every lens, verifier, and builder handoff gets; the `building` skill's intake and the builder (Branch scope below) |
| `.clerk-dev/status-seen`     | the highest follow-up id already shown                                                                                                                    | the `status` skill                                                                                                                                                                                                                     | the `status` skill (marks newer items as new)                                                                                                                  |
| `.clerk-dev/followups.md`    | work this repository owes because of changes elsewhere                                                                                                    | `followups.py`, from the `building` skill (After each handoff and its Clients of a changed contract) and `checkpoint` | the review orchestrator (as a document for completeness and cross-repo lenses), the `followups` skill (works and closes items, one commit each), the user |
| `.clerk-dev/deferred.md` | known gaps with a path chosen for now: what was deferred, from where, what was done meanwhile, what is left, when to look again ("Deferred items" below) | `deferred.py`, from every skill that applies Defer | `status.py` (open count and items), the user, a plan step's "deferred items reviewed" |
| `.clerk-dev/review-workspace.md` | the repositories and worktrees of a review job across repositories; the file in the worktree where the job was set up, a link to it in every other worktree of the job | the review orchestrator's feature mode (set up with the user, see `workspace-manifest.md`), the user | feature mode, the `building` skill (clients of a changed contract), the `followups` skill (source worktrees), `status.py` (follow-ups owed elsewhere), follow-ups (consuming worktrees) |
| `.clerk-dev/feature/` | a feature's records (brainstorms, designs, decisions, pieces, plans, briefs) and `feature.md` with their index; only in the hub worktree (see `skills/feature/records.md`) | `records.py`, from the `feature` skill; the user | the `feature` skill, the review orchestrator (active records for the reviewed repository, as documents) |
| `.clerk-dev/passes.md` | this worktree's passes: focus, lenses, piece, mode, commit range, checklist, and pass-review result (see `skills/pass/passes.md`) | `passes.py`, from the `pass` skill | the `pass` skill, the user |
| `.clerk-dev/build.md` | this worktree's milestones (a plan row's ordered passes, required ones, skips) and handoffs: brief requirements covered and their status (including requirements a decision dropped from a brief), model and effort, commit and its subject (to re-find it after a rebase), questions, accepted deviations; and record entries (`Record:` a decision, plan step, or brief built directly by a commit); the only place requirement status lives | `build.py`, from the `building` and `pass` skills | `status.py` (progress per brief, next steps), `records.py digest` (the overview's Plan, and the decisions and plan steps marked built), the user |

## Branch notes

`<worktree>/.clerk-dev/branch-notes.md` says what the branch is for and holds the
rules the user set for this branch only. Format:

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

## Guidance

### Do not report naming findings in generated files
Why: they are regenerated from the schema; a naming fix belongs there.
From: discussion of finding 12, 2026-10-08

### Prefer one test per scenario over table-driven tests
Why: the user reads failures by test name.
From: the user, 2026-10-09
```

Each rule under Guidance is a `###` heading that states it in one line, then
body lines (usually a `Why:` line), and ends with `From: <source>, <date>`.
State it so it stands without the question that prompted it, and in the terms
of the work, not of one file or symbol. Skills add rules here through
"Guidance from answers" below; the user edits them freely. When a rule refines or contradicts one already
here, edit that rule rather than adding a second; never leave two that
disagree. When the user retracts one, delete it. When a rule is several weeks
old, or names code that no longer exists, ask whether it still applies before
relying on it. Never record anything the user did not say.

Agents get these rules through one file, not this one:
`records.py guidance <worktree> [--area <area> | --for <BRIEF-33, BRIEF-33.4, or
BRIEF-18-1.Q-6>] [--context <review-context SKILL.md>] --out <file>` writes Purpose,
these rules, the feature's active guidance, and the review context's Known noise
into it, and that file is what lenses, verifiers, and the builder's handoffs
get as `GUIDANCE`. `--for` takes the area of the record it names; `--context`
adds the noise.

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
6. Write the file with both headings (an empty Guidance when there is nothing
   for it), create `.clerk-dev/` and its `.git/info/exclude` entry if
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
`review-protocol` skill), and every item the `building` skill's intake sends
decides how to change code by it. Code is on one of three sides:

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
It states a contract and a need, never the change to make in the receiving
repository or its size, since the sender cannot see the receiving code. The
contract takes one of two forms:

- `changed: <old to new>`, from a provider to its consumers: the endpoint,
  event, or schema as it was and as it is now. The need is the behavior the
  consumer must now handle. Contract `changed: GET /reports/:id/download: took
  no parameters, now requires the exportId that POST /reports/:id/exports
  returns`; need "a download poll without exportId is now refused with 400".
- `wanted: <shape, and how it differs from today>`, from a consumer to its
  provider: the shape it needs. The need is what the consumer is building
  against. Contract `wanted: GET /contacts?q= matches phoneNumber too; today it
  matches name only`; need "contact search sends phone digits as q and expects
  the matching contacts".

The need is never the receiver's action: "show the number on the contact card"
is the receiving repository's call. The receiving session sizes the item and
routes it through intake (the `building` skill).

When a fix in the api changes a contract the frontend consumes, the item goes
into the frontend worktree's `.clerk-dev/followups.md`, with the need as the
text and the contract as `--contract`:

```
followups.py add <owing worktree> "A download poll without exportId is now refused with 400" \
  --from "api 7c1e2ab" \
  --contract "changed: GET /reports/:id/download: took no parameters, now requires the exportId that POST /reports/:id/exports returns" \
  --finding "api 8"
```

A builder's `follow-ups:` line and a finding's `follow_up` field carry one
follow-up per line as `<repo>: changed|wanted: <contract>; needs: <behavior>`:
the item goes to `<repo>`'s worktree, the part after `; needs:` is its text,
and the part between `<repo>: ` and `; needs:` is its `--contract`.
A line not in that form (no `changed:` or `wanted:`, or no `; needs:`) is
not filed as written: restate it in the form from the rest of the report or
finding, or ask the builder for it, as a malformed report is sent back.

Find the owing worktree in `.clerk-dev/review-workspace.md` (see
`workspace-manifest.md`). When the file is missing or does not list the
owing repository, add the item to the current worktree's file with the text
starting `[<repo>]`, and say so.

The item's id (`F3`) is the handle in conversation. Each item has an
Instruction and a Status (see Items below). For a follow-up, "done as written"
and `Fix as recommended` mean meeting the need as intake sizes it. Refine
(investigate, then set one of the others) is the instruction for an item whose
need is unclear against the local code. The user sets one by saying so
("refine F3", "ignore F2, the web app dropped that screen"), which is recorded
with `followups.py set <worktree> F3 "Refine" [--note "..."]`. The `followups` skill works the open items by their
instructions, one handoff and one commit each, and closes each with
`followups.py close <worktree> F3 --ref <sha>` (or `--status
wont-fix|deferred --ref "<reason>"`). Close one by hand the same way when the
user says it is done. Hand-ticked boxes are honored as fixed.

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
- The `followups` skill gives each handoff the open findings in the files
  it will change, as context, and notes on a finding when the follow-up's
  contract overrides its recommendation.

## Guidance from answers

When the user answers a question (a design question, a builder's stopped
handoff, a finding to discuss or a fix to adjust, a follow-up to refine, a pass
item), the answer often carries guidance: a rule that would settle other
choices the same way, beyond this one. Record it without being asked, where
the routing below sends it, and say in one line what the rule says and how far it reaches, as "Talking to
the user" describes, so the user can correct the scope or the wording.

Recognize it two ways:

- **Explicit:** a line or message starting `guidance:` (any case), optionally
  with a scope, `guidance (branch): ...` or `guidance (harness): ...`. Always
  record it, in the user's words: at the scope given when the routing below
  finds it is guidance, and where the routing sends it otherwise, saying so.
- **Implicit:** the answer states a rule rather than a one-off: "always",
  "never", "prefer", "in general", "as a rule", "we don't", "from now on", or
  reasoning that would decide other cases too ("because the core should not
  know capability names"). Record it, and phrase the rule so it stands without
  the question.

Route it before picking a scope. Ask these in order, and take the first that
fits:

1. Would the sentence still be true for a different feature? It is guidance.
   Pick its scope, narrowest first:
   - this branch: a `###` rule under Guidance in the branch notes (Branch notes
     above);
   - this feature, or one of its areas: a `guidance` record in the hub
     (`records.py new <worktree> guidance "<rule>" --area <area> --from <the
     question>`), body as in `skills/feature/records.md`;
   - all the user's work: the user's own CLAUDE.md; propose the line and ask
     first;
   - the team: the plugin itself, such as the `writing-code` skill; propose it
     and ask first.
2. Does it describe what the product does or must do? A requirement in the
   brief, or a decision when it was chosen among alternatives.
3. Does it fix the shape of something between components (a type, a route, an
   event, a table another part reads)? A decision, or the brief's Contracts.
4. Does it say what may change on this branch, or how carefully? Purpose, as a
   dated line under "New in this branch" or "Deployed code it changes on
   purpose".
5. Is it a fact about branches, repositories, or worktrees? The review
   workspace manifest (`workspace-manifest.md`) or the feature summary.
6. Does it settle this question only? The question's own outcome or notes.

When unsure, record it as a decision, and say so in the confirmation line so
the user can redirect it.

When the user redirects where something was recorded ("that is a branch rule,
not a decision"), fix it the usual way: supersede, discard, or move it to the
place the routing gives, with a note starting `rerouted:` that says where it
went (`rerouted: to branch guidance`). The note is the discard's `--note`, or
a line in the body of the superseding record or the moved branch rule. Status
counts these notes, so how often the routing sends answers to the wrong place
can be judged.

Promoting a rule to a wider scope (a branch rule the user wants for the whole
feature, a feature rule for all their work) supersedes the narrower copy,
saying "promoted to <where>". A guidance record is superseded by the new
record when the wider place is one, and otherwise discarded with that note
(`records.py discard <worktree> GUIDE-61 --note "promoted to <where>"`). A promoted
branch rule is deleted from the branch notes.

Nothing the plugin records goes to Claude's memory. Memory is for preferences
about how sessions behave, not for rules, decisions, or scope.

When new guidance refines or contradicts an active one, supersede it rather
than add a second, restated in full as "When a record changes another" in
`skills/feature/SKILL.md` describes. When it contradicts an active decision, record the guidance
and say which decision it bears on; the user decides whether that decision
changes. The line to the user: "Recorded as guidance GUIDE-61 (harness):
capabilities wire in through explicit lists. Say if it is narrower than
that." For a branch rule: "Added to this branch's guidance: do not report
naming findings in generated files. Say if it reaches the whole feature."

### Lessons from a discussion

A discussion is a set of questions put to the user together: a brief's or
plan's open questions, a design check's walk, the triage's discussions, a
stopped handoff with several questions, a pass's open items. When its last
question is settled, and before the next step starts (a build, the next
handoff, the next pass), look back over the whole discussion once for guidance
no single answer stated. This is the only time it happens; the rules above
still record what an answer states as it comes.

1. Gather the candidates. Look for:
   - reasons the user gave that would decide other cases ("both humans and
     agent-swarm read these reports");
   - choices against a draft's or a decision summary's recommendation, and what made the
     recommendation wrong;
   - guidance or decisions cited during the discussion, and whether the outcome
     honored them or showed their limit (a rule cited against the option the
     user chose);
   - gaps in the records the discussion exposed: a decision the built code no
     longer matches, a term no record defines.
2. Check each against the active guidance and decisions (`records.py guidance
   <worktree>`, and the decisions the discussion touched). Say which it is:
   - **new:** nothing active says it;
   - **extends:** an active rule says part of it; widen that rule;
   - **conflicts:** an active rule or decision says otherwise, or was applied
     past its reason; propose superseding it with the limit stated, or keeping
     it and treating this as a one-off, and recommend one;
   - **records gap:** not guidance; say where the routing above sends it and
     when (now, or a record update already planned).
3. Propose them in one message: each as a rule that stands on its own, its
   scope from the routing above, its kind from step 2, and for a conflict the
   options with the recommendation first. Keep it to what would decide a
   future case; drop observations that only explain this one.
4. Record what the user accepts, in the words they settle on, through the
   routing above, and say in one line each what was recorded. Then start the
   next step.

These are inferred, not said, so propose them and wait; never record one
unasked. When nothing generalizes, say so in one line and move on. When the
user says to skip it ("no lessons", "just build"), skip it without a word.

## Talking to the user

The user works at the level of the feature: what it does, the choices in it,
the rules they set, and what needs their judgment. The plugin exists to take the
inventory off their hands, so the conversation is about the feature, and the
inventory stays out of it unless they ask.

- Lead with the substance: what changed in the feature or the code, what was
  decided, what is open, and what you need from them. Say it in the feature's
  own words ("the voice runtime now hangs up cleanly when the caller drops"),
  not the plugin's ("PASS-10 done, BUILD-17 closed, DEC-40 stamped").
- Bookkeeping gets at most one short closing line, and only when the user
  might want to correct it: a rule recorded from their answer, a decision
  written down, an idea parked. Say what it says and its reach, not the
  mechanics ("Noted as a rule for the voice runtime: no retries on hangup."),
  never the file, the record kind, a script, or the steps taken. Routine
  writes (stamps, statuses, logs, progress, checkpoint notes that only restate
  the conversation) go unmentioned.
- Use the plugin's vocabulary (pass, piece, brief, handoff, milestone, record,
  item, lens, area, overview) only when the user needs it to steer the work, and then in
  plain words ("the edge-cases work on the voice runtime", not "PASS-10"). If the
  user has to ask what a label means, the message should not have needed it.
- Drop an id whenever it adds nothing to what the user will do next. Keep it
  when they are likely to refer back to it ("fix 3"), and then name it as
  below.
- Short and in prose. No tables or headings for a short answer; a list only
  for things the user will pick from or tick off.

### Diagrams

Whatever is written for a person (a message, a record, the overview, a review
report, a PR description) carries diagrams beside the prose they illustrate,
wherever a picture shows something faster than words: how parts connect, what
passes between them, the order things happen in, how options differ.

- Draw them yourself from what you understand now. They are snapshots, like
  the prose around them: never maintained, and replaced along with the document
  that holds them. Nothing cites a diagram as evidence.
- Keep each one focused on a single idea. Several small diagrams beat one that
  covers everything.
- In files, use mermaid. In the conversation, draw ASCII, since mermaid source
  is not rendered there.
- Lay mermaid out top to bottom unless the diagram is only a few nodes wide:
  renderers shrink a wide diagram to the page width until it is unreadable.

### Naming ids

When an id does appear, it names what it stands for. On its first
mention in a message, an id is never bare: lead with what it is and give the
id after it ("the chunk plan (PLAN-31) allows independent improvements as PRs
ahead of the core chunk (C)"), or follow the id with a gloss of two to six
words ("PLAN-31 (the chunk plan)"). Later mentions in the same message may be
bare. This covers record ids (PLAN-31, DEC-19), requirements (BRIEF-52.19),
checks and their questions (BRIEF-30-1.Q-12), plan pieces (S, C), handoffs
and milestones of the build log (BUILD-15, MILE-1), passes (PASS-3), follow-ups (F3), ideas
(IDEA-7), deferred items (DEFER-6), and finding numbers ("finding 12 (the
unbounded export query)"). A record's prefix names its type (IDEAS brainstorm,
DESIGN, DEC decision, GUIDE guidance, PIECES, PLAN, BRIEF)
but is not a gloss: it still needs one. Older ids (R31, B15, M1, P3, I7, D6,
Q3, R52.19) still appear in files and resolve to the same things; cite them
in the new form.

Get the names with `records.py names <worktree> PLAN-31 S C BUILD-15 ...` rather than
opening files. A gloss says what the thing is, not all it says.

The rule holds in every case, the ones where it slips most included:

- Each message stands alone. An id glossed in an earlier message is glossed
  again in this one; the user may have cleared, scrolled, or switched sessions.
- Relayed text counts. A subagent's report (an overview refresh, a design
  check, a builder, a lens) cites bare ids by design; rewrite it with
  glosses before passing it on, never paste it through.
- Ids used as labels count. A bullet or heading that leads with "DEC-19 vs DEC-21:"
  or "BUILD-15:" is a first mention; gloss it there ("DEC-19 (production edits only
  without runtime effect) vs DEC-21 (small, safe changes allowed):").
- Lists and counts count ("guidance GUIDE-15 and GUIDE-19 to GUIDE-22"): gloss each id, or
  replace the list with what the records are about when the ids add nothing.

Scripts whose output is shown to the user (`status.py`) gloss ids themselves
with `records.py`'s `gloss`. Before sending a message that mentions any id, run `records.py names` on every
id in it you have not glossed, and check the draft for bare ids.

The plugin's scripts (`records.py`, `status.py`, and the rest) are tooling,
not something the user runs: never name them to the user. Point to what to
say instead ("what guidance have I given", "what ideas did we park").

Files keep their ids as they are: records, check files, logs, and reports cite
ids by design, and commit messages carry none. The rule is for conversation.

So rather than:

> Seams 1 and 2 don't need a chunk. PLAN-31 already allows "independent
> improvements may become PRs ahead of C", so they're main PRs, like S.

say:

> Seams 1 and 2 don't need a chunk. The chunk plan (PLAN-31) already allows
> "independent improvements may become PRs ahead of" the core harness chunk
> (C), so they're PRs to main, like the sandbox change (S).

## Items

Review findings, follow-ups, and design-check questions are all items, and use
one vocabulary in two layers. Findings keep their cards and `status.tsv`;
follow-ups (`F3`), deferred items (`DEFER-3`), and design questions (`Q-3`) are
checkbox lists read and written by `scripts/items.py` (`followups.py` and
`deferred.py` build on it).

Instruction, what to do; blank means not decided yet (a follow-up with none is
done as written):

- `Fix as recommended`: do what the item recommends.
- `Fix as noted`: do it as the note after the colon says ("Fix as noted: use
  the banner, not a toast").
- `Discuss`: talk it through with the user before anything else happens.
- `Defer`: not now. Add a deferred item with `deferred.py add <worktree>
  "<what>" --from <source> --path "<what was done for now>" --open "<what is
  left>" [--revisit "<when to look again>"]`, where the source is the finding
  (`<run> N`), question (`BRIEF-18-1.Q-6`), follow-up (`F3`), pass item (`PASS-3.4`),
  handoff (`BUILD-9`), or "this session". Then set the source's status to `deferred`
  with its Outcome naming the new DEFER id: `render-report.py --set N=deferred:DEFER-3`
  for a finding, `items.py status <file> Q-3 deferred --ref DEFER-3` for a design
  question, `followups.py close <worktree> F3 --status deferred --ref DEFER-3` for a
  follow-up, `passes.py done <worktree> PASS-3 4 --na "deferred, DEFER-3"` for a pass
  item. "Deferred items" below says what they are.
- `Ignore`: not at all; the status becomes `wont-fix`, with why.
- `Refine`: investigate first (read the source change and the local code),
  propose a concrete fix or a reason not to, as the `deliberate` skill does,
  then set one of the others. Follow-ups and design questions only; a
  finding's author is a lens in this repository, and Discuss covers it.

Status, where it stands: `open`, `in-progress`, `fixed`, `wont-fix`,
`deferred`. The box is ticked exactly when the status is one of the last three.
`Outcome` holds what closed it: a commit (`in 1a2b3c4`), a decision record
(`DEC-18`), or a reason. A design question is `fixed` when its answer is recorded.

## Deferred items

A deferred item (`DEFER-3`, in `.clerk-dev/deferred.md`, kept by `deferred.py`) is a
known gap with a path chosen for now, not an idea: ideas are good things for
later, a deferred item is something this work already knows is missing. Its
fields are From (the source), Path (what was done for now), Open (what is left
to decide or do), Revisit (a trigger, such as "after the BRIEF-13 draft"), Added,
Instruction, Status, and Outcome.

It closes in one of two ways: `fixed`, with the commit that closed the gap
(`deferred.py close <worktree> DEFER-3 --ref <sha>`), or `wont-fix`, with the reason
(`--status wont-fix --ref "<why>"`). `deferred.py reopen` puts one back. A plan
step's done line may say "deferred items reviewed", meaning every open item was
looked at when the step ended: closed, or revisited with a new trigger.

## What stays the user's

Untracked files in the worktree, such as personal notes, drafts, and scratch
specs, are the user's own. Reviews do not read them, and fixes never stage or
commit them. The plugin's own files are only those under `.clerk-dev/`,
including feature records, which the user writes too. Documents
committed to the repository are read through the review-context
`## Work tracking` section and never written to.

---
name: building
description: The one intake for every item that becomes code: a coding request, a brief's requirements, a pass item, a review finding, or a follow-up. Sizes each against this repository's code in the session that owns the branch, hands the work to clerk-dev:builder at a model and effort, reviews the result, commits, keeps the build log, and works milestones. Use when the user says "build the plan", "build the next step", "build BRIEF-9", "build finding 4", "start building", "send the next handoff", or similar. The builder agent does not load this skill; it preloads writing-code.
allowed-tools: Bash(git *), Bash(python3 *), Read, Grep, Glob, Agent, Write
---

# Building

When talking to the user, follow "Talking to the user" in `skills/review/tracking.md`: the feature first, the bookkeeping last or not at all, and ids named: every id (DEC-19, BUILD-15, MILE-1, F3, Q-3, PASS-3, IDEA-7, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

If this conversation was compacted, re-read this file before going on: a
compacted skill may be cut short, and the steps it drops are the ones that
keep the work safe. Prefer `/clear` at a natural boundary to compaction; the
`checkpoint` skill writes down what is pending first.

The feature records exist so that design choices are settled outside the code.
Once they are, building is handed off: the session that owns the branch keeps
the judgment (what to build, in what order, whether the result is right) and
the commits, and hands each part of a piece to a `clerk-dev:builder` agent
in a handoff. This keeps the session's context for the whole feature instead of
filling it with one file's details, and gives every handoff a check before it
lands.

## Before the first handoff

Before handing off or writing the first code on a branch, run
`${CLAUDE_PLUGIN_ROOT}/scripts/status.py <worktree> --setup` and settle each
gap it prints with the user before building. Two of its gaps are this skill's
own:

- No Purpose in `.clerk-dev/branch-notes.md`: draft it as
  `skills/review/tracking.md` describes and say in one line where.
- The work is not cut into milestones: the feature's active plan names, for
  each step, its pieces, its brief, and what is done when it ends. If there is
  no plan, or its steps have no done line, propose the milestones to the user
  (a short numbered list) and record them as a plan, or a new plan superseding
  the old one, with the `feature` skill. Small changes with no feature records
  skip this.

The others (a hub and feature, a review workspace, workspace rows whose
worktree is missing) are settled as the output says.

## Intake

Every item that becomes code enters here, after the setup check: a coding
request, a brief's requirements, a pass item, a review finding, or a
follow-up. Intake sizes the item, applies the scope test, and says one line
for it before anything is handed off.

### Size and route

Size the item against the code of the repository it is in, in the session
that owns that branch, never in the repository that sent it: only that code
shows how far the change goes. Most items size in one line, as the
`deliberate` skill's trivial exit does.

An item that is already `in-progress` with an active brief as its reference
(a finding's reference in `status.tsv`, a follow-up's Outcome) is being built
as that brief: it is not sized again. Say so in its intake line and go on, in
a queue to the next item.

- Small, one handoff and one commit: send one handoff, as "The handoff"
  describes, or do it in the session when the handoff would be longer than
  the change (What stays in the session).
- Large, many files, a shape others build on, or a new state to handle:
  propose it to the user as a piece, a brief plus a one-step milestone, with
  a sentence on what the change reaches, and wait for the user's yes; never
  cut the item into handoffs silently. On yes, grow it as "Growing an item"
  describes. On no, the item stays open at its source with the proposal as
  its note.
- Unclear: weigh it with the `deliberate` skill, the local code as its
  facts; its answer routes the item as small or large.

Items reach intake in these ways:

- a request from the user;
- a brief's requirements, from Milestones;
- a pass item, from the `pass` skill;
- a finding, from the `review-fix` skill ("fix finding 4", and the triage
  queue through its Queue mode), bringing its handoff block and how it
  closes; or handed to this skill directly ("build finding 4"): its handoff is
  `Source: finding` with the Finding entry of By kind pasted, pointed at the
  run files as the `review-fix` skill's Build the handoff step lists them;
- a follow-up, from the `followups` skill (one item or its work list),
  bringing its handoff block and how it closes; or handed to this skill
  directly ("build F3"): its handoff is `Source: follow-up` with the
  Follow-up entry of By kind pasted, filled from the item as the `followups`
  skill's Build the handoff step lists;
- several of these handed over together, a queue, sorted as "Queues"
  describes.

### Growing an item

Growing turns a large request, finding, or follow-up into a piece: a brief
and a one-step milestone, with no pieces record. Only size grows an item:
intake sized it large, or a builder reported `size: too big` on a small
finding, follow-up, or request (After each handoff, step 4). `scope: out`
never grows an item; it takes the source's row of the Scope table, whatever
the item's size. On the user's yes:

1. Write the brief: `records.py new <hub> brief "<title>" --from <the item>
   --area <area>`, where the item is `F3` for a follow-up, `<run> N` for a
   finding, or "this session" for a request, and the area is chosen as the
   `feature` skill's Areas section says. Draft it as that skill's brief step
   in "Writing each type" describes, giving the drafting subagent, in place of
   a pieces row, the item's By kind entry with the material its handoff would
   point at (the run files for a finding; the item and `git -C <path> show
   <sha>` for a follow-up; the user's words for a request) and the sentence
   on what the change reaches. Items that share files and size large
   together grow into one brief, its `--from` naming each. The brief is
   active at once.
2. Give it a one-step milestone. When the feature has an active plan, write a
   new plan that supersedes it, restated in full as "Replanning writes a new
   plan" in the `feature` skill's `records.md` says, with the piece appended
   as a step naming the piece, "brief BRIEF-<n>", and a done line in the
   item's words; then run `build.py milestone <worktree> --step
   PLAN-<new>.<n> --passes <list>`, and edit the Plan line of every milestone
   under way to the new plan's step, as Milestones step 1 says. When the
   feature has no plan, run `build.py milestone <worktree> --brief BRIEF-<n>
   --piece "<title>" --passes <list>` and write no plan. The pass list is the
   one Milestones step 1 gives.
3. Mark the source item `in-progress`, naming the brief: a finding with
   `render-report.py --set N=in-progress:BRIEF-<n>`, re-rendered as the
   `review-fix` skill does, its instruction unchanged; a follow-up with
   `items.py status <worktree>/.clerk-dev/followups.md F3 in-progress --ref
   BRIEF-<n>`. A request has nothing to mark; the brief's Goal quotes it.
   Items grown into one brief are each marked alike.
4. Say its intake line, routed `grown into BRIEF-<n>` with its milestone and
   when it runs: after the milestone under way, since passes cannot nest,
   unless the user says now; then end or abandon the open pass first, as the
   `pass` skill's Start step asks.

The piece is built like any other: its handoffs are `Source: piece`, logged
with `build.py add` and `done`, and its source items close when it is built
(After each handoff, step 7).

### Scope

Apply one scope test to every item: the Branch scope rule in the guidance
file that `records.py guidance` writes (The handoff, item 3), read there
rather than restated here. The item's source says what the branch owes:

| Source | What the branch owes | Reaching deployed code Purpose does not cover |
| --- | --- | --- |
| Finding | What Purpose covers; nobody asked for the change | Propose the fix and its rollout considerations, and change no code |
| Follow-up | The work, whatever its size | Ask the user once, add a dated line to Purpose under "Deployed code it changes on purpose", and go on |
| Request | What the user asked | As a follow-up: ask once, add the dated Purpose line, and build |
| Brief requirement or pass item | The work, in scope by its record | As a follow-up: ask once, add the dated Purpose line, and go on |

Size and scope are separate answers: too big for one handoff routes to a
piece, and not this branch's business routes to a proposal, so a large
follow-up is still owed. A builder's `size: too big` and `scope: out` come
back to these routes, as steps 3 and 4 of "After each handoff" describe.

### The intake line

Say one line per item before its handoff is sent, giving its size, its route,
and its scope answer:

```
<item>: <small | large | unclear>, <route>; scope: <in | out, proposed | out, asked once>
```

The route is one of `one handoff`, `inline`, `proposed as a piece`, `to
deliberate`, or `grown into BRIEF-<n> (MILE-<m>, runs after MILE-<k> | now)`;
in a queue, a grown item's line ends `; leaves the queue`. An item already
being built is not sized, and its line is `<item>: being built as
BRIEF-<n>`.

The line is not written to any file: the build log entry, when the route
builds a record, and the source item's note, when it does not, carry what
persists.

### Queues

A queue is several items handed to intake together ("build F2, F3, F5",
"build findings 4, 7, 9"). Sort it in one pass before any handoff, as "Sort in
one pass" under "Several items waiting" in the `deliberate` skill sorts
choices:

1. Gather the files each item reaches, once, and size the items that share
   files together; a group that shares files and sizes large grows into one
   brief.
2. Say one intake line per item.
3. Propose the large ones together, in one message, each with its sentence
   on what the change reaches: this is the one question a queue asks. On yes,
   each is grown as "Growing an item" describes and leaves the queue with its
   line; on no, it stays open at its source with the proposal as its note.
4. Run the small ones, one handoff and one commit each, in the queue's order,
   with no further question. Before each item, check that the tree is clean:
   `git status --short --untracked-files=no` prints nothing. When it prints
   anything, stop the queue and show those files, since no item owns them.

After the sort's one question, nothing asks. A stop that would need the user
(a builder's `scope: out` or `size: too big`, failed tests, a question, or a
guidance rule that cannot hold) is recorded on the item as its source's skill
records a stop in a queue, with its edits reverted as Leftover edits says for
a queue, and the queue goes on.

## What stays in the session

- Settling choices. When a handoff needs a choice no record settles and it
  shapes code others build on, settle it with the user first (the
  `deliberate` skill) and record it (a decision, or an open item resolved in
  the brief), then hand it off. An agent that stops on a `questions:` line is
  handled the same way.
- Cutting each piece's work into handoffs and ordering them.
- Reviewing each result, running its tests, and committing it.
- Changes small enough that the handoff would be longer than the change: a few
  lines, one obvious edit. Do those inline.

## Handoffs

A handoff is one requirement or a few that belong together, or one port of
reference code, with tests that prove it, small enough to review in a few
minutes: usually a module, an entity with its migration, a set of DTOs, an
executor step. Cut along the brief's requirements, and order handoffs so each
builds on committed ones.

## Model and effort

Pass `model` and `effort` on each builder call:

| Handoff | Model | Effort |
| --- | --- | --- |
| Foundation work, where a mistake is expensive to undo: the feature's central types and extension-point interfaces that every later handoff builds on; schema changes to tables that are already deployed; concurrency or state-machine code with no settled pattern to follow | fable | high |
| Other shape-setting code others build on: types, interfaces, cross-module wiring, new schema and migration design, concurrency-sensitive code | opus | high |
| Implementing to a settled brief inside established patterns; ports of reference code; their tests | sonnet | medium |
| Mechanical edits: moves and renames with their import updates, regenerated files, applying one pattern across files | sonnet | low |

Fable is for the few handoffs in the first row, not a default: it costs about
two and a half times Opus. Most features have a handful of such handoffs, near
the start.

Raise a handoff a row when its first attempt comes back with deviations or
failing tests that point at reasoning, not at the handoff; a handoff that fails
that way at Opus goes to Fable.

Not every account has Fable, and it may have its own usage limits. When a
builder on Fable fails because the model is unavailable or a limit is
reached, run the same handoff on Opus at the same effort, say so once in a line,
and use Opus for the rest of the session's Fable handoffs, as Model fallback in
the review skill describes.

## The handoff

Give paths, not contents, for code and records. Every handoff gives:

1. `Source: <piece | pass | finding | follow-up | request>` as its first
   line, and `Reference: <path or git ref>` when porting.
2. The goal in a sentence or two.
3. The decisions to follow, by id and path, and the guidance file's path:
   `records.py guidance <worktree> --for <the piece's brief> [--context <the
   repository's review-context SKILL.md>] --out <scratchpad>/guidance-<area>.md`
   writes the Branch scope rule, the branch's Purpose, its guidance, the
   feature's active guidance for the brief's area, and the repository's Known
   noise (`--area <area>` names the area directly).
4. The files expected to change, and any it must not touch.
5. The tests to write or port, and the exact command to run them.
6. The user's rules that bear on code, restated: the user's instructions
   beyond the repository's conventions (for example a no-comments rule). Do
   not assume the agent sees the user's own instructions; restate the ones
   that apply.
7. Model and effort, on the invocation, from Model and effort above.

After the `Source:` line, paste its source's entry from By kind below word for
word as its own block, and the Reference entry too when porting. These are
instructions, not code or records, so they go in whole. A piece's handoff is
`Source: piece`; a change the user asked for with no brief behind it is
`Source: request`.

### By kind

What each handoff adds, pasted word for word:

1. Piece: the requirements by brief id and number with the brief's path,
   and the later handoffs and pieces that touch the same code.
2. Pass: the one lens's Pass mode text and the items as the goal; stay
   inside the items.
3. Finding: the run files to read (the merged entry's claim, scenario,
   steps, evidence, fix, and snippet; the verifier's note; the notes file;
   the guidance file), the review context sections for the finding's lens,
   a pull request comment and its replies when they stand in for claim and
   scenario, the text of a linked comment, and the user's own words quoted,
   which override the recommendation; read the code the evidence names at
   its current state, since line numbers may be off and function names are
   reliable; make the smallest change that makes the scenario impossible,
   covering the sibling paths the evidence names; add or update a test that
   reproduces the scenario and passes with the fix.
4. Follow-up: the item's text is the need and its `Contract:` the contract,
   changed (old to new) or wanted (the shape another repository needs, and how
   it differs from today's); read the source change with
   `git -C <path> show <sha>` and check both against it; the item does not
   say how to change this repository, so shape the change from the local
   code, and for a wanted contract this repository is the provider and builds
   the shape asked for; an older item whose text prescribes a change is the
   sender's guess, and the contract wins; when the handoff gives the
   `stale-findings.py <run> --open-in <files>` command, list those findings
   before editing and treat them as context, not work; where one's
   recommendation conflicts with the contract, the contract wins and
   `findings:` says so.
5. Request: the user's words as the goal, and the files it reaches.
6. Reference (with any source): the reference by path or
   `git show <ref>:<path>`; keep its behavior and tests, changing only what
   the new structure, the decisions, or this repository's patterns require;
   a test weakened or dropped to make the port pass is a deviation.

## Order and parallelism

Run handoffs one at a time by default. Run two at once only when they change
disjoint files and their tests share no resources (databases, ports, fixtures);
many repositories' integration tests share databases and must never run
concurrently. A larger fan-out is a multi-agent workflow, which runs only when
the user asks for one.

## The build log

The build log, `.clerk-dev/build.md`, is kept with
`${CLAUDE_PLUGIN_ROOT}/scripts/build.py` (below, `build.py`). An entry is
written only for a route that builds a record: a brief's requirements, a
piece grown from an item included, through `build.py add` and `done`; or a
decision, plan step, or whole brief, through `build.py built`. A small
finding, follow-up, or request gets no entry: it closes at its source with
its commit, as its source's skill closes one, and status already reports
that commit as a branch commit no entry names. Status reports a brief's
progress from the log, so a brief's handoff not logged is invisible there:

- when handing off: `build.py add <worktree> "<title>" --brief BRIEF-52 --reqs 4,5
  --model <model> --effort <effort>`, which gives the handoff's id (BUILD-3);
- when the agent stops on a question: `build.py stop <worktree> BUILD-3 --question
  "<the question>"`; after it is settled and recorded, `build.py resend` with
  the new model or effort if they changed;
- when it is sent back with a correction: `build.py resend <worktree> BUILD-3
  --note "<what changed>"`;
- after committing: `build.py done <worktree> BUILD-3 --commit <sha> --covered
  "<the report's requirements line, as 4:done,5:partial: what is missing>"`,
  adding `--deviation "..."` for each one accepted;
- when dropped: `build.py abandon <worktree> BUILD-3 --note "<why>"`;
- after committing work that builds a decision, a plan step, or a whole brief
  rather than requirements: `build.py built <worktree> DEC-27 --commit <sha>`
  (`PLAN-32.4` for a plan step). Any skill that commits does this when its handoff
  names a record the commit builds, and never cites the record in the commit
  message. A rebase that changes the hash is followed by its `Subject:` line;
  `build.py relink <worktree>` persists the re-found commits and lists entries
  it could not follow, and `build.py relink <worktree> BUILD-4 --commit <sha>`
  re-links one by hand. `build.py records <worktree>` lists the records logged
  as built.

When a decision takes a requirement out of a brief (moved to another brief,
or no longer wanted), do not supersede the brief to delete one line: run
`build.py drop <worktree> --brief BRIEF-18 --reqs 17 --why "<the decision that
dropped it, and where it went>"`. The requirement leaves the brief's count and
shows as dropped in the checklist; the brief itself stays as written.

A change done inline gets an entry only when it covers brief requirements:
a handoff added and marked done in one go, so the brief's progress stays
whole.

"Log the built work" (status suggests it when the branch has commits the log
does not name): list the branch's commits since its base, read each one's
message and the files it changed (`git show --stat`, and the diff only where
the message does not say), match it to the brief's requirements or to the
decision or plan step it built, and log each group of commits that make one
handoff as a handoff added and marked done, with the last commit and the
requirements it covers, partial where the commit leaves part of a requirement
for later; a commit that built a record goes in with `built`. Show the mapping in a few lines
before writing it. Commits that cover no requirement (merges, unrelated
fixes) are left out, and say so in one line. Requirement
status lives only here; the brief is not edited for it.

## After each handoff

1. **Read the report.** Read it by its `status`, `size`, `scope`, `files:`,
   `requirements:`, `questions:`, `deviations:`, `rollout:`, `follow-ups:`,
   and `contract:` lines. A report that is empty, misses a line of the
   builder's report, or has them out of order is sent back once, to the same
   builder with SendMessage, asking for the report alone; a second such report
   is handled as `status: stopped` with that as its reason, and its `files:`
   are taken from `git status --short`.
2. **Questions.** `questions:`, and a `status: stopped` that steps 3 and 4 do
   not cover, go back to the user (or are settled from the records and
   guidance) before anything else. Before asking,
   weigh each question with the `deliberate` skill, with the handoff and the code and
   records it touches as its facts, and put its decision summary to the user
   rather than the bare question. When the
   user's answer carries guidance (a rule beyond this case), or says
   `guidance: ...`, record it as "Guidance from answers" in
   `skills/review/tracking.md` describes, and say so in one line. For a
   question, or a guidance rule that cannot hold, re-send the handoff with
   the answer in it.
3. On `scope: out`, act on the source's row of the table in Intake's Scope:
   for a finding, propose the fix and change nothing; for any other source,
   ask the user once, and on yes add the dated Purpose line, write the
   guidance file again, and re-send the handoff.
4. On `size: too big`, act by source. For a piece or pass handoff, cut the
   handoff smaller and re-send it (`build.py resend` with a note on the cut),
   telling the user in one line; stop it (`build.py stop`) and weigh the cut
   with the `deliberate` skill when the cut needs a choice the brief did
   not make, or when a handoff already cut once comes back too big again. For a finding, follow-up, or request, the report means the item
   is large and intake sized it small: take Intake's large route, proposing a
   piece and waiting for the user's yes.
5. `deviations:` are judged against the brief, decisions, and guidance, and either accepted (say so to the user in
   a line, and record it when it changes a decision) or sent back with a
   correction.
6. Read the diff (`git diff --stat`, then the parts that carry the handoff's
   shape), and run the handoff's tests yourself.
7. **Commit.** `git add` only the handoff's files (the report's `files:`),
   never anything under `.clerk-dev/` or an untracked file the handoff did
   not create, then commit. The message stands alone, because review runs,
   the follow-ups file, and the records are local and never committed: no
   finding numbers, run labels, follow-up ids, record ids, `.clerk-dev/`
   paths, or mention of the review. The subject follows the repository's
   usual style and says what the change does (`fix(<area>): <what the fix
   does>` for a finding). The body, two or three sentences starting from the
   builder's `summary` and written for a reader of `git log` who has never
   seen the source, says what was wrong and what can go wrong because of it,
   or for a follow-up what changed on the other side (the contract, in plain
   words), and what the change does, with the `rollout:` text when it is not
   "none". No push, no amend. Several items get one commit each, in the
   queue's order. When the route builds a record, mark the handoff done in
   the build log (or log the record it builds with `built`, as "The build
   log" describes), with
   the `requirements:` ids turned to bare numbers for `--covered`
   (`BRIEF-52.7: done` becomes `7:done`), and `--covered` passed only when
   the line names a brief; and
   tick the brief's open items it closes. A small finding, follow-up, or
   request gets no entry and closes at its source with the commit. When the
   commit builds a grown piece, leaving every requirement of its brief done
   or dropped (`build.py checklist <worktree> --brief BRIEF-<n>` all ticked),
   close its source items, naming the brief: a finding with
   `render-report.py --set "N=fixed:<sha> (BRIEF-<n>)"`, and
   `<run>/resolution/<merged id>.md` written as the `review-fix` skill's
   Resolution step describes, its first paragraph naming the brief and saying that the milestone's pass review and the next
   triage's moved-code check stand in for a recheck, so no recheck runs; a
   follow-up with `followups.py close <worktree> F3 --ref "in <sha>
   (BRIEF-<n>)"`. A request has nothing to close.
8. Add each `follow-ups:` line with `followups.py add` to the owing
   repository's worktree, as Follow-ups in `skills/review/tracking.md`
   describes, with the commit as `--from`. When `contract:` is not "none",
   check every related worktree as "Clients of a changed contract" below
   describes.
9. Say one line: the handoff, the commit, the tests, anything accepted, the
   rollout considerations when `rollout:` is not "none", the worktrees that
   got a follow-up, the source items step 7 closed, and the count it moves
   ("BUILD-15 done in 4c1e2ab, tests pass: BRIEF-52 now 27 of 32").

**Leftover edits.** A stopped report whose `files:` is not "none" left edits.
Interactively, show the files and ask whether to keep them (the source item
records them as `in-progress`, as its skill closes one) or discard them
(revert the listed files and delete those marked "(new)"). In a queue, revert
and delete them without asking, note it on the item, and go on.

Whenever you report progress against a brief at more length (the user asks,
the draft ends, a milestone's passes are done), show `build.py checklist
<worktree> --brief BRIEF-52` as it prints it: one checkbox per requirement, ticked
when done, with partial and in-progress items marked. Never list requirement
numbers in prose ("1 to 18, 20 to 24 done; 19, 25 to 28 open").

### Clients of a changed contract

The builder sees only this repository, so its `follow-ups:` covers the clients
it happens to know about. When its `contract:` line is not "none", check every
related worktree yourself, without a model:

1. The worktrees: every other row of `.clerk-dev/review-workspace.md`
   (`skills/review/workspace-manifest.md`). When the file is missing, check
   nothing elsewhere: say in one line that no other repositories are known for
   this branch, so their clients were not checked, and that a feature review
   sets them up.
2. Search each: `git -C <worktree> grep -l -F -e <term> -e <term> ...` with the
   terms after `search:`. Print only the count of files per worktree.
3. A worktree with hits and no follow-up yet for this change gets one, through
   `followups.py add`, with the builder's contract sentence in the `changed:`
   form as `--contract`, this commit as `--from`, the finding as `--finding`
   when the item is one, and as text the need: the part after `needs:` of the
   builder's `follow-ups:` line for that repository, or, when it has none, the
   behavior the `contract:` sentence implies for a reader of the old shape.
   Name the files that matched as where the old contract is relied on, not as
   the change to make. A worktree with no hits gets nothing.

## Milestones

A builder holds one focus at a time: the draft, or one pass. The focuses
are applied by orchestrating passes, not by adding checklists to a handoff. A
handoff never quotes a lens's text, except the one lens of the pass it belongs
to.

A milestone is a numbered step of the feature's active plan: a checkpoint
where the work so far gets its review passes, not a point to merge or open a
pull request. Merging and pull requests are the user's call, never a next
step a milestone suggests. Work it as a sequence of passes, with the `pass`
skill:

1. **Plan it** when its work starts: `build.py milestone <worktree> --step
   PLAN-8.2 --passes <list>`, where PLAN-8.2 is step 2 of plan PLAN-8. The log takes the
   brief and the piece from the step and keeps the pointer, so it does not
   restate the plan; it stops when the plan or the step is missing, or the plan
   is not active. When the step names no brief, add `--brief`; a log with no plan
   takes `--brief BRIEF-52 --piece "<piece>"` instead. The list is prep, happy-path,
   then the passes `skills/pass/passes.md` suggests for the milestone's brief,
   in the order it gives; security is required when it is in the list. Show the
   plan in one line and go on. When the plan is replaced, status flags a
   milestone under way that points at a step that is gone or a superseded plan;
   edit its Plan line in the build log to the new plan's step.
2. **Prep**, the refactor-first pass, looking ahead to the milestone's later
   handoffs and the plan's later milestones; it may end with no changes.
3. **The draft** is the happy-path pass: start it, build it in handoffs as
   above (logged in the build log, committed one by one), end it when the
   draft is whole, and run its pass review.
4. **The other passes**, in order, each as the `pass` skill runs one: its own
   builder with its one lens's Pass mode text, then its pass review.
5. **Complete** when every planned pass has run or was skipped with a reason
   (`build.py skip <worktree> MILE-1 <pass> --why "..."`; never a required one)
   and the required passes' findings are triaged. `build.py milestones` and
   status say where each milestone stands and what runs next; a complete
   milestone leads to the next one. When a milestone completes, run a closing checkpoint, as "Closing checkpoint" in the `checkpoint` skill describes.

Run the sequence without pausing between passes. Stop and bring to the user:
a question a builder stopped on, a check that found anything rated major
or blocker (triage it before the next pass, since later passes build on the
code), or any finding in a required pass's check. Minor findings collect in
their pass's run for triage at the end.

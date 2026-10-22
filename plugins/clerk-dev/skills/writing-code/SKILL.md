---
name: writing-code
description: How to write code: hand off the building of settled pieces to implementer subagents at the right model and effort, while the session that owns the branch settles choices, reviews, and commits; and how to shape the code itself (refactor first to a clean baseline, reuse and extend what exists, one source of truth, clean abstractions). Use before writing or changing code of any size - implementing a feature, a brief or spec, a piece, a handoff, a chunk, a port, a pass, a fix, a follow-up, or a small edit - and when planning how a change will be built. Preloaded by the implementer and the review fixer.
---

# Writing code

When talking to the user, follow "Talking to the user" in `skills/review/tracking.md`: the feature first, the bookkeeping last or not at all, and ids named: every id (DEC-19, BUILD-15, MILE-1, F3, Q-3, PASS-3, IDEA-7, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

If this conversation was compacted, re-read this file before going on: a
compacted skill may be cut short, and the steps it drops are the ones that
keep the work safe. Prefer `/clear` at a natural boundary to compaction; the
`checkpoint` skill writes down what is pending first.

Human reviewers of this team's changes keep asking for more reuse, cleaner
abstractions, and less duplication than agents deliver. Lean hard that way.
This is deliberately strong; the team tunes it down if it goes too far.

## Refactor first

Before writing any change, large or small, read the code it touches and ask
whether reshaping that code first would make the change smaller or plainer:

- a helper to extract, so the change reuses it instead of adding a copy;
- a function to split, so the change edits one step instead of threading
  through all of them;
- a data shape to fix, so the change needs no conversions;
- dead code or a leftover option to drop, so the change has fewer cases.

If so, do that refactor first, in its own commits, with the tests passing and
behavior unchanged, and build the change on it; the change's own commits should
read as small additions. If not, say in one line that the baseline is clean.

When the change is one part of several (a plan's milestones, a feature's
pieces, a brief's handoffs), look ahead too: read what the later parts will
touch, and prefer the refactor that makes this part and those smaller or
plainer. Keep the look short. When nothing is clear yet, say so in one line and
look again at the next part, when more of the shape is known; do not refactor
for a guess.

This holds at every scale: a feature's first piece, a one-function fix, a
follow-up. Refactoring deployed code still follows the branch's scope (Branch
scope in `skills/review/tracking.md`): when the branch's Purpose does not cover
that code, propose the refactor instead of making it.

## Changing live code

An enabling refactor of deployed code, especially on a hot path, keeps the
same values as new code but weighs them differently: what the paths you did
not touch do matters more than how tidy the change is.

- Add to a decision rather than redefine it. When a function, flag, column, or
  predicate already means something to its callers (`hasId()` meaning "this
  row was inserted"), keep that meaning and add an explicit signal for the new
  case. Changing what an existing signal means changes every caller at once,
  including the ones you did not read.
- Make the new condition opt-in, with a default under which every path you did
  not touch behaves exactly as before. The old behavior is the fallback.
- Before changing a branch, find its live callers and say how many take it.

Before calling the clean fix risky and offering a workaround instead, find the
fix's smallest form: the opt-in flag, the added signal, the precedent the
codebase already has. Present that version next to the workaround, with the
argument for its safety. Judged in the abstract, the right fix often looks
riskier than it is.

## Reuse

- Before writing any helper, type, validator, query, or pattern, search the
  codebase and its shared libraries for one that exists. Search by behavior,
  not name: the verbs, the types it takes and returns, the distinctive calls
  inside it. Look first in the shared libraries (`libs/`, `packages/`,
  `shared/`, `common/`, `core/`, `utils/`, the workspace packages and path
  aliases in the manifests).
- Use what exists. When it nearly fits, extend it (the option or case to add)
  rather than write a near-copy. When your code is the more general of the two,
  move it into the shared place and have the old one call it.
- Do things the way the codebase already does them: one way to handle errors,
  wire dependencies, build queries, lay out modules. A second pattern needs a
  reason, even when it is nicer.

## One source of truth

- When a change would repeat logic, extract the shared abstraction instead,
  including logic repeated across files and across the code you are adding.
- No hand-kept lists, enums, schemas, or constants that must stay in sync with
  another; derive one from the other.
- Abstractions at the right level: no framework for one caller, no wrapper
  around one call, no parameter added to a shared type because one function
  needs it.

## Delegating

This section is for the session that owns the branch. An implementer or fixer
agent that preloads this skill skips it: it is the one receiving the handoff.

The feature records exist so that design choices are settled outside the code.
Once they are, building is delegated: the session that owns the branch keeps
the judgment (what to build, in what order, whether the result is right) and
the commits, and hands each part of a piece to a `clerk-dev:implementer` agent
in a handoff. This keeps the session's context for the whole feature instead of
filling it with one file's details, and gives every handoff a check before it
lands.

### Before the first handoff

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

### What stays in the session

- Settling choices. When a handoff needs a choice no record settles and it
  shapes code others build on, settle it with the user first (the
  `deliberate` skill) and record it (a decision, or an open item resolved in
  the brief), then hand it off. An agent that stops on a `questions:` line is
  handled the same way.
- Cutting each piece's work into handoffs and ordering them.
- Reviewing each result, running its tests, and committing it.
- Changes small enough that the handoff would be longer than the change: a few
  lines, one obvious edit. Do those inline.

### Handoffs

A handoff is one requirement or a few that belong together, or one port of
reference code, with tests that prove it, small enough to review in a few
minutes: usually a module, an entity with its migration, a set of DTOs, an
executor step. Cut along the brief's requirements, and order handoffs so each
builds on committed ones.

### Model and effort

Pass `model` and `effort` on each implementer call:

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

Not every account has Fable, and it may have its own usage limits. When an
implementer on Fable fails because the model is unavailable or a limit is
reached, run the same handoff on Opus at the same effort, say so once in a line,
and use Opus for the rest of the session's Fable handoffs, as Model fallback in
the review skill describes.

### The handoff

Give paths, not contents. Include:

- the goal, in a sentence or two;
- the requirements it covers, by brief id and number, and the brief's path;
- the decisions it must follow, by id and path;
- the reference code to port or follow (`git show <ref>:<path>` for another
  branch);
- the files expected to change, and any it must not touch;
- the later handoffs and pieces that will touch the same code, by name and
  brief id, so the agent shapes this handoff's code for them without building
  them;
- the tests to write or port, and the exact command to run them;
- the guidance file's path: `records.py guidance <worktree> --for <the
  piece's brief> [--context <the repository's review-context SKILL.md>] --out
  <scratchpad>/guidance-<area>.md` writes the branch's Purpose, its guidance,
  the feature's active guidance for the brief's area, and the repository's Known
  noise (`--area <area>` names the area directly);
- the rules that apply beyond the repository's conventions: the user's
  instructions that bear on code (for example a no-comments rule). Do not
  assume the agent sees the user's own instructions; restate the ones that
  apply.

### Order and parallelism

Run handoffs one at a time by default. Run two at once only when they change
disjoint files and their tests share no resources (databases, ports, fixtures);
many repositories' integration tests share databases and must never run
concurrently. A larger fan-out is a multi-agent workflow, which runs only when
the user asks for one.

### The build log

Log every handoff in `.clerk-dev/build.md` with
`${CLAUDE_PLUGIN_ROOT}/scripts/build.py` (below, `build.py`); status reports
progress from it, so a handoff not logged is invisible there:

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

A change done inline that covers brief requirements is logged too, as a
handoff added and marked done in one go, so the progress stays whole.

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

### After each handoff

1. Read the report. `stopped` or `questions:` go back to the user (or are
   settled from the records and guidance) before anything else. Before asking,
   weigh each question with the `deliberate` skill, with the handoff and the code and
   records it touches as its facts, and put its decision summary to the user
   rather than the bare question. When the
   user's answer carries guidance (a rule beyond this case), or says
   `guidance: ...`, record it as "Guidance from answers" in
   `skills/review/tracking.md` describes, and say so in one line.
   `deviations:` are judged against the brief, decisions, and guidance, and either accepted (say so to the user in
   a line, and record it when it changes a decision) or sent back with a
   correction.
2. Read the diff (`git diff --stat`, then the parts that carry the handoff's
   shape), and run the handoff's tests yourself.
3. Commit as step 6 of the `review-fix` skill describes: only the handoff's
   files, a message that stands alone and describes the change, never
   `.clerk-dev/` paths or record ids. Mark the handoff done in the build log (or log
   the record it builds with `built`, as "The build log" describes), and
   tick the brief's open items it closes.
4. Say one line: the handoff, the commit, the tests, anything accepted, and the
   count it moves ("BUILD-15 done in 4c1e2ab, tests pass: BRIEF-52 now 27 of 32").

Whenever you report progress against a brief at more length (the user asks,
the draft ends, a milestone's passes are done), show `build.py checklist
<worktree> --brief BRIEF-52` as it prints it: one checkbox per requirement, ticked
when done, with partial and in-progress items marked. Never list requirement
numbers in prose ("1 to 18, 20 to 24 done; 19, 25 to 28 open").

### Milestones

An implementer holds one focus at a time: the draft, or one pass. The focuses
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
   implementer with its one lens's Pass mode text, then its pass review.
5. **Complete** when every planned pass has run or was skipped with a reason
   (`build.py skip <worktree> MILE-1 <pass> --why "..."`; never a required one)
   and the required passes' findings are triaged. `build.py milestones` and
   status say where each milestone stands and what runs next; a complete
   milestone leads to the next one. When a milestone completes, run a closing checkpoint, as "Closing checkpoint" in the `checkpoint` skill describes.

Run the sequence without pausing between passes. Stop and bring to the user:
a question an implementer stopped on, a check that found anything rated major
or blocker (triage it before the next pass, since later passes build on the
code), or any finding in a required pass's check. Minor findings collect in
their pass's run for triage at the end.


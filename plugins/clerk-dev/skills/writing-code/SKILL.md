---
name: writing-code
description: How to write code: delegate the building of settled pieces to implementer subagents at the right model and effort, while the session that owns the branch settles choices, reviews, and commits; and how to shape the code itself (refactor first to a clean baseline, reuse and extend what exists, one source of truth, clean abstractions). Use before writing or changing code of any size - implementing a feature, a spec, a chunk, a port, a pass, a fix, a follow-up, or a small edit - and when planning how a change will be built. Preloaded by the implementer and the review fixer.
---

# Writing code

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

This holds at every scale: a feature's first piece, a one-function fix, a
follow-up. Refactoring deployed code still follows the branch's scope (Branch
scope in `skills/review/tracking.md`): when the branch's Purpose does not cover
that code, propose the refactor instead of making it.

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
agent that preloads this skill skips it: it is the piece being delegated.

The feature records exist so that design choices are settled outside the code.
Once they are, building is delegated: the session that owns the branch keeps
the judgment (what to build, in what order, whether the result is right) and
the commits, and hands each piece to a `clerk-dev:implementer` agent with a
brief. This keeps the session's context for the whole feature instead of
filling it with one file's details, and gives every piece a check before it
lands.

### What stays in the session

- Settling choices. When a piece needs a choice no record settles and it
  shapes code others build on, settle it with the user first and record it (a
  decision, or an open item resolved in the spec), then delegate. An agent that
  stops on a `questions:` line is handled the same way.
- Cutting the work into pieces and ordering them.
- Reviewing each result, running its tests, and committing it.
- Changes small enough that the brief would be longer than the change: a few
  lines, one obvious edit. Do those inline.

### Pieces

A piece is one requirement or a few that belong together, or one port of
reference code, with tests that prove it, small enough to review in a few
minutes: usually a module, an entity with its migration, a set of DTOs, an
executor step. Cut along the spec's requirements, and order pieces so each
builds on committed ones.

### Model and effort

Pass `model` and `effort` on each implementer call:

| Piece | Model | Effort |
| --- | --- | --- |
| Shape-setting code others build on: core types, interfaces, extension points, cross-module wiring, schema and migration design, concurrency-sensitive code | opus | high |
| Implementing to a settled spec inside established patterns; ports of reference code; their tests | sonnet | medium |
| Mechanical edits: moves and renames with their import updates, regenerated files, applying one pattern across files | sonnet | low |

Raise a piece a row when its first attempt comes back with deviations or
failing tests that point at reasoning, not at the brief.

### The brief

Give paths, not contents. Include:

- the goal, in a sentence or two;
- the requirements it covers, by spec id and number, and the spec's path;
- the decisions it must follow, by id and path;
- the reference code to port or follow (`git show <ref>:<path>` for another
  branch);
- the files expected to change, and any it must not touch;
- the tests to write or port, and the exact command to run them;
- the rules that apply beyond the repository's conventions: the user's
  instructions that bear on code (for example a no-comments rule) and the
  branch's Purpose. Do not assume the agent sees the user's own instructions;
  restate the ones that apply.

### Order and parallelism

Run pieces one at a time by default. Run two at once only when they change
disjoint files and their tests share no resources (databases, ports, fixtures);
many repositories' integration tests share databases and must never run
concurrently. A larger fan-out is a multi-agent workflow, which runs only when
the user asks for one.

### The build log

Log every delegated piece in `.clerk-dev/build.md` with
`${CLAUDE_PLUGIN_ROOT}/scripts/build.py` (below, `build.py`); status reports
progress from it, so a piece not logged is invisible there:

- when briefing: `build.py add <worktree> "<piece>" --spec R52 --reqs 4,5
  --model <model> --effort <effort>`, which gives the piece's id (B3);
- when the agent stops on a question: `build.py stop <worktree> B3 --question
  "<the question>"`; after it is settled and recorded, `build.py resend` with
  the new model or effort if they changed;
- when it is sent back with a correction: `build.py resend <worktree> B3
  --note "<what changed>"`;
- after committing: `build.py done <worktree> B3 --commit <sha> --covered
  "<the report's requirements line, as 4:done,5:partial: what is missing>"`,
  adding `--deviation "..."` for each one accepted;
- when dropped: `build.py abandon <worktree> B3 --note "<why>"`.

A change done inline that covers spec requirements is logged too, as a piece
added and marked done in one go, so the progress stays whole. Requirement
status lives only here; the spec is not edited for it.

### After each piece

1. Read the report. `stopped` or `questions:` go back to the user (or are
   settled from the records) before anything else; `deviations:` are judged
   against the spec and decisions, and either accepted (say so to the user in
   a line, and record it when it changes a decision) or sent back with a
   correction.
2. Read the diff (`git diff --stat`, then the parts that carry the piece's
   shape), and run the brief's tests yourself.
3. Commit as step 6 of the `review-fix` skill describes: only the piece's
   files, a message that stands alone and describes the change, never
   `.clerk-dev/` paths or record ids. Mark the piece done in the build log, and
   tick the spec's open items it closes.
4. Say one line: the piece, the commit, the tests, anything accepted.

At milestones (the end of a chunk, a set of pieces that make one behavior),
check the work with a pass's narrow check or a review, as the user prefers.


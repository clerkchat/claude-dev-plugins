# Feature records

A feature's records are its history: what was considered, what was settled, and
how it was broken down and planned. They live in the hub worktree, at
`<hub>/.clerk-dev/feature/`, and are never committed.

```
.clerk-dev/feature/
  feature.md                  name, summary, and the generated index of records
  records/
    001-brainstorm-<slug>.md
    002-decision-<slug>.md
    ...
  checks/
    R13-1.md                  a design check of R13 (the design-check skill)
    R13-1/raw/<lens>.md       each lens's reply, verbatim
  overview.md                 generated from the active records; never edited
  ideas.md                    parked ideas, I1, I2, ...; kept by records.py
  guidance.md                 the guidance as a handbook, generated; never edited
```

`overview.md` is the feature's current state in one read, generated from the
active records (below). `ideas.md` holds ideas set aside for later (below). Check files are not
records: they have no R id, are never superseded, and are
listed in the index under every record they checked.

Manage files only through `${CLAUDE_PLUGIN_ROOT}/scripts/records.py`: it
assigns ids, writes the frontmatter, marks superseded records, and regenerates
the index. Write the body with Edit or Write after `records.py new` creates the
file.

## Rules

- **Point in time.** A record says what was true or intended on its date. It is
  written in the session that creates it, and may be edited there. After that it
  is not rewritten: a revision is a new record with `--supersedes`. The only
  later changes are its status (`discard`, `reactivate`, or superseded by a new
  record), which the script makes.
  One exception: a spec's Open items checklist tracks progress, so ticking an
  item or adding one is fine at any time.
- **Ids.** One sequence per feature: R1, R2, ... The id is the handle in
  conversation ("R7"), in other records (`from:`), and in items that link to a
  decision.
- **Status.** `active`, `superseded` (by the record named in `superseded_by`),
  or `discarded` (with a `note`). Brainstorms have no status; they stay as
  history. "What is true now" is the code plus the active records.
- **Repo.** The repository the record is about, defaulting to the one it was
  written from. A feature spanning repositories keeps all its records in the
  hub; `repo` says which one each concerns.
- **Area.** Optional: a short name for the part of the problem the record is
  about, such as `auth`, `delivery`, or `data-model`. On a complex feature the
  thinking splits by capability or layer, and each area becomes its own thread
  of records; the index groups by it. There is no list of areas: they are
  whatever the records use, coined when the thinking splits. Reuse an existing
  name (`records.py areas`) rather than coin a near-duplicate. A record with no
  area is feature-wide, like the broad first brainstorm. A new record inherits
  the area of the record it supersedes, or of its `from` records when they
  share one. The area is a label, not content: retag a record (`records.py
  tag`) or rename an area (`records.py rename-area`) whenever the split turns
  out different. An area is not a piece: an area is a part of the problem you
  think about, a piece a unit of work you build and review; a spec has both.
- **From.** The records this one builds on: the brainstorms a design settles,
  the design a capabilities record breaks down, the capability a spec details.
- **Short over complete.** Each record holds what a reader needs months later to
  understand the choice, and no more. Leave out a template section with nothing
  to say rather than filling it.

## Types

### brainstorm

Divergent thinking from one session about one area (or the whole feature):
ideas, alternatives, questions, leanings. Append a new one per session and
area; never revise an old one, even when it turned out wrong. That is the point
of keeping it.

```markdown
# R1. Polling vs push for export status

## Context

What prompted this session, and what was already known.

## Ideas

- **Poll from the client.** Simple; costs a request every few seconds per open
  export dialog.
- **Push over the websocket.** No polling; but the websocket server does not
  know about export jobs today.

## Open questions

- Do exports finish in seconds or minutes? Decides whether polling cost matters.

## Leaning

Polling, unless exports are long. Not settled.
```

### design

The settled outcome of one or more brainstorms (`from:`): the shape of the
solution as agreed on its date. It states what was chosen; the reasons and the
rejected alternatives for each significant choice go in decisions, which the
design cites.

```markdown
# R4. Report exports: design

## Problem

Who needs what, and why now.

## Shape

The solution in a few paragraphs or a short list: components, data flow, and
where each repository's part lies.

## Decisions

- R5: poll export status with backoff
- R6: exports are stored for 7 days

## Not doing

What the design deliberately leaves out.
```

### decision

One choice, with what was rejected and why. The strongest record: specs,
reviews, and fixes defer to active decisions. To refine one, write a new
decision that supersedes it; to drop one, discard it with a note.

```markdown
# R5. Poll export status with backoff

## Decision

Clients poll GET /exports/:id, starting at 1s and backing off to 10s.

## Why

Exports take 5 to 60 seconds; the websocket server has no job events today,
and adding them is a larger change than this feature.

## Rejected

- Websocket push: needs job events in the websocket server.
- Email when ready: too slow for the common case.

## Consequences

Polling load is bounded by open export dialogs; revisit if exports grow long.
```

### guidance

A rule from the user that settles choices beyond the question that prompted
it: a principle, a preference, a constraint ("capabilities wire in through
explicit lists, never a runtime registry"). A decision settles one choice and
records what it rejected; guidance decides the next ones. Written without
being asked whenever an answer carries one (see "Guidance from answers" in
`skills/review/tracking.md`). Refined by superseding, like a decision.
Implementer briefs, lens and fixer prompts, and design checks all get the
active guidance through the file `records.py guidance` writes. `guidance.md`
is also the place to read it: every rule at a glance, then each in full by
area with its why, what it applies to, and where it came from, and superseded
rules under History.

```markdown
# R61. Capabilities wire in through explicit lists

## Rule

Capabilities wire into the core through explicit lists and enums edited in
code, never a runtime registry.

## Why

Every capability is then visible by grepping one list, and a missing one fails
to compile instead of failing at run time.

## Applies to

How any capability chunk registers graders, narrowers, validators, and issue
codes; any new extension point.

## From

R30-1.Q12, answered 2026-10-16.
```

### capabilities

The breakdown of a design (`from:`) into pieces that can each be specified,
built, and reviewed on their own. Each piece names its repository and what it
depends on.

```markdown
# R7. Report exports: capabilities

1. **Export job** (api): create an export and run it in a worker. Depends on
   nothing.
2. **Export status endpoint** (api): GET /exports/:id. Depends on 1.
3. **Export dialog** (web): start an export and poll until ready. Depends on 2.
```

### plan

Order and sequencing across pieces and repositories, including which repository
goes first and where work is expected to loop back. Each numbered step is a
milestone: its pieces, its spec, and what is true when it is done. The
`writing-code` skill builds one milestone at a time, so every step needs that
done line, which may say "deferred items reviewed". Replanning writes a new
plan that supersedes the old one.

```markdown
# R8. Report exports: plan

1. api: pieces 1 and 2 (R7, spec R9), behind the `report-exports` flag.
   Done: an export can be started and polled with the flag on; api review;
   deferred items reviewed.
2. web: piece 3 (spec R10); expect contract changes back to api from this
   exploration. Done: the dialog exports a report end to end.
3. Feature review across api and web.

## Risks to the order

- The dialog may need progress, not just done/not done, which reopens piece 2.
```

### spec

Detailed implementation notes for one piece (`from:` the capabilities or
design record). Reviews read active specs: the spec-conformance lens checks the
change against Requirements, and the completeness lens checks Open items, so
keep both sections and keep requirements checkable.

```markdown
# R9. Export status endpoint

## Goal

One or two sentences.

## Requirements

1. GET /exports/:id returns status, progress, and a download URL when ready.
2. Returns 404 for an export of another tenant.

## Out of scope

- Cancelling an export.

## Baseline

The refactor to do before building, as its own commits, so the piece lands as
a small addition: helpers to extract, code to split, shapes to fix, dead code
to drop. Or "Clean: <why>" when the existing code already fits.

## Approach

Where the code goes, the patterns to follow, and the existing code and shared
library helpers to reuse or extend (with paths).

## Contracts

Endpoints, payloads, events, and schemas other parts or repositories rely on.
For runtime state handed to another component, when in the run it comes into
being.

## Open items

- [ ] Decide the download URL lifetime.
```

## Ideas

Good ideas come up all the time that are not for now. Parking one keeps it
from being lost or from creeping into the current work. `ideas.md` is a
checkbox list (I1, I2, ...) kept by `records.py idea`, `adopt`, `drop`, and
`unpark`, in the item vocabulary of "Items" in `skills/review/tracking.md`:

- **Parked** (status open): the idea, where it came from (a record, a check
  question, "this session"), why it is worth having, and when to look at it
  again: a trigger rather than a date ("after the core lands", "if exports
  get slow"). An area when it belongs to one; inherited from its `from`
  record otherwise.
- **Adopted** (fixed): it became a record (a brainstorm, a decision, a spec,
  or a piece of the plan); Outcome names the record.
- **Dropped** (wont-fix): it will not be done; Outcome says why.

An idea is not a rejected alternative (those stay in the decision that
rejected them) or a deferred item (a known gap with a path chosen for now,
kept in `deferred.md`; see "Deferred items" in `skills/review/tracking.md`).
Ideas are not records: they are not superseded, and parking one decides
nothing.

## The overview

Records are history, split one decision per file, which is right for drilling
in and wrong for skimming. `overview.md` is the other half: the feature as it
stands now, in one read, generated from the active records and never edited by
hand. A change of substance is a new record, after which the overview is
regenerated. Its stamp line, written by `records.py stamp-overview`, says which
records it is through; the index and status say when it is stale.

It is written from `records.py digest` alone, and every statement in it cites
the records it comes from, so it can be checked against them. It adds no claim,
opinion, or recommendation of its own; where records disagree or leave a gap,
it says so under Open. Aim for something read in five minutes.

````markdown
# Overview: report exports

## Goal

One paragraph: what the feature is for and what done looks like (summary,
designs).

## Guidance

Each active guidance rule, one line, feature-wide first, then by area:
"R61 (harness): capabilities wire in through explicit lists, never a
registry." Omitted when there is none.

## Shape

How the solution works, in a few paragraphs, from the active designs, citing
them and the decisions behind each part (R30; R21, R22).

## Plan

The order of work, from plans, capabilities, and decisions that set order,
citing them. When pieces depend on each other in more than a straight line,
start with a dependency graph in a code block. Then one row per piece, in
order, so it can be skimmed: the piece, its repository, its branch or worktree
when the records name one, what it branches from, what it depends on, its
spec, and how far it is built (from the digest's Build progress). Ordering
rules and notes that fit no row follow as a short list.

```
main ──► [C] core ──┬──► [A] assertions ──► [CA] capture
                    └──► [B] bisection
```

| Piece | Repo | Branch | From | Depends on | Spec | Built |
|---|---|---|---|---|---|---|
| C core harness | api | `feat/core` | main | nothing (R19, R29) | R32 | 9 of 32; B7 stopped |
| B bisection | api | `feat/bisection` | C | C; adds `baselineTestRunId` (R22) | none | not started |

- Each PR targets the branch it starts from until that merges, then main (R31).

## By area

### harness

Two or three sentences on where the area stands. Then each active decision,
one line:

- R22: `narrowing` is one result field, built by a ranked chain of localizers
  the core owns.

## Open

Three subsections, always with these headings (status counts their bullets),
each "None." when empty:

### Questions

Settle-first design questions first, then other open questions and open items
in specs, one bullet each, citing the check or record.

### Gaps

What the records lack: an area with decisions but no design, a piece with no
spec, no plan.

### Disagreements

Records that disagree, that rely on a superseded record, or that go against
active guidance, one bullet each naming both sides: "R5 relies on R3's frozen-contract rule; R3 is superseded
by R28 (R5, R28)."

## Parked

One line per parked idea, by area, with when to look again (I4, harness:
streaming results; when a suite runs longer than a minute). "None." when there
are none.

## Explored

One line per brainstorm: what it explored (R1: how to split the harness branch
into chunks).
````

When there are no areas, By area becomes Decisions, one line each.

## The hub

The hub is the worktree that holds a feature's records: the one the engineer
started in, which depends on their background. Records stay there, where they
are at hand while working.

`records.py hub <worktree>` resolves it: the worktree named on the `Hub:` line
of `.clerk-dev/review-workspace.md` (see `skills/review/workspace-manifest.md`),
or else the worktree itself. A session in any worktree of the workspace reads
and writes the hub's records through the script.

Removing the hub worktree removes the records with it. Before removing it, copy
`.clerk-dev/feature/` somewhere to keep.

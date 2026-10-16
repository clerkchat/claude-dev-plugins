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
```

Check files are not records: they have no R id, are never superseded, and are
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
goes first and where work is expected to loop back. Replanning writes a new plan
that supersedes the old one.

```markdown
# R8. Report exports: plan

1. api: pieces 1 and 2 (R7), behind the `report-exports` flag.
2. web: piece 3; expect contract changes back to api from this exploration.
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

## Approach

Where the code goes, the patterns to follow, and the existing code to reuse.

## Contracts

Endpoints, payloads, events, and schemas other parts or repositories rely on.

## Open items

- [ ] Decide the download URL lifetime.
```

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

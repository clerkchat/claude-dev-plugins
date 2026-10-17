---
name: feature
description: Keep a feature's records while designing it - brainstorms, designs, decisions, capabilities, plans, and specs, grouped by the areas the thinking splits into - in the hub worktree's .clerk-dev/feature/. Use when the user says "start a feature", "let's brainstorm X", "capture this", "park that idea", "let's skip that for now", "save that for later", "what ideas did we park", "split this out into its own area", "write this up as a brainstorm", "let's settle on", "record a decision", "we decided", "supersede R3", "break this into pieces", "make a plan", "write the spec for", "what did we decide about X", "show the feature records", or asks to import a Notes-*.md or Spec-*.md file as records.
argument-hint: "[start <name> | brainstorm | design | decide | breakdown | plan | spec <piece> | list | import <file>]"
allowed-tools: Bash(python3 *), Bash(git *), Read, Write, Edit, Grep, Glob
---

# Feature records

The records, their types, templates, and rules are in `records.md` next to this
file; read it before writing the first record in a session. Files are managed
only through `${CLAUDE_PLUGIN_ROOT}/scripts/records.py`; it prints the path of
each new record, and you write the body there.

Records are the user's thinking, written down. Draft them from the conversation
in the user's terms, keep them short, and show the user what you wrote in a line
or two (id, title, path), not the whole record. Never commit them.

None of this is a required sequence. A small change may have one spec or no
records at all; a large one may go round brainstorm and design several times.
Do what the user asks, and suggest a next record only when it is clearly due
(several brainstorms converging, a design with no decisions behind it, a plan
with a piece that has no spec).

## Finding the feature

1. `records.py hub <worktree>` prints the hub. Records always go there, whatever
   worktree the session is in.
2. If the hub has no `.clerk-dev/feature/feature.md`, there is no feature yet.
   Asked for a record anyway, offer to start one, proposing the branch name as
   its name.

## Starting a feature

`records.py start <worktree> "<name>" --summary "<one paragraph>"`. Draft the
summary from the conversation. Read `.clerk-dev/branch-notes.md` Purpose, and
draft it if it is missing (as `skills/review/tracking.md` describes): Purpose is
what this branch builds, the feature summary is what the whole feature is for,
and they should agree.

When the feature spans repositories, the hub is the worktree the user starts in.
Once a second repository joins, set up `.clerk-dev/review-workspace.md` as
`skills/review/workspace-manifest.md` describes, with the `Hub:` line naming
this repository, so sessions in the other worktrees find the records.

## Areas

A complex feature's thinking splits into areas, one per capability or layer, the
way separate `Notes-*.md` files would. Areas are not declared up front.

- When writing a record, give it the area the conversation is about. Check
  existing names first (`records.py areas <worktree>`) and reuse one when it
  fits; when the subject is new, propose a short name in a line ("filing this
  under a new area, `delivery`") and go on. When the subject is the whole
  feature, leave the area off. Inherited areas (from `--supersedes` or
  `--from`) are usually right; override with `--area` when not.
- When a conversation moves between areas, write one record per area rather
  than one mixed record.
- "Split this out into its own area": write a brainstorm in the new area `from`
  the record it grew out of; the old record stays as it was. When existing
  records belong to the new area, retag them with `records.py tag`.
- When areas turn out to be named or cut wrong, `records.py rename-area` or
  `tag`; they are labels, not content.
- Questions like "where are we on delivery?" read that area's records (`list
  --area delivery`) and the feature-wide ones.

## Writing each type

- **brainstorm**: during an exploratory conversation, offer to capture it when
  it reaches a pause, or when the user says "capture this". One record per
  session and area. Include the alternatives the user turned down and the open
  questions; they are what later readers need most.
- **design**: when brainstorming settles. `--from` the brainstorms it settles.
  Write a decision record for each significant choice first, and cite them.
- **decision**: one choice per record, with what was rejected and why. When a
  new choice changes an earlier one, `--supersedes R<n>`; never edit the old
  one. When the user drops one, `records.py discard <worktree> R<n> --note
  "<why>"`.
- **capabilities**: `--from` the design. Each piece names its repository and its
  dependencies.
- **plan**: order across pieces and repositories. Replanning is a new plan with
  `--supersedes`.
- **spec**: one per piece, `--repo` the repository it is built in, `--from` the
  capabilities or design record. Before writing Approach, read the code the
  piece will touch: the patterns to follow, the helpers to reuse or extend,
  and what to refactor first (the Baseline section; always filled, "Clean"
  with a reason when nothing needs it). Keep
  Requirements numbered and checkable, and Open items as checkboxes; reviews
  read both.

A record created earlier in this session may be edited freely. One from an
earlier session is not rewritten: write a new record that supersedes it, or, for
a brainstorm, a new brainstorm.

## Parked ideas

When an idea comes up that is not for now ("cool, but later", "let's skip that
for now", "park that"), or when you set one aside yourself while scoping, park
it: `records.py idea <worktree> "<the idea>" --from <R-id, check question, or
"this session"> --why "<what it would buy>" --when "<what would make it worth
doing>"`, with `--area` when it belongs to one. One line to the user ("parked
as I7"). Offer to park ideas the conversation drops without deciding, at most
once per pause, listing them in a line each.

"What ideas did we park", "anything parked for the harness": `records.py ideas
<worktree> [--area <area>]`. When the work reaches an idea's trigger, mention
it in a line. When an idea is taken up, write the record it becomes and
`records.py adopt <worktree> I7 --by R<n>`; when it is ruled out, `records.py
drop <worktree> I7 --why "<why>"`.

## The overview

`overview.md` is the feature in one read, generated, never edited (format and
rules: "The overview" in `records.md`). Refresh it when the user asks ("refresh
the overview", "update the overview", "give me the big picture"), and on your
own when a conversation that wrote, superseded, or retagged records reaches a
pause: say so in one line and do it.

To refresh: write `records.py digest <worktree>` to a scratch file, and hand it
to a `general-purpose` subagent with the path of `records.md` (for the format
and rules) and the output path `<hub>/.clerk-dev/feature/overview.md`, asking it
to write the overview from the digest alone, citing ids for every statement.
When it returns, run `records.py stamp-overview <worktree>`, and tell the user
the path. If the user wants something in it changed, that is a new or
superseding record, then a refresh; never edit the overview itself.

## Rolling up

Decisions are written one at a time, so the synthesis records (designs, plans,
capabilities) fall behind unless something prompts them. After writing records,
run `records.py suggest <worktree>` and mention at most two of its suggestions,
one line each, as offers: an area with several decisions and no design (roll
them up into a design that cites them), a design older than several decisions
(supersede it with one that includes them), a decision that reads like a plan
or breakdown (file it as one, `--from` that decision), no plan yet on a large
feature. A roll-up design or plan restates what the decisions settled, citing
them; it does not decide anything new.

## Answering from the records

"What did we decide about X", "why did we do Y": `records.py list <worktree>
--active --type decision` (or the type in question, with `--area` when X is an
area), read the matching records,
and answer citing their ids. Superseded records answer "what did we think
before"; say they are superseded when quoting them.

"Show the records": `records.py list <worktree>` and show its output as it is.

## Importing existing notes

Asked to import a `Notes-*.md`, `Spec-*.md`, or similar file: read it, pick the
type it mostly is (notes are usually a brainstorm, sometimes a design with
decisions in it; a spec is a spec), create the record with the file's date
noted in its Context section and an area from the file's subject (none for the
broad one), and copy the content into the template's sections
without rewriting the substance. When a notes file holds several settled
choices, offer to split them out as decision records. Leave the original file
where it is; it is the user's.

A set of notes files (`Notes-*.md`, one per capability or layer, plus usually
a broad one) imports as one record per file: the broad file feature-wide, each
other file in an area named after its subject, `from` the broad one when it
grew out of it. Show the proposed areas in one line before writing, since they
become the index's grouping.

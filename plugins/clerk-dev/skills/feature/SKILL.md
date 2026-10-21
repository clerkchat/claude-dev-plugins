---
name: feature
description: Keep a feature's records while designing it - brainstorms, designs, decisions, capabilities, plans, and specs, grouped by the areas the thinking splits into - in the hub worktree's .clerk-dev/feature/. Use when the user says "start a feature", "let's brainstorm X", "capture this", "park that idea", "guidance: ...", "record this as guidance", "as a rule", "from now on", "let's skip that for now", "save that for later", "what ideas did we park", "split this out into its own area", "write this up as a brainstorm", "let's settle on", "record a decision", "we decided", "supersede R3", "break this into pieces", "make a plan", "write the spec for", "what did we decide about X", "show the feature records", or asks to import a Notes-*.md or Spec-*.md file as records.
argument-hint: "[start <name> | brainstorm | design | decide | breakdown | plan | spec <piece> | list | import <file>]"
allowed-tools: Bash(python3 *), Bash(git *), Read, Write, Edit, Grep, Glob
---

# Feature records

When talking to the user, follow "Talking to the user" in `skills/review/tracking.md`: the feature first, the bookkeeping last or not at all, and ids named: every id (R19, B15, M1, F3, Q3, P3, I7, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

If this conversation was compacted, re-read this file before going on: a
compacted skill may be cut short, and the steps it drops are the ones that
keep the work safe. Prefer `/clear` at a natural boundary to compaction; the
`checkpoint` skill writes down what is pending first.

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

## Setup first

Start the session with `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/status.py
<worktree> --setup`. It prints what the worktree is missing for feature work (a
Purpose, a hub and feature, a review workspace, workspace rows whose worktree is
missing, a plan with done lines) or "Setup: complete." Settle each gap with the
user before going on, then carry on with the request.

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
  new choice changes an earlier one, `--supersedes R<n>` and restate it ("When
  a record changes another" below); never edit the old one. When the user drops one, `records.py discard <worktree> R<n> --note
  "<why>"`.
- **capabilities**: `--from` the design. Each piece names its repository and its
  dependencies.
- **plan**: order across pieces and repositories, cut into milestones: each
  numbered step is one milestone, naming its pieces, its spec, and the point
  where it is done (what works, and what a review can check). Building works
  milestone by milestone, so a plan without them is not finished. Replanning is
  a new plan with `--supersedes`.
- **spec**: one per piece, `--repo` the repository it is built in, `--from` the
  capabilities or design record. Before writing Approach, read the code the
  piece will touch: the patterns to follow, the helpers to reuse or extend,
  and what to refactor first (the Baseline section; always filled, "Clean"
  with a reason when nothing needs it). Keep
  Requirements numbered and checkable, and Open items as checkboxes; reviews
  read both. When the piece changes the behavior of a spec that is already
  built, Approach names that spec and what changes ("When a record changes
  another" below). Any other list in a spec uses plain numbers, cited as
  R33.4, never letter-prefixed ids (I, F, D, B, M, P, Q, R), which clash with
  the plugin's ids. Every implementer works from the spec, so draft it with a
  `general-purpose` subagent on `model: fable`, effort `high` (falling back to Opus at the same effort as Model fallback in the `review` skill describes):
  give it the spec template in `records.md`, the records the piece builds on
  (its capabilities or plan row, the design, the decisions of its area, and
  the guidance file `records.py guidance <worktree> --area <area> --out
  <scratchpad>/guidance-<area>.md` writes), the reference code to
  port by path, and the output path `records.py new` gave; ask it to write the
  body and list anything it could not settle from the records as open items.
  Then read it, settle what you can with the user, and edit it in this
  session.

## When a record changes another

A record that changes any part of an active record supersedes it and states the
whole current version: what still holds, and the change. No record amends
another in part ("as R8, except ..."), because that moves the merge to read
time, when the context is gone and each reader merges differently. The writer
has the most context.

Before writing any record, find the active records it changes: the area's
active records (`records.py list <worktree> --active --area <area>`) and those
its `from` cites. Supersede each one it changes with `--supersedes`, and write
the body as the complete current version, so a reader never needs the old
record to understand it. `--supersedes` takes one record: when the new record
changes several, give it the one it mostly restates, restate the others in the
body, and discard each of them with `records.py discard <worktree> R<n> --note
"restated in R<new>"`.

When the change touches one part of a large design or capabilities record,
either restate that whole record, or first split the settled part into its own
decision and supersede that.

Carve-out: a spec whose piece is built is history and is not restated. A spec
is built when the build log shows all its requirements done or dropped;
`records.py digest` marks each active spec "built: yes" or "built: no". A later
spec that changes a built spec's behavior says so in its Approach, naming that
spec and what changes; the overview treats that as consistent.

A record created earlier in this session may be edited freely. One from an
earlier session is not rewritten: write a new record that supersedes it, or, for
a brainstorm, a new brainstorm.

### Recording defects

A recording defect is a later record that changes an earlier active one
without superseding it. The later record already settled the change, so fix
it when you find it (an overview refresh, a roll-up, a design check, or
reading records for any reason): write a record that supersedes the earlier
one and restates it in full with the later change folded in, and tell the
user in one line what was restated. When it is unclear what the change was,
or the two records cannot both hold, it is a real conflict: put it to the
user instead.

## Guidance

Whenever the user answers a question or steers the work, in this skill or any
other, and the answer carries a rule beyond this case, or the user writes
`guidance: ...`, record it as "Guidance from answers" in
`skills/review/tracking.md` describes: its routing says whether it is
guidance at all, and its scope where it goes (a `###` rule in the branch notes
for this branch only, a `guidance` record for the feature or one of its areas,
and a proposal first for anything wider). Say in one line what was recorded.
"What guidance have I given", "the rules for the harness": `records.py
guidance <worktree> [--area <area>]`.

When the last open question of a set put to the user is settled (a spec's or
plan's open questions, or any other skill's discussion), look back over the
whole discussion as "Lessons from a discussion" in `skills/review/tracking.md`
describes, before the next step starts.

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
to a `general-purpose` subagent on `model: fable`, effort `high` (finding the
gaps and disagreements across every record is the part that needs it; falling back to Opus at the same effort as Model fallback in the `review` skill describes), with the path of `records.md` (for the format
and rules) and the output path `<hub>/.clerk-dev/feature/overview.md`, asking it
to write the overview from the digest alone, citing ids for every statement.
The digest marks each spec built or not and lists every idea with its status;
the overview names an adopted idea by the record it became, and never calls
one missing. Disagreements are only recording defects (a later record that
should have superseded an earlier one: name both, and say the later one is to
be restated in full) or real conflicts for the user to decide; a built spec and
a later spec that names its change in Approach are consistent, not a
disagreement.
When it returns, run `records.py stamp-overview <worktree>`, and tell the user
the path. Its report cites bare ids; run `records.py names` on them and gloss
each one in what you tell the user (the gaps and disagreements it found
especially), as "Talking to the user" requires. If the user wants something in it changed, that is a new or
superseding record, then a refresh; never edit the overview itself.
When it lists recording defects, fix them as "Recording defects" above
describes, then refresh again so the overview no longer lists them.

## Rolling up

Decisions are written one at a time, so the synthesis records (designs, plans,
capabilities) fall behind unless something prompts them. After writing records,
run `records.py suggest <worktree>` and mention at most two of its suggestions,
one line each, as offers: an area with several decisions and no design (roll
them up into a design that cites them), a design older than several decisions
(supersede it with one that includes them), a decision that reads like a plan
or breakdown (file it as one, `--from` that decision), no plan yet on a large
feature. A roll-up design or plan restates what the decisions settled, citing
them; it does not decide anything new. Draft it with a `general-purpose`
subagent on `model: fable`, effort `high` (falling back to Opus at the same effort as Model fallback in the `review` skill describes), given the records it
rolls up and the template, asked to cite every decision it draws on and to
list, rather than resolve, any that do not fit together. Fix the recording
defects in that list as "Recording defects" above describes.

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

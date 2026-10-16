---
name: feature
description: Keep a feature's records while designing it - brainstorms, designs, decisions, capabilities, plans, and specs - in the hub worktree's .clerk-dev/feature/. Use when the user says "start a feature", "let's brainstorm X", "capture this", "write this up as a brainstorm", "let's settle on", "record a decision", "we decided", "supersede R3", "break this into pieces", "make a plan", "write the spec for", "what did we decide about X", "show the feature records", or asks to import a Notes-*.md or Spec-*.md file as records.
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

## Writing each type

- **brainstorm**: during an exploratory conversation, offer to capture it when
  it reaches a pause, or when the user says "capture this". One record per
  session. Include the alternatives the user turned down and the open
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
  piece will touch: the patterns to follow, the helpers to reuse. Keep
  Requirements numbered and checkable, and Open items as checkboxes; reviews
  read both.

A record created earlier in this session may be edited freely. One from an
earlier session is not rewritten: write a new record that supersedes it, or, for
a brainstorm, a new brainstorm.

## Answering from the records

"What did we decide about X", "why did we do Y": `records.py list <worktree>
--active --type decision` (or the type in question), read the matching records,
and answer citing their ids. Superseded records answer "what did we think
before"; say they are superseded when quoting them.

"Show the records": `records.py list <worktree>` and show its output as it is.

## Importing existing notes

Asked to import a `Notes-*.md`, `Spec-*.md`, or similar file: read it, pick the
type it mostly is (notes are usually a brainstorm, sometimes a design with
decisions in it; a spec is a spec), create the record with the file's date
noted in its Context section, and copy the content into the template's sections
without rewriting the substance. When a notes file holds several settled
choices, offer to split them out as decision records. Leave the original file
where it is; it is the user's.

---
name: checkpoint
description: Write down everything this conversation settled that is not yet in a file (decisions, guidance, parked ideas, answers to design questions, built pieces, follow-ups owed elsewhere, scope changes), then say whether it is safe to clear the conversation. Use when the user says "checkpoint", "wrap up", "save where we are", "before I clear", "is it safe to clear", "I'm going to clear", or similar.
allowed-tools: Bash(python3 *), Bash(git *), Read, Write, Edit, Grep, Glob, Agent
---

# Checkpoint

When talking to the user, follow "Talking to the user" in `skills/review/tracking.md`: the feature first, the bookkeeping last or not at all, and ids named: every id (R19, B15, M1, F3, Q3, P3, I7, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

The plugin keeps its state in files, so a cleared conversation loses only what
was settled in it and never written down. A checkpoint finds that and writes
it, in the places the other skills would have, then says whether clearing is
safe. It records what was settled; it decides nothing new.

`records.py`, `build.py`, `passes.py`, and `followups.py` below are in
`${CLAUDE_PLUGIN_ROOT}/scripts/`.

## 1. Find what is not written down

Read back over this conversation since the start or the last checkpoint, and
list each thing that was settled but has no file yet:

- **Decisions**: a choice made between options. A `decision` record (the
  `feature` skill, which also says when it supersedes and restates an earlier
  record), or an edit to a record written earlier in this session.
- **Guidance**: a rule the user gave beyond one case, or anything they wrote
  as `guidance: ...`. Recorded as "Guidance from answers" in
  `skills/review/tracking.md` describes, at its scope.
- **Ideas set aside**: "later", "not now", "skip that". Parked with `records.py
  idea`, with why and when.
- **Answers to design questions** that are not yet in their check file:
  `items.py set` and `items.py status`, as the `design-check` skill's walk does.
- **Pieces of work** built or committed but not in the build log, and
  requirements a commit covered: `build.py add` and `done`, as the
  `writing-code` skill describes. A piece briefed and still running is not
  pending; see step 3.
- **Follow-ups** another repository now owes because of a change here:
  `followups.py add` in its worktree.
- **Scope**: the branch's purpose widened or narrowed in conversation: a
  dated line in `.clerk-dev/branch-notes.md` Purpose.
- **Spec open items** settled or raised: tick or add them in the spec.

When it is unclear whether something was settled or only discussed, do not
record it: list it in step 4 as open, in the user's words.

## 2. Write them

Write each in its place, following the skill that owns it. Then, when records
changed in this session and the overview is now stale (`records.py
overview-status`), refresh it as the `feature` skill describes, or, when the
user wants to clear right away, say it is stale and leave it for the next
session.

## 3. Check what is in flight

- `git status --short`: uncommitted changes to tracked files. Name them; a
  finished piece is committed as the `writing-code` skill describes before
  clearing, and anything else is the user's to decide.
- Subagents still running (an implementer, a review, a design check): clearing
  may lose their reports. Wait for them, or say which are running and what to
  do with their results in the next session.
- An open pass or a briefed piece: these are in the logs already and survive a
  clear. Write what the next session needs to finish it (what to log, what to
  run next) as its note, replacing the old one: `passes.py note <worktree> P9
  "<next steps>"` or `build.py note <worktree> B3 "<next steps>"`. Status shows
  the note of every open pass and piece, so this is the only place in-flight
  next steps go; no other file takes them.

## 4. Report

In a few lines:

- what was written, one line each, with names ("decision R74, chunk C ships
  the seams as PRs to main ahead of the core chunk");
- what is still open and only in this conversation, if anything;
- what is in flight, with the notes just written;
- **safe to clear** or **not yet, because ...**;
- what to ask after clearing to pick up: "where are we on the implementation"
  or "where are we on the design", as fits. Next steps that belong to no open
  pass or piece are not written down: status reports its own, so name only
  what it already reports.

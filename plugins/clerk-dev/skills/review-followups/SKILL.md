---
name: review-followups
description: Work through this worktree's review follow-ups (.clerk-dev/followups.md), the work it owes because of changes in another repository. Use when the user says "go through the follow-ups", "work the follow-ups", "do the review followups", "do F3", "fix follow-up F2", or similar. Implements one item at a time through a fixer subagent, one commit per item, and closes each item with its commit.
argument-hint: "[F3[,F5...]]"
allowed-tools: Bash(git *), Bash(gh pr view *), Bash(python3 *), Read, Grep, Glob, Agent, Write
---

# Working follow-ups

When talking to the user, follow "Talking to the user" in `skills/review/tracking.md`: the feature first, the bookkeeping last or not at all, and ids named: every id (DEC-19, BUILD-15, MILE-1, F3, Q-3, PASS-3, IDEA-7, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

A follow-up is work this repository owes because a change landed somewhere else,
usually a contract change made while fixing a review finding in another
repository. The file and its format are in `skills/review/tracking.md` of this
plugin; manage it only through `${CLAUDE_PLUGIN_ROOT}/scripts/followups.py`.

You coordinate; you never edit code in this session. Every item goes through its
own `clerk-dev:review-fixer` agent, gets its own commit, and is closed before
the next one starts. Never implement several items in one change.

The request ("go through the follow-ups", "do F3") is the user's go-ahead to
edit and commit for those items, under the same rules as fixing a review
finding: one commit per item, only the files its fix touched, only after the
touched tests pass. Never commit anything under `.clerk-dev/` or any untracked
file the fix did not create, and never push or amend.

If this conversation was compacted, re-read this file before going on: a
compacted skill may be cut short, and the steps it drops are the ones that keep
items separate and commits clean.

Keep this session small: pass the fixer paths rather than file contents, run
commands quietly (`git commit -q`), and print one line per item. The fixer's
report is the only thing an item should add here.

## Before the first item

1. List the open items: `followups.py list <worktree> --open`. With item ids as
   the argument, take only those; otherwise all open items, in id order. Sort
   them by instruction (the vocabulary is "Items" in `skills/review/tracking.md`):
   - none, `Fix as recommended`, or `Fix as noted`: the work list, done in id
     order; a note replaces the item's text where they differ;
   - `Refine`: before the work list, weigh each with the `deliberate` skill,
     whose facts include the source change (`git -C <source worktree> show
     <sha>`) and the local code it touches; record the instruction the user
     picks with `followups.py set`, and add the item to the work list when it
     becomes a fix;
   - `Discuss`: after the work list, walk them with the user one at a time,
     each through the `deliberate` skill, and record what they
     decide with `followups.py set`; for Refine and Discuss
     alike, when the user's answer carries guidance (a rule beyond this item)
     or says `guidance: ...`, record it as "Guidance from answers" in
     `skills/review/tracking.md` describes;
   - `Defer` still open: apply Defer as "Items" in `skills/review/tracking.md`
     describes, with the follow-up as the source (`F3`), in one line each.
   - `Ignore` still open: close it now, `followups.py close <worktree> F3
     --status wont-fix --ref "<the note, or why>"`, in one line each.
   Fix the work list now; its length is the total.
2. Draft this worktree's Purpose if it is missing (Branch notes in
   `skills/review/tracking.md`), then write the guidance file to the
   scratchpad: `records.py guidance <worktree> --context
   <git common dir>/clerk-dev/repo-context.md --out
   <scratchpad>/guidance.md`.
   Write it again whenever a rule is recorded during the run.
3. Check the working tree with `git status --short`. Each commit must hold only
   its item's change, so uncommitted edits to tracked files get in the way. If
   there are any, stop and ask the user whether to commit or set them aside
   first, or to go ahead and leave those files out of every commit. Untracked
   files are fine; they stay out of every commit.
4. Say in one line how many items there are and roughly how long (about five
   minutes each).

## Each item

Open each item with a progress line: "Follow-up 3 of 9 (F3): 2 done, 7 left
(this one included)."

1. Build the handoff from the item: its text (what to do), `Contract:` (what the
   other side now sends or accepts, which the change must match), `From:`
   (repository and commit), and `Finding:`. Find the source repository's
   worktree by its name in `.clerk-dev/workspace.md`, and pass its path
   and the commit so the fixer can read the change with
   `git -C <path> show <sha>`. When the item names a
   finding, add the source run's `resolution/<merged id>.md` if it exists
   (resolve the number through that run's `numbers.tsv`). Point it at the
   guidance file, whose branch scope and rules the fix follows. When this
   worktree has a review run (`.clerk-dev/latest` with a `merged.md`), give the fixer the command
   to list the open findings in the files it will change:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stale-findings.py <run> --repo
   <worktree> --open-in <files>`,
   as context, not as work. Do not read the source diff yourself.
2. Check for an open decision. Items often leave a product choice open: wording
   the user will read, where a control goes, what to show on an empty or error
   state. Weigh it with the `deliberate` skill, which settles it in a line
   when the item text, the code, or the guidance already does, and wait for
   the user's choice before delegating; put the choice in the handoff. A choice
   that would settle later items the same way is recorded as "Guidance from
   answers" in `skills/review/tracking.md` describes.
3. Delegate to `clerk-dev:review-fixer`, saying that the handoff is a follow-up,
   not a finding. It defaults to sonnet; pass `model: opus` when the item
   touches structure or more than two files.
4. If the fixer reports `scope: out`, commit nothing, leave the item open, tell
   the user why in one line (with the proposal and its rollout considerations
   when the reason is deployed code Purpose does not cover, as Branch scope in
   `tracking.md` describes), and go on to the next. If the touched tests fail,
   commit nothing, show the failure, and ask how to proceed.
5. Commit: `git add` only the files the fixer changed, then commit. The message
   stands alone, since the follow-ups file and review runs are local: no
   follow-up ids, finding numbers, run labels, or `.clerk-dev/` paths. The subject
   follows `skills/review/commits.md` and says what the client now does; the
   body, two or three sentences from the fixer's `summary`, says what changed on
   the other side (the contract, in plain words) and what this change does about
   it. When the handoff names a record the follow-up builds, log it after the
   commit as "The build log" in the `writing-code` skill describes.
6. Close the item: `followups.py close <worktree> F3 --ref <sha>`. Any
   follow-ups the fixer listed for yet another repository are added with
   `followups.py add` to that repository's worktree, and its `contract:` line is
   checked against every related worktree, both as the `review-fix` skill
   describes under Clients of a changed contract. For each line under the
   fixer's `findings:`, add a note to that finding with the renderer's
   `--note N=<file>`, as the `review-triage` skill describes under Recording a
   decision: "<date>, after <sha> (a follow-up): <why>". Do not change its
   instruction or status; the next triage judges it against the commit.
7. Print one line ("F3 done in 1a2b3c4: shows the export error on failed
   downloads"), drop the item's detail, and move to the next.

If the user stops partway, the file is the record; the next invocation resumes
with whatever is still open.

## At the end

Say how many items were done with their commits, which were left open and why in
a few words each, any follow-ups added elsewhere, and any findings noted as
affected. There is no recheck lens for a follow-up; the next review of this
branch checks open and closed items through its completeness lens, and the next
triage checks the open findings against these commits. After saying so,
run a closing checkpoint, as "Closing checkpoint" in the `checkpoint` skill describes.

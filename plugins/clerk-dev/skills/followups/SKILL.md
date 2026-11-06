---
name: followups
description: Work through this worktree's follow-ups (the repository backlog's follow-ups scoped to its branch), the work it owes because of changes in another repository, from a review or from coding there. Use when the user says "go through the follow-ups", "work the follow-ups", "do BL-4", "fix follow-up BL-2", or similar. Hands each item to the building skill's intake, one commit per item, and closes each item with its commit.
argument-hint: "[BL-4[,BL-6...]]"
allowed-tools: Bash(git *), Bash(gh pr view *), Bash(python3 *), Read, Grep, Glob, Agent, Write
---

# Working follow-ups

When talking to the user, follow "Talking to the user" in `skills/review/tracking.md`: the feature first, the bookkeeping last or not at all, and ids named: every id (DEC-19, BUILD-15, MILE-1, BL-4, Q-3, PASS-3, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

A follow-up is work this repository owes because a change landed somewhere else:
a contract changed or wanted by another repository, while fixing a review
finding there or while coding. It is an item of kind `followup` in this
repository's backlog, described under Follow-ups in `skills/review/tracking.md`
of this plugin; manage it only through `${CLAUDE_PLUGIN_ROOT}/scripts/backlog.py`.

You coordinate; you never edit code in this session. Every item goes through
the `building` skill's intake, gets its own commit, and is closed before the
next one starts. Never build several items in one change.

The request ("go through the follow-ups", "do BL-4") is the user's go-ahead to
edit and commit for those items, as the Commit step of "After each handoff" in
the `building` skill describes, only after the touched tests pass.

If this conversation was compacted, re-read this file before going on: a
compacted skill may be cut short, and the steps it drops are the ones that keep
items separate and commits clean.

Keep this session small: pass the builder paths rather than file contents, run
commands quietly (`git commit -q`), and print one line per item. The builder's
report is the only thing an item should add here.

## Before the first item

1. List the open items: `backlog.py list <worktree> --kind followup`, and read
   each one's fields (instruction, origin, contract, finding) and need with
   `backlog.py show <worktree> BL-4`. With item ids as the argument, take only
   those; otherwise all open items, in id order. Sort them by instruction
   (the vocabulary is "Items" in `skills/review/tracking.md`):
   - none, `Fix as recommended`, or `Fix as noted`: the work list, done in id
     order; a note replaces the item's text where they differ;
   - `Refine`: before the work list, weigh each with the `deliberate` skill,
     whose facts include the source change (`git -C <source worktree> show
     <sha>`) and the local code it touches; record the instruction the user
     picks with `backlog.py instruct <worktree> BL-4 "<instruction>" [--note
     ".."]`, and add the item to the work list when it
     becomes a fix;
   - `Discuss`: after the work list, walk them with the user one at a time,
     each through the `deliberate` skill, and record what they
     decide with `backlog.py instruct`; for Refine and Discuss
     alike, when the user's answer carries guidance (a rule beyond this item)
     or says `guidance: ...`, record it as "Guidance from answers" in
     `skills/review/tracking.md` describes;
   - `Defer` still open: hand it to new work with `backlog.py rescope
     <worktree> BL-4 new`, in one line each; no deferred item is written and
     the instruction stays as it is.
   - `Ignore` still open: close it now, `backlog.py set <worktree> BL-4
     dropped --ref "<the note, or why>"`, in one line each.
   Fix the work list now; its length is the total. It is handed to Intake in
   the `building` skill as one queue, in id order.
2. Draft this worktree's Purpose if it is missing (Branch notes in
   `skills/review/tracking.md`), then write the guidance file to the
   scratchpad: `records.py guidance <worktree> --context
   <git common dir>/clerk-dev/repo-context.md --out
   <scratchpad>/guidance.md`.
   Write it again whenever a rule is recorded during the run.
3. Check that the tree is clean, as Queues in the `building` skill describes.
4. Say in one line how many items there are and roughly how long (about five
   minutes each).

## Each item

Open each item with a progress line: "Follow-up 3 of 9 (BL-4): 2 done, 7 left
(this one included)."

1. **Build the handoff.** Build it as "The handoff" in the `building` skill
   describes:
   its first line is `Source: follow-up`, and it pastes the Follow-up entry
   from By kind word for word. Then fill it from the item (`backlog.py show`):
   its title and body (the need), `Contract:` from `contract` (what the other
   side now sends or accepts, which the change must match), `From:` from
   `origin` (repository and commit), and `Finding:` from `finding`. Find the source repository's
   worktree by its name in `.clerk-dev/workspace.md`, and pass its path
   and the commit so the builder can read the change with
   `git -C <path> show <sha>`. When the item names a
   finding, add the source run's `resolution/<merged id>.md` if it exists
   (resolve the number through that run's `numbers.tsv`). Point it at the
   guidance file, whose branch scope and rules the change follows. When this
   worktree has a review run (`.clerk-dev/latest` with a `merged.md`), give the builder the command
   to list the open findings in the files it will change:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stale-findings.py <run> --repo
   <worktree> --open-in <files>`,
   as context, not as work. Do not read the source diff yourself.
2. Check for an open decision. Items often leave a product choice open: wording
   the user will read, where a control goes, what to show on an empty or error
   state. Weigh it with the `deliberate` skill, which settles it in a line
   when the item text, the code, or the guidance already does, and wait for
   the user's choice before handing the item over; put the choice in the handoff. A choice
   that would settle later items the same way is recorded as "Guidance from
   answers" in `skills/review/tracking.md` describes.
3. **Hand it to intake.** Intake in the `building` skill sizes the item,
   applies the Follow-up row of its Scope table, sends the handoff, reads the
   report as "After each handoff" there describes, and commits.
4. **Close it** by what Intake gives back, the first that applies:
   - A commit: `backlog.py set <worktree> BL-4 done --ref <sha>`. For each line
     under the builder's `findings:`, add a note to that finding with the renderer's
     `--note N=<file>`, as the `review-triage` skill describes under Recording a
     decision: "<date>, after <sha> (a follow-up): <why>". Do not change its
     instruction or status; the next triage judges it against the commit.
   - Large, from Intake's sizing, or from a builder's `size: too big` on a
     work list of one item: Growing an item in the `building` skill
     marks it `backlog.py set <worktree> BL-4 in-progress --ref BRIEF-<n>`,
     and nothing more happens here; when the user says not to grow it,
     `backlog.py instruct <worktree> BL-4 Discuss --note "<the route they
     chose>"`.
   - In a work list of several items, any other stop: `backlog.py instruct
     <worktree> BL-4 Discuss --note "<reason>"`, the reason ending "; its edits
     were reverted" when Leftover edits in the `building` skill reverted any,
     and go on to the next item.
   - With one item, any other stop: the item stays open, with its edits kept
     or discarded as Leftover edits in the `building` skill describes.
5. Print one line ("BL-4 done in 1a2b3c4: shows the export error on failed
   downloads"), drop the item's detail, and move to the next.

If the user stops partway, the backlog is the record; the next invocation resumes
with whatever is still open.

## At the end

Say how many items were done with their commits, which were left open and why in
a few words each, any follow-ups added elsewhere, and any findings noted as
affected. There is no recheck lens for a follow-up; the next review of this
branch checks open and closed items through its completeness lens, and the next
triage checks the open findings against these commits. After saying so,
run a closing checkpoint, as "Closing checkpoint" in the `checkpoint` skill describes.

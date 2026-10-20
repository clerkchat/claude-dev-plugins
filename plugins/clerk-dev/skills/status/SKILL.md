---
name: status
description: Say where a worktree's work stands and what to do next, for its review and for the feature it belongs to. Use when the user asks "where are we at", "where are we", "where are we on the design", "are we ready to build", "where are we on <an area or piece>", "where are we on the implementation", "how far along is the build", "what's built", "what's the status", "what's left", "what's next", "status of the review", "status of the feature", "anything new", or similar about this branch's review, fixes, follow-ups, passes, or feature records. Reports implementation progress per spec (requirements done, partial, in progress, not started; pieces stopped on a question), new follow-ups (they arrive from other repositories at any time), passes in progress and their checks, open design questions, open items in specs, passes in other repositories, commits no review has read, staged changes, unmarked findings, the fix and discussion queues, and findings whose code moved, then the next steps.
allowed-tools: Bash(python3 *), Bash(git *), Read
---

# Where the work stands

When talking to the user, name ids and codes as "Naming things to the user" in `skills/review/tracking.md` describes: every id (R19, B15, M1, F3, Q3, P3, I7, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

If this conversation was compacted, re-read this file before going on: a
compacted skill may be cut short, and the steps it drops are the ones that
keep the work safe. Prefer `/clear` at a natural boundary to compaction; the
`checkpoint` skill writes down what is pending first.

Run, from the worktree:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/status.py <worktree> [--focus implementation|review]
```

Pick the focus from the question. About the building ("where are we on the
implementation", "how far along is the build", "what's built", "what's left to
build", "what's the next piece"): `--focus implementation`, which shows only
progress per spec, unlogged commits, passes, the questions and open items of
the specs being built, and building steps. About the design ("where are we on the
design", "are we ready to build", "what's unsettled", "what specs are
missing"): `--focus design`. About one area or piece ("where are we on the
harness", "on bisection", "on R52"): `--area <area>` or `--area R<n>`, with
the area name as the records use it (the script lists them when the name is
not one). About the review only ("status of the review", "what's left in the
review"): `--focus review`. Anything broader
("where are we", "what's next"): no focus, which shows everything.

Its output already glosses each id on its first mention (`records.py gloss`);
keep those glosses when you show or summarize it, and gloss any id you add.

It reads only files and git: the latest review run, `.clerk-dev/followups.md` and
`.clerk-dev/passes.md` and `.clerk-dev/build.md` here and in the other
worktrees of
`.clerk-dev/review-workspace.md`, the feature records and design checks in the
hub, and the commits since the review. It starts no agent and changes nothing except `.clerk-dev/status-seen`,
which remembers the follow-ups already shown so the next status can mark new
ones. Pass `--run <label>` when the user names a run.

Show its output as it is. Then add one or two sentences: which step to take
first and why, when the order is not obvious from the list. The order the script
gives follows the dependencies (a piece stopped on a question or not landed
first, then a pass in progress, then settle-first
design questions, then follow-ups and the cross-check before fixes,
since both can change what a fix should be; reviewing new commits before
marking, since a review adds findings to mark), so usually just confirm the
first step. Mention anything striking the list does not say, such as many staged
and unstaged files at once, or a follow-up whose source no longer exists.

Do not start any of the steps; the user picks one. Do not read the report, the
findings, or the diffs to embellish the summary.

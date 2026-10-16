---
name: review-status
description: Say where a worktree's work stands and what to do next, for its review and for the feature it belongs to. Use when the user asks "where are we at", "where are we", "what's the status", "what's left", "what's next", "status of the review", "status of the feature", "anything new", or similar about this branch's review, fixes, follow-ups, passes, or feature records. Reports new follow-ups (they arrive from other repositories at any time), passes in progress and their checks, open design questions, open items in specs, passes in other repositories, commits no review has read, staged changes, unmarked findings, the fix and discussion queues, and findings whose code moved, then the next steps.
allowed-tools: Bash(python3 *), Bash(git *), Read
---

# Where the work stands

Run, from the worktree:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/review-status.py <worktree>
```

It reads only files and git: the latest review run, `.clerk-dev/followups.md` and
`.clerk-dev/passes.md` here and in the other worktrees of
`.clerk-dev/review-workspace.md`, the feature records and design checks in the
hub, and the commits since the review. It starts no agent and changes nothing except `.clerk-dev/status-seen`,
which remembers the follow-ups already shown so the next status can mark new
ones. Pass `--run <label>` when the user names a run.

Show its output as it is. Then add one or two sentences: which step to take
first and why, when the order is not obvious from the list. The order the script
gives follows the dependencies (a pass in progress first, then settle-first
design questions, then follow-ups and the cross-check before fixes,
since both can change what a fix should be; reviewing new commits before
marking, since a review adds findings to mark), so usually just confirm the
first step. Mention anything striking the list does not say, such as many staged
and unstaged files at once, or a follow-up whose source no longer exists.

Do not start any of the steps; the user picks one. Do not read the report, the
findings, or the diffs to embellish the summary.

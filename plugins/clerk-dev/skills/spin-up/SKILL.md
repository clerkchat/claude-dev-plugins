---
name: spin-up
description: Walk the repository's backlog, take up one item or file a new one, and spin up a worktree off main for it with git worktree add, run the configured after-create command there, and seed it so the next session can start. Use when the user says "start on a backlog item", "spin up a worktree for BL-4", "take up BL-7", "what's in the backlog", "start new work off main", "spin up", or /clerk-dev:spin-up.
argument-hint: "[BL-4 | <repo>:BL-4 | <new work in a sentence>]"
allowed-tools: Bash(python3 *), Bash(git *), Read, Write, Edit
---

# Spinning up new work

When talking to the user, follow "Talking to the user" in `skills/review/tracking.md`: the feature first, the bookkeeping last or not at all, and ids named: every id (DEC-19, BUILD-15, MILE-1, BL-4, Q-3, PASS-3, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

If this conversation was compacted, re-read this file before going on: a
compacted skill may be cut short, and the steps it drops are the ones that
keep the work safe. Prefer `/clear` at a natural boundary to compaction; the
`checkpoint` skill writes down what is pending first.

Spin-up runs from any worktree of the repository, the main checkout or a
feature worktree, and creates the new worktree where the configured pattern
puts it; nothing links the two. The backlog is read and written only through
`${CLAUDE_PLUGIN_ROOT}/scripts/backlog.py`, and the worktree is created and
seeded only through `${CLAUDE_PLUGIN_ROOT}/scripts/spin-up.py`, which runs
plain `git worktree add`. Never create the worktree any other way, and never
name a user's own worktree tooling: whatever the user wants run in a new
worktree is the config's after-create command.

## Setup first

Find the per-user config: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/config.py path`
prints where it is read from. When that file does not exist, offer the
`clerk-dev:setup` skill's steps first, then carry on. When the user declines,
say in one line that spin-up goes on with the defaults: the new worktree at
`<repo parent>/<branch>`, no after-create command, and only this repository's
backlog.

## The walk

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/backlog.py list <worktree>` and
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/backlog.py check <worktree>`.
2. Show the open items in prose, grouped by kind (ideas, cleanups,
   follow-ups), each with its title, its scope (a branch, new work, or "from
   feat/x, branch gone"), its age from its `date`
   (`backlog.py show <worktree> BL-n`), and for a row another repository owns,
   "owned by api, also touches agent-swarm". Without the config, say in one
   line that items owned by other repositories are not shown.
3. For each item whose branch is gone, offer to rescope it to new work
   (`backlog.py rescope <worktree> BL-n new`) or drop it
   (`backlog.py set <worktree> BL-n dropped --ref "<reason>"`).
4. For each cleanup `check` found gone from main, offer to close it
   (`backlog.py set <worktree> BL-n done --ref "<what removed it>"`).
5. For each cleanup with only a trigger, ask whether the trigger has
   happened; on yes it is ready to take up.

## Taking or recording

The user names an item (`BL-4`, or `api:BL-4` for one another repository
owns) or describes new work. New work is filed before anything is created:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/backlog.py add <worktree> "<title>" --kind idea|cleanup|followup --scope new --from "this session" [--why .. --when ..] [--removes .. --trigger ..] [--origin ..] [--repo NAME]
```

with `--why` and `--when` for an idea, `--removes` and `--trigger` for a
cleanup, `--origin` for a follow-up, and `--repo` when another repository would
own the work. It prints the new id. The user may stop there, leaving the item
open for later.

## The branch and where it goes

1. Propose a branch name from the item's title: `feat/<slug>` for an idea or a
   follow-up, `chore/<slug>` for a cleanup, the slug lowercase with hyphens.
   The user confirms it or gives another.
2. Run
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/spin-up.py where <worktree> <branch> [--repo NAME]`,
   with `--repo` naming the owning repository for a `<repo>:BL-n` item. It
   prints the worktree's `path:`, its `base:` (the local main branch when there
   is one, else `origin/<main>`, with how far it is ahead or behind
   `origin/<main>` as of the last fetch), the `after-create:` command or
   "none", and the `repo:`. Show these before creating. When it refuses
   because the branch or the path exists, ask for another name.

## Creating

Run
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/spin-up.py create <worktree> <branch> --item BL-n|<repo>:BL-n`.
It refuses in one line, creating nothing, when the branch exists (here or on
origin), the path exists, the item is not open, or an item from another
repository has no config row. Otherwise it creates the worktree off the base,
runs the after-create command there with its output shown, and seeds it:

- every item: `.clerk-dev/` excluded from git, and the branch notes with a
  Purpose drafted from the item and an empty Guidance;
- an idea: the feature, named for the item, and its first brainstorm with the
  item as its context; the item is marked adopted by that brainstorm;
- a follow-up or cleanup: no feature and no record; the item is rescoped to
  the new branch and stays owed.

It prints `worktree:`, `branch:`, `base:`, the `after-create:` result, then one
line per seeded file or backlog change. When the after-create command failed,
seeding still went on: say so in one line, with the command to rerun in the
new worktree. Do not draft or rewrite the Purpose here; the user edits it in
the new worktree.

## Closing

Give the "Where the work sits" header (`skills/review/tracking.md`) for the new
worktree: the feature's name (for owed work, the item's title), the
repository, and the branch. Then the worktree's path, and the next step in
plain words: open a new session in that path, and there brainstorm the idea,
or build the follow-up or cleanup, which the `building` skill's intake takes
up and marks in progress.

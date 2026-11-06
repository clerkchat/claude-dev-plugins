---
name: setup
description: Set up or rescan the per-user clerk-dev config, ~/.claude/clerk-dev/local.md, which lists the search roots, the repositories (name, main checkout, main branch), and the worktree path pattern that cross-repository work needs. Use when the user says "set up the config", "set up clerk-dev", "rescan the config", or similar, and when another skill finds the config missing (spin-up, filing into another repository's backlog, setting up a review workspace across repositories). Proposes the file from a scan of git, shows it, and writes it once the user confirms.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/config-setup.py *), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/config.py *), Read, Edit
---

# Setting up the config

The config is `~/.claude/clerk-dev/local.md` (`config.py path` prints where it
is read from). It is optional: without it the plugin works in the current
repository only. Filing into another repository's backlog, listing across
repositories, setting up a review workspace across repositories, and spin-up
need it, and say so with this line when it is missing:

```
No clerk-dev config at <path>; run the config setup to reach other repositories.
```

A caller that gets that line, or finds the file missing before it starts, runs
the steps below and then carries on with the request that needed the config.

A headless session never asks: it stops and prints, as its last line, that the
config has to be set up in an interactive session first.

## Steps

1. Offer, in one line: cross-repository work needs
   `~/.claude/clerk-dev/local.md`, and a scan of the repositories near this one
   can propose it. When the user says no, carry on in this repository only.
2. On yes, ask whether to also scan other directories, or register
   repositories by a path anywhere inside them. Never offer the home directory
   itself; the script refuses it.
3. Run
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/config-setup.py scan <worktree> [--root DIR ...] [--path DIR ...] --out <proposal>`,
   with `<proposal>` a new file in the system's temporary directory. Its first
   line is the proposal's path; each line after it is a note: a repository with
   no `origin/HEAD`, a name taken from `workspace.md` over another, worktrees
   that do not follow the pattern, a root it also proposed, a repository new
   since the last scan, a registered checkout that is gone.
4. Read the proposal and show it with its notes. Settle each note with the
   user: fill in an empty `Main branch`, pick the pattern when the worktree
   paths disagree. The `After create:` line is left empty unless the user
   gives a command to run in each new worktree.
5. Apply what the user changes to the proposal with Edit, show it again when
   the changes were more than one line, and confirm.
6. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/config-setup.py write <proposal>`.
   It refuses in one line when the file does not parse or a main checkout does
   not exist; fix that with the user and run it again. On success it prints
   the config's path: say it in one line.
7. Carry on with the request that needed the config.

## Rescanning

"Rescan the config" runs the same steps. The scan reads the existing config
first and keeps everything in it as the user left it; it only appends new
search roots and repositories, each noted, and notes registered checkouts that
no longer exist. Ask before removing a row for a checkout that is gone.

## The format

```markdown
# clerk-dev config

Proposed 2026-11-06 from /Users/me/src/api/feat/exports. Edit freely.

## Search roots

- /Users/me/src/api
- /Users/me/src

## Repositories

| Name | Main checkout            | Main branch |
| ---- | ------------------------ | ----------- |
| api  | /Users/me/src/api/main   | main        |
| web  | /Users/me/src/web/main   | master      |

## Worktrees

Pattern: <repo parent>/<branch>
After create:
```

- `Search roots`: directories the scan walks, three levels down, for
  repositories.
- `Repositories`: one row per repository. `Main checkout` is the directory
  holding its git common dir; `Main branch` is `origin/HEAD` without `origin/`.
- `Pattern:` where a new worktree goes, with the placeholders `<repo parent>`
  (the main checkout's parent), `<repo>` (the repository's name), and
  `<branch>`.
- `After create:` an optional command run in each new worktree.

The scan reads only git, `.clerk-dev/workspace.md` tables, and the existing
config; it never reads CLAUDE.md or other prose.

# Review workspace

A review job that spans repositories is described by one file,
`review-workspace.md`. It says which repositories take part and which worktree
of each holds the feature. It is the only record of that: nothing is inferred
from directory layout or branch names.

## Where it lives

The file is created in the worktree where the job was set up, at
`<worktree>/.review/review-workspace.md`. Every other worktree in its table gets
a symbolic link at the same path pointing at it, so a session in any of those
worktrees reads the same file at `.review/review-workspace.md`. Like everything
under `.review/`, it is excluded from git through each repository's
`.git/info/exclude`.

A worktree belongs to at most one review job. A worktree without the file is not
part of a review job across repositories.

## Format

```markdown
# Review workspace: report exports

Set up 2026-10-14 from /Users/me/src/api-exports. Edit freely.

| Repo   | Worktree                     | Main        |
| ------ | ---------------------------- | ----------- |
| api    | /Users/me/src/api-exports    | origin/main |
| web    | /Users/me/src/web-exports    |             |
| worker | /Users/me/src/worker-exports |             |
```

- `Repo`: the short name used in reports, follow-up `From:` lines, and finding
  references ("api 8").
- `Worktree`: absolute path of the worktree that holds this job's branch.
- `Main`: optional, the remote main branch to compare against. Empty means
  that repository's `origin/HEAD`; when that is missing, run
  `git remote set-head origin --auto` there or fill in this column.

Reading it: the row whose `Worktree` is the current worktree (compare real
paths) is this repository, and the other rows are the related worktrees. A row
whose path no longer exists is reported in one line and skipped.

## Setting it up

Feature mode (`--feature`) needs the file. When the current worktree has none,
set it up with the user before anything else. A headless session never asks: it
stops and prints, as its last line, that the review workspace has to be set up
in an interactive session first.

1. Name this repository. Propose the last path segment of
   `git remote get-url origin` without `.git`, or else the directory name of
   the main checkout (the parent of
   `git rev-parse --path-format=absolute --git-common-dir`).
2. Ask which other repositories take part. Offer as choices the git
   repositories next to this repository's main checkout, and let the user give
   any other path. A path anywhere in a repository will do; the worktree comes
   next.
3. For each one, list its worktrees with
   `git -C <path> worktree list --porcelain` and ask which holds this job,
   listing worktrees on the same branch name as this one first. The user can
   also name a path or leave that repository out.
4. Ask for a short name for the job, proposing the branch name.
5. Show the table, and on confirmation write the file here. Then, for every
   other worktree in it, create `.review/` (and its `.git/info/exclude` entry
   when needed) and link the file:
   `ln -s <this file> <worktree>/.review/review-workspace.md`. If a worktree
   already has a `review-workspace.md` for another job, say so and ask whether
   to replace it; never replace it silently. Say in one line where the file is.

To change the job later, the user edits the file. To add a repository, add a
row and create its link; do both when the user asks.

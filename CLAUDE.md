# claude-dev-plugins

## Versioning

Every merge into `main` bumps the plugin version. Before merging a branch, run
`scripts/bump-version.py <patch|minor|major>` on it and commit the result:
patch for fixes, minor for new behavior, major for a change that breaks run
directories, record formats, or what a skill expects from another. The
checked-in `.githooks/pre-merge-commit` hook refuses a merge on `main` that
does not raise the version; enable it once per clone with
`git config core.hooksPath .githooks`.

## The live plugin

The main checkout is the installed plugin. Build features in worktrees; nothing
is live until it is merged into `main`.

## Tests

Run `python3 -m unittest discover tests -q` from the repository root. The
scripts and tests use the Python standard library only. A single module needs
`PYTHONPATH=tests`, for example
`PYTHONPATH=tests python3 -m unittest tests.test_post_review -q`. Tests never
write to the repository's own files; copy what they change into a temporary
directory.

## Skills and scripts

Skills, agents, and lens files are prompts: change a skill's behavior by
editing its text. File formats under a run or `.clerk-dev/` are read and
written only through `plugins/clerk-dev/scripts/`, which are their single
source.

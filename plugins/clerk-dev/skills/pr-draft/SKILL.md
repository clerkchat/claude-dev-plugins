---
name: pr-draft
description: Draft the pull request description of a large change at the end of a deployable unit of work, one description per repository in the unit, written to .clerk-dev/pr-description.md for the user to post. Use only when the user asks for it: "draft the PR description", "write the PR description", "write the PR descriptions for the feature", "describe this PR", or /clerk-dev:pr-draft. Never run it from another skill or at the end of a build. Meant for large PRs, where a walkthrough ordered by the change's main flow pays off. It never creates, edits, posts, or previews a pull request.
argument-hint: "[--base <branch>] [<repo>...]"
allowed-tools: Bash(git *), Bash(gh pr view *), Bash(python3 *), Read, Write, Grep, Glob, Agent
---

# Pull request descriptions

When talking to the user, follow "Talking to the user" in `skills/review/tracking.md`: the feature first, the bookkeeping last or not at all, and ids named: every id (DEC-19, BUILD-15, MILE-1, F3, Q-3, PASS-3, IDEA-7, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

If this conversation was compacted, re-read this file before going on: a
compacted skill may be cut short, and the steps it drops are the ones that
keep the work safe. Prefer `/clear` at a natural boundary to compaction; the
`checkpoint` skill writes down what is pending first.

This skill writes, for each repository of a unit of work, the description a
reviewer reads first: what the change adds, what the base lacks, and a
walkthrough of the diff in the order a reviewer follows it. It gathers and
checks; `style.md` next to this file says how the draft looks, with a worked
example. Read `style.md` before writing anything and follow it. It is the one
style for every user: when the user asks for something different, change their
draft as asked, and keep no rule from it for other drafts.

The scripts below are in `${CLAUDE_PLUGIN_ROOT}/scripts/`.

## 1. The repositories

The unit is every row of `.clerk-dev/review-workspace.md` (read as
`skills/review/workspace-manifest.md` says), or only this worktree when there
is no workspace. `<repo>` arguments narrow it to those rows. A row whose
worktree is missing gets one line in the report and is skipped.

Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/preflight.py <worktree>...` once
for all of them: branch, HEAD, remote main, merge base, commits, diff stat,
branch notes, workspace rows, open follow-ups, and the latest review run.

## 2. The base

The base is the branch the pull request merges into, per repository:

1. the user's answer or `--base`;
2. else the open pull request's base: `gh pr view <branch> -R <owner>/<repo>
   --json number,url,baseRefName,body` (owner and repo from `git -C <worktree>
   remote get-url origin`), skipped silently when `gh` is missing or finds no
   pull request. Keep its number, link, and body for later steps;
3. else the branch this one was cut from. The default is the workspace row's
   `Main`, else `origin/HEAD`. Take the first commit after the merge base with
   the default (`git rev-list --first-parent --reverse <merge base>..HEAD`)
   and list the remote branches that hold it (`git for-each-ref
   --format='%(refname:short)' --contains <that commit> refs/remotes`),
   leaving out `origin/HEAD`, this branch's own remote branch, and any branch
   whose merge base with HEAD is HEAD itself (branches stacked on this one).
   Of those and the default, the base is the one whose merge base with HEAD
   has the fewest commits after it (`git rev-list --count <its merge
   base>..HEAD`); ties go to the default. With no default and no candidate,
   ask.

The base is always the remote-tracking ref (`origin/<base>`), never a local
branch; never fetch. When the ref does not exist here, say so and ask the user
to fetch it. An inferred base is used without asking and stated in one line of
the report, so a wrong guess is caught. The diff is `git diff
origin/<base>...HEAD`, from the merge base. The comparison label is the base's
name without the remote: **On master:**, **On feat/x:**.

A repository with no commits after its base gets one line in the report and no
draft.

## 3. Gather

For each repository, read:

- the full commit messages: `git log --format='%h %s%n%b'
  origin/<base>..HEAD`;
- `git diff --stat origin/<base>...HEAD`, then the diff itself, in full (by
  the stage writers of step 6 when the diff is large);
- why the change exists: the branch notes' Purpose, the feature's active
  records (`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/records.py list <worktree>
  --active`, then the briefs, decisions, and designs that bear on this
  repository), the open items in briefs (`records.py digest <worktree>`), and
  the open items in `.clerk-dev/deferred.md` and `.clerk-dev/followups.md`;
  these become **Not yet** and Open for review lines;
- the latest review's deferred and discussed findings
  (`.clerk-dev/latest/report.md`), for Open for review;
- the pull request's current body, when there is one, and an earlier
  `.clerk-dev/pr-description.md`, when there is one: the author's own
  statement, to build on where it still holds;
- the review's state: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/status.py
  <worktree> --focus review --no-mark`. Findings open in Fix before merging,
  or commits no review has read (no review at all included), do not stop the
  draft: they get a one-line warning in the report.

Everything is translated into what the change does: nothing in the draft cites
where it came from.

## 4. The template

Look where GitHub does, with one call:

```
git -C <worktree> ls-files ':(icase)pull_request_template.md' ':(icase).github/pull_request_template.md' ':(icase)docs/pull_request_template.md' ':(icase)pull_request_template/*.md' ':(icase).github/pull_request_template/*.md' ':(icase)docs/pull_request_template/*.md'
```

A single `pull_request_template.md` is the template. With none, a
`PULL_REQUEST_TEMPLATE/` directory with one file is the template, and with
several, ask the user which. With no template at all, use the default in
`style.md`. A template's headings, checkboxes, and order are kept and filled
as `style.md` says.

## 5. The spine

Before writing, find the spine: the flow a reviewer follows to understand the
diff (a run's layers, a request's path, a record's lifecycle). Name it in one
sentence, list its stages in order, and assign the diff's files to stages;
what no stage covers is glue, for the **Support** line.

Each stage's size comes from `git diff --numstat origin/<base>...HEAD --
<files>`: the lines added outside tests, fixtures, factories, and test-only
helpers, rounded as `style.md` says. A file in several stages is split evenly
between them. Prep commits are not subtracted.

Classify the commits by kind (prep, live, new, tests, breaking), from a marker
in the message when it has one, else from the diff: extractions and renames
the rest builds on are prep; a change to code that runs on the base, behavior
unchanged, is live; a commit that only adds code nothing on the base calls is
new; tests only is tests; removing or changing a route, field, table, or check
callers rely on is breaking. A mixed commit goes under its riskiest kind,
breaking first, then live, new, prep, tests.

A change that needs no spine (a fix in one place, a dependency bump, a few
small edits) gets a short description: the Description and the template
sections, no walkthrough.

## 6. Write the draft

The walkthrough comes first, then what is built from it.

**Stages.** A diff is large when its non-test lines run past about 1k or the
spine has more than three stages. A large diff is drafted with subagents from
the start: launch one `general-purpose` subagent per stage (a few small stages
may share one), all in one message, with `model: opus`. Give each:

- the worktree, `origin/<base>`, and the comparison label;
- the spine sentence, the full stage list (so it knows its neighbors), its
  stage, and its files;
- the open items that bear on its stage, already in reviewer language;
- the path of `style.md`, to write its section exactly as "Stages" there says;
- these rules: read its files' diff in full; check every **On `<base>`** line
  against the base before writing it (`git show origin/<base>:<path>`, `git
  grep <pattern> origin/<base>`), and leave out a claim it cannot check,
  returning it as a question; no internal ids (records, findings, follow-ups,
  passes, handoffs), no local tooling, no placeholders, and no code comments
  in any code it quotes or writes; write no file.

Each returns its stage section, its row of the overview table (stage,
enables, on the base, here, each a short phrase), and the claims it left out.
For a smaller diff, write the stages yourself the same way, checking each
**On `<base>`** line before writing it.

**The rest.** From the stages, write the overview table and the spine diagram
(three or more stages), the Description with its Commits summary and the
sections that apply, and the template sections last. Then check that they
agree: the table, the diagram, and the sections name the same stages in the
same order; the Commits counts add up to the branch's commits; no **Not yet**
contradicts another stage's **Here**; every size is rounded. Any claim in the
Description about the base is checked like the stages' are.

## 7. Several repositories

Draft each repository in its own worktree with its own base, then make one
pass over all the drafts:

- each names its sibling pull requests: number and link when `gh pr view`
  finds one in that worktree, else the branch name;
- each deployment section states the deploy order and what depends on what,
  in the same words in every description. The order comes from the records
  and follow-ups that state a contract dependency; when none does, ask;
- the same thing has the same name in every draft.

## 8. Write the file

Write each draft to `<worktree>/.clerk-dev/pr-description.md`, replacing an
earlier one, as plain Markdown with no hard wrapping and no render step. When
`git -C <worktree> check-ignore -q .clerk-dev` fails, add a `.clerk-dev/` line
to the `info/exclude` file under `git -C <worktree> rev-parse
--git-common-dir`, keeping its other lines, and say so once.

The only `gh` use is `gh pr view`: never create, edit, comment on, or post a
pull request, and never preview the draft. The user previews it with their own
tools and posts the title and body into GitHub's two fields.

## 9. Report

Per repository, in a few lines:

- the draft's absolute path and its title;
- the base, in one line ("Base: origin/master, the default branch");
- the spine's stages, in one line;
- the claims that could not be checked and the sections that could not be
  filled, if any;
- the warning from step 3, if any, in one line.

Then the rows skipped, one line each. No id is left bare.

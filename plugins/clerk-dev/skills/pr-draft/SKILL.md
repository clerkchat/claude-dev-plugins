---
name: pr-draft
description: Draft, refine, and post the pull request descriptions of a large change at the end of a deployable unit of work, one per repository in the unit. Drafts go to .clerk-dev/pr-description.md; refinements are made in place and logged as notes that later drafts follow; posting pushes the branches, creates the pull requests, and links the siblings to each other. Use only when the user asks for it: "draft the PR description", "write the PR descriptions for the feature", "describe this PR", "in the PR draft, ...", "refine the PR description", "post the PRs", "open the pull requests", or /clerk-dev:pr-draft. Never run it from another skill or at the end of a build, and never post without the user asking to post. Meant for large PRs, where a walkthrough ordered by the change's main flow pays off.
argument-hint: "[--base <branch>] [<repo>...]"
allowed-tools: Bash(git *), Bash(gh pr view *), Bash(gh pr create *), Bash(gh pr edit *), Bash(python3 *), Read, Write, Edit, Grep, Glob, Agent
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
example. Read `style.md` before writing anything and follow it.

A first draft is rarely the last. The skill has three modes, picked from what
the user asks:

- **Draft** (steps 1 to 9): write the descriptions, or write them again.
- **Refine** (step 10): change a draft as the user asks, and log each change
  as a note, so a later draft keeps it.
- **Post** (step 11): only when the user asks to post. Push the branches,
  create the pull requests, and link the siblings to each other.

The scripts below are in `${CLAUDE_PLUGIN_ROOT}/scripts/`.

## 1. The repositories

The unit is every row of `.clerk-dev/workspace.md` (read as
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
origin/<base>...HEAD`, from the merge base.

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
  these become Left out on purpose items. Keep what a reviewer would weigh
  before merging: wrong behavior and undecided design. Gaps (what the change
  does not cover yet) stay out of the draft; they go in the report, for the
  user to add while refining. A bug is kept only when a reviewer could hit it by using
  the feature. Leave out process items (where the branch lands, review
  order), internal cleanup nits, import and module layout, items another
  repository has since fixed, and bugs in code the change does not touch
  unless the change leans on it. An item the records have since settled is
  dropped; a decided choice may still be described in the stage it shaped,
  but not as open;
- the latest review's deferred and discussed findings
  (`.clerk-dev/latest/report.md`), for Left out on purpose; with no report
  there (a review planned but not run), there are none, and step 3's review
  warning covers it;
- the pull request's current body, when there is one, and an earlier
  `.clerk-dev/pr-description.md`, when there is one: the author's own
  statement, to build on where it still holds;
- the draft notes, `.clerk-dev/pr-draft-notes.md` (step 10), when there are
  any: every note for this repository is a rule for this draft, and every
  open note for this pull request is an edit it keeps;
- the review's state: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/status.py
  <worktree> --focus review --no-mark`. Findings open in Fix before merging,
  or commits no review has read (no review at all included), do not stop the
  draft: they get a one-line warning in the report.

Everything is translated into what the change does: nothing in the draft cites
where it came from.

When re-drafting, keep the user's edits. They are the differences between
`.clerk-dev/pr-description.md` and `.clerk-dev/pr-description.generated.md`,
the copy of what the skill last wrote (step 8), together with the open notes
for this pull request. Carry each into the new draft unless the code has
changed under it, and then say so in the report. Re-read the open items:
drop the ones settled since, and any subsection left empty.

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
sentence, list its stages in order, and assign the diff's files to stages.
Files of code the base already runs, outside the new feature's own code, go to
one last stage for those changes, as `style.md` says, not to the flow stages
that use them. On a stacked base, the feature is the code the unit's
branches build (all of them, the base's share included), and only code the
default branch already has goes to that last stage.
Then list the non-test files no stage holds (`git diff --name-only`, less the
assigned ones): each goes to a stage that uses it, else to "Other files,
outside any stage". Do this before launching any writer, so no shared file
falls between stages. A file is test-only when its name marks it so (`*.test.*`,
`*.spec.*`, `__tests__/`, fixtures, factories) or nothing outside tests imports
it; test-only files are assigned to no stage and counted in no size.

Each stage's size comes from `git diff --numstat origin/<base>...HEAD --
<files>`: the lines added outside tests, fixtures, factories, and test-only
helpers, rounded as `style.md` says. A file in several stages is split evenly
between them. Prep commits are not subtracted.

Sort the commits into the groups of `style.md`'s Overview of commits by their
types, as `skills/review/commits.md` maps them (prep to refactors, live to
changes to deployed code, new, tooling, tests, docs, and `!` to break). A
commit with no type is sorted from its diff: extractions and renames the rest
builds on are refactors; a change to how code that runs on the base behaves
is a change to deployed code; a commit that only adds code nothing on the base
calls is new; pipeline and housekeeping changes are tooling; tests only is
tests; docs only is docs; removing or changing a route, field, table, or check
callers rely on is a break. A mixed commit goes under its riskiest group, in
the order `commits.md` gives. A type is a claim, not proof: when a stage
writer finds that a commit typed refactor or chore changes behavior, the
commit moves to changes to deployed code. Note whether the branch's subjects
carry types, for the Conventions subsection. On a stacked base, changes to
deployed code and changes to code on the base are separate groups and may
both appear.

A change that needs no spine (a fix in one place, a dependency bump, a few
small edits, or a repository of a few hundred non-test lines in a larger
unit) gets a short description, no walkthrough, as `style.md` says.

## 6. Write the draft

The walkthrough comes first, then what is built from it.

**Stages.** A diff is large when its non-test lines run past about 1k or the
spine has more than three stages. A large diff is drafted with subagents from
the start: launch one `general-purpose` subagent per stage (a few small stages
may share one), all in one message, with `model: opus`. In a unit of several
repositories, a repository whose diff is not large gets one subagent that
writes its whole draft, launched in the same message. Write what every writer
shares (the spine, the stage list with each stage's files, the core terms,
and the stage that owns each request and response type) to one brief in the scratchpad, and give each writer
its path and its stage. Give each stage writer:

- the worktree and `origin/<base>`;
- the spine, the full stage list (so it knows its neighbors), its stage, and
  its files;
- the core terms the Description defines, in the words it will use, and the
  coined terms other stages define, so it links rather than redefines;
- the open items that bear on its stage, already in reviewer language;
- the notes for this repository and the open notes for this pull request
  that bear on its stage (step 10);
- the path of `style.md`, to write its section exactly as "Stages" and
  "Words" there say;
- these rules: read its files' diff in full; check every Before cell against
  the base before writing it (`git show origin/<base>:<path>`, `git grep
  <pattern> origin/<base>`), and a claim about another service's behavior in
  that service's repository when it is checked out locally; leave out a claim
  it cannot check, returning it as a question; grep the base for each term it
  leans on, and define at first use any the branch coins; write no open items
  in its section and no line for files outside its stage; no internal ids
  (records, findings, follow-ups, passes, handoffs), no local tooling, no
  placeholders, and no code comments in any code it quotes or writes; write
  no file.

Each returns its stage section; its row of the contents table (section, what
changes); its open items, each sorted as a known bug, a gap, or a design
question (gaps go to the report, not the draft); the commits whose marker disagrees with what they do; capabilities
a reviewer would ask "what can it do?" about, with where it put them; and the
claims it left out; and the request and response fields its files add,
remove, or rename, with the routes that carry them, for the types its stage
owns. A field is owned by the stage whose files define its request or
response type; other stages link to it rather than describe it again. For a smaller diff, write
the stages yourself the same way. An open item two writers report links to
the stage whose code has it.

**The rest.** From the stages, write the Walkthrough's intro, diagram, and
contents table; the Other files table; Left out on purpose, from every
stage's open items; the Description with its Overview of commits and the
sections that apply; and the template sections last. Then check that they
agree: the table, the diagram, and the sections name the same stages in the
same order, and every anchor link resolves to a heading; each capability
reviewers would ask about has one home, and a built one is not phrased as a
design question; no open item contradicts a stage's After; every size is
rounded. Any claim in the Description about the base is checked like the
stages' are.

Two checks are written out, not only made, and their lists go in the report
(step 9):

- **Behavior changes.** Each commit or change Overview of commits lists under
  changes to deployed code or to code on the base, with the stage and the
  Before/After row that holds it. A change with no row gets one, and a row
  with no entry in Overview of commits gets one there.
- **Fields.** Each request and response field the writers returned, with the
  Client-facing table and row that holds it. A field with no row gets one;
  a removed field's row names what replaces it.

## 7. Several repositories

Draft each repository in its own worktree with its own base, then make one
pass over all the drafts:

- each names its sibling pull requests as a bullet list, one per repository,
  with what each holds: number and link when `gh pr view` finds one in that
  worktree, else the branch name;
- each defines the shared core terms in the same words;
- a known bug is listed in the draft of the repository whose code has it,
  not repeated in its siblings';
- each deployment section states the deploy order and what depends on what,
  in the same words in every description. The order comes from the records
  and follow-ups that state a contract dependency; when none does, ask;
- the same thing has the same name in every draft.

Drafts name siblings by branch. Posting (step 11) replaces each with its pull
request's number and link.

## 8. Write the file

Write each draft to `<worktree>/.clerk-dev/pr-description.md`, replacing an
earlier one, as plain Markdown with no hard wrapping and no render step, and
the same text to `<worktree>/.clerk-dev/pr-description.generated.md`, the
record of what the skill wrote, against which step 3 finds the user's edits. When
`git -C <worktree> check-ignore -q .clerk-dev` fails, add a `.clerk-dev/` line
to the `info/exclude` file under `git -C <worktree> rev-parse
--git-common-dir`, keeping its other lines, and say so once.

Drafting and refining use only `gh pr view`, and never preview the draft:
the user previews it with their own tools. Only step 11 creates or edits a
pull request.

## 9. Report

Per repository, in a few lines:

- the draft's absolute path and its title;
- the base, in one line ("Base: origin/master, the default branch");
- the spine's stages, in one line;
- the claims that could not be checked and the sections that could not be
  filled, if any;
- the warning from step 3, if any, in one line;
- the Testing question: what was actually run (commands, manual or
  end-to-end checks), since the draft can only list the test files;
- the two checks of step 6, as lists, with what was added to make them hold;
- the user's edits and open notes carried over, and any that no longer fit
  the code.

Then the gaps the writers and records found, one line each, for the user to
pick from while refining; then the rows skipped, one line each, and the next
step: refine the draft, or
ask to post the pull requests, which also links them to each other. No id is
left bare.

## 10. Refine

When the user asks for a change to a draft ("in the PR draft, define pin
earlier", "drop that section"), make it in `.clerk-dev/pr-description.md` of
the repositories it concerns, and in their siblings when the change is to
something every draft shares (a core term, the deploy order). Then log it in
`.clerk-dev/pr-draft-notes.md` of each repository changed, one entry per
change:

```
## N. <what changed, in a few words>

- Scope: pr | repo | plugin
- Change: <what was changed, before and after in short>
- Why: <the user's reason, in their words where they gave one>
- Rule: <the rule it suggests, for repo and plugin scope>
- Status: open | folded | dropped
```

The scope says where the change applies, proposed by the skill in one line
for the user to correct:

- **pr**: this pull request only; a later draft keeps the edit, and no rule
  is drawn.
- **repo**: a rule for every draft in this repository ("this repository's
  Testing section is left empty"). It stays open, and every later draft here
  follows it.
- **plugin**: a rule that would help any team. It is followed here like a
  repo note, and is open for whoever maintains the plugin to fold into
  `style.md`; mark it folded once they have.

A note whose change a re-draft can no longer carry (the code moved) is marked
dropped, with why. A change the user makes by hand needs no note: step 3
finds it by comparing the files.

## 11. Post

Only when the user asks to post ("post the PRs", "open the pull requests"),
for every repository of the unit that has a draft:

1. **Ask how to post**, unless the request said: as draft pull requests or
   ready for review, the same for all of them unless the user splits them.
2. **Push.** For each branch with no remote branch, or with commits its remote
   branch lacks: `git -C <worktree> push -u origin <branch>`, never with
   force. If any push is rejected, stop before creating any pull request, and
   say which branch and why.
3. **Create.** For each repository with no open pull request for the branch
   (`gh pr view`): the title is the draft's Title section; the body is
   everything after it, written to `.clerk-dev/pr-body.md` with soft wraps
   joined: an editor or formatter may have hard-wrapped the draft, and GitHub
   shows every newline in a body as a line break. Join each paragraph's and
   each list item's continuation lines into one line, and leave code blocks,
   tables, headings, and `<details>` tags as they are. Run `gh pr create
   -R <owner>/<repo> --base <base> --head <branch> --title "<title>"
   --body-file <worktree>/.clerk-dev/pr-body.md`, adding `--draft` for a
   draft. Owner and repo come from `git -C <worktree> remote get-url origin`,
   without the host, any leading `/` or `:`, and a trailing `.git`. A
   repository that already has an open pull request keeps its body; only step
   4 touches it.
4. **Link.** Once every pull request exists, for each one: read its body with
   `gh pr view --json body`, since the user may have edited it on GitHub;
   replace each sibling's branch name in the sibling list with its number and
   link (`[#123](<url>)`), changing nothing else; and save it with `gh pr edit
   <number> -R <owner>/<repo> --body-file <worktree>/.clerk-dev/pr-body.md`.
   Write the same body back to `.clerk-dev/pr-description.md`, under its
   Title section, and to `pr-description.generated.md`.
5. **Report**: each pull request's number, link, and whether it is a draft,
   and any repository not posted with why. A single repository has no
   sibling list, and step 4 is skipped.

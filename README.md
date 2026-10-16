# Clerk dev plugins

A Claude Code plugin marketplace with Clerk AI's development plugins.

| Plugin                          | What it does                                                             |
| ------------------------------- | ------------------------------------------------------------------------ |
| [Code reviewer](#code-reviewer) | Multi-focus code review of a branch, or of a feature across repositories |

## Getting started

You need access to the `clerkchat/claude-dev-plugins` repository on GitHub;
Claude Code uses your existing git credentials (SSH key or `gh auth login`). Add
the marketplace once:

```
/plugin marketplace add clerkchat/claude-dev-plugins
```

Then install the plugins you want, as each section below shows, or run `/plugin`
to browse them. Plugins are active as soon as they are installed; no restart is
needed. Updates arrive in the background, and `/reload-plugins` picks them up in
a running session.

From a shell, the same steps are:

```
claude plugin marketplace add clerkchat/claude-dev-plugins
claude plugin install <plugin>@clerk-dev
```

## Plugins

### Code reviewer

A multi-focus code review for Claude Code. It reviews your branch the way a
senior reviewer would, looking at multiple concerns (security, tenant isolation,
rollout, edge cases, tests, tech debt, and more), and writes a report you can
work through: fix findings one at a time, discuss the ones that need a decision,
and keep track of what is done. It can also review a feature that spans several
repositories at once, and keeps track of the work one repository owes another.

```
/plugin install clerk-dev@clerk-dev
```

It needs `git` and `python3`. The GitHub CLI (`gh`) is optional: when it is
installed and signed in, reviews also read the pull request's description and
its review comments.

#### How it works

A review splits the work among many small agents, and each job goes to the
cheapest model that does it well: Haiku for sizing up the change and matching
findings, Sonnet for checklist-style reviews and for double-checking minor
findings. The jobs that need careful reasoning get stronger models and more
thinking: Opus for security, concurrency, rollout, and the other reviews where a
missed problem is costly, and for double-checking major findings; Fable, when
your account has it, for the few calls that matter most, such as confirming a
blocker. Each reviewer reads only the part of the change it needs, and a
re-review reads only what changed since the last one.

Progress is always saved to files in the worktree, never only in the
conversation. You can `/clear` at any point to free up context, then ask again
("where are we?", "triage the review findings") and it picks up where it left
off.

#### A typical review

You talk to it in plain words, in your branch's worktree.

**1. Start a review.**

> Review the branch.

The first time, it gets a few things straight before any reviewer runs:

- Whether to review just this repository or the whole feature across
  repositories. For a feature, it asks which repositories and worktrees take
  part, and remembers the answer.
- What the branch is for. It drafts a short statement from the pull request
  description and the commits, saved in `.clerk-dev/branch-notes.md`, and asks you
  to correct it. This is what tells the reviewer agents which code is new and
  which is already live, so it is worth a minute.

Then it shows the plan, with an estimate of how long it takes, and starts when
you say go. You can keep working; it reports progress as it goes.

Other ways to start:

> Review the staged changes.
>
> Review my last commit.
>
> Do a quick review of the branch.
>
> Review the whole feature.
>
> Review the branch without tech debt.

**2. Read the report.** It opens with a summary and a table of every finding,
then one card per finding, grouped by what to do about it:

- **Fix before merging**: problems this branch introduced that should not ship.
- **Worth a look**: real but less pressing.
- **Already on main**: problems the branch did not cause. The recommendation is
  to fix them in a separate pull request, but you can override this by marking
  it "Fix as noted: fix now" (see below).
- **Cleanup and refactoring**: ways to make the touched code smaller and easier
  to change, labeled cleanup, simplify, or refactor.

Each card says how big the fix is and whether another repository has to change
too, if the change is made. The report lives at `.clerk-dev/latest/report.md`.

**3. Decide what to do.** Tick an instruction on each card in the report: Fix as
recommended, Fix as noted (write your notes on the card), Discuss, Defer, or
Ignore. Then:

> Triage the review findings.

It fixes every finding marked for fixing, one at a time, each in its own commit,
after running the tests for the code it touched, and checks that each fix
worked. Then it walks you through the ones you marked Discuss.

Or act on single findings directly:

> Fix finding 3.
>
> Fix 4 and 7 as recommended.
>
> Fix 5, but keep the old parameter name.
>
> Let's discuss finding 12.

Fixes are committed for you, one commit per finding. Nothing is ever pushed.

**4. Ask what's next.**

> What's next?

It checks where things stand in this worktree and lists the next steps in the
order to take them: follow-ups another repository left for this one, findings
still to decide, fix, or discuss, and commits no review has read yet. Take the
first step by saying it ("go through the follow-ups", "triage the review
findings", "review my last commit"), then ask again.

For a feature that spans repositories, ask in a Claude Code session in each
repository's worktree. When a fix in one repository changes something another
relies on, the other repository's next steps include that follow-up.

**5. Before merging.**

> Do a final review pass.

Reads the whole branch fresh and reports only what would hold the merge, ending
with a pass or not-pass verdict.

This is how a good human reviewer behaves on the last round. After a few rounds
of review and fixes, they are trying to bring the review to a close, not looking
for new things to ask for. Every fresh review of a large change turns up
something: another naming nit, another possible refactor. A final pass sets
those aside. It only raises what would really hold the merge, such as a broken
path, a security hole, or a rollout that fails. It does not reopen decisions you
already made, like findings you declined or deferred. So the review can end.

#### The slash command

Everything above also works as a command: `/clerk-dev:review`, followed by a
target and options. Type it and use completion to see what it accepts.

The optional review context lives at `.claude/skills/review-context/SKILL.md` in
the repository. It is yours to edit and commit.

# Clerk dev plugins

A Claude Code plugin marketplace with Clerk AI's development plugins.

| Plugin                  | What it does                                                                                                         |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------- |
| [Clerk dev](#clerk-dev) | A feature's design records, design checks, focused writing passes, and multi-focus code review, across repositories |

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

### Clerk dev

Help through the whole life of a feature: keeping its design thinking as
records, checking a design before the code exists, writing the code in focused
passes, and reviewing it. The same set of focuses (security, tenant isolation,
rollout, edge cases, and the rest) drives all four: as questions about a
design, as what to do while writing, and as what to check in a review.

The review reads your branch the way a senior reviewer would and gives you a
report to work through. It can cover a feature that spans several repositories,
and keeps track of the work one repository owes another. The review is the most
mature part; the design records, design checks, and passes are a first draft,
being refined on real features.

```
/plugin install clerk-dev@clerk-dev
```

It needs `git` and `python3`. The GitHub CLI (`gh`) is optional: when it is
installed and signed in, reviews also read the pull request's description and
its review comments.

#### The cycle

You work through a feature in a conversation, in your branch's worktree. You
say what you want in plain words; it does the legwork, shows you what it found,
and asks you only for the decisions that are yours. You can join anywhere: a
small fix can go straight to building and review, a big feature starts by
thinking out loud.

```
  1. Think it through   "let's brainstorm X"          you talk, it keeps notes
       |
  2. Poke holes         "check the design"            it asks, you answer
       |
  3. Build              "build the plan"              it writes, you weigh in
       |
  4. Harden             "do an edge-cases pass"       one concern at a time
       |
  5. Review             "review the branch"           you mark, it fixes
       |
  6. Wrap up            "do a final review pass"      pass or not pass

  Any time:  "where are we?"   "help me decide"   "checkpoint"
```

1. **Think it through.** Talk the feature over as you would with a colleague.
   When something is settled, say "we decided" or "capture this", and it is
   written down with its reason. Good ideas that are not for now: "park that
   idea". Weeks later, "what did we decide about polling?" has an answer.
2. **Poke holes.** Before any code exists, "check the design" comes back with
   the questions a security, rollout, or scaling reviewer would ask, the
   important ones first. You go through them together; each answer is kept.
3. **Build.** Say which part to build. Code appears as small commits you can
   read, each with its tests run. When it hits a choice nobody made yet, it
   stops and asks you rather than guessing.
4. **Harden.** Go over the code one concern at a time ("what passes does this
   need?"), each ending with a short check of just that concern. Or ask to be
   guided and write it yourself.
5. **Review.** "Review the branch" gives you a report to read, one card per
   finding. You tick what to do with each (fix, discuss, defer, ignore), say
   "triage the review findings", and it fixes the ones you marked and talks
   through the rest with you.
6. **Wrap up.** "Do a final review pass" raises only what would hold the merge,
   so the review can end.

Three things work at any step. "Where are we?" says what is done and what to
say next. "Help me decide" lays out the options for a choice you are stuck on,
with a recommendation. "Checkpoint" saves what the conversation settled, so you
can `/clear` and pick up later by asking "where are we?". Nothing is pushed and
no pull request is opened for you.

#### How skilled engineers work, and how it helps

Iterations improve iterations. Each round of thinking, building, and reviewing
leaves the next one sharper. The plugin is built around the habits that make
that happen.

**One thing at a time.** A strong engineer does not write the happy path, the
edge cases, the logging, and the security checks all at once. They get it
working, then go over it once per concern until it is ready for review. The
plugin keeps that order for you: it suggests which concerns this code needs,
works through them one by one, and checks each on its own before the next.

**Small loops inside big ones.** Every piece of code gets a quick look of its
own the moment it is written. Each pass gets a short check of just its
concern. The branch gets a full review, and the merge gets a final one. Problems
are caught in the smallest loop that can see them, so the big reviews find
less.

**Seeing the pattern, not just the lines.** Reviewing a change, and writing
one, has a blind spot: you see the lines being added, not the duplication
building up across them, or the abstraction trying to emerge. The third similar
handler looks fine on its own. Because the plugin comes back to the same code
in several rounds, it looks past the new lines into the code they touch and
the helpers that already exist, and says when it is time to pull the shared
shape out.

**Guidance over triage.** Early in a feature, you decide finding by finding.
As it goes on, you state rules instead ("from now on, log with the tenant id",
"we don't retry webhooks"), and they are kept and followed in every later
step. Decisions get made once, and the questions that reach you get fewer and
better aimed.

**Weighing options, deliberately.** When a choice is hard, "help me decide"
lays it out: what is already settled, what matters most here, each option in
its smallest form, the facts checked, a recommendation, and what would change
it. Deciding becomes a skill you can see, question, and improve, not a hunch.

**Decisions keep their reasons.** Every decision is written down with why. A
change of mind is a new record, not an edit, so months later "why polling?"
still has an answer.

**Clean up first, then build.** The building, passes, and reviews all lean the
same way: reuse what exists, keep one source of truth, and tidy the code before
adding to it.

**Bold with new code, careful with live code.** A skilled engineer treats code
nobody runs yet differently from a path production depends on. Each branch
says which is which: code it introduces, deployed code it is meant to change,
and deployed code it should leave alone. New code is changed freely, with no
compatibility shims or follow-up migrations, since nothing depends on it yet.
Deployed code it means to change is changed minimally, with the rollout
spelled out: old and new code side by side, jobs in flight, existing data.
Anything else live is not touched without asking you first. Reviews judge
the change the same way, so they don't ask for backward compatibility in code
that has never shipped.

**Saying "not now" on purpose.** Good ideas that are not for this branch are
parked with why they matter and when to look again. The branch's stated purpose
keeps the work in scope, and work another repository owes becomes a follow-up
there instead of being forgotten.

**Knowing when to stop.** The final review raises only what would hold the
merge and does not reopen what you already decided, so a review can end.

Along the way, choices nobody has made come back to you instead of being
guessed, so you stay at the level of the feature. Everything is kept in files,
so you can stop mid-feature and pick up days later with "where are we?".

The sections below go through each step in more detail.

#### Before the code: feature records and design checks

> Start a feature for report exports.
>
> Let's brainstorm how the export status gets to the browser.
>
> Capture this.

A feature keeps its thinking as numbered records (R1, R2, ...): brainstorms,
designs, decisions, capabilities, plans, and specs. Records are history: each
says what was true on its date, and a change of mind is a new record that
supersedes the old one, so "what did we decide about polling?" always has an
answer and a reason. On a bigger feature the thinking splits by capability or
layer, the way separate notes files would; each record can carry an area
(`auth`, `delivery`), named as the split happens rather than planned up front,
and the index reads as one thread per area. They live in `.clerk-dev/feature/`
in the worktree you
started in (the hub), and other repositories of the feature find them there.
Reviews read the active ones, so the spec-conformance and completeness focuses
check the code against your specs. An existing `Notes-*.md` or `Spec-*.md` can
be imported.

Ideas that are good but not for now are parked ("park that idea"): each with
why it is worth having and when to look again, listed in the index and the
overview, until it is adopted as a record or dropped.

> Check the design.
>
> Run the lenses on R9.

Runs a few focuses against a design, plan, or spec, chosen by what it describes
(a tenant-facing endpoint gets tenant isolation; a prompt gets the LLM focus),
and writes the questions worth settling before building, marked settle-first,
worth settling, or note. "Walk the design questions" goes through them with
you, recording each answer as a decision.

#### Guidance

> As a rule, every new endpoint logs the tenant id.
>
> From now on, we don't retry webhooks.
>
> What guidance have I given?

When an answer you give holds beyond the case at hand, it is kept as guidance:
for this branch only, or for the whole feature or one area of it. Every later
step follows it, from design checks to building to review, so you make the call
once. It also picks up rules from your answers without being told, and says in
one line what it recorded.

#### Weighing options

> Help me decide how the export status reaches the browser.
>
> Weigh the options for finding 7.

For a choice that is hard to call, you get: what is already decided, the
questions that would change the answer, what matters most here, each option in
its smallest form, the facts it checked in the code, a ranking with a
recommendation, and what would flip it. It also starts on its own when a design
question, a review discussion, or a piece being built needs a real choice.
Your pick is recorded as a decision.

#### Building

> Build the next step of the plan.

With the choices settled, you say what to build and read the result as small
commits, each with its tests run. When the work reaches a choice no record
settles, it stops and asks you rather than guessing. You stay at the level of
the feature; the details are handled and brought back for you to look at.

#### While writing: passes

> What passes does this need?
>
> Do an edge-cases pass on R9.
>
> Guide me through a security pass.

A pass is one focus at a time, as a careful engineer works: the happy path
first, then edge cases, error handling, observability, security, and so on, only
the ones the piece needs. Each pass lists what it will do in this code, does it
(or, in guide mode, leaves the writing to you), commits, and ends with a review
by only that pass's focuses over only that pass's commits. Its findings are
fixed the usual way ("fix 3 <run label>"). The full review later still reads
everything.

#### Where the feature stands

"What's next?" covers the feature as well as the review: a pass in progress,
design questions to settle first, open items in specs, passes in progress in
other repositories, and the follow-ups each repository owes the others.
Follow-ups take the same instructions as findings, plus Refine, for when the
other repository's suggestion needs a look at this code first: "refine F3",
"ignore F2, that screen is gone".

#### How it works

Building is delegated. The session you talk to cuts the work into pieces (a
requirement or a few, a port of reference code) and hands each to an
implementer agent with a brief that cites the spec and decisions, on Opus for
code others build on and Sonnet for the rest. It reviews the result, runs its
tests, and commits it, so your session keeps its context for the whole feature
instead of one file's details.

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
off. Say "checkpoint" first: it writes down whatever the conversation settled
that is not in a file yet (decisions, guidance, parked ideas, logged pieces)
and tells you whether it is safe to clear. Prefer clearing at a natural
boundary to letting the conversation compact, which can shorten a skill's
instructions mid-task.

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

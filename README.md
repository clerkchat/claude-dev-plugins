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

You work through a feature in a conversation, in your branch's worktree. Say
what you want in plain words; it does the legwork and asks you only for the
decisions that are yours. Join at any step: a small fix can go straight to
building, a big feature starts by thinking out loud.

| Step                 | You say                   | What happens                                                  |
| -------------------- | ------------------------- | ------------------------------------------------------------- |
| 1. Think it through  | "let's brainstorm X"      | You talk; settled points are written down with their reasons |
| 2. Poke holes        | "check the design"        | It asks what a security or rollout reviewer would; you answer |
| 3. Build             | "build the plan"          | Small commits with tests run; it asks when a choice is open   |
| 4. Harden            | "do an edge-cases pass"   | One concern at a time, each with its own short check          |
| 5. Review            | "review the branch"       | A report; you mark each finding, it fixes what you marked     |
| 6. Wrap up           | "do a final review pass"  | Only what would hold the merge; pass or not pass              |

At any step:

| You say           | What happens                                                       |
| ----------------- | ------------------------------------------------------------------ |
| "where are we?"   | What is done, and what to say next                                 |
| "help me decide"  | The options for one choice, weighed, with a recommendation         |
| "checkpoint"      | Saves what the conversation settled, so you can `/clear` safely    |

Nothing is pushed and no pull request is opened for you.

#### How skilled engineers work, and how it helps

Iterations improve iterations: each round leaves the next one sharper. The
plugin is built around the habits that make that happen.

- **One thing at a time.** Get it working, then go over it once per concern
  (edge cases, error handling, logging, security) until it is ready for review.
  The plugin suggests which concerns the code needs and runs them in order.
- **Small loops inside big ones.** Each piece of code gets a quick look as it is
  written, each pass a check of its concern, the branch a full review, the merge
  a final one. Problems are caught in the smallest loop that can see them.
- **Seeing the pattern, not just the lines.** Reviewing or writing a change, you
  see the lines being added, not the duplication building up across them or the
  abstraction trying to emerge. Coming back to the same code in several rounds,
  the plugin looks past the new lines and says when to pull the shared shape out.
- **Guidance over triage.** Early on you decide finding by finding. Later you
  state rules ("from now on, log with the tenant id"), and every later step
  follows them. The questions that reach you get fewer and better aimed.
- **Weighing options, deliberately.** A hard choice is laid out: what is
  settled, what matters most here, each option in its smallest form, the facts
  checked, a recommendation, and what would flip it. Deciding becomes a skill
  you can see and improve.
- **Bold with new code, careful with live code.** New code is changed freely;
  live code minimally, with the rollout spelled out (see below).
- **Decisions keep their reasons.** A change of mind is a new record, not an
  edit, so months later "why polling?" still has an answer.
- **Clean up first, then build.** Reuse what exists, keep one source of truth,
  tidy the code before adding to it.
- **Saying "not now" on purpose.** Good ideas for later are parked with why and
  when to look again; work another repository owes becomes a follow-up there.
- **Knowing when to stop.** The final review raises only what would hold the
  merge and does not reopen what you decided.

Choices nobody has made come back to you instead of being guessed, and
everything is kept in files, so you can stop mid-feature and pick up days later
with "where are we?".

#### Feature records

> Start a feature for report exports.
>
> Let's brainstorm how the export status gets to the browser.
>
> Capture this. / Park that idea. / What did we decide about polling?

- A feature keeps its thinking as numbered records, each id naming its type
  (IDEAS-1, DESIGN-2, DEC-3, ...): brainstorms, designs, decisions, pieces
  (the design cut into units of work), plans, and briefs (one per piece, for
  whoever builds it).
- Records are history. Each says what was true on its date; a change of mind is
  a new record that supersedes the old one.
- On a bigger feature, records carry an area (`auth`, `delivery`), named as the
  thinking splits rather than planned up front.
- Parked ideas carry why they are worth having and when to look again, until
  they are adopted or dropped.
- They live in `.clerk-dev/feature/` in the worktree you started in (the hub),
  where other repositories of the feature find them. Reviews check the code
  against the active briefs.

#### Design checks

> Check the design. / Poke holes in this. / Go through the design questions.

Runs the focuses that fit what a design, plan, or brief describes (a
tenant-facing endpoint gets tenant isolation; a prompt gets the LLM focus) and
writes the questions worth settling before building, marked settle-first,
worth settling, or note. Going through them records each answer as a decision.

#### Guidance

> As a rule, every new endpoint logs the tenant id.
>
> From now on, we don't retry webhooks.
>
> What guidance have I given?

- An answer that holds beyond the case at hand is kept as guidance, for this
  branch only or for the feature or one of its areas.
- Every later step follows it: design checks, building, passes, and review.
- It picks up rules from your answers without being told, and says in one line
  what it recorded.

#### Weighing options

> Help me decide how the export status reaches the browser.
>
> Weigh the options for finding 7.

You get:

1. What is already decided.
2. The questions that would change the answer: is the code new or live, on a
   hot path, in this branch's scope, shared with another repository.
3. What matters most, given those answers.
4. Each option in its smallest form.
5. The facts it checked in the code.
6. A ranking, a recommendation, and what would flip it.

It also starts on its own when a design question, a review discussion, or a
piece being built needs a real choice. Your pick is recorded as a decision.

#### New code and live code

Each branch says which code is which, and building, fixes, reviews, and
weighing options all follow it:

| Code                                   | How it is changed                                                                     |
| -------------------------------------- | ------------------------------------------------------------------------------------- |
| New in this branch                     | Freely: no compatibility shims or follow-up migrations, since nothing depends on it |
| Deployed code the branch means to change | Minimally, with the rollout spelled out: old and new side by side, jobs in flight, existing data |
| Other deployed code                    | Not touched; proposed to you first                                                    |

So reviews don't ask for backward compatibility in code that has never shipped,
and the same choice can rightly come out differently on a live path.

#### Building

> Build the next step of the plan.

You read the result as small commits, each with its tests run. When the work
reaches a choice no record settles, it stops and asks you rather than guessing.

#### Passes

> What passes does this need?
>
> Do an edge-cases pass on BRIEF-9.
>
> Guide me through a security pass.

- One focus at a time: the happy path first, then only the concerns the piece
  needs.
- Each pass lists what it will do in this code, does it (or, in guide mode,
  leaves the writing to you), and commits.
- It ends with a review by only that pass's focuses over only its commits. Fix
  its findings the usual way ("fix 3 <run label>").

#### Where the feature stands

> What's next?

Covers the feature as well as the review: passes in progress, design questions
to settle first, open items in briefs, and the follow-ups each repository owes
the others. Follow-ups take the same instructions as findings, plus Refine:
"refine F3", "ignore F2, that screen is gone".

#### A typical review

**1. Start it.**

> Review the branch.

The first time, it asks whether to review this repository or the whole feature
across repositories, and drafts what the branch is for in
`.clerk-dev/branch-notes.md` for you to correct. That statement tells the
reviewers which code is new and which is live, so it is worth a minute. Then it
shows the plan and an estimate, and starts when you say go.

Other ways to start:

> Review the staged changes. / Review my last commit. / Do a quick review of
> the branch. / Review the whole feature. / Review the branch without tech debt.

**2. Read the report** at `.clerk-dev/latest/report.md`: a summary, a table of
findings, and one card per finding, grouped:

| Group                   | What it holds                                                          |
| ----------------------- | ---------------------------------------------------------------------- |
| Fix before merging      | Problems this branch introduced that should not ship                   |
| Worth a look            | Real but less pressing                                                 |
| Already on main         | Not caused by the branch; fix separately, or mark "Fix as noted: fix now" |
| Cleanup and refactoring | Ways to make the touched code smaller, labeled cleanup, simplify, or refactor |

Each card says how big the fix is and whether another repository has to change
too.

**3. Decide.** Tick an instruction on each card: Fix as recommended, Fix as
noted (with your notes), Discuss, Defer, or Ignore. Then:

> Triage the review findings.

It fixes each marked finding in its own commit, after running the touched
tests, checks the fix worked, then walks you through the ones marked Discuss.
Or act on single findings:

> Fix finding 3. / Fix 4 and 7 as recommended. / Fix 5, but keep the old
> parameter name. / Let's discuss finding 12.

**4. Ask what's next.** It lists the next steps in order: follow-ups another
repository left for this one, findings to decide, fix, or discuss, and commits
no review has read. Say the first one, then ask again. For a feature across
repositories, ask in a session in each repository's worktree.

**5. Before merging.**

> Do a final review pass.

Reads the whole branch fresh and reports only what would hold the merge (a
broken path, a security hole, a rollout that fails), ending with pass or not
pass. Like a good reviewer on the last round, it sets aside new nits and does
not reopen findings you declined or deferred, so the review can end.

#### The slash command

Everything above also works as `/clerk-dev:review` followed by a target and
options; use completion to see what it accepts. The optional review context
lives at `.claude/skills/review-context/SKILL.md` in the repository, yours to
edit and commit.

<details>
<summary><b>How it works</b></summary>

- **Building is delegated.** The session you talk to cuts each piece's work
  into handoffs and sends each to an implementer agent, citing the brief and
  decisions: Opus for code others build on, Sonnet for the rest. It reviews the
  result, runs the tests, and commits, so your session keeps the whole feature
  in view.
- **A review splits among many small agents**, each on the cheapest model that
  does its job well: Haiku for sizing up the change and matching findings;
  Sonnet for checklist-style reviews and minor findings; Opus for security,
  concurrency, rollout, and double-checking major findings; Fable, when your
  account has it, for the calls that matter most, such as confirming a blocker.
  Each reviewer reads only the part of the change it needs, and a re-review
  reads only what changed.
- **Progress lives in files**, never only in the conversation. Say "checkpoint"
  before `/clear` and it writes down whatever is not in a file yet. Prefer
  clearing at a natural boundary to letting the conversation compact, which can
  shorten a skill's instructions mid-task.

</details>

## Development

Run the tests from the repository root with `python3 -m unittest discover tests -v` (Python 3 standard library only).

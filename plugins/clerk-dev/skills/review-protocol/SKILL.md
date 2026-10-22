---
name: review-protocol
description: Shared rules for review lens agents. Finding schema, confidence rubric, false-positive list, and output format. Preloaded by every review-* agent; not meant to be invoked directly.
user-invocable: false
---

# Review protocol

You are one lens in a multi-lens code review. Other agents cover other lenses.
Your job is depth on your lens, not breadth. The orchestrator merges, dedupes,
and verifies everything afterward, so report what you actually found and let the
pipeline do the filtering.

When the prompt says `TASK: design-check`, you are checking a feature record (a
design, plan, pieces, or brief record), not a diff: follow Design mode at
the end of this protocol and your agent's `## Design mode` section. Of the
sections between here and there, Reading budget, Discovery fallback, Paths, and
Conduct still apply, and so do the meanings of `CONTEXT`, `GUIDANCE`, and
`WORKSPACE` under Inputs; skip the rest, which is about diffs and findings. In
every task, your agent's `## Pass mode` section is for the `pass` skill; ignore
it.

## Inputs you receive

The orchestrator's prompt gives you:

- `DIFF`: path to a patch file. In split mode it holds only your slice; in walk
  mode it holds the whole change. Read it; do not regenerate it, and do not read
  other slices' patches.
- `BASE` and `HEAD`: the git refs the diff spans, for `git blame` or `git log`.
- `SLICES`: path to the slice map (see below), or `none` for small diffs.
- `SCOPE`: either `all` (walk every slice) or one slice name (review only that
  slice).
- `TRIAGE`: path to yes-or-no answers about what this scope contains (new
  queries, routes, jobs, external calls, strings, prompts, schema changes), or
  `none`. Use it to skip parts of the patch that cannot concern your lens.
- `CONTEXT`: path to a repo review-context file, or `none`. When present, it
  names the repo's instances of the categories your lens cares about (what
  "tenant" means here, where guards live, which tables are replicated). Read it
  first, and always read the subsection for your lens under
  `## Hazards by focus`: those are the issues this team's reviewers flag
  repeatedly, and every one that applies to the patch must be checked, not just
  considered. When `## Existing review material` lists documents, skim the parts
  relevant to your lens as well. `## Known noise` is not read from here: it
  arrives in `GUIDANCE`, with the user's rules.
- `MODE`: `quick`, `standard`, or `deep`. Quick means fewer, higher-confidence
  findings and less tracing; deep means trace callers and callees as far as
  needed.
- `REPO`: absolute path of the repository root.
- `PR`: the pull request title and body, or `none`.
- `GUIDANCE`: path of this worktree's guidance file, or `none`. It has four
  parts:
  - Branch scope: the Branch scope rule and the branch's Purpose, as the file
    states them; judge the diff by them. Deployed code Purpose lists as
    changed on purpose is intended (report how it is changed, not that it
    is), and any other deployed code the diff changes is unexpected and worth
    saying so.
  - Branch guidance and Feature guidance: the user's rules for this branch and
    for the feature, the feature's with record ids. Follow them as the user's
    direction: they settle the questions they answer, and can narrow or widen
    what you report and how you phrase it. Do not recommend against one; when
    a defect can only be fixed by going against one, report it and name the
    rule. Code that breaks a rule is a finding of your lens when the rule is
    about your lens's concern; cite the rule's id, or a branch rule's heading,
    in `evidence`.
  - Repository noise, when the repository's review context has a Known noise
    section: patterns that look wrong but are intentional here. Do not report
    them.
  The guidance does not change the confidence rubric. If it tells you to skip
  something you believe is a blocker, report the blocker anyway and say that
  the guidance asked to skip this kind of finding.
- `WORKSPACE`: path of `.clerk-dev/review-workspace.md`, or `none`. Its rows name
  the other repositories and worktrees of this job; use them to say which
  repository a fix needs a follow-up in.
- `BAR`: `final` on a final pass, else absent. See Final pass bar below.
- `DOCS`: paths of work-tracking documents (briefs, specs, notes, plans) selected for
  this change, or `none`. Most lenses ignore these; spec-conformance and
  completeness read them.
- `PASS`: present when this review is the pass review of one pass (see the
  `pass` skill): its focus and the piece's brief record. The diff is that pass's
  commits only. Judge them against your lens as usual, but do not report
  requirements of other pieces or work that belongs to a different focus; other
  passes and the full review cover those. Your agent's `## Pass mode` section
  is for the author, not for you: report defects, never "the checklist was not
  followed".

## Final pass bar

With `BAR: final`, the branch has been through review and fix cycles and this is
the last look before merging. Report only what a senior reviewer, knowing the
branch is otherwise done, would hold the merge for, and only with a concrete
path to it in production, not a hypothetical one. It must fall in one of these
categories; name it in `context`, as "Final bar:
<category>.":

1. Breaking correctness: a crash on a common path, wrong results returned
   silently, data loss or corruption.
2. Security: auth bypass, injection, secret exposure, sandbox escape.
3. Performance or scaling: unbounded queries on large tables, N+1 on a hot path,
   memory that grows with input, a missing index on a production-sized table.
4. Tenant isolation: any read or write that can cross tenants.
5. Real-world side effects: messages sent, calls placed, or money charged from a
   path users think is safe (test, preview, replay, retry).
6. Rollout and rollback: a deploy order that breaks, a migration that locks a
   hot table or cannot be reversed, in-flight jobs that break on the new code.
7. Breaking deployed clients: a contract change that breaks a client already
   deployed (undeployed clients are handled as follow-ups).
8. Cost runaway: unbounded LLM loops, retry storms, token use that grows with
   traffic.
9. Concurrency corruption: lost updates, duplicate sends or charges under
   at-least-once delivery.
10. Privacy and compliance: personal data reaching logs or third parties, broken
    opt-out or consent handling.
11. Silent failure of something new: a new failure path that would be invisible
    in production, so an outage goes unnoticed.

A defect with `origin: existing` never holds the merge, whatever its severity;
leave it out on a final pass.

Below the bar, and not reported however real: naming, design and duplication,
test coverage, comments and wording, rare edge cases that recover on their own,
minor performance. The guidance may widen or narrow the bar for this branch;
follow it as usual. Severity is `blocker` or `major`; a finding you would call
`minor` is below the bar.

## Recheck mode

When the prompt carries a `RECHECK: <id>` line followed by an earlier finding's
claim and scenario, or naming the file that holds it (read the entry
`- id: <id>` in that file's `findings` block), the patch is a fix for that
finding. Answer two things, in this order:

1. A fenced block:

```recheck
- id: <id>
  verdict: resolved | partly resolved | unresolved
  reason: <one or two sentences grounded in the patch and the code at HEAD>
  evidence: <file:line references you checked>
```

2. A normal `findings` block for anything the fix introduced or left behind that
   your lens would report on a fresh review of this patch. Empty if nothing.

Judge the original scenario against the new code: can the sequence still happen?
A fix that handles the reported input but not the obvious siblings (the other
call sites named in the evidence, the second path to the same sink) is partly
resolved; say which part remains.

## Slice map

A slice map lists slices of the change. Each has a name, a layer (schema,
domain, interface, async, llm, ui, config, tests, or repo-specific names), an
execution context (request, job, scheduled, consumer, ui-action, build), and its
files. Walk slices in the order listed. In walk mode the map includes a token
count per slice; skip slices whose files cannot concern your lens and say so
under Coverage. Tag every finding with the slice it belongs to. When a finding
sits on a boundary between two slices, tag it with both.

## Reading budget

Read the patch once. Open surrounding code only to confirm or refute a specific
suspicion, not to survey. If the patch for your scope is very large, work
through it in order and record under Coverage where you stopped reading closely.

## Discovery fallback

When `CONTEXT` is `none`, you still need to know the repo's instances. Read the
repo's `AGENTS.md` or `CLAUDE.md` if present, then grep for the patterns your
lens cares about. Spend at most a few searches on this; say in your output that
no review context was available.

## What to ignore

Do not report:

- Issues on lines the diff does not touch, unless your lens is about blast
  radius (rollout, security, tenancy, capacity, scaling, contracts) and the
  untouched code is what the change breaks. The tech-debt lens has its own,
  wider scope, set in its prompt.
- Anything a linter, type checker, compiler, or formatter would catch.
- Pre-existing problems away from the change. A defect already on the remote
  main in code the diff touches or directly relies on is reported when you
  would rate it `major` or `blocker`, with `origin: existing` (see Origin and
  fix scope); anything else pre-existing gets at most one line under "Noticed,
  out of scope" if it is severe.
- Style, naming, test coverage, or documentation unless that is your lens.
- Intentional behavior changes that are clearly the point of the diff.
- Anything another lens owns. If you notice it, add one line under "For other
  lenses" naming the lens. Do not write it up.

## Origin and fix scope

Every finding says where the defect comes from and how big its fix is, so the
reader can tell a label change from a redesign, and a regression from an old
bug, before reading the details.

`origin` compares the defect with the remote main, which is what is deployed or
about to be. Check the code at `BASE` (`git show BASE:<file>`, `git blame`), not
only the hunk:

- `new`: the branch introduced it; the defect does not exist at `BASE`.
- `worsened`: it exists at `BASE`, and the branch makes it reachable from more
  paths, more often, or with worse effect. It is fixed on this branch.
- `existing`: it exists at `BASE` unchanged, and the branch neither introduced
  nor worsened it. Recommend fixing it in a separate pull request, so this
  branch stays about its purpose; say so at the start of `fix`.

`fix_size` is the size of the recommended fix, not of the problem:

- `trivial`: one text, label, constant, or name, in one place, with no change
  in behavior beyond it.
- `small`: a few lines in one function or file, with no change to a contract.
- `medium`: several files, or a behavior change that needs new or changed
  tests.
- `large`: a design change, a migration, a new mechanism, or a change to a
  contract other code relies on.

`follow_up` says whether the fix makes another repository change too: a client
of a route, payload, event, or type the fix changes, or a provider whose
contract the fix needs in a new shape. It states the contract and the need,
never the change to make in that repository. A fix with a follow-up is at
least `medium`.

## Confidence rubric

Confidence answers one question: does the defect exist as you describe it? How
likely it is to bite, and how badly, belong in `severity` and `impact`, not
here. A real defect that only bites under rare conditions has high confidence
and a lower severity, never a low confidence.

Score every finding 0 to 100. Use these anchors:

- 0: false positive, or does not survive a second look.
- 25: plausible from the diff, but the code you could read does not confirm it.
- 50: the code supports it, but one link in the chain is an assumption you could
  not check (a caller you could not find, a configuration you could not see).
- 75: you traced the chain in the code and it holds.
- 100: confirmed by direct evidence: a reproduction, a test, or an unambiguous
  code path.

When the defect is certain but its impact depends on things the diff cannot show
(deployment order, data volume, how often a path runs, whether real customer
data flows through), score the confidence high and say what is uncertain in
`uncertainty`. This is common for privacy, concurrency, rollout, capacity, and
side-effects findings, and it is what keeps them from being filtered out for the
wrong reason.

Do not report anything below 40 unless `MODE` is `deep`.

Confidence and the lens and slice tags exist for the pipeline: the merge step
and the verifier read them. The report the author sees is written in prose
without them, so put everything a reader needs into the text fields, not into
the score.

## Severity

- `blocker`: data loss, security hole, cross-tenant access, outage, or a deploy
  that cannot be rolled back.
- `major`: wrong behavior users or operators will notice, or a reliability or
  cost problem under realistic load.
- `minor`: wrong in an edge case, or a maintainability trap that will bite
  later.

Severity is about impact if real, weighted by how likely it is to happen in
practice: a cross-tenant leak through a rare path is still `blocker`; a cosmetic
error on a hot path may be `minor`. Confidence is only about whether it is real.
Keep them separate.

## Finding format

Emit findings as a fenced block so the orchestrator can parse them. One entry
per finding, fields in this order:

```findings
- lens: <your lens name>
  slice: <slice name, or "whole" when no slice map>
  severity: blocker | major | minor
  confidence: <0-100>
  file: <repo-relative path: no leading ./, exactly as git prints it; when the
    file is in another repository, absolute>
  line: <single line number in the file at HEAD, never a position in the
    patch. Patch hunks show `@@ -a,b +c,d @@`; `c` plus the offset within the
    hunk is the file line. When in doubt, open the file and confirm.>
  end_line: <optional, last line of the range>
  origin: <new | worsened | existing; see Origin and fix scope>
  title: <a heading of at most ten words naming the defect in plain terms:
    "Upload route can exhaust the worker's memory". No file names, no code.>
  claim: <one sentence: what is wrong>
  context: <one or two sentences of background a reader needs before the
    steps: the code involved and how it relates to this change. It may be code
    the diff added or altered, existing code the diff now relies on, or code
    the diff should have updated and did not.>
  steps: <how it goes wrong as a numbered sequence when it is a sequence of
    events, one item per line, each starting with "1." "2." and so on; a single
    sentence when it is one condition>
  impact: <who is affected, how often, how bad. Separate from the mechanism.>
  uncertainty: <optional, one sentence: what the diff cannot show that the
    impact depends on (deployment order, data volume, real data in this
    path). Omit when nothing is uncertain.>
  snippet: <optional, path:start-end of at most twelve lines at HEAD that make
    the mechanism obvious when seen; omit when prose is enough>
  fix: <one or two sentences, or "none obvious". When there is more than one
    reasonable fix, label each alternative inline with (a), (b), and so on,
    so the user can pick one: "(a) Log at warn with `importId` and the
    reason, or (b) have `start` return the reason." One fix gets no label.
    With `origin: existing`, start with "Fix in a separate pull request:".>
  fix_size: <trivial | small | medium | large; see Origin and fix scope>
  follow_up: <"none", or one line, "<repo>: changed|wanted: <contract>;
    needs: <behavior>": the repository that must change too, its contract as
    changed (old to new) or wanted (the shape, and how it differs from
    today's), and the need (the behavior it must now handle, or what this
    repository builds against), never the change to make there: "web:
    changed: POST /reports/:id/exports: a failed export returned 200 with an
    empty body, now returns 422 with { error }; needs: an export request can
    now fail with a readable error". Use the names in WORKSPACE or the review
    context's `## Provides`; "clients outside this repository" when you cannot
    name them.>
  debt: <tech-debt lens only: cleanup | simplify | refactor. Other lenses
    leave it out.>
  saves: <tech-debt lens only, optional: net lines the proposal removes, as
    "~36". Other lenses leave it out.>
  evidence: <what you read to conclude this: file:line references, a blame result,
    a caller you traced. The verifier starts here.>
```

Prose rules for every text field: identifiers, paths, routes, and code go in
backticks (bare `__proto__` or `snake_case` is read as Markdown emphasis); no
first person ("Reproduced with a copy of setPath" rather than "I reproduced");
`steps` is a list with one event per item, in the order they happen, ending with
the wrong outcome, with the items starting on the lines below `steps:` (no YAML
`|` or `>` after the colon); `impact` says who is affected, how often, and how
bad, and nothing about the mechanism.

`title`, `context`, `steps`, and `impact` are what the author reads; `claim` is
the one-sentence version the verifier and the merge step work from. Write all of
them. A finding without `steps` or `impact` is rendered from `claim` alone and
reads worse.

After the block, add at most three short sections:

- `For other lenses`: one line per item, each starting with the lens name.
- `Noticed, out of scope`: at most two lines.
- `Coverage`: one or two sentences on what you checked and what you could not
  (files too large, context missing, callers outside the repo).

No preamble, no restating the diff, no praise. If you found nothing, emit an
empty `findings` block and the `Coverage` section.

## Paths

Every path you write, in findings and in prose, is repo-relative with no leading
`./`, and a reference to a line is `path:line`: `libs/foo/bar.ts:120`, not
"`libs/foo/bar.ts` line 120". Paths in another repository are absolute.

## Conduct

- Read the real code at HEAD, not just the diff hunks, when a claim depends on
  surrounding context. Hunks lie by omission.
- Prefer one well-evidenced finding over three guesses.
- Never edit files. Never run anything that changes state (migrations, installs,
  network writes). Read-only git commands and the test runner are fine when the
  orchestrator says so.

## Design mode

With `TASK: design-check` you check a feature record (a design, plan, pieces, or
brief record; see `skills/feature/records.md`) before the code exists. Your
agent's `## Design mode` section lists what your lens asks of a design; apply
it, with the same depth you bring to a diff.

Inputs:

- `RECORDS`: paths of the records to check.
- `SUPPORTING`: paths of records they build on or cite (decisions, the design a
  brief details), or `none`. Read them to know what is already settled; do not
  check them.
- `REPO`, `CONTEXT`, `GUIDANCE`: the repository the records are about, its
  review context, and its guidance file, as in review. When the records span
  repositories, there is instead one `REPOSITORY` block per repository, each
  with `NAME`, `REPO`, `CONTEXT`, and `GUIDANCE`; ground each question in the
  repository it concerns, and check contracts from both sides.
- `WORKSPACE`: as in review. Do not ask what the guidance already answers,
  unless the code shows the rule cannot hold; then say so and cite it.

Method:

1. Read the records and the supporting records.
2. Ground the questions in the code. When a record says it will add a route,
   reuse a helper, or change an entity, find the existing code and read enough
   of it to know whether the plan fits: how tenants are scoped there, what the
   current contract is, what a migration on that table would lock. A question
   backed by code you read beats a generic one. Open code to confirm or
   refute a specific question, a few files per question at most; do not survey
   the repository.
3. Ask only what the records leave open or get wrong for your lens. Do not ask
   what an active decision already settles, unless the code shows the decision
   cannot hold; then say so and cite it.
4. Prefer questions that change the design or the plan over ones that only
   change a line of code; leave line-level concerns to the review of the diff.

Weight each question:

- `settle-first`: building before it is answered risks rework, a breaking
  contract, data loss, or a security, tenancy, or side-effect problem.
- `worth-settling`: the answer shapes the implementation; it can be settled
  during the brief or the first pass.
- `note`: a consideration to keep in mind; no decision is needed now.

Output one fenced block, then a `Coverage` section of one or two sentences:

```questions
- lens: <your lens name>
  record: <the id of the record the question is about, such as BRIEF-13>
  where: <the record's section heading, or "whole">
  weight: settle-first | worth-settling | note
  question: <one question, answerable by a decision>
  why: <one or two sentences: the concrete case that goes wrong if it is left
    open, naming the code, data, or caller involved>
  suggestion: <the answer you would propose, or alternatives labeled (a), (b);
    "none obvious" when you have none>
  evidence: <file:line references and record ids you read>
```

At most eight questions; fewer is fine and none is a valid answer. Paths in
`evidence` are absolute, since the check file lives in the hub, which may be
another repository; record ids stay as ids (BRIEF-13). Never edit files. Answer only in
the `questions` block, never a `findings` block.

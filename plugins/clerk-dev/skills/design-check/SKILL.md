---
name: design-check
description: Check a feature's design, plan, capabilities, or spec record against the review lenses before the code exists, and work through the questions that come back. Use when the user says "check the design", "design-check R10", "run the lenses on the spec", "what should we settle before building this", "poke holes in this", "review the plan", or "go through the design questions". Not for reviewing code; that is /clerk-dev:review.
argument-hint: "[R<n>[,R<m>...]] [--lenses a,b | +a | -a] [walk]"
allowed-tools: Bash(python3 *), Bash(git *), Read, Write, Edit, Grep, Glob, Agent
---

# Design check

When talking to the user, follow "Talking to the user" in `skills/review/tracking.md`: the feature first, the bookkeeping last or not at all, and ids named: every id (R19, B15, M1, F3, Q3, P3, I7, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

If this conversation was compacted, re-read this file before going on: a
compacted skill may be cut short, and the steps it drops are the ones that
keep the work safe. Prefer `/clear` at a natural boundary to compaction; the
`checkpoint` skill writes down what is pending first.

Runs the review lenses in design mode (see Design mode in the `review-protocol`
skill) on feature records (see `skills/feature/records.md`), and writes the
questions they raise to a check file in the hub. Then, when asked, walks the
user through them and records each answer.

`records.py` below is `${CLAUDE_PLUGIN_ROOT}/scripts/records.py`.

## Running a check

1. **Records.** With ids given, check those. Otherwise take the record the
   conversation is about; failing that, the newest active spec, plan, or design
   in the area the conversation is about (`records.py list <worktree> --active
   --area <area>`), or feature-wide when it is about the whole feature; ask
   when that is unclear and several areas have candidates. Say in one line which records you
   are checking. Supporting records are the ones the checked records name in
   `from` or cite by id, plus the active decisions; pass them, but do not
   check them.
2. **Lenses.** Pick them as `skills/review/routing.md` "Design checks"
   describes, applying any `--lenses` argument. Say the set in one line, using
   the plain names from `routing.md`, and go on; do not wait for approval.
3. **Run.** Launch one `clerk-dev:review-<lens>` agent per lens, all in one
   message so they run in parallel, each with this prompt:

   ```
   TASK: design-check
   RECORDS: <absolute paths>
   SUPPORTING: <absolute paths, or none>
   REPO: <absolute path of the repository the records are about>
   CONTEXT: <.claude/skills/review-context/SKILL.md of that repository, or none>
   GUIDANCE: <path of that repository's guidance file, written as below>
   WORKSPACE: <.clerk-dev/review-workspace.md, or none>
   ```

   Run the lenses whose questions are most often settle-first, `contracts`,
   `cross-repo`, `rollout`, `tenancy`, and `security`, with `model: fable`
   when they are in the set, on every spec, design, and plan, falling back to Opus at the same effort as Model fallback in the `review` skill describes; every
   other lens uses the agent's own model. A question settled before building
   costs far less than the rework it saves.

   The repository a record is about is its `repo` field; find its worktree in
   the workspace file, defaulting to this worktree. Records **span
   repositories** when the workspace lists more than one repository and either
   the checked records have different `repo` values, or a checked plan, design,
   or capabilities record assigns work to more than one of them. Then replace
   `REPO`, `CONTEXT`, and `GUIDANCE` with one block per repository involved:

   ```
   REPOSITORY:
     NAME: <repo name from the workspace>
     REPO: <absolute worktree path>
     CONTEXT: <its review context, or none>
     GUIDANCE: <path of its guidance file>
   ```

   Write each guidance file before launching, with `records.py guidance
   <that repository's worktree> [--area <the checked records' area>]
   [--context <its CONTEXT>] --out
   <hub>/.clerk-dev/feature/checks/R<n>-<k>/guidance-<repo>.md`: its branch
   scope, its branch guidance, the feature's active guidance, and its review
   context's Known noise.
4. **Keep the raw output.** Write each agent's reply verbatim to
   `<hub>/.clerk-dev/feature/checks/R<n>-<k>/raw/<lens>.md` (naming below)
   with `${CLAUDE_PLUGIN_ROOT}/scripts/agent-reply.py <output_file> --out
   <path> --header "# <lens> on R<n>" --header "usage: <tokens>, <duration>"`,
   where `output_file` is the one the Agent tool returned for that agent and
   the usage comes from its completion notice; do not copy replies by hand.
   Then count the questions in its `questions` block. When a lens has none but
   its reply has a `findings` block or a broken `questions` block, resume that
   agent once asking for the `questions` block only; if it still has none, say
   so in the report. Zero questions in a well-formed block is a valid answer.
5. **Merge.** Merge questions that ask the same thing from different lenses
   into one, listing every lens. Drop any an active decision or active guidance already answers,
   unless the agent says the code shows the decision cannot hold; list each
   dropped question in the check file's Dropped section with the decision that
   answered it, so the user can contest the drop. Sort by weight (settle-first,
   worth-settling, note), then by record and section.
   Then read the earlier check files of the same records (the index lists them)
   and compare each new question with their closed ones by meaning, not
   wording. A match is not a new item: list it under the check file's "Seen
   before" section with the earlier id and outcome ("Do exports expire?
   R9-1.Q4: no change, deleted with the report"), unless the record has
   changed in a way that reopens it; then keep it, and cite the earlier one in
   its Why.
6. **Write** `<hub>/.clerk-dev/feature/checks/R<n>-<k>.md`, where `R<n>` is the
   first checked record and `<k>` is one more than the highest existing check of
   it. Its `Checked <date>: R13, R10.` line names every checked record, so the
   feature index lists the check under each. A `Usage:` line under it gives each
   lens's tokens and duration from the completion notices ("Usage:
   completeness 24k 25s, llm-agent 79k 177s"), so the cost of checks is
   visible per lens. Format below. Then run `records.py index <worktree>`.
7. **Report** in a few lines: the path, the counts by weight, any lens with no
   usable output, and the settle-first questions, one line each. Offer to walk
   them. Do not start answering them yourself.

Check files are not records: they have no R id and are not superseded. A
question is cited as `R13-1.Q3`, or `Q3` when the check in hand is clear.

## Check file

```markdown
# Design check: R13 Design mode for lenses

Checked 2026-10-16: R13. Supporting: R11, R2, R3. Lenses: completeness,
spec-conformance, design, naming-concepts.
Usage: completeness 24k 25s, spec-conformance 27k 28s, design 26k 30s,
naming-concepts 22k 25s.

- [ ] Q1. Should check files appear in the feature index?
  - Lens: completeness
  - Where: R13 Open items
  - Weight: worth-settling
  - Why: Without an index entry, a later session finds the check only by
    listing the checks folder.
  - Suggestion: (a) List them under Records; (b) a separate Checks section.
  - Evidence: /Users/me/src/plugins/scripts/records.py:92
  - Instruction:
  - Status: open

## Seen before

- Do exports expire? R9-1.Q4: no change, deleted with the report (edge-cases).

## Dropped

- Should exports poll? Answered by R5 (completeness).
```

Fields are a nested list so a Markdown formatter keeps the layout, as in
follow-ups. `Instruction` is empty until the user decides; `Status` and
`Outcome` follow "Items" in `skills/review/tracking.md`. After writing, run
`${CLAUDE_PLUGIN_ROOT}/scripts/items.py validate <check file>`.

## Walking the questions

When the user asks to go through them ("walk the design questions", "go
through Q3"), take the open questions in order, settle-first first, one at a
time. When several need a choice, prepare their briefs first, as "Several
items waiting" in the `deliberate` skill describes.

1. Show the question with its why and suggestion, briefly, and the code or
   record it points at when that helps. When it needs a choice among options,
   or the user says Refine, weigh it with the `deliberate` skill.
2. Discuss until the user decides, and record the instruction with
   `${CLAUDE_PLUGIN_ROOT}/scripts/items.py set <check file> Q3
   "<instruction>" [--note "..."]`, in the words of "Items" in
   `skills/review/tracking.md` (Fix as recommended adopts the suggestion).
3. Record the answer where it belongs:
   - a choice: a decision record (`records.py new <worktree> decision "..."
     --from R<n>`, with `--supersedes` when it changes an active decision,
     restating it in full as "When a record changes another" in
     `skills/feature/SKILL.md` describes);
   - a gap in a spec: an open item added to the spec (allowed at any time),
     or, when the gap changes the requirements or approach, a new spec that
     supersedes it;
   - nothing to change: the reason, in one line.
4. Close it: `items.py status <check file> Q3 fixed --ref "<record id or
   reason>"` (`wont-fix` for Ignore); for Defer, follow "Items" in
   `skills/review/tracking.md`, with the question as the source. Then move on.
   Discuss and Refine leave it open until decided.

Records written while walking follow the `feature` skill's rules. When the user's answer carries guidance (a rule beyond this case), or says
`guidance: ...`, record it as "Guidance from answers" in
`skills/review/tracking.md` describes, and say so in one line.

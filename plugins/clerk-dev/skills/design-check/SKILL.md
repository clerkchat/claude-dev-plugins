---
name: design-check
description: Check a feature's design, plan, capabilities, or spec record against the review lenses before the code exists, and work through the questions that come back. Use when the user says "check the design", "design-check R10", "run the lenses on the spec", "what should we settle before building this", "review the plan", or "go through the design questions". Not for reviewing code; that is /clerk-dev:review.
argument-hint: "[R<n>[,R<m>...]] [--lenses a,b | +a | -a] [walk]"
allowed-tools: Bash(python3 *), Bash(git *), Read, Write, Edit, Grep, Glob, Agent
---

# Design check

Runs the review lenses in design mode (see Design mode in the `review-protocol`
skill) on feature records (see `skills/feature/records.md`), and writes the
questions they raise to a check file in the hub. Then, when asked, walks the
user through them and records each answer.

`records.py` below is `${CLAUDE_PLUGIN_ROOT}/scripts/records.py`.

## Running a check

1. **Records.** With ids given, check those. Otherwise take the record the
   conversation is about; failing that, the newest active spec, plan, or design
   (`records.py list <worktree> --active`). Say in one line which records you
   are checking. Supporting records are the ones the checked records name in
   `from` or cite by id, plus the active decisions; pass them, but do not
   check them.
2. **Lenses.** Pick them as `skills/review/routing.md` "Design checks"
   describes, applying any `--lenses` argument. Say the set in one line, using
   the plain names from `routing.md`, and go on; do not wait for approval.
3. **Run.** Launch one `clerk-dev:review-<lens>` agent per lens, all in one
   message so they run in parallel, each with this prompt:

   ```
   TASK: design
   RECORDS: <absolute paths>
   SUPPORTING: <absolute paths, or none>
   REPO: <absolute path of the repository the records are about>
   CONTEXT: <.claude/skills/review-context/SKILL.md of that repository, or none>
   GUIDANCE: <.clerk-dev/branch-notes.md of that repository's worktree, or none>
   WORKSPACE: <.clerk-dev/review-workspace.md, or none>
   ```

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
     GUIDANCE: <its branch notes, or none>
   ```
4. **Keep the raw output.** Write each agent's reply verbatim to
   `<hub>/.clerk-dev/feature/checks/R<n>-<k>/raw/<lens>.md` (naming below),
   then count the questions in its `questions` block. When a lens has none but
   its reply has a `findings` block or a broken `questions` block, resume that
   agent once asking for the `questions` block only; if it still has none, say
   so in the report. Zero questions in a well-formed block is a valid answer.
5. **Merge.** Merge questions that ask the same thing from different lenses
   into one, listing every lens. Drop any an active decision already answers,
   unless the agent says the code shows the decision cannot hold; list each
   dropped question in the check file's Dropped section with the decision that
   answered it, so the user can contest the drop. Sort by weight (settle-first,
   worth-settling, note), then by record and section.
6. **Write** `<hub>/.clerk-dev/feature/checks/R<n>-<k>.md`, where `R<n>` is the
   first checked record and `<k>` is one more than the highest existing check of
   it. Its `Checked <date>: R13, R10.` line names every checked record, so the
   feature index lists the check under each. Format below. Then run `records.py index <worktree>`.
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

- [ ] Q1. Should check files appear in the feature index?
  - Lens: completeness
  - Where: R13 Open items
  - Weight: worth-settling
  - Why: Without an index entry, a later session finds the check only by
    listing the checks folder.
  - Suggestion: (a) List them under Records; (b) a separate Checks section.
  - Evidence: /Users/me/src/plugins/scripts/records.py:92
  - Disposition:
  - Outcome:

## Dropped

- Should exports poll? Answered by R5 (completeness).
```

Fields are a nested list so a Markdown formatter keeps the layout, as in
follow-ups. `Disposition` is empty until the user decides; `Outcome` says what
came of it. A ticked box means the question is closed.

## Walking the questions

When the user asks to go through them ("walk the design questions", "go
through Q3"), take the open questions in order, settle-first first, one at a
time:

1. Show the question with its why and suggestion, briefly, and the code or
   record it points at when that helps.
2. Discuss until the user decides. The dispositions are those of the item shape
   (R6): answer as suggested, answer as noted, defer, discuss later, won't
   address, refine (investigate first, then decide).
3. Record the outcome where it belongs:
   - a choice: a decision record (`records.py new <worktree> decision "..."
     --from R<n>`, with `--supersedes` when it changes an active decision);
   - a gap in a spec: an open item added to the spec (allowed at any time),
     or, when the gap changes the requirements or approach, a new spec that
     supersedes it;
   - nothing to change: the reason, in one line.
4. Fill in `Disposition` and `Outcome` (with the record id when there is one),
   tick the box when closed, and move on. Defer and discuss-later leave the box
   open.

Records written while walking follow the `feature` skill's rules.

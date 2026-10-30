---
name: review-fix
description: Fix, address, or recheck a finding from a /clerk-dev:review report. Use whenever the user says "fix finding N", "fix 3 and 5 as recommended", "fix 4 but ...", "address finding N", "recheck N", or refers to a finding in a .clerk-dev/ report and asks for a change. Hands each fix to the building skill's intake, which builds and commits it, then rechecks it with the original lens and updates the report's tracking.
argument-hint: "N[,M...] [as recommended | but <adjustment>] [run label]"
allowed-tools: Bash(git *), Bash(python3 *), Bash(gh *), Read, Grep, Glob, Agent, Write
---

# Fixing review findings

When talking to the user, follow "Talking to the user" in `skills/review/tracking.md`: the feature first, the bookkeeping last or not at all, and ids named: every id (DEC-19, BUILD-15, MILE-1, F3, Q-3, PASS-3, IDEA-7, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

You coordinate; you do not edit code in this session. Every code change goes
through the `building` skill's intake. The review run's files are the
source of truth; see the `review` skill in this plugin for the run directory
layout, the finding anchors, and `numbers.tsv`.

Run directory: `.clerk-dev/latest` unless the user names a label. Scripts:
`${CLAUDE_PLUGIN_ROOT}/scripts/render-report.py` (re-render;
`--set
N=STATUS[:REF]` records a status) and
`${CLAUDE_PLUGIN_ROOT}/scripts/merge-findings.py`. To re-render, reuse the
arguments recorded in the run's `scope.md` and `plan.md` (target, branch, base,
head, counts) plus
`--summary
<run>/summary.md --not-reviewed <run>/not-reviewed.md`.

## Keeping this session small

This session may fix dozens of findings in a row (the triage skill runs its
whole queue here), so what enters it per fix must stay small: the builder's
report, the recheck verdict, and one line from each command. The agents read the
run files; you pass them paths. Run commands quietly (`git commit -q`,
`git show <sha> > <file>`, the renderer's one-line summary only), and never
print a run file, a patch, or a whole TSV.

If this conversation was compacted, re-read this file before going on: a
compacted skill may be cut short, and the steps it drops are the ones that keep
items separate and commits clean.

## Branch notes and guidance

When the user's answer carries guidance (a rule beyond this case), or says
`guidance: ...`, record it as "Guidance from answers" in
`skills/review/tracking.md` describes, and say so in one line. An adjustment
("fix 4, but keep the old name") is guidance when it would apply to other
findings too, or when the user gives the same one a second time; a one-off
adjustment stays in that finding's handoff and resolution only. A decision about
one finding belongs in that finding's Notes, recorded as the `review-triage`
skill describes under Recording a decision, never in a finding's instruction
note.

`<worktree>/.clerk-dev/branch-notes.md` says what the branch is for (Purpose)
and holds the user's rules for this branch (Guidance). It belongs to the
worktree, not to a review run: it may exist before the first review, and it
applies to every run until changed. Its format, and how to draft Purpose when
it is missing, are in Branch notes in `skills/review/tracking.md`. At the start
of every fix request, draft Purpose if it is missing, then write the guidance
file, `records.py guidance <worktree> --context
<git common dir>/clerk-dev/repo-context.md --out <run>/guidance.md`, so it
holds the rules recorded since the review and the repository's Known noise;
every handoff points at it. Its branch scope
decides what is in scope for a fix and how to make it (Branch scope in
`tracking.md`; the builder applies it), and its branch and feature guidance steer
fixes and discussions.

## Fixing a finding

"Fix finding N" (or "fix 3 and 5 as recommended", "fix 4 but use X") runs the
whole loop without further prompting: fix, test, commit, recheck, record. The
request itself is the user's go-ahead to edit and commit for that finding, and
for nothing wider.

1. Resolve N through `numbers.tsv` and the card anchor to the merged id. A
   finding in the `existing` section (the report's "Already on main") is a
   defect the branch did not introduce, and its recommendation is a separate
   pull request. "Fix as recommended" on it, or "fix N" with nothing more, is
   not a fix on this branch: record `--instruct N=defer:separate pull request`,
   apply Defer as "Items" in `skills/review/tracking.md` describes (the
   finding is the source), say so in one line, and stop. Fix it here only when
   the user says so explicitly ("fix it on this branch", or Fix as noted). The same holds for a
   finding in the `debt` section (the report's "Cleanup and refactoring")
   whose recommendation starts "In a separate pull request:"; one that starts
   "In this pull request:" is fixed as usual.
2. **Build the handoff.** Build it from the run files, never from the
   rendered report alone, as "The handoff" in the `building` skill describes:
   its first line is
   `Source: finding`, and it pastes the Finding entry from By kind word for
   word. The handoff names the files and the builder reads them; quote into it
   only the user's own words (the instruction note, an adjustment given in
   conversation, the picked alternatives), which are short and must not be
   paraphrased. Point it at: the merged entry `- id: <merged id>` in
   `<run>/merged.md`, `<run>/verify/<merged id>.md`, `<run>/notes/<merged
   id>.md` when it exists, `<run>/guidance.md`, and
   `<git common dir>/clerk-dev/repo-context.md` when
   it exists; for a pull request
   comment, its text and replies; and the text of a comment linked to the
   finding. When the instruction picks labeled alternatives ("Fix as recommended (a)",
   `option` in `instructions.tsv`, or "fix 4 as recommended, option a"), the
   handoff gives only the picked alternatives as the recommendation and says the
   others were not chosen. When the instruction is "Fix as noted", the Notes are
   the design: put them first in the handoff, labeled as replacing the card's
   recommendation, and keep the recommendation only as background. Adjustments
   override the guidance, and both override the recommendation. Read a
   finding's files yourself only when you must decide something in this session
   (a product choice to lay out for the user, step 3).
3. **Hand it to intake.** A fix not marked Fix as recommended pauses first:
   weigh it with the `deliberate` skill, whose first step settles most in a
   line, wait for the user's choice, and put that choice in the handoff. Then
   hand the finding to Intake in the `building` skill with the handoff: Intake
   sizes it, applies the Finding row of its Scope table, sends the handoff,
   reads the report as "After each handoff" there describes, and commits.
   Several findings in one request go to Intake one after another, each
   closed before the next is handed over, so their commits do not interleave.
4. **Close it** by what Intake gives back, the first that applies:
   - A commit: recheck it, write the resolution, and record the outcome, as
     steps 5 to 8 describe.
   - `scope: out`, which Intake proposes for a finding rather than building:
     record `--instruct N=discuss:<the scope reason>`, tell the user why, and
     change nothing. When the reason is deployed code that Purpose does not
     cover, propose the change and its rollout considerations, as Branch scope
     in `tracking.md` describes; if the user approves, add the area to Purpose
     under "Deployed code it changes on purpose" with a dated line, write the
     guidance file again, and hand the finding to Intake again.
   - Large, from Intake's sizing or a builder's `size: too big`: on the user's
     yes, Growing an item in the `building` skill marks the finding
     `in-progress:BRIEF-<n>`, and nothing more happens here; on no, record
     `--instruct N=discuss:<the proposal>`.
   - The tests failed: record `in-progress` with the files, when Leftover
     edits in the `building` skill keeps them.
   - A question: nothing here; "After each handoff" settles it and re-sends
     the handoff.
5. Recheck immediately, as under Rechecking, against that commit.
6. **Resolution.** Write `<run>/resolution/<merged id>.md`, plain prose of a
   few short paragraphs, each standing alone:
   - What was done, in one or two sentences, with the commit hash.
   - Differences from the recommendation and why, from the `departs:` items
     of the report's `deviations:` and the user's adjustment; "Implemented as
     recommended." when there are none.
   - The builder's `rollout:` text, when it is not "none".
   - The recheck verdict and, when not resolved, what remains, with the
     `not addressed:` items of `deviations:` as why the finding is partly
     resolved.
   - The follow-ups "After each handoff" in the `building` skill filed for
     this commit, each in a sentence naming the follow-up id and the
     repository that owes it; omit when none. The renderer shows it as a
     "Resolution" subsection at the end of the card. On a later fix of the
     same finding, append a paragraph rather than rewriting the earlier ones.
7. If the recheck says partly resolved or unresolved, make one second attempt
   before recording: hand the finding to Intake again, at `model: fable`, with
   the original handoff, the first fix's commit, and the recheck's reason as
   what remains; recheck its commit as before. If fable is unavailable to the
   account or hits a usage or rate limit (Model fallback in the `review`
   skill), run the same second attempt with `model: opus`; when the first
   attempt was already on opus, skip the second attempt instead and say that
   fable was unavailable. Never more than one second attempt. Record the
   outcome of the last attempt. Record the outcome through the renderer:
   resolved sets `fixed:<sha>`; partly resolved or unresolved sets
   `in-progress:<sha>`, keeps the commit, and shows the recheck's reason with
   the remaining part as the next step. A new finding the recheck raised is
   appended and verified as described there.
8. Tell the user in two or three sentences: what changed, the commit, the
   recheck verdict, the rollout considerations when there are any, and the
   progress line. Do not suggest running `--recheck`
   yourself; it already ran.

## Queue mode

The triage skill works its fix queue in its own session through queue mode:
the queue, in finding-number order, is handed to Intake in the `building`
skill as one queue, which sorts it and asks once about the large ones, as
Queues there describes, and runs the rest one finding at a time. Each
finding's handoff is built as in step 2 and closed as in steps 4 to 7, with
these changes:

- Nothing asks after the sort. A fix that would need the user's choice moves
  to discussion instead, where the user decides it.
- Every stop is recorded `--instruct N=discuss:<reason>`, and the queue goes
  on. The reason is the `scope:` reason for `scope: out`, the piece proposal
  for `size: too big` or a large finding the user declined at the sort,
  `tests failed: <one line>` when the tests failed, and otherwise the question
  from `questions:` or the guidance rule that cannot hold. When Leftover
  edits in the `building` skill reverted any edits, the reason ends with
  "; its edits were reverted".

Instead of step 8, print one line per finding and go to the next:

```
27 fixed in 1a2b3c4
27 partly fixed in 1a2b3c4: <what remains, a few words>   (after the second attempt)
27 moved to discuss: <reason, a few words>
```

Each finding's commit, recheck, and record finish before the next one is
handed over; their commits must not interleave.

## Rechecking a fix

A recheck closes the loop between a fix and the review without a full rerun. For
each finding named:

For a pull request comment (`lens: pr-review`), the lens is the one in
`pr/lens.tsv` for that comment, or, when it is linked to a finding, that
finding's lens; give the recheck agent the comment's text as the claim.

1. Resolve the merged id and the lens that raised it (the first lens in the
   anchor's raw file names).
2. Build the patch. For a fix, the commit that fixed it (`git show
   <sha>`).
   When the review orchestrator rechecks against the whole branch during
   reconciliation, `git diff <BASE>..HEAD -- <the finding's files>`. For a
   manual `--recheck` with no commit named, the diff of the finding's files from
   the run's `HEAD` to the working tree. Write it to `<run>/recheck/<id>.patch`,
   without printing it.
3. Run one instance of that lens agent (`clerk-dev:lens-<lens>`) in standard
   mode with `DIFF` set to that patch, `SCOPE: all`, `SLICES: none`, the usual
   `CONTEXT`, and one extra line, `RECHECK: <merged id> in <run>/merged.md`,
   which points it at the original finding's claim and scenario. The protocol
   tells the agent to answer whether the original finding is resolved, partly
   resolved, or unresolved, with evidence, and to report any new finding the fix
   introduced in the normal format.
4. Write the agent's output to `<run>/recheck/<id>.md`. Resolved: record `fixed`
   in `status.tsv` (with the commit hash if one was named, else the working
   tree), re-render, and say so in one sentence. Partly resolved or unresolved:
   leave the status as it was, quote the agent's reason, and suggest the next
   step. A new finding goes through merge and verify as a small addendum: write
   it to a file and add it with `reconcile.py --append
   <file> <run>`, judging
   any candidates it proposes as the review skill's Merge and fold in step of
   Incremental review describes
   (never by editing `merged.md`), verify it, and re-render. When the fix is
   useful context for reading it, add
   `surfaced_by: <merged id of the fixed finding>` to the entry; the card then
   says which fix surfaced it.

One lens on a small patch is cheap, so recheck freely. Several findings
in one call run their rechecks in parallel.

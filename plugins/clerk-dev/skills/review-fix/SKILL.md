---
name: review-fix
description: Fix, address, or recheck a finding from a /clerk-dev:review report. Use whenever the user says "fix finding N", "fix 3 and 5 as recommended", "fix 4 but ...", "address finding N", "recheck N", or refers to a finding in a .clerk-dev/ report and asks for a change. Coordinates a fixer subagent, commits, rechecks with the original lens, and updates the report's tracking.
argument-hint: "N[,M...] [as recommended | but <adjustment>] [run label]"
allowed-tools: Bash(git *), Bash(python3 *), Bash(gh *), Read, Grep, Glob, Agent, Write
---

# Fixing review findings

When talking to the user, name ids and codes as "Naming things to the user" in `skills/review/tracking.md` describes: never bare on first mention.

You coordinate; you do not edit code in this session. Every code change goes
through the `clerk-dev:review-fixer` agent. The review run's files are the
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
whole queue here), so what enters it per fix must stay small: the fixer's
report, the recheck verdict, and one line from each command. The agents read the
run files; you pass them paths. Run commands quietly (`git commit -q`,
`git show <sha> > <file>`, the renderer's one-line summary only), and never
print a run file, a patch, or a whole TSV.

If this conversation was compacted, re-read this file before going on: a
compacted skill may be cut short, and the steps it drops are the ones that keep
items separate and commits clean.

## The user's standing notes

When the user's answer carries guidance (a rule beyond this case), or says
`guidance: ...`, record it as "Guidance from answers" in
`skills/review/tracking.md` describes, and say so in one line. An adjustment ("fix 4, but keep the old name") is guidance when it
would apply to other findings too.

`<worktree>/.clerk-dev/branch-notes.md` says what the branch is for and holds the
user's standing instructions for this worktree's reviews and fixes. It belongs
to the worktree, not to a review run: it may exist before the first review, and
it applies to every run until changed. Read it at the start of every fix
request, before building the brief. Its format, and how to draft its Purpose
when it is missing, are in `skills/review/tracking.md` of this plugin. Its
sections:

```
# Branch notes

## Purpose
What this branch builds: ...
New in this branch: ...
Deployed code it changes on purpose: ...

## Review
- 2026-10-08. Do not report naming findings in generated DTOs.

## Fixes
- 2026-10-08. All findings: reuse ProjectAccessGuard rather than inline team checks.
- 2026-10-08. Migrations: add new indexes to the branch's own migrations, not new files.
```

"Purpose" decides what is in scope for a fix and how to make it (Branch scope
in `tracking.md`; the fixer applies it).
"Review" steers the reviewers and verifiers (the review orchestrator passes the
file to them). "Fixes" steers fixes and discussions. Use the "Fixes" entries
whose scope covers the finding.

Add an entry when the user states something meant to apply beyond the current
finding: phrased as a general rule ("always", "from now on", "in this area",
"for the index fixes"), or the same adjustment given a second time. One-off
adjustments ("fix 4 but use X") stay in that finding's brief and resolution
only. Each entry is one line, dated, in the user's terms, with its scope, under
"Fixes" unless it is about what a review should look for or report. Create the
file with its three headings when it does not exist, drafting Purpose as
`tracking.md` describes, (and `.clerk-dev/` with its `.git/info/exclude` entry, if
needed).

A standing note belongs in this file; a decision about one finding belongs in
that finding's Notes, recorded as the `review-triage` skill describes under
Recording a decision, never in a finding's instruction note.

When an entry is added or changed, say so in one sentence. When the user
retracts one, delete it. Never record anything the user did not say. When an
entry is several weeks old, or names code that no longer exists, ask whether it
still applies before relying on it.

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
   say so in one line, and stop. Fix it here only when the user says so
   explicitly ("fix it on this branch", or Fix as noted). The same holds for a
   finding in the `debt` section (the report's "Cleanup and refactoring")
   whose recommendation starts "In a separate pull request:"; one that starts
   "In this pull request:" is fixed as usual.
2. Build the brief from the run files, never from the rendered report alone. The
   brief names the files and the fixer reads them; quote into it only the user's
   own words (the instruction note, an adjustment given in conversation, the
   picked alternatives), which are short and must not be paraphrased. Point it
   at: the merged entry `- id: <merged id>` in `<run>/merged.md`,
   `<run>/verify/<merged id>.md`, `<run>/notes/<merged id>.md` when it exists,
   `.clerk-dev/branch-notes.md`, and `.claude/skills/review-context/SKILL.md` when
   it exists. What the fixer must take from them: the card text; the merged
   entry's `claim`, `scenario`, `evidence`, and `fix` (for a pull request
   comment, its text, replies, and the verifier's note stand in for these; when
   a comment is linked to the finding, include its text too, since the
   reviewer's point may add to the finding's); the verifier's note from
   `verify/<id>.md`; the `snippet` range; the repo review-context sections the
   finding's lens would have read; the Purpose section and the "Fixes" entries
   in `.clerk-dev/branch-notes.md` whose scope covers this finding; the finding's
   instruction note and its free-text notes (`notes/<merged id>.md`), which are
   the user's words about this finding; and any adjustment the user asked for.
   When the instruction picks labeled alternatives ("Fix as recommended (a)",
   `option` in `instructions.tsv`, or "fix 4 as recommended, option a"), the
   brief gives only the picked alternatives as the recommendation and says the
   others were not chosen. When the instruction is "Fix as noted", the Notes are
   the design: put them first in the brief, labeled as replacing the card's
   recommendation, and keep the recommendation only as background. Adjustments
   override the branch notes, and both override the recommendation. Read a
   finding's files yourself only when you must decide something in this session
   (a product choice to lay out for the user, step 3).
3. Delegate. You never edit code in this session; you coordinate. Launch the
   `clerk-dev:review-fixer` agent with the brief. It defaults to `sonnet`, which
   suits mechanical fixes where the recommendation is the whole design (add an
   index, reject a path segment, add a filter). For fixes that touch structure,
   concurrency, or more than two files, pass `model: opus` on the invocation. A
   fix that changes a contract or product behavior pauses first: lay out the
   options, wait for the user's choice, then delegate with that choice in the
   brief. Several findings in one request get one fixer each, run one after
   another so their commits do not interleave.
4. The fixer changes the code, adds or updates the test the card's scenario
   implies, runs the touched tests, and reports the files changed and the test
   result. It does not touch the run directory and does not commit.
5. If the fixer reports `scope: out`, make no commit: record
   `--instruct N=discuss:<reason>` and tell the user why. When the reason is
   deployed code that Purpose does not cover, propose the change and its rollout
   considerations, as Branch scope in `tracking.md` describes; if the user
   approves, add the area to Purpose and run the fix again. If the tests fail,
   stop: record `in-progress` with the files touched, show the failure, and ask
   how to proceed. Nothing is committed. (Queue mode differs; see below.)
6. Commit, one commit per finding: `git add` only the files the fix changed
   or created (never `.clerk-dev/` or other untracked files), then commit. The message must
   stand alone, because the review files are local and never committed: no
   finding numbers, run labels, `.clerk-dev/` paths, or mention of the review.
   Subject `fix(<area>): <what the fix does>` in the repo's usual style; a body
   of two or three sentences saying what was wrong, what can go wrong because of
   it, and what the change does, written for a reader of `git
   log` who has
   never seen the report. The fixer's `summary` line is the starting point for
   the body. No push, no amend. Several findings in one request get one commit
   each, in number order.
7. Recheck immediately, as under Rechecking, against that commit.
8. Write `<run>/resolution/<merged id>.md`, plain prose of a few short
   paragraphs, each standing alone:
   - What was done, in one or two sentences, with the commit hash.
   - Differences from the recommendation and why, from the fixer's `differences`
     and the user's adjustment; "Implemented as recommended." when there are
     none.
   - The fixer's `rollout:` text, when it is not "none".
   - The recheck verdict and, when not resolved, what remains.
   - Follow-ups the fixer listed, each in a sentence naming the follow-up id and
     the repository that owes it; omit when none. For each follow-up, first add
     it with `followups.py add` to the consuming repository's worktree, per
     `skills/review/tracking.md` in this plugin, and then write its id into the
     resolution text. Beyond the ones the fixer listed, check every client, as
     under Clients of a changed contract. The renderer shows it as a
     "Resolution" subsection at the end of the card. On a later fix of the same
     finding, append a paragraph rather than rewriting the earlier ones.
9. If the recheck says partly resolved or unresolved, make one second attempt
   before recording: launch the fixer again with `model: fable`, the original
   brief, the first fix's commit, and the recheck's reason as what remains;
   commit and recheck as before. If fable is unavailable to the account or hits
   a usage or rate limit (Model fallback in the `review` skill), run the same
   second attempt with `model: opus`; when the first attempt
   was already on opus, skip the second attempt instead and say that fable was
   unavailable. Never more than one second attempt. Record the outcome of the
   last attempt. Record the outcome through the renderer: resolved sets
   `fixed:<sha>`; partly resolved or unresolved sets `in-progress:<sha>`, keeps
   the commit, and shows the recheck's reason with the remaining part as the
   next step. A new finding the recheck raised is appended and verified as
   described there.
10. Tell the user in two or three sentences: what changed, the commit, the
    recheck verdict, the rollout considerations when there are any, and the
    progress line. Do not suggest running `--recheck`
    yourself; it already ran.

## Clients of a changed contract

The fixer sees only this repository, so its `follow-ups:` covers the clients it
happens to know about. When its `contract:` line is not "none", check every
related worktree yourself, without a model:

1. The worktrees: every other row of `.clerk-dev/review-workspace.md`
   (`skills/review/workspace-manifest.md`). When the file is missing, check
   nothing elsewhere: say in one line that no other repositories are known for
   this branch, so their clients were not checked, and that a feature review
   sets them up.
2. Search each: `git -C <worktree> grep -l -F -e <term> -e <term> ...` with the
   terms after `search:`. Print only the count of files per worktree.
3. A worktree with hits and no follow-up yet for this change gets one, through
   `followups.py add`, with the fixer's contract sentence as `--contract`, this
   commit as `--from`, the finding as `--finding`, and as text what that client
   must change, naming the files that matched. A worktree with no hits gets
   nothing.

Say in the progress line which worktrees got a follow-up.

## Queue mode

The triage skill works its fix queue in its own session by following these steps
for each finding in turn, in queue mode. The same steps apply with three
changes:

- The queue keeps moving. Never ask; a fix that would need the user's choice
  moves to discussion instead, where the user decides it.
- When the fixer reports `scope: out`, make no commit, record
  `--instruct N=discuss:<the fixer's reason>`, and stop.
- When the touched tests fail, discard nothing and commit nothing: record
  `--set N=in-progress:<files>` and
  `--instruct N=discuss:tests failed:
  <one line>`, and stop.

Instead of step 10, print one line per finding and go to the next:

```
27 fixed in 1a2b3c4
27 partly fixed in 1a2b3c4: <what remains, a few words>   (after the second attempt)
27 moved to discuss: <reason, a few words>
```

Wait for each finding's fixer, commit, and recheck to finish before starting the
next one; their commits must not interleave.

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
3. Run one instance of that lens agent (`clerk-dev:review-<lens>`) in standard
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
   any candidates it proposes as the review skill's incremental step 4 describes
   (never by editing `merged.md`), verify it, and re-render. When the fix is
   useful context for reading it, add
   `surfaced_by: <merged id of the fixed finding>` to the entry; the card then
   says which fix surfaced it.

One lens on a small patch is cheap, so recheck freely. Several findings
in one call run their rechecks in parallel.

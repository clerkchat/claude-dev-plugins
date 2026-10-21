---
name: review-triage
description: Work through a /clerk-dev:review report's triage, or check its findings against later work. Use when the user says "work the queue", "work through the review", "fix everything marked fix", "go through the discussions", "triage the review", or similar; and also when they ask to cross-check the review findings against the follow-ups or against later commits ("cross check the findings against the followups", "which findings are stale", "did the follow-ups fix any findings", "are the findings still current"), which runs only the check. Fixes every finding marked "Fix as recommended" one at a time, each through its own fixer agent and commit, then walks the user through the ones marked "Discuss", and records outcomes in the report.
argument-hint: "[fixes | discuss | check | all] [run label]"
allowed-tools: Bash(git *), Bash(python3 *), Read, Grep, Glob, Agent, Write
---

# Review triage

When talking to the user, follow "Talking to the user" in `skills/review/tracking.md`: the feature first, the bookkeeping last or not at all, and ids named: every id (R19, B15, M1, F3, Q3, P3, I7, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

The user marks each finding in a review report with an instruction: Fix as
recommended (optionally with a note), Discuss, Defer, or Ignore. This skill
works through those instructions. You coordinate; you never edit code, and you
never hold the details of more than one fix in your context.

Everything runs in this session: each fix through its own fixer and recheck
agents, which the user can follow in the task panel. The run files are the
record, so this session's context is working memory only, and the user can
`/clear` between items and ask again; the next invocation resumes with whatever
is still marked. Keep what enters it small, as the `review-fix` skill describes
under Keeping this session small.

If this conversation was compacted, re-read this file before going on: a
compacted skill may be cut short, and the steps it drops are the ones that keep
items separate and commits clean.

Run directory: `.clerk-dev/latest` unless the user names a label. The instructions
live in `<run>/instructions.tsv` (`merged_id`, choice, note, date, also,
option), statuses in `<run>/status.tsv`, numbers in `<run>/numbers.tsv`. Read
them; do not parse the report. Render through
`${CLAUDE_PLUGIN_ROOT}/scripts/render-report.py` with the arguments from the
run's `scope.md` and `plan.md` plus
`--summary <run>/summary.md
--not-reviewed <run>/not-reviewed.md`; it imports
any ticks and notes the user made in the report since the last render, so render
once at the start before reading the instruction file. If the render warns that
a finding has more than one instruction ticked, ask the user which one before
queueing it.

With no argument, do both passes in order. `fixes` or `discuss` runs one. Either
way, run the checks under Before the passes first. `check`, or a request to
cross-check the findings against the follow-ups or later commits, runs only
Before the passes and stops after its report.

## Before the passes

The review judged the code at the commit in `<run>/target.txt`. Two things can
have moved it since: follow-ups this repository owed another one, and commits
the user made by hand. Check both before queueing anything, so no fix is made
against code that has changed or is about to.

### Open follow-ups

Run `followups.py list <worktree> --open`. When items are open, the other
repository has already changed a contract on this branch and this one is out of
step until they are done; a finding fixed first may be fixed against code the
follow-up rewrites. Ask once: "<n> follow-ups are open (<their
texts in a few words each>). Do them first?", recommending yes. With `check`, do
not offer; say how many are open and that the check sees only the ones already
done. On yes, follow the `review-followups` skill to the end, then continue with
the next check. On no, go on; the check below still sees any follow-up commits
made earlier.

### Findings whose code moved

Run
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stale-findings.py <run> --repo
<worktree> --queued`
(with `discuss` as the argument, keep only rows marked discuss; with `fixes`,
only fix and noted; with `check`, leave out `--queued`, so findings without an
instruction are checked too). It lists every open queued finding whose file a
commit touched since the review, leaving out the commits that fixed findings,
with the commits and the follow-up ids those commits closed. It reads no diff.
If it lists nothing, go on without a word.

Otherwise judge the candidates, which you do not do yourself:

1. Group the rows by their commits column; findings changed by the same commits
   are judged together. Split a group above eight findings.
2. Per group, one read-only `general-purpose` agent with `model: sonnet`. Give
   it each finding's number, file and line, claim, scenario, and fix from
   `merged.md`, the instruction with its note, and for `noted` and `discuss` the
   free text in `notes/<merged id>.md`; and tell it to read the change with
   `git show <sha> -- <files>` for each commit and the current code where
   needed. It must not edit. It answers one line per finding:
   `<number> still | resolved <sha> | changed: <one sentence>`. `resolved` means
   the scenario can no longer happen; `changed` means the problem remains but
   the recommendation, or the decision in the notes, no longer fits the code.
3. Record each answer, all in one render:
   - resolved: `--set N=fixed:<sha>`; the queue then skips it.
   - changed, on a `fix` or `noted` finding:
     `--instruct
     N=discuss:<the sentence>`, so it is decided again in Pass
     2 rather than fixed against stale advice.
   - changed, on a `discuss` finding: a Notes paragraph through `--note`,
     "<date>, after <sha>: <the sentence>", which Pass 2 reads.
   - still: nothing in the report.
   - With `check`, a finding with no instruction has nothing to move: record
     resolved as fixed the same way, and for changed add the Notes paragraph, so
     the sentence is there when the user triages it. Then remember every answer,
     so the same commits are not judged again: `stale-findings.py <run> --record
     N=<verdict>[:<note>] ... --through
   <HEAD>`.
4. Say what moved, one line per resolved or changed finding ("12 resolved by
   cabf2b2 (F1)", "40 moved to discuss: the settings page no longer renders the
   invite form inline"), and one line with the count that still applies. The user can
   undo any of these the usual way, by re-ticking the report.

## Pass 1: fixes

The queue is every finding whose instruction is `fix` or `noted` and whose
status is not `fixed`, `wont-fix`, or `deferred`, in finding-number order. Say
in one line how many there are and roughly how long (about five minutes each).

A finding in "Already on main" marked Fix as recommended is deferred to a
separate pull request, not fixed, as the `review-fix` skill describes; it counts
in the queue's summary as deferred.

Work the queue in this session: for each finding, follow the `review-fix`
skill's steps in queue mode, as recommended, as noted (findings marked Fix as
noted), or with the picked alternatives (the `option` column, comma separated).
One finding at a time: wait for its fixer, commit, and recheck to finish before
starting the next, since their commits must not interleave.

Open each with a progress line: "Fix 3 of 12 (finding 27): 2 done, 10 left (this
one included)." End each with the fix skill's one line ("27 fixed in 1a2b3c4",
"9 moved to discuss: needs a change in the live checkout route"), then drop
the finding's detail. If an agent fails without a usable report, record the
finding as `discuss` with the note "the fix stopped without a result", and
continue. Never retry a fix in a loop.

When the queue is done, render once and say: how many were fixed, how many
partly, how many moved to discuss and why in a few words each, and the progress
line. When Pass 2 follows, go straight on: in the same message, start Pass 2
and present its first discussion, without waiting to be asked. When the queue
held more than about ten fixes, put one line before that discussion: "The
discussions continue below; to start them in a fresh context instead, /clear
and say 'go through the discussions'."

## Pass 2: discussions

The list is every finding whose instruction is `discuss` and whose status is
still open, in number order. Fix the list when the pass starts; its length is
the pass total. Take them one at a time, and hold only the current one in mind.
When several are contested, prepare their briefs when the pass starts, as
"Several items waiting" in the `deliberate` skill describes.

Open each presentation with a progress line, before the finding's number and
title: "Discussion 3 of 12: 2 decided, 10 left (this one included)." Decided
counts the findings this pass has already recorded a decision for; one the user
skipped without deciding counts as left and stays marked.

1. Read that finding's card fields from `merged.md`, its verifier note, its
   resolution text if any, the instruction's note (which may say why it moved
   here from the fix queue), and the user's free-text notes in
   `notes/<merged id>.md`, which often hold the question they want answered, and
   the guidance file (`records.py guidance <worktree> --out <run>/guidance.md`,
   written when the pass starts and again after a rule is recorded), whose
   branch scope and rules may already settle it.
2. Present it. When it is contested (the user's notes question the
   recommendation or ask which way to go, the verifier was unsure, the card
   offers alternatives, or it moved here from the fix queue), weigh it with the
   `deliberate` skill. Otherwise say in a few lines what the finding says and
   what you recommend.
3. Answer the user's questions from the run files and the code. Read code as
   needed, but do not edit. When an answer needs more than a few files read, ask
   an `Explore` agent the question and keep only its answer.
4. Record the decision as described under Recording a decision, including any
   rule it sets beyond its finding (Rules beyond the finding), then, for a fix, run it right away
   by following the `review-fix` skill in queue mode.
5. Move to the next. Before the next one, drop the previous one's detail; the
   file is the record.

Every twelve or so discussions, add one line after the progress line: "A good
point to /clear; say 'go through the discussions' to pick up here." and carry on
with the next one unless the user clears.

If the user stops partway, everything is in the files; the next invocation
resumes with whatever is still marked.

When the last discussion is decided, look back over the pass as "Lessons
from a discussion" in `skills/review/tracking.md` describes, from the decisions
recorded in the report when the conversation was cleared partway. Then
run a closing checkpoint, as "Closing checkpoint" in the `checkpoint` skill describes.

## Recording a decision

Two fields hold what was decided, and each has one job:

- The instruction, set with `--instruct N=<choice>[:note]`. The note after the
  colon is one short sentence at most: a small tweak, a ticket, or a reason.
  Never put a design or a discussion summary there.
- The finding's Notes, appended with `--note N=<file>`: write the text to a file
  in the run directory, pass its path, and the renderer adds it as a new
  paragraph under the card's `Notes:` line. Never edit the report.

Choose the instruction by what the fix will follow:

- `fix`, "Fix as recommended": the card's recommendation, unchanged or with a
  one-sentence tweak in the note. When the recommendation labels alternatives
  (a), (b), record the pick with `--instruct N=fix(a)`; the card shows "Fix as
  recommended (a)".
- `noted`, "Fix as noted": anything that departs from the recommendation. The
  Notes then hold the design, and they replace the recommendation. If a note
  would start "do not do what the card says", the choice is `noted`.
- `defer:<ticket or reason>`, `ignore:<reason>`: a reason for Ignore is worth
  asking for; re-reviews show it next to any finding that comes up again. For
  Defer, also follow "Items" in `skills/review/tracking.md`, with the finding
  as the source (`<run> N`); its Path and Open come from the reason and the
  discussion.

A discussion's Notes entry records what was decided, not the conversation. Write
it like this:

```
2026-10-08, decided in discussion:
1. Imported contacts keep the source system's id in `external_id`; rows
   without one get a generated 'import-<row>' id, so duplicates stay visible
   instead of merging silently.
2. One shared IMPORT_ID_PREFIX constant, also used by the CSV exporter's
   round-trip check.
3. Out of scope: merging duplicates already in the database (deferred under
   finding 41).
First confirm the importer sees the source id for every supported file format.
```

A dated first line; a numbered list of decisions in plain words, with the
specific values that were agreed (names, constants, test data); what is out of
scope and where it went; any precondition to check first. About fifteen lines at
most, no code blocks. Refer to other findings by number. Show the user the entry
before writing it when the discussion was long.

### Rules beyond the finding

Some decisions reach past their finding: a rule that would settle similar
findings the same way, or a change to what the branch is for. Record those as
well, without being asked, as soon as the decision is recorded, as "Guidance
from answers" in `skills/review/tracking.md` describes: its routing says
where each goes (a `###` rule under Guidance in the branch notes, a guidance
record, a dated Purpose line naming the finding, or a decision), and the format
of a branch rule is in Branch notes there. Every review and fix gets the rules
through the guidance file, so a rule recorded now keeps the next run from
raising the same question. A decision that only settles its own finding (this
card's tweak, a one-off exception) stays in the finding's Notes. Do not ask
first; say in one line what the rule says and how far it reaches, so the user can
correct it.

## What never happens here

- No edits to code in this session; fixes go through the fix skill.
- No commits except through the fix skill, which follows the user's commit
  rules.
- No changes to an instruction the user set, except: the fix skill moves a `fix`
  to `discuss` when the fix is out of scope or its tests fail, with the reason
  as the note; and the check under Findings whose code moved marks a finding
  fixed by a later commit, or moves a `fix` or `noted` finding to `discuss` when
  that commit changed what its fix should be.

---
name: deliberate
description: Weigh the options for one choice with the user and recommend one - what is decided, the questions that would reorder the options, the priority profile, each option in its smallest form, the facts checked, a ranking and what would flip it. Use when the user says "deliberate on", "weigh the options", "help me decide", "what should we do about", or "refine F3" / "refine Q3"; and when review-triage (a contested Discuss), design-check (a question that needs a choice, or Refine), writing-code (a stopped piece's question), pass (an item that needs a choice), review-followups (Refine, or a choice the item leaves open), or review-fix (a fix that changes a contract or product behavior) runs it. Not for an item marked Fix as recommended; that is decided.
allowed-tools: Bash(python3 *), Bash(git *), Read, Write, Grep, Glob, Agent
---

# Deliberate

When talking to the user, name ids and codes as "Naming things to the user" in `skills/review/tracking.md` describes: every id (R19, B15, M1, F3, Q3, P3, I7, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

If this conversation was compacted, re-read this file before going on: a
compacted skill may be cut short, and the steps it drops are the ones that
keep the work safe. Prefer `/clear` at a natural boundary to compaction; the
`checkpoint` skill writes down what is pending first.

One way to weigh a choice before the user makes it, so a finding, a design
question, and a stopped piece are judged alike. The session runs it, not an
agent: the choice is the user's, and its context is in this conversation. It
ends when the user decides. Recording the answer stays with the skill that ran
it.

`records.py` below is `${CLAUDE_PLUGIN_ROOT}/scripts/records.py`.

## When it runs

- a finding marked Discuss that is contested (`review-triage`);
- a design question that needs a choice, or one marked Refine
  (`design-check`);
- the question a delegated piece stopped on, or a choice to settle before
  delegating (`writing-code`);
- a pass item that needs a choice nothing settles (`pass`);
- a follow-up marked Refine, or one that leaves a choice open
  (`review-followups`);
- a fix that changes a contract or product behavior (`review-fix`);
- the user asking directly.

Fix as recommended never runs it: the user has already chosen.

An item is too small for it when it has one realistic option, when a record or
a guidance rule already settles it, or when a wrong pick costs minutes to
undo. Then say so in one line, give the recommendation and why, and go to
step 7.

## Inputs

- The item: a finding card (its entry in `merged.md`, the verifier's note, the
  user's notes), a design question in a check file, a stopped piece's question
  with its brief, a follow-up with its source change, or a pass item.
- The guidance file: `records.py guidance <worktree> [--area <area>] --out
  <file>`. Use the one the calling skill wrote when there is one.

## Steps

1. **Frame.** Say in one sentence what is decided, and what a wrong choice
   costs: rework, a migration, a contract another repository depends on,
   behavior users see.
2. **Decisive questions.** Ask only the ones whose answers would reorder the
   options: is the code deployed or new on this branch, is it in the branch's
   scope, does the codebase have a precedent, is it on a hot path, does it
   cross repositories. Answer each from the guidance file, the records, and
   the code first, with its source. Ask the user only what none of them
   answers.
3. **Profile.** Pick the priority profile the answers imply:
   - net-new code: the plainest shape, reuse, one source of truth (the
     `writing-code` skill);
   - changing live code: "Changing live code" in the `writing-code` skill;
   - a fix outside the branch's scope: propose it, do not change it (Branch
     scope in `skills/review/tracking.md`);
   - a contract across repositories: what each side sends and accepts, and
     the follow-ups the change owes (Follow-ups in `tracking.md`).
   Guidance rules adjust the profile's weights. A decisive answer can override
   the profile; say so when it does.
4. **Options, each in its smallest form.** List the realistic options, usually
   two to four, including Defer or Ignore when they are real. Shrink each to
   its smallest form before weighing it: the least change that still gets the
   option's benefit. For live code, find it as "Changing live code"
   describes. Judged in the abstract, the right fix often looks riskier than
   its smallest form is, so never weigh a full form against a workaround.
5. **Verify.** Check each fact the ranking rests on: a caller count, a
   precedent, whether anything else reads a column. When a fact needs more
   than a few files read, ask one quick `Explore` agent and keep only its
   answer. A fact that turns out wrong sends you back to step 3.
6. **Rank and recommend.** Rank the options under the profile, recommend one,
   and say what would flip the ranking.
7. **After the user decides.** Record the answer where its source records
   answers: the calling skill's recording step, or for a choice the user
   brought directly, a decision record through the `feature` skill. Then check
   whether the answer carries guidance, a rule beyond this item, and route it
   as "Guidance from answers" in `skills/review/tracking.md` describes.

## The decision brief

What the user sees after step 6, in about fifteen lines: what is decided, the
decisive questions with their answers and sources, the profile, the options in
smallest form, and the ranking with what would flip it. Quote code only when
it settles a question.

```
Deciding: where the importer keeps the source system's contact id.
A wrong choice costs: a backfill of deployed contact rows.
- Deployed? Yes: contacts.external_id is on main (git log).
- In scope? Yes: Purpose lists the importer as changed on purpose.
- Precedent? The CSV exporter already reads external_id (exporter.ts:88).
Profile: changing live code.
(a) Set external_id only when the source sends one; other rows unchanged.
(b) A new import_source_id column, read only by the importer.
(c) Defer: keep generated ids until the merge feature.
Recommend (a): it adds to what external_id already means and needs no
migration. Would flip it: a reader of external_id that assumes imports
never set it.
```

## Several items waiting

When several items wait for a choice (a discussion queue, a check's open
questions, more than one stopped piece), prepare their briefs in parallel and
walk them one at a time:

1. Launch one `general-purpose` subagent per item, all in one message, with
   `model: opus`. Give each the item by path, the guidance file, and steps 1,
   2, 4, and 5 above as its task, and have it write
   `<scratchpad>/deliberate/<item>.md`: the frame, the facts with their
   sources, the options in smallest form, and the decisive questions it could
   not answer. It does not recommend, and edits no code or records.
2. Walk the items in the calling skill's order. For each, read only its brief
   file and ask the decisive questions it left open. Then pick the profile
   (step 3), verify any fact an answer changed (step 5), rank (step 6), show
   the decision brief, and take the decision through step 7. Drop the item's
   detail before the next.

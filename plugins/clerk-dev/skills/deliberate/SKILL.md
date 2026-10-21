---
name: deliberate
description: Weigh the options for one choice with the user and recommend one - what is decided, the questions that would reorder the options, the priority profile, each option in its smallest form, the facts checked, a ranking and what would flip it. Use when the user says "deliberate on", "weigh the options", "help me decide", "what should we do about", or "refine F3" / "refine Q-3"; and whenever a skill or the session has a recommendation the user may accept as is (a Discuss or Refine item, a design question, a stopped piece, a pass or follow-up item, a fix, suggested marks for unmarked findings). It sizes the work itself, so trivial items cost one line. Not for an item marked Fix as recommended; that is decided.
allowed-tools: Bash(python3 *), Bash(git *), Read, Write, Grep, Glob, Agent
---

# Deliberate

When talking to the user, follow "Talking to the user" in `skills/review/tracking.md`: the feature first, the bookkeeping last or not at all, and ids named: every id (DEC-19, BUILD-15, MILE-1, F3, Q-3, PASS-3, IDEA-7, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

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

Every recommendation the user may accept as is: a Discuss or Refine item, a
design question, a stopped piece's question or a choice to settle before
delegating, a pass item, a follow-up, a fix, marks a session suggests for
findings the user has not marked, and the user asking directly. Calling skills
send each such item here without judging whether it needs weighing; step 0
judges that.

Fix as recommended never runs it: the user has already chosen.

## Inputs

- The item: a finding card (its entry in `merged.md`, the verifier's note, the
  user's notes), a design question in a check file, a stopped piece's question
  with its brief, a follow-up with its source change, or a pass item.
- The guidance file: `records.py guidance <worktree> [--area <area>] --out
  <file>`. Use the one the calling skill wrote when there is one.

## Steps

0. **Size.** Before anything else, decide how much the item needs:
   - trivial: one realistic option, a record or guidance rule already settles
     it, or a wrong pick costs minutes to undo. Say so in one line, with the
     recommendation and the facts you checked, and go to step 7;
   - several items at once: sort them as "Several items waiting" describes;
   - a single real choice: steps 1 to 7.
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
   When the user brought the choice directly rather than through another
   skill, run a closing checkpoint, as "Closing checkpoint" in the `checkpoint` skill describes.

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
questions, more than one stopped piece, a set of suggested marks), sort them
first, then brief only the borderline ones:

1. Sort in one pass. Gather the facts the items share (the files the next
   piece touches, the branch's scope, the guidance file) once, and judge each
   item against them as step 0 does. Settle the obvious ones in a line each,
   with the recommendation and its reason, and take them through step 7 with
   the user together. The rest are borderline.
2. For the borderline items, launch one `general-purpose` subagent per item, all in one message, with
   `model: opus`. Give each the item by path, the guidance file, and steps 1,
   2, 4, and 5 above as its task, and have it write
   `<scratchpad>/deliberate/<item>.md`: the frame, the facts with their
   sources, the options in smallest form, and the decisive questions it could
   not answer. It does not recommend, and edits no code or records.
3. Walk the borderline items in the calling skill's order. For each, read only its brief
   file and ask the decisive questions it left open. Then pick the profile
   (step 3), verify any fact an answer changed (step 5), rank (step 6), show
   the decision brief, and take the decision through step 7. Drop the item's
   detail before the next.

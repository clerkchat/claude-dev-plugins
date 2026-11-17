---
name: design-check
description: Check a feature's design, plan, pieces, or brief record against the review lenses before the code exists, or survey existing code for the refactors worth doing first and the traps already in it before a change is defined, and work through what comes back. Use when the user says "check the design", "design-check BRIEF-10", "run the lenses on the brief", "run the lenses on the spec", "what should we settle before building this", "poke holes in this", "review the plan", "go through the design questions", "survey <paths | record>", "survey this module", "what should we refactor first in <paths>", "survey the code for BRIEF-85", or "walk the survey". Not for reviewing a change; that is /clerk-dev:review.
argument-hint: "[<record id>[,<record id>...] | survey <paths | record id> [--cap <n>]] [--lenses a,b | +a | -a] [walk]"
allowed-tools:
  - Bash(python3 *)
  - Bash(git diff *)
  - Bash(git log *)
  - Bash(git rev-parse *)
  - Bash(git show *)
  - Bash(git status *)
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Agent
---

# Design check

When talking to the user, follow "Talking to the user" in `skills/review/tracking.md`: the feature first, the bookkeeping last or not at all, and ids named: every id (DEC-19, BUILD-15, MILE-1, BL-4, Q-3, PASS-3, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

If this conversation was compacted, re-read this file before going on: a
compacted skill may be cut short, and the steps it drops are the ones that
keep the work safe. Prefer `/clear` at a natural boundary to compaction; the
`checkpoint` skill writes down what is pending first.

Runs the review lenses in design mode (see Design mode in the `review-protocol`
skill) on feature records (see `skills/feature/records.md`), or in survey mode
(see Survey mode there) on existing code, and writes the items they raise to a
check file in the hub. Then, when asked, walks the user through them and
records each answer.

`records.py` below is `${CLAUDE_PLUGIN_ROOT}/scripts/records.py`.

## Running the lenses

Each kind of run below picks what it runs on and its lenses and says them in
a line each, the lenses by their plain names from `skills/review/routing.md`,
then goes on without waiting for approval. It runs these steps with its own
parts: the area, the prompt, the block it reads back, its sort and earlier
runs, the file's name and header, and the report's counts. A record's
repository is its `repo` field, at the worktree the workspace file lists for
it, defaulting to this worktree.
Set `<checks>` to the output of `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/paths.py <hub> checks-dir`.
The kind names its file `<checks>/<run>.md` and gives the `<subject>` it is
on; the run's own files go in `<checks>/<run>/`.

1. **Guidance.** Before launching, write the guidance file of each repository
   the prompt names, with `records.py guidance <that repository's worktree>
   [--area <the kind's area>] [--context <its CONTEXT>]
   --out <checks>/<run>/guidance-<repo>.md`: its branch
   scope, its branch guidance, the feature's active guidance, and its review
   context's Known noise.
2. **Launch.** Launch one `clerk-dev:lens-<lens>` agent per lens, all in one
   message so they run in parallel, each with the kind's prompt.

   Run the lenses whose items most often must be settled first, `contracts`,
   `cross-repo`, `rollout`, `tenancy`, and `security`, with `model: fable`
   when they are in the set, falling back to Opus at the same effort as Model
   fallback in the `review` skill describes; every other lens uses the agent's
   own model. A question settled before building costs far less than the
   rework it saves.
3. **Keep the raw output.** Write each agent's reply verbatim to
   `<checks>/<run>/raw/<lens>.md` with
   `${CLAUDE_PLUGIN_ROOT}/scripts/agent-reply.py <output_file> --out <path>
   --header "# <lens> on <subject>" --header "usage: <tokens>, <duration>"`, where
   `output_file` is the one the Agent tool returned for that agent and the
   usage comes from its completion notice; do not copy replies by hand. Then
   count the items in the kind's block. When a lens has none but its reply has
   a different block (a `findings` block) or a broken one, resume that agent
   once asking for the kind's block only; if it still has none, say so in the
   report. Zero items in a well-formed block is
   a valid answer.
4. **Merge** the items:
   - Merge items that say the same thing from different lenses into one,
     listing every lens.
   - Drop any an active decision or active guidance already answers, unless
     the agent says the code shows it cannot hold; list each dropped item in
     the file's Dropped section with the record that answered it, so the user
     can contest the drop.
   - Compare each remaining item with the closed items of earlier runs on the
     same target (the kind says which files those are), by meaning, not
     wording. A match is not a new item: list it
     under the file's "Seen before" section with the earlier id and outcome
     ("Do exports expire? BRIEF-9-1.Q-4: no change, deleted with the report"),
     unless the target has changed in a way that reopens it; then keep it, and
     cite the earlier one in its Why.
   - Sort by the kind's weight order, then its location key.
5. **Write** the kind's file, its header as the kind describes. Fields are a
   nested list so a Markdown formatter keeps the layout, as in follow-ups.
   `Instruction` is empty until the user decides; `Status` and `Outcome`
   follow "Items" in `skills/review/tracking.md`. A `Usage:`
   line under the header gives each lens's tokens and duration from the
   completion notices ("Usage: completeness 24k 25s, llm-agent 79k 177s"), so
   the cost of each run is visible per lens. Then run
   `${CLAUDE_PLUGIN_ROOT}/scripts/items.py validate <the file>` and
   `records.py index <worktree>`. When validate names a field, correct it
   from that lens's raw reply and run validate again; name in the report any
   field that still fails, rather than changing it to pass.
6. **Report** in a few lines: the path, the kind's counts, any lens with no
   usable output, and the items the kind lists one line each. Offer to walk
   them. Do not start answering them yourself.

## Running a check

A check runs the lenses in design mode on feature records, through "Running
the lenses", with these parts.

- **Records.** With ids given, check those. Otherwise take the record the
  conversation is about; failing that, the newest active brief, plan, or design
  in the area the conversation is about (`records.py list <worktree> --active
  --area <area>`), or feature-wide when it is about the whole feature; ask
  when that is unclear and several areas have candidates. Supporting records are the ones the checked records name in
  `from` or cite by id, plus the active decisions; pass them, but do not
  check them.
- **Lenses.** Pick them as `skills/review/routing.md` "Design checks"
  describes, applying any `--lenses` argument.
- **Prompt.**

  ```
  TASK: design-check
  RECORDS: <absolute paths>
  SUPPORTING: <absolute paths, or none>
  REPO: <absolute path of the repository the records are about>
  CONTEXT: <<git common dir>/clerk-dev/repo-context.md of that repository, or none>
  GUIDANCE: <path of that repository's guidance file>
  WORKSPACE: <path of the workspace file, or none>
  ```

  The records' repository is found as "Running the lenses" says. Records **span
  repositories** when the workspace lists more than one repository and either
  the checked records have different `repo` values, or a checked plan, design,
  or pieces record assigns work to more than one of them. Then replace
  `REPO`, `CONTEXT`, and `GUIDANCE` with one block per repository involved:

  ```
  REPOSITORY:
    NAME: <repo name from the workspace>
    REPO: <absolute worktree path>
    CONTEXT: <its repo context, or none>
    GUIDANCE: <path of its guidance file>
  ```

- **Block.** The `questions` block.
- **Sort and earlier runs.** Sort by weight (settle-first, worth-settling,
  note), then by record and section. Earlier runs are the index's checks of the
  same records.
- **Area.** The area of the checked records.
- **File.** `<subject>` is the first checked record's id (BRIEF-13;
  `records.py names` gives its type). `<run>` is `<subject>-<k>`, where `<k>`
  is one more than the highest existing check of it, counting older files
  named with its old id (R13-1.md). Its `Checked <date>: BRIEF-13, DESIGN-10.` line names every
  checked record, so the feature index lists the check under each. Format
  below.
- **Report.** The counts by weight, and the settle-first questions.

Check files are not records: they have no record id and are not superseded. A
question is cited as `BRIEF-13-1.Q-3`, or `Q-3` when the check in hand is clear.

## Running a survey

A survey runs the lenses in survey mode on existing code, before a change to
it is defined, through "Running the lenses", with these parts. It is asked as
`survey <paths | record id> [--cap <n>]`, or in words ("survey this module",
"what should we refactor first in src/export", "survey the code for
BRIEF-85").

- **For.** `FOR` is the record given as the target, else the record the
  conversation is about, else `none`. The repository is `FOR`'s, else this
  worktree.
- **Target.** Paths: each a file or directory under the repository. A record:
  the paths in backticks in its body that exist under the repository; when it
  names none, say so, ask for paths, and stop.
- **Files.** `<k>` is one more than the highest existing survey's. Resolve the
  target with `${CLAUDE_PLUGIN_ROOT}/scripts/survey-files.py <repository>
  <path>... [--cap <n>] [--exclude <glob>]... --out
  <checks>/SURVEY-<k>/files.txt`, which expands each
  directory to its tracked files, drops what `measure-patch.py`'s default
  exclusions drop, and writes the absolute paths, sorted, one per line; that
  file is `FILES`. Pass as `--exclude` the globs of the `tests` and `config`
  categories, classified as "Categories and path heuristics" in
  `skills/review/routing.md` says: the repo context's `## Slices` globs of
  those layers first, then each heuristic of those two rows with a `*` added
  at either end that lacks one (`.test.` as `*.test.*`, `.env*` as
  `*.env*`). The script applies them only to files a directory expanded to,
  so a file the target names directly stays. The cap is 40 files, or
  `--cap`. Over it, the script writes nothing and prints the directories with
  their file counts: show them, ask the user to narrow the target, and stop
  before any lens runs; never truncate the list. On any other error, show it
  and stop. On success it prints the file count with the files' total lines
  and estimated tokens: show that line to the user before any lens runs.
- **Lenses.** Pick them as `skills/review/routing.md` "Surveys" describes,
  applying any `--lenses` argument, and name each trap lens with the category
  behind it.
- **Prompt.**

  ```
  TASK: survey
  FILES: <absolute path of files.txt>
  TARGET: <the target as the user gave it>
  FOR: <the record's id and absolute path, or none>
  REPO: <absolute path of the repository>
  CONTEXT: <<git common dir>/clerk-dev/repo-context.md of that repository, or none>
  GUIDANCE: <path of that repository's guidance file>
  WORKSPACE: <path of the workspace file, or none>
  ```

- **Block.** The `survey` block.
- **Sort and earlier runs.** Sort by weight (do-first, worth-doing, note), then
  by file and line. Earlier runs are the surveys whose `Surveyed` line names a
  path in this target.
- **Area.** `FOR`'s area, or none.
- **File.** `<run>` is `SURVEY-<k>` and `<subject>` the target as given.
  Format below.
- **Report.** The counts by weight and by kind, and the do-first items. A
  survey with no items still writes its file, with the header, `Surveyed` and
  `Usage` lines and no items, and the report says per lens that it found
  nothing. A lens whose reply has no usable `survey` block after the retry in
  step 3 of "Running the lenses" is named in the report as not run, never
  counted as no items.

A survey file is a check file over code: cited as `SURVEY-2`, its items as
`SURVEY-2.Q-3`.

## Check file

```markdown
# Design check: BRIEF-13 Design mode for lenses

Checked 2026-10-16: BRIEF-13. Supporting: DESIGN-11, DEC-2, DEC-3. Lenses: completeness,
spec-conformance, design, naming-concepts.
Usage: completeness 24k 25s, spec-conformance 27k 28s, design 26k 30s,
naming-concepts 22k 25s.

- [ ] Q-1. Should check files appear in the feature index?
  - Lens: completeness
  - Where: BRIEF-13 Open items
  - Weight: worth-settling
  - Why: Without an index entry, a later session finds the check only by
    listing the checks folder.
  - Suggestion: (a) List them under Records; (b) a separate Checks section.
  - Evidence: /Users/me/src/plugins/scripts/records.py:92
  - Instruction:
  - Status: open

## Seen before

- Do exports expire? BRIEF-9-1.Q-4: no change, deleted with the report (edge-cases).

## Dropped

- Should exports poll? Answered by DEC-5 (completeness).
```

## Survey file

```markdown
# Survey: src/export

Surveyed 2026-10-30: src/export. For: BRIEF-85. Lenses: tech debt, design and
reuse, naming, tenant isolation.
Usage: tech-debt 41k 62s, design 38k 55s, naming-concepts 30k 40s, tenancy
52k 90s.

- [ ] Q-1. Export query built in two places
  - Lens: tech-debt, design
  - Kind: refactor
  - Where: /Users/me/src/app/src/export/job.ts:42
  - Weight: do-first
  - Why: The next change adds a filter to both copies; one query helper makes
    it one edit.
  - Suggestion: Extract the query into `src/export/query.ts` and call it from
    the job and the controller.
  - Size: small
  - Evidence: /Users/me/src/app/src/export/job.ts:42,
    /Users/me/src/app/src/export/controller.ts:88
  - Instruction:
  - Status: open
```

Seen before and Dropped follow as in a check file. It differs from a check file in its name, its `Surveyed` line in place of
`Checked` (the paths as given, or the record id and its paths; then `For:`),
Kind and Size, and Where pointing at code rather than a record section. When lenses merged into one item
disagree on Kind, it is `trap`. Where is the single `path:line` the lens
gave first, never a range.

## Walking the questions

When the user asks to go through them ("walk the design questions", "go
through Q-3", "walk the survey"), take the open items in order, settle-first
or do-first first, one at a time. Sort them and prepare the borderline ones first, as "Several items
waiting" in the `deliberate` skill describes.

1. Show the question with its why and suggestion, briefly, and the code or
   record it points at when that helps. Weigh it with the `deliberate` skill,
   which sizes it first.
2. Discuss until the user decides, and record the instruction with
   `${CLAUDE_PLUGIN_ROOT}/scripts/items.py set <check file> Q-3
   "<instruction>" [--note "..."]`, in the words of "Items" in
   `skills/review/tracking.md` (Fix as recommended adopts the suggestion).
3. Record the answer where it belongs:
   - a choice: a decision record (`records.py new <worktree> decision "..."
     --from <the checked record's id>`, with `--supersedes` when it changes an active decision,
     restating it in full as "When a record changes another" in
     `skills/feature/SKILL.md` describes);
   - a gap in a brief: an open item added to the brief (allowed at any time),
     or, when the gap changes the requirements or approach, a new brief that
     supersedes it;
   - nothing to change: the reason, in one line.
4. Close it: `items.py status <check file> Q-3 fixed --ref "<record id or
   reason>"` (`wont-fix` for Ignore); for Defer, follow "Items" in
   `skills/review/tracking.md`, with the question as the source. Then move on.
   Discuss and Refine leave it open until decided.

A survey item takes steps 1 and 2; in place of 3 and 4, it closes by its
instruction:

- `Fix as recommended` or `Fix as noted` makes it a constraint on the next
  change: it stays `open` until the next design or brief cites it, as
  "Writing each type" in the `feature` skill says, and closes
  `fixed --ref <that record>`. A constraint that is a choice in its own right
  becomes a decision record now, as for a question, and closes with it.
- A small trap may instead be fixed at once: hand it to the `building`
  skill's Intake as a request, quoting the item, and close it
  `fixed --ref <sha>` with the commit.
- `Defer` parks an idea, as `Defer` under "Items" in
  `skills/review/tracking.md` says for a survey item.
- `Ignore` closes it `wont-fix` with why; `Discuss` and `Refine` leave it
  open.

An item a second survey of the same paths finds again is under that survey's
Seen before, by the merge in "Running the lenses"; the walk adds no rule for it.

Records written while walking follow the `feature` skill's rules. When the user's answer carries guidance (a rule beyond this case), or says
`guidance: ...`, record it as "Guidance from answers" in
`skills/review/tracking.md` describes, and say so in one line.
When the walk's last item is settled, look back over it as "Lessons
from a discussion" in `skills/review/tracking.md` describes, then
run a closing checkpoint, as "Closing checkpoint" in the `checkpoint` skill describes.

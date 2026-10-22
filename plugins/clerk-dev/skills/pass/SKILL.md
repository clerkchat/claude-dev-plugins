---
name: pass
description: Write code in focused passes, one value at a time (edge cases, error handling, security, observability, DRY, and so on), each ended by a pass review with only that pass's lenses. Use when the user says "do an edge-cases pass", "make a security pass on this", "pass for observability", "what passes does this need", "guide me through a tests pass", "check the pass", "review the pass", "abandon the pass", or "how are the passes doing". Not for reviewing a whole branch (that is /clerk-dev:review) or fixing review findings (review-fix).
argument-hint: "[<pass> [on BRIEF-<n> | on <paths>] [guide]] | suggest [BRIEF-<n>] | check PASS-<n> | abandon PASS-<n> | list | stats"
allowed-tools: Bash(python3 *), Bash(git *), Bash(claude -p *), Read, Edit, Write, Grep, Glob
---

# Passes

When talking to the user, follow "Talking to the user" in `skills/review/tracking.md`: the feature first, the bookkeeping last or not at all, and ids named: every id (DEC-19, BUILD-15, MILE-1, F3, Q-3, PASS-3, IDEA-7, finding numbers) gets a gloss of what it is on its first mention in each message, including in relayed subagent reports, list items, and labels; get the glosses with `records.py names`.

The catalogue of passes, their lenses, and how to suggest them for a piece is
`passes.md` next to this file. The log is `.clerk-dev/passes.md`, managed only
through `${CLAUDE_PLUGIN_ROOT}/scripts/passes.py` (below, `passes.py`), which
reads it strictly and refuses unsafe steps; when it refuses, say why in one line
and ask, never edit the log around it. A lens's author-side text is printed by
`${CLAUDE_PLUGIN_ROOT}/scripts/lens-section.py <lens>`; never read the agent
files themselves, which are reviewer prompts.

A pass covers one worktree. If this conversation was compacted mid-pass, re-read
this file before going on.

## Suggesting passes

"What passes does this need": find the piece (a brief record the user names or
the conversation is about, else the paths the user names, else the branch's
changes), and suggest passes as `passes.md` describes. Show the list with one
reason each, in a few lines. Do not start one.

## Running a pass

Inside a milestone (the `building` skill's Milestones), the happy-path pass
is the draft: start it, then build it in handoffs as that skill describes
(logged in the build log) instead of listing items, and end it when
the draft is whole. The other passes run as below, one after another, with the
milestone's stopping rules: stop for an implementer's question, for a check
with findings rated major or blocker (`grep -cE "severity: (blocker|major)"
<run>/merged.md`), and for any finding in a required pass.

The request to run a pass is the go-ahead to edit and commit for it, under the
commit rules below.

1. **Start.** Resolve the focus to a catalogue pass and its lenses, keeping only
   those whose categories the piece touches. Run `passes.py start <worktree>
   <pass> --lenses <a,b> --mode <claude|guide> [--piece BRIEF-<n>]`. When it refuses
   for uncommitted tracked files, show them and ask whether to commit them
   first or leave them out (`--leave-out`); when another pass is open, ask
   whether to end or abandon it.
2. **List the work.** Print each lens's Pass mode text, read the piece's brief
   (if any) and the code the piece touches, and write what this pass will do in
   this code as items: `passes.py item <worktree> PASS-<n> "<what, with
   path:line>"`, one per change, specific enough that someone else could do it.
   Leave out anything another pass in the catalogue owns. Show the items in a
   few lines.
3. **Write.** Follow the `writing-code` skill for the code and the `building`
   skill for the handoffs throughout.
   - Claude mode: do the items, one coherent change per commit, handed off as
     the `building` skill describes: group items that change the
     same code into one handoff, send a `clerk-dev:builder` per handoff whose
     first line is `Source: pass`, with the `building` skill's Pass entry from By kind
     pasted word for word, the lens's Pass mode text, and the items as its
     goal, at the model and effort the handoff calls for (a pass's items are
     usually sonnet, medium; prep refactors that reshape shared code, opus,
     high), read each report as the `building` skill's "After each handoff" describes
     (a `scope: out` included), review, run the tests, and commit each.
     Items of a few lines are done inline. Mark each item as it lands
     (`passes.py done <worktree> PASS-<n> <k>`, or `--na "<why>"` when it turns out
     not to apply). Stay inside the items: something outside them goes in a
     line to the user, not into this pass. An item the pass cannot finish is
     deferred as "Items" in `skills/review/tracking.md` describes, with the
     pass item as the source (`PASS-<n>.<k>`).
   - Guide mode: stop after the list. The engineer writes and commits; when
     they say they are done, mark the items they name and go on.
4. **End.** `passes.py end <worktree> PASS-<n>`. It refuses while tracked changes
   are uncommitted; it reports items not done and whether the pass made no
   commits (then there is nothing to check; say so and stop).
5. **Check.** The pass review. Get the range with `passes.py range <worktree> PASS-<n>` (it refuses
   when the pass was rebased; offer to abandon it or re-anchor by hand). Then
   run the review headless, so its orchestration stays out of this session:

   ```
   claude -p "/clerk-dev:review <start>..<end> --standalone --pass PASS-<n> --lenses <lenses> --no-pr-comments"
     --allowedTools "Bash(git *)" "Bash(gh pr *)" "Bash(python3 *)" "Bash(ln *)" "Bash(mkdir *)" Read Grep Glob Agent Write
   ```

   from the worktree, in the background, output to a log in the scratchpad.
   When it ends, take the run directory from its `RUN_DIR:` line (the run label
   is its last path segment), read only its `summary.md`, count the findings
   per lens from `merged.md` (`grep -c "lens: <lens>"`), and record the result:
   `passes.py check <worktree> PASS-<n> --run <label> --ran <lenses that ran>
   --findings <lens>=<n>,...` (or `--result empty|error`). It exits non-zero
   when a requested lens did not run; say which.
6. **Report** in a few lines: the commits, items done and not applicable, and
   the pass review's findings by lens with the run label. The pass ends here.
   Findings are fixed through `review-fix` with the run label ("fix 3
   <label>") or `review-triage`; never start fixing them, or a second pass, on
   your own. After the report, run a closing checkpoint, as "Closing checkpoint" in the `checkpoint` skill describes.

## Answers during a pass

When an item needs a choice, or an implementer stops on one, weigh it with
the `deliberate` skill before asking. Put the answer in the
implementer's handoff, and when it changes what the pass does, in its items
(`passes.py item`, or `passes.py done ... --na "<why>"`).

When the user's answer carries guidance (a rule beyond this case), or says
`guidance: ...`, record it as "Guidance from answers" in
`skills/review/tracking.md` describes, and say so in one line.

## Commit rules

Commit as the Commit step of "After each handoff" in the `building` skill
describes, adding only the files this pass changed and never files left out.
A message never names the pass or its id. Never push or amend; a pass's range
depends on its commits staying put. A commit that builds a record
the pass's handoff names is logged as "The build log" in the `building`
skill describes.

## Other requests

- "Check the pass", "review the pass": steps 5 and 6 for an ended pass.
- "Abandon the pass": `passes.py abandon <worktree> PASS-<n> --note "<why>"`. Its
  commits stay; say so.
- "List the passes", "how are the passes doing": `passes.py list` or
  `passes.py stats`, shown as they are. `stats` counts findings per lens across
  checked passes and the plugin version each used, the signal for whether a
  lens's Pass mode text works.

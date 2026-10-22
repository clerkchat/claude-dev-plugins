#!/usr/bin/env python3
"""Manage a worktree's follow-ups file, <worktree>/.clerk-dev/followups.md.

Follow-ups are work this repository owes because of a change somewhere else:
a contract another repository changed, or a shape another repository wants
from this one. Each states the contract and the need, never the change to make
here or its size; this repository sizes it. The file is a Markdown checkbox
list, one item per top-level checkbox with its fields as a nested bullet list,
so a Markdown formatter keeps the layout; editing boxes by hand is fine.

Usage:
  followups.py add WORKTREE "the need" --from "<repo> <sha>" --contract "changed: <old to new>" [--finding "<repo> N"]
  followups.py add WORKTREE "the need" --from "<repo> <sha>" --contract "wanted: <shape, and how it differs from today>"
  followups.py list WORKTREE [--open]
  followups.py close WORKTREE F3 [--ref <sha or note>] [--status fixed|wont-fix|deferred]
  followups.py reopen WORKTREE F3
  followups.py set WORKTREE F3 "Refine" [--note "..."]

Entry format:
  - [ ] F3. A download poll without exportId is now refused with 400.
    - From: api 7c1e2ab
    - Contract: changed: GET /reports/:id/download: took no parameters, now requires the exportId that POST /reports/:id/exports returns
    - Finding: api 8
    - Added: 2026-10-07
    - Instruction: Refine
    - Status: open
    - Outcome: 2026-10-09 in 1a2b3c4   (once closed)
"""
from records import load_script
import ids

items = load_script("items.py")

HEADER = """# Follow-ups

Work this repository owes because of changes elsewhere. Kept by the review
plugin; ticking boxes by hand is fine. Each item says where it came from, its
contract, changed (old to new) or wanted (the shape another repository needs,
and how it differs from today's), and as its text the need: the behavior this
repository must now handle, or what the other repository builds against. This
repository sizes the change. Instruction and Status use the words in the
plugin's tracking.md "Items"; a blank instruction means meet the need as
written.

"""

LIST = items.WorktreeList("followups.md", ids.FOLLOWUP, HEADER, extras=("Contract", "Finding"), required=("Contract",), legacy_outcome="Done")
read = LIST.read

if __name__ == "__main__": LIST.main("followups.py")

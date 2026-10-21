#!/usr/bin/env python3
"""Manage a worktree's follow-ups file, <worktree>/.clerk-dev/followups.md.

Follow-ups are work this repository owes because of a change somewhere else,
usually a contract change made while fixing a review finding in another
repository. The file is a Markdown checkbox list, one item per top-level
checkbox with its fields as a nested bullet list, so a Markdown formatter keeps
the layout; editing boxes by hand is fine.

Usage:
  followups.py add WORKTREE "what to do" --from "<repo> <sha>" [--contract "..."] [--finding "<repo> N"]
  followups.py list WORKTREE [--open]
  followups.py close WORKTREE F3 [--ref <sha or note>] [--status fixed|wont-fix|deferred]
  followups.py reopen WORKTREE F3
  followups.py set WORKTREE F3 "Refine" [--note "..."]

Entry format:
  - [ ] F3. Send exportId back when polling report downloads.
    - From: api 7c1e2ab
    - Contract: POST /reports/:id/exports accepts and returns exportId
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
plugin; ticking boxes by hand is fine. Each item says where the change came
from and which contract it touches. Instruction and Status use the words in
the plugin's tracking.md "Items"; a blank instruction means do as written.

"""

LIST = items.WorktreeList("followups.md", ids.FOLLOWUP, HEADER, extras=("Contract", "Finding"), legacy_outcome="Done")
read = LIST.read

if __name__ == "__main__": LIST.main("followups.py")

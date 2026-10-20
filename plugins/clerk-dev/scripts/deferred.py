#!/usr/bin/env python3
USAGE = """Manage a worktree's deferred list, <worktree>/.clerk-dev/deferred.md.

A deferred item is a known gap with a path chosen for now: marking a finding,
question, follow-up, or pass item Defer adds one, and the source's outcome names
it. The file is a Markdown checkbox list in the items format.

Usage:
  deferred.py add WORKTREE "what" --from SRC --path "what was done for now" --open "what is left" [--revisit "when to look again"]
  deferred.py list WORKTREE [--open]
  deferred.py close WORKTREE D3 [--ref <sha or reason>] [--status fixed|wont-fix]
  deferred.py reopen WORKTREE D3
  deferred.py set WORKTREE D3 "Refine" [--note "..."]

SRC is a finding "<run> N", a question "R18-1.Q6", a pass item "P3.4", a piece
"B9", or "this session".
"""
import importlib.util, os

_spec = importlib.util.spec_from_file_location("items", os.path.join(os.path.dirname(os.path.abspath(__file__)), "items.py"))
assert _spec and _spec.loader
items = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(items)

HEADER = """# Deferred

Known gaps with a path chosen for now. Kept by the plugin; ticking boxes by
hand is fine. Each item says where it came from, what was done for now (Path),
what is left (Open), and when to look again (Revisit). Close one as fixed with a
commit, or wont-fix with a reason.

"""

LIST = items.WorktreeList("deferred.md", "D", HEADER, extras=("Path", "Open", "Revisit"), required=("Path", "Open"), closes=("fixed", "wont-fix"))
read = LIST.read

if __name__ == "__main__": LIST.main("deferred.py", USAGE)

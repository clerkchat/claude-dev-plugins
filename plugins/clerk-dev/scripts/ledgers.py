import os
from typing import NamedTuple
from records import hub, load_script, this_repo, workspace, worktrees
import paths

def workspace_rows(wt):
    return {n: os.path.realpath(os.path.expanduser(p)) for n, p in workspace(wt)[1].items()}

def related_worktrees(wt, rows):
    real = os.path.realpath(wt)
    return [(name, path) for name, path in rows.items() if path != real and os.path.isdir(path)]

def builders(wt, rows):
    """(name, path) of the other worktrees building this feature: the
    workspace's rows, and any worktree of this repository whose workspace
    file names this worktree's hub."""
    try: mine = os.path.realpath(hub(wt))
    except SystemExit: mine = ""
    out = list(related_worktrees(wt, rows))
    seen = {os.path.realpath(p) for _, p in out} | {os.path.realpath(wt)}
    for p in (w.path for w in worktrees(wt)):
        if p in seen or not os.path.isdir(p): continue
        try: theirs = os.path.realpath(hub(p))
        except SystemExit: continue
        if mine and theirs == mine and p != mine:
            out.append((f"{this_repo(p, {})} ({os.path.basename(p)})", p)); seen.add(p)
    return out

class BuildLog(NamedTuple):
    name: str
    path: str
    entries: list
    err: str | None
    relinked: list
    unlinked: list

def read_build(wt, name=""):
    try:
        found = load_script("build.py").log(wt)
        return BuildLog(name, wt, found.entries, None, found.relinked, found.unlinked)
    except SystemExit as e: return BuildLog(name, wt, [], str(e), [], [])

def builder_logs(wt, rows):
    return [read_build(p, name) for name, p in builders(wt, rows)]

def read_passes(wt):
    """The pass log's entries, or None with the reason when it cannot be read."""
    p = paths.passes(wt)
    if not os.path.exists(p): return [], None
    try: return load_script("passes.py").read(p), None
    except SystemExit as e: return [], str(e)

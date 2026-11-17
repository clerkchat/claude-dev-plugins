import os
from typing import NamedTuple
from records import git, load_script, this_repo, worktrees
import paths

def workspace_rows(wt):
    return {n: os.path.realpath(os.path.expanduser(p)) for n, p in load_script("records.py").workspace(wt)[1].items()}

def related_worktrees(wt, rows):
    real = os.path.realpath(wt)
    return [(name, path) for name, path in rows.items() if path != real and os.path.isdir(path)]

def builders(wt, rows):
    """(name, path) of the other worktrees building this feature: the
    workspace's rows, and any worktree of this repository whose workspace
    file names this worktree's hub."""
    rc = load_script("records.py")
    try: hub = os.path.realpath(rc.hub(wt))
    except SystemExit: hub = ""
    out = list(related_worktrees(wt, rows))
    seen = {os.path.realpath(p) for _, p in out} | {os.path.realpath(wt)}
    for p in (w.path for w in worktrees(wt)):
        if p in seen or not os.path.isdir(p): continue
        try: theirs = os.path.realpath(rc.hub(p))
        except SystemExit: continue
        if hub and theirs == hub and p != hub:
            out.append((f"{this_repo(p, {})} ({os.path.basename(p)})", p)); seen.add(p)
    return out

def branch_name(wt): return git(wt, "rev-parse", "--abbrev-ref", "HEAD")

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

def final_pass_stands(run):
    report, target = os.path.join(run, "final-review-report.md"), os.path.join(run, "target.txt")
    if not os.path.exists(report): return False
    with open(report, encoding="utf-8") as f: passed = f.readline().strip() == "# Final review: PASSED"
    return passed and os.path.getmtime(report) >= os.path.getmtime(target)

#!/usr/bin/env python3
"""Watch review runs on disk and print one line when their progress changes.

Usage: progress.py (--run RUN_DIR | --worktree NAME=PATH ...) [--since EPOCH]
         [--interval 30] [--heartbeat 120] [--heartbeat-only] [--once]

Meant to run under the Monitor tool while the orchestrator waits on reviewers:
every stdout line is a notification, so it prints only when something changed,
or, when nothing has for --heartbeat seconds, one "still running" line with the
elapsed time. It reads files only and starts nothing.

--run watches one run directory (this session's run). --worktree watches the
run each per-repository session writes in its worktree (feature mode): the
target of <path>/.review/latest once it was created after --since (default:
when this script started). Progress per run is read from what the run writes:
plan.md's instance list against raw/, the verify/ files, and report.md.

--heartbeat-only prints nothing on changes, for a run whose reviewers already
report their own completion to the orchestrator. --once prints the current
line and exits. The script exits when every watched run has its report.
"""
import argparse, os, re, time

def instances(run):
    """Raw files the plan committed to, from the instance table in plan.md."""
    p = os.path.join(run, "plan.md")
    if not os.path.exists(p): return None
    return re.findall(r"\|\s*(raw/[^|\s]+\.md)\s*\|", open(p, encoding="utf-8").read())

def state(run):
    if not run or not os.path.isdir(run): return "not started"
    if os.path.exists(os.path.join(run, "report.md")): return "done"
    vdir = os.path.join(run, "verify")
    checked = len([n for n in os.listdir(vdir) if n.endswith(".md")]) if os.path.isdir(vdir) else 0
    if checked: return f"verifying, {checked} checked"
    if os.path.exists(os.path.join(run, "merged.md")): return "merging findings"
    inst = instances(run)
    if inst is None: return "planning"
    done = sum(1 for r in inst if os.path.exists(os.path.join(run, r)))
    return f"reviewing, {done} of {len(inst)} reviewers done"

def child_run(path, since):
    link = os.path.join(path, ".review", "latest")
    if not os.path.exists(link): return None
    run = os.path.realpath(link)
    return run if os.stat(run).st_mtime >= since or os.lstat(link).st_mtime >= since else None

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run"); ap.add_argument("--worktree", action="append", default=[])
    ap.add_argument("--since", type=float); ap.add_argument("--interval", type=float, default=30)
    ap.add_argument("--heartbeat", type=float, default=120)
    ap.add_argument("--heartbeat-only", action="store_true"); ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    if not a.run and not a.worktree: ap.error("give --run or at least one --worktree")
    start = time.time(); since = a.since or start
    trees = [w.split("=", 1) for w in a.worktree]
    if any(len(t) != 2 for t in trees): ap.error("--worktree takes NAME=PATH")

    def snapshot():
        if a.run: return [("", state(a.run))]
        return [(name, state(child_run(path, since))) for name, path in trees]

    def line(snap):
        return " · ".join(f"{n}: {s}" if n else s for n, s in snap)

    last, last_out = None, start
    while True:
        snap = snapshot()
        now = time.time()
        finished = all(s == "done" for _, s in snap)
        if a.once:
            print(line(snap)); return
        if snap != last and last is not None:
            last_out = now
            if not a.heartbeat_only: print(line(snap), flush=True)
        elif now - last_out >= a.heartbeat and not finished:
            m = int((now - start) // 60)
            print(f"still running ({f'{m} min' if m else 'under a minute'}): {line(snap)}", flush=True); last_out = now
        last = snap
        if finished:
            if not a.heartbeat_only: print(f"all done: {line(snap)}", flush=True)
            return
        time.sleep(a.interval)

if __name__ == "__main__":
    main()

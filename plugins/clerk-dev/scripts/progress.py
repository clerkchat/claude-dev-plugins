#!/usr/bin/env python3
"""Watch review runs on disk and print one line when one moves to its next step.

Usage: progress.py (--run RUN_DIR | --worktree NAME=PATH ...) [--since EPOCH]
         [--interval 30] [--heartbeat 120] [--heartbeat-only] [--once]

Meant to run under the Monitor tool while the orchestrator waits on reviewers:
every stdout line is a notification, so it prints only when a run moves to its
next step (planning, reviewing, merging, verifying, done), or, when none has for
--heartbeat seconds, the same line again. Reviewers finishing within the
reviewing step do not print on their own; their count rides along in the next
line. It reads files only and starts nothing.

A line is compact, for the orchestrator to lay out for the user:
"6 min in · api: reviewing 18/21 (3 min) · clerkai: merging (4 min)". The time
in parentheses is how long that run has been in its current step, read from file
times, so it survives a restart of this script; it is left out under a minute.

--run watches one run directory (this session's run). --worktree watches the
run each per-repository session writes in its worktree (feature mode): the
target of <path>/.review/latest once it was created after --since (default:
when this script started). Progress per run is read from what the run writes:
plan.md's instance list against raw/, merged.md, the verify/ files, and
report.md. The "min in" total counts from --since, else from the run's plan.md,
else from when this script started.

--heartbeat-only prints nothing on step changes, for a run whose reviewers
already report their own completion to the orchestrator. --once prints the
current line and exits. The script exits when every watched run has its report.
"""
import argparse, os, re, time

def instances(run):
    """Raw files the plan committed to, from the instance table in plan.md."""
    p = os.path.join(run, "plan.md")
    if not os.path.exists(p): return None
    return re.findall(r"\|\s*(raw/[^|\s]+\.md)\s*\|", open(p, encoding="utf-8").read())

def mtime(path):
    return os.path.getmtime(path) if os.path.exists(path) else None

def state(run):
    """(step, detail, when the step started or None)."""
    if not run or not os.path.isdir(run): return ("not started", "", None)
    if os.path.exists(os.path.join(run, "report.md")): return ("done", "", None)
    vdir = os.path.join(run, "verify")
    checked = len([n for n in os.listdir(vdir) if n.endswith(".md")]) if os.path.isdir(vdir) else 0
    merged = mtime(os.path.join(run, "merged.md"))
    if checked: return ("verifying", f"{checked} checked", merged)
    inst = instances(run)
    raws = [m for m in (mtime(os.path.join(run, r)) for r in inst or []) if m]
    if merged: return ("merging", "", max(raws, default=None))
    if inst is None: return ("planning", "", None)
    return ("reviewing", f"{len(raws)}/{len(inst)}", mtime(os.path.join(run, "plan.md")))

def child_run(path, since):
    link = os.path.join(path, ".review", "latest")
    if not os.path.exists(link): return None
    run = os.path.realpath(link)
    return run if os.stat(run).st_mtime >= since or os.lstat(link).st_mtime >= since else None

def minutes(sec):
    return f"{int(sec // 60)} min"

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
    began = a.since or (a.run and mtime(os.path.join(a.run, "plan.md"))) or start

    def snapshot():
        if a.run: return [("", state(a.run))]
        return [(name, state(child_run(path, since))) for name, path in trees]

    def line(snap, now, total="{} in"):
        parts = [total.format(minutes(now - began) if now - began >= 60 else "under 1 min")]
        for name, (step, detail, at) in snap:
            s = f"{step} {detail}".strip()
            if at and now - at >= 60: s += f" ({minutes(now - at)})"
            parts.append(f"{name}: {s}" if name else s)
        return " · ".join(parts)

    last, last_out = None, start
    while True:
        snap = snapshot()
        now = time.time()
        steps = [st[0] for _, st in snap]
        finished = all(s == "done" for s in steps)
        if a.once:
            print(line(snap, now)); return
        if finished:
            if not a.heartbeat_only: print(line(snap, now, "all done after {}"), flush=True)
            return
        if last is not None and steps != last:
            last_out = now
            if not a.heartbeat_only: print(line(snap, now), flush=True)
        elif now - last_out >= a.heartbeat:
            print(line(snap, now), flush=True); last_out = now
        last = steps
        time.sleep(a.interval)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Where a feature stands across its whole lifecycle, in one line.

Usage: lifecycle.py WORKTREE [--run LABEL]

Prints the feature's name, then one segment per stage the files show signs
of, in the order design, build, passes, review, PR, joined by " · ":

  lifecycle-progress · design ✓ · build 7/9 (milestone 2) · review round 2 · 6 → 2 open

Each segment carries its own count and never a rolled-up number; a stage with
nothing open shows ✓ after its name. Build and passes are summed over every
worktree building the feature; review and the pull request are read from the
hub worktree, --run naming the review run in place of latest. Open design
questions ride after the last segment once a later stage has begun. A build
or pass log that cannot be read shows as "build ?" or "passes ?".

Prints nothing when the worktree has no hub with a started feature. It reads
files and git only, starts nothing, writes nothing, and exits 0.
"""
import argparse, os
from records import DESIGN_CHECK, checks, feature_name, git, hub, load_script, open_questions, plural, records, started
from ledgers import builder_logs, read_build, read_passes, workspace_rows
import ids, paths
import run_files as rf

bd = load_script("build.py")
sf = load_script("stale-findings.py")
pr_posted = load_script("pr-posted.py")

SEP = " · "

def segment(name, done, words="", *after):
    head = " ".join(x for x in (name, "✓" if done else "", words) if x)
    return SEP.join([head, *(a for a in after if a)])

def questions_open(asked, settle, word):
    return f"{plural(asked, word)} open" + (f" ({settle} settle-first)" if settle else "")

def design_questions(h):
    """(open, settle-first) questions across the hub's design checks."""
    asked = settle = 0
    for c in checks(h):
        if c["kind"] != DESIGN_CHECK or not c["open"]: continue
        qs, first = open_questions(h, c["name"])
        asked += len(qs); settle += len(first)
    return asked, settle

def has_design(h):
    return bool(records(h)) or any(c["kind"] == DESIGN_CHECK for c in checks(h))

def feature_logs(wt, h):
    logs = [read_build(wt)] + builder_logs(wt, workspace_rows(wt))
    return logs if any(same_path(log.path, h) for log in logs) else logs + [read_build(h)]

def same_path(a, b): return os.path.realpath(a) == os.path.realpath(b)

def milestone_name(m):
    step = ids.read(m["f"].get("Plan") or "", ids.REF)
    return str(step.sub) if step else m["title"]

def under_way(log):
    return [m for m in bd.milestones(log.entries) if m["f"].get("Status") != "abandoned" and not bd.milestone_view(log.path, m).ready]

def build_segment(logs):
    if not any(log.err or bd.handoffs(log.entries) or bd.milestones(log.entries) for log in logs): return None
    if any(log.err for log in logs): return "build ?"
    try:
        rows = [r for log in logs if log.entries for r in bd.progress(log.path, log.entries) if r.record and r.record.get("status") == "active"]
        current = [m for log in logs for m in under_way(log)]
    except SystemExit: return "build ?"
    entries = [e for log in logs for e in bd.handoffs(log.entries)]
    done, counted = sum(len(r.done) for r in rows), sum(len(r.items) for r in rows)
    stopped = sum(1 for e in entries if e["f"].get("Status") == "stopped")
    busy = any(e["f"].get("Status") in bd.OPEN for e in entries)
    words = " ".join(x for x in (f"{done}/{counted}" if counted else "", f"(milestone {milestone_name(current[-1])})" if current else "") if x)
    return segment("build", done == counted and not current and not busy, words, f"{stopped} stopped" if stopped else "")

def outside_milestones(passes, entries):
    briefs = [m["f"].get("Brief") or "" for m in bd.milestones(entries)]
    return [e for e in passes if e["f"].get("Status") != "abandoned" and not any(ids.same(e["f"].get("Piece") or "", b) for b in briefs)]

def passes_segment(logs):
    counted, unreadable = [], False
    for log in logs:
        ps, err = read_passes(log.path)
        unreadable |= bool(err)
        counted += [(log.path, e) for e in outside_milestones(ps, log.entries)]
    if unreadable: return "passes ?"
    if not counted: return None
    checked = [(wt, e) for wt, e in counted if e["f"].get("Status") == "checked"]
    left = sum(bd.open_findings(wt, e) or 0 for wt, e in checked)
    return segment("passes", len(checked) == len(counted) and not left, f"{len(checked)}/{len(counted)} checked", f"{left} open" if left else "")

def rounds(run):
    """The run and the runs it was seeded from, latest first."""
    chain = [run]
    while (prev := rf.previous_run(chain[-1])) and prev not in chain and os.path.exists(rf.merged_path(prev)):
        chain.append(prev)
    return chain

def review_segment(run):
    if not run: return None
    chain = rounds(run)
    latest, triage = sf.open_count(run), len(sf.unmarked(run))
    left = f"{latest} open" + (f" ({triage} to triage)" if triage else "")
    if len(chain) == 1: return segment("review", not latest, "", left if latest else "")
    before = sf.open_count(chain[1])
    stalled = ", not converging" if latest and latest >= before else ""
    return segment("review", not latest, f"round {len(chain)}", f"{before} → {left}{stalled}")

def branch_landed(h, entries, posted):
    try: return bd.landed(h, entries, posted)
    except SystemExit: return False

def pr_segment(h, run, hub_log):
    drafted = os.path.exists(paths.pr_description(h))
    posted = pr_posted.read(h) is not None
    approved = bool(run and rf.read_approvals(run))
    states = (("merged", branch_landed(h, hub_log.entries, posted)), ("approved", approved), ("posted", posted), ("drafted", drafted))
    return next((f"PR {word}" for word, on in states if on), None)

def strip(wt, run=None):
    """The feature's lifecycle strip, or "" when wt has no hub with a started feature."""
    try: h = hub(wt)
    except SystemExit: return ""
    if not started(h): return ""
    logs = feature_logs(wt, h)
    review = rf.review_run(h, run)
    hub_log = next(log for log in logs if same_path(log.path, h))
    later = [s for s in (build_segment(logs), passes_segment(logs), review_segment(review), pr_segment(h, review, hub_log)) if s]
    asked, settle = design_questions(h)
    design = []
    if has_design(h):
        design = [segment("design", not asked, "", "" if later or not asked else questions_open(asked, settle, "question"))]
    if later and asked: later[-1] += SEP + questions_open(asked, settle, "design question")
    return SEP.join([feature_name(h) or "feature", *design, *later])

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("worktree"); ap.add_argument("--run")
    a = ap.parse_args()
    wt = git(a.worktree, "rev-parse", "--show-toplevel") or os.path.realpath(a.worktree)
    line = strip(wt, a.run)
    if line: print(line)

if __name__ == "__main__":
    main()

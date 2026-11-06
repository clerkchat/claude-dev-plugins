#!/usr/bin/env python3
"""Start an incremental run from a previous finished run.

Usage: carry.py PREV_RUN CUR_RUN

Copies the previous run's review state into the new run directory so the new
run only has to review the commits since the previous run's HEAD. First it imports any ticks and notes made in the previous
report since its last render, so triage done there is not left behind. Then
writes CUR_RUN/reconcile/matches.tsv with one `carried` row per earlier
finding and CUR_RUN/reconcile/previous.txt. Nothing is copied over an
existing file.
"""
import datetime, os, re, shutil, sys
from records import load_script

rr = load_script("render-report.py")

def import_pending(prev):
    """Bring ticks and notes the user made in the previous report since its
    last render into its status and instruction files, so they are carried."""
    entries = rr.read_findings(prev, rr.mf) if os.path.exists(os.path.join(prev, "merged.md")) else []
    changed = rr.load_triage(prev, entries, datetime.date.today().isoformat())
    rr.write_triage(prev)
    return len(changed)

def main():
    prev, cur = sys.argv[1], sys.argv[2]
    n = import_pending(prev)
    if n: print(f"imported {n} triage edits made in the previous report", file=sys.stderr)
    os.makedirs(cur, exist_ok=True)
    for name in ("merged.md", "titles.tsv", "status.tsv", "instructions.tsv", "numbers.tsv",
                 "slices.md", "summary.md", "not-reviewed.md", "stale.tsv", "commits.tsv", "posted.tsv"):
        src, dst = os.path.join(prev, name), os.path.join(cur, name)
        if os.path.exists(src) and not os.path.exists(dst): shutil.copy2(src, dst)
    for d in ("verify", "overrides", "resolution", "recheck", "pr", "notes", "posted"):
        src, dst = os.path.join(prev, d), os.path.join(cur, d)
        if os.path.isdir(src) and not os.path.exists(dst): shutil.copytree(src, dst)
    status = rr.read_status(prev)
    nums = rr.read_numbers(prev)
    ids = [int(m) for m in re.findall(r"^- id: (\d+)$", rr.read_text(os.path.join(prev, "merged.md")), re.M)]
    rd = os.path.join(cur, "reconcile"); os.makedirs(rd, exist_ok=True)
    open(os.path.join(rd, "previous.txt"), "w").write(os.path.basename(os.path.normpath(os.path.realpath(prev))) + "\n")
    with open(os.path.join(rd, "matches.tsv"), "w") as fh:
        fh.write("cur_id\tprev_id\thow\tprev_number\tprev_status\tprev_ref\n")
        for i in ids:
            st = status.get(i, {"status": "open", "ref": ""})
            fh.write(f"{i}\t{i}\tcarried\t{nums.get(i, '')}\t{st['status']}\t{st['ref']}\n")
    open(os.path.join(rd, "unmatched.tsv"), "w").write("prev_id\tprev_number\tprev_status\tprev_ref\tlocation\ttitle\n")
    print(f"carried {len(ids)} findings from {os.path.basename(os.path.normpath(prev))}", file=sys.stderr)

if __name__ == "__main__": main()

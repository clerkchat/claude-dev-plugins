#!/usr/bin/env python3
"""Start an incremental run from a previous finished run.

Usage: carry.py PREV_RUN CUR_RUN

Copies the previous run's review state into the new run directory so the new
run only has to review the commits since the previous run's HEAD:
merged.md, verify/, overrides/, titles.tsv, status.tsv, instructions.tsv,
notes/, resolution/, numbers.tsv, slices.md, summary.md,
not-reviewed.md, stale.tsv, commits.tsv. First it imports any ticks and notes made in the previous
report since its last render, so triage done there is not left behind. Then
writes CUR_RUN/reconcile/matches.tsv with one `carried` row per earlier
finding and CUR_RUN/reconcile/previous.txt. Nothing is copied over an
existing file.
"""
import datetime, os, re, shutil, sys
from records import load_script

def import_pending(prev):
    """Bring ticks and notes the user made in the previous report since its
    last render into its status and instruction files, so they are carried."""
    rr = load_script("render-report.py")
    today = datetime.date.today().isoformat()
    st = rr.import_hand_edits(prev, rr.read_status(prev), today); rr.write_status(prev, st)
    ins = rr.read_instructions(prev); changed = rr.import_instruction_edits(prev, ins, today)
    rr.write_instructions(prev, ins)
    return len(changed)

def main():
    prev, cur = sys.argv[1], sys.argv[2]
    n = import_pending(prev)
    if n: print(f"imported {n} triage edits made in the previous report", file=sys.stderr)
    os.makedirs(cur, exist_ok=True)
    for name in ("merged.md", "titles.tsv", "status.tsv", "instructions.tsv", "numbers.tsv",
                 "slices.md", "summary.md", "not-reviewed.md", "stale.tsv", "commits.tsv"):
        src, dst = os.path.join(prev, name), os.path.join(cur, name)
        if os.path.exists(src) and not os.path.exists(dst): shutil.copy2(src, dst)
    for d in ("verify", "overrides", "resolution", "recheck", "pr", "notes"):
        src, dst = os.path.join(prev, d), os.path.join(cur, d)
        if os.path.isdir(src) and not os.path.exists(dst): shutil.copytree(src, dst)
    status = {}
    p = os.path.join(prev, "status.tsv")
    if os.path.exists(p):
        for line in open(p):
            f = line.rstrip("\n").split("\t")
            if f and f[0].isdigit(): status[int(f[0])] = (f[1], f[2] if len(f) > 2 else "")
    nums = {}
    p = os.path.join(prev, "numbers.tsv")
    if os.path.exists(p):
        for line in open(p).read().splitlines()[1:]:
            f = line.split("\t")
            if len(f) > 1 and f[1].isdigit(): nums[int(f[1])] = f[0]
    ids = [int(m) for m in re.findall(r"^- id: (\d+)$", open(os.path.join(prev, "merged.md")).read(), re.M)]
    rd = os.path.join(cur, "reconcile"); os.makedirs(rd, exist_ok=True)
    open(os.path.join(rd, "previous.txt"), "w").write(os.path.basename(os.path.normpath(os.path.realpath(prev))) + "\n")
    with open(os.path.join(rd, "matches.tsv"), "w") as fh:
        fh.write("cur_id\tprev_id\thow\tprev_number\tprev_status\tprev_ref\n")
        for i in ids:
            s, ref = status.get(i, ("open", ""))
            fh.write(f"{i}\t{i}\tcarried\t{nums.get(i, '')}\t{s}\t{ref}\n")
    open(os.path.join(rd, "unmatched.tsv"), "w").write("prev_id\tprev_number\tprev_status\tprev_ref\tlocation\ttitle\n")
    print(f"carried {len(ids)} findings from {os.path.basename(os.path.normpath(prev))}", file=sys.stderr)

if __name__ == "__main__": main()

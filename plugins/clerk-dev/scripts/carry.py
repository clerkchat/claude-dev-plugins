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
import run_files as rf

rr = load_script("render-report.py")

def import_pending(prev):
    """Bring ticks and notes the user made in the previous report since its
    last render into its status and instruction files, so they are carried."""
    entries = rf.read_findings(prev)
    changed = rr.load_triage(prev, entries, datetime.date.today().isoformat())
    rr.write_triage(prev)
    return len(changed)

CARRIED_FILES = ("merged.md", "titles.tsv", "status.tsv", "instructions.tsv", "numbers.tsv", "slices.md", "summary.md",
                 "not-reviewed.md", "stale.tsv", "commits.tsv", "posted.tsv",
                 "verify", "overrides", "resolution", "recheck", "pr", "notes", "posted")

def copy_if_absent(src, dst):
    if not os.path.exists(dst): shutil.copy2(src, dst)

def copy_missing(src, dst):
    if os.path.isdir(src): shutil.copytree(src, dst, dirs_exist_ok=True, copy_function=copy_if_absent)
    elif os.path.exists(src): copy_if_absent(src, dst)

def main():
    prev, cur = sys.argv[1], sys.argv[2]
    if not os.path.exists(rf.merged_path(prev)):
        sys.exit(f"nothing carried; {rf.merged_path(prev)} does not exist, so {prev} is not a finished review run")
    n = import_pending(prev)
    if n: print(f"imported {n} triage edits made in the previous report", file=sys.stderr)
    os.makedirs(cur, exist_ok=True)
    for name in CARRIED_FILES: copy_missing(os.path.join(prev, name), os.path.join(cur, name))
    status = rf.read_status(prev)
    nums = rf.read_numbers(prev)
    ids = [int(m) for m in re.findall(r"^- id: (\d+)$", rf.read_text(rf.merged_path(prev)), re.M)]
    rf.write_previous(cur, rf.run_label(prev))
    rf.write_matches(cur, {i: {"prev_id": str(i), "how": "carried", **rf.previous_state(status, nums, i)} for i in ids})
    rf.write_unmatched(cur, {})
    print(f"carried {len(ids)} findings from {os.path.basename(os.path.normpath(prev))}", file=sys.stderr)

if __name__ == "__main__": main()

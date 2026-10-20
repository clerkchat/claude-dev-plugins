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
import argparse, datetime, importlib.util, os, re, subprocess, sys

_spec = importlib.util.spec_from_file_location("items", os.path.join(os.path.dirname(os.path.abspath(__file__)), "items.py"))
assert _spec and _spec.loader
items = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(items)

HEADER = """# Follow-ups

Work this repository owes because of changes elsewhere. Kept by the review
plugin; ticking boxes by hand is fine. Each item says where the change came
from and which contract it touches. Instruction and Status use the words in
the plugin's tracking.md "Items"; a blank instruction means do as written.

"""

def path(wt):
    d = os.path.join(wt, ".clerk-dev"); os.makedirs(d, exist_ok=True)
    ex = subprocess.run(["git", "-C", wt, "check-ignore", "-q", ".clerk-dev"])
    if ex.returncode != 0:
        common = subprocess.run(["git", "-C", wt, "rev-parse", "--git-common-dir"], capture_output=True, text=True).stdout.strip()
        if common:
            exf = os.path.join(common if os.path.isabs(common) else os.path.join(wt, common), "info", "exclude")
            os.makedirs(os.path.dirname(exf), exist_ok=True)
            with open(exf, "a") as fh: fh.write(".clerk-dev/\n")
    return os.path.join(d, "followups.md")

FIELDS = ("From", "Contract", "Finding", "Added", "Instruction", "Status", "Outcome")

def read(p):
    """Items as {done, id, text, fields, meta}. A `Done:` field from before
    statuses existed reads as status fixed with that outcome."""
    its = items.read(p, list(FIELDS) + ["Done"])
    for it in its:
        f = it["fields"]
        if "Done" in f:
            f.setdefault("Outcome", f.pop("Done")); f["Status"] = "fixed"; it["done"] = True
        it["meta"] = [f"{k}: {f[k]}" for k in FIELDS if f.get(k)]
    return its

def write(p, its):
    items.write(p, its, HEADER, order=FIELDS)

def guard(wt):
    s = importlib.util.spec_from_file_location("records", os.path.join(os.path.dirname(os.path.abspath(__file__)), "records.py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); m.guard(wt)

def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("add"); a.add_argument("wt"); a.add_argument("text"); a.add_argument("--from", dest="src", required=True)
    a.add_argument("--contract"); a.add_argument("--finding"); a.add_argument("--instruction")
    l = sp.add_parser("list"); l.add_argument("wt"); l.add_argument("--open", action="store_true")
    c = sp.add_parser("close"); c.add_argument("wt"); c.add_argument("fid"); c.add_argument("--ref")
    c.add_argument("--status", choices=items.DONE, default="fixed")
    r = sp.add_parser("reopen"); r.add_argument("wt"); r.add_argument("fid")
    s = sp.add_parser("set"); s.add_argument("wt"); s.add_argument("fid"); s.add_argument("instruction"); s.add_argument("--note")
    args = ap.parse_args()
    guard(args.wt)
    p = path(args.wt); its = read(p); today = datetime.date.today().isoformat()
    if args.cmd == "add":
        n = max([int(i["id"][1:]) for i in its] or [0]) + 1
        f = {"From": args.src, "Contract": args.contract or "", "Finding": args.finding or "", "Added": today,
             "Instruction": items.instruction(args.instruction) if args.instruction else "", "Status": "open"}
        its.append({"done": False, "id": f"F{n}", "text": args.text.rstrip(".") + ".", "fields": {k: v for k, v in f.items() if v}, "order": []})
        write(p, its); print(f"F{n} added to {p}")
    elif args.cmd == "list":
        for i in its:
            if args.open and i["done"]: continue
            print(f"{'x' if i['done'] else ' '} {i['id']}. {i['text']}  [{'; '.join(i['meta'])}]")
    else:
        it = items.find(its, args.fid)
        if args.cmd == "set":
            it["fields"]["Instruction"] = items.instruction(args.instruction) + (f": {args.note}" if args.note else "")
            write(p, its); print(f"{it['id']}: {it['fields']['Instruction']}")
        else:
            items.set_status(it, args.status if args.cmd == "close" else "open", ((f"in {args.ref}" if re.fullmatch(r"[0-9a-f]{7,40}", args.ref) else args.ref) if args.ref else "closed") if args.cmd == "close" else None)
            write(p, its); print(f"{args.fid} {'closed (' + args.status + ')' if args.cmd == 'close' else 'reopened'}")

if __name__ == "__main__": main()

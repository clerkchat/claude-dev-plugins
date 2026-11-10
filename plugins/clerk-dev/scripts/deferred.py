#!/usr/bin/env python3
USAGE = """Manage a worktree's deferred list, <worktree>/.clerk-dev/deferred.md.

A deferred item is a known gap with a path chosen for now: marking a finding,
question, follow-up, or pass item Defer adds one, and the source's outcome names
it. The file is a Markdown checkbox list in the items format.

Usage:
  deferred.py add WORKTREE "what" --from SRC --path "what was done for now" --open "what is left" [--revisit "when to look again"]
  deferred.py list WORKTREE [--open]
  deferred.py close WORKTREE DEFER-3 [--ref <sha or reason>] [--status fixed|wont-fix]
  deferred.py reopen WORKTREE DEFER-3
  deferred.py set WORKTREE DEFER-3 "Refine" [--note "..."]

SRC is a finding "<run> N", a question "BRIEF-18-1.Q-6", a pass item "PASS-3.4",
a handoff "BUILD-9", or "this session".
"""
import argparse, datetime, os
from records import load_script
import ids, paths

items = load_script("items.py")

EXTRAS = ("Path", "Open", "Revisit")
REQUIRED = ("Path", "Open")
CLOSING_STATUSES = ("fixed", "wont-fix")
FIELDS = ("From", *EXTRAS, "Added", "Instruction", "Status", "Outcome")

HEADER = """# Deferred

Known gaps with a path chosen for now. Kept by the plugin; ticking boxes by
hand is fine. Each item says where it came from, what was done for now (Path),
what is left (Open), and when to look again (Revisit). Close one as fixed with a
commit, or wont-fix with a reason.

"""

def path(wt):
    paths.ensure(wt)
    return paths.deferred(wt)

def read(p):
    its = items.read(p, list(FIELDS))
    for it in its:
        f = it["fields"]
        it["meta"] = [f"{k}: {f[k]}" for k in FIELDS if f.get(k)]
    return its

def write(p, its): items.write(p, its, HEADER, order=FIELDS)

def add(its, text, source, instruction_value=None, **extra):
    iid = ids.item(ids.DEFERRED, ids.next_number([i["id"] for i in its], ids.DEFERRED))
    f = {"From": source, **{k: extra.get(k) or "" for k in EXTRAS}, "Added": datetime.date.today().isoformat(),
         "Instruction": items.instruction(instruction_value) if instruction_value else "", "Status": "open"}
    its.append({"done": False, "id": iid, "text": text.rstrip(".") + ".", "fields": {k: v for k, v in f.items() if v}, "order": []})
    return iid

def main():
    ap = argparse.ArgumentParser(prog="deferred.py", description=USAGE, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("add"); a.add_argument("wt"); a.add_argument("text"); a.add_argument("--from", dest="src", required=True)
    for k in EXTRAS: a.add_argument(f"--{k.lower()}", dest=k, required=k in REQUIRED)
    a.add_argument("--instruction")
    l = sp.add_parser("list"); l.add_argument("wt"); l.add_argument("--open", action="store_true")
    c = sp.add_parser("close"); c.add_argument("wt"); c.add_argument("iid"); c.add_argument("--ref")
    c.add_argument("--status", choices=CLOSING_STATUSES, default="fixed")
    r = sp.add_parser("reopen"); r.add_argument("wt"); r.add_argument("iid")
    s = sp.add_parser("set"); s.add_argument("wt"); s.add_argument("iid"); s.add_argument("instruction"); s.add_argument("--note")
    args = ap.parse_args()
    if args.cmd == "add":
        for k in REQUIRED:
            if not getattr(args, k).strip(): a.error(f"--{k.lower()} must not be blank")
    p = path(args.wt); its = read(p)
    if args.cmd == "add":
        iid = add(its, args.text, args.src, args.instruction, **{k: getattr(args, k) for k in EXTRAS})
        write(p, its); print(f"{iid} added to {p}")
    elif args.cmd == "list":
        for i in its:
            if args.open and i["done"]: continue
            print(f"{'x' if i['done'] else ' '} {i['id']}. {i['text']}  [{'; '.join(i['meta'])}]")
    else:
        it = items.find(its, args.iid)
        if args.cmd == "set":
            items.set_instruction(it, args.instruction, args.note)
            write(p, its); print(f"{it['id']}: {it['fields']['Instruction']}")
        else:
            if args.cmd == "close": items.close(it, args.status, args.ref)
            else: items.reopen(it)
            write(p, its); print(f"{args.iid} {'closed (' + args.status + ')' if args.cmd == 'close' else 'reopened'}")

if __name__ == "__main__": main()

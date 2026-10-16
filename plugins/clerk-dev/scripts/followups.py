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
  followups.py close WORKTREE F3 [--ref <sha or note>]
  followups.py reopen WORKTREE F3

Entry format:
  - [ ] F3. Send exportId back when polling report downloads.
    - From: api 7c1e2ab
    - Contract: POST /reports/:id/exports accepts and returns exportId
    - Finding: api 8
    - Added: 2026-10-07
"""
import argparse, datetime, os, re, subprocess, sys

HEADER = """# Follow-ups

Work this repository owes because of changes elsewhere. Kept by the review
plugin; ticking boxes by hand is fine. Each item says where the change came
from and which contract it touches.

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

FIELDS = ("From", "Contract", "Finding", "Added", "Done")
FIELD_RE = re.compile(r"(?:^|\s)(" + "|".join(FIELDS) + r"):\s")

ITEM_RE = re.compile(r"^[-*+] \[( |x|X)\] (F\d+)\.\s+(.*)$")

def read(p):
    """Items as {done, id, text, meta, fields}. Everything indented under an
    item's checkbox belongs to it; bullet markers are dropped, the text is
    read as one paragraph, and it is split on the field labels. So a file a
    formatter rewrapped or re-indented, or one written before fields were
    bullets (one field per indented line), reads the same; writing it back
    restores the bullet layout."""
    if not os.path.exists(p): return []
    items, cur = [], None
    for line in open(p, encoding="utf-8"):
        m = ITEM_RE.match(line.rstrip("\n"))
        if m:
            cur = {"done": m.group(1).lower() == "x", "id": m.group(2), "lines": [m.group(3)]}
            items.append(cur); continue
        if not line.strip(): continue
        if cur and line[0] in " \t":
            cur["lines"].append(re.sub(r"^[-*+]\s+", "", line.strip()))
        else:
            cur = None
    for it in items:
        para = " ".join(it.pop("lines"))
        parts = FIELD_RE.split(para)
        it["text"] = parts[0].strip()
        it["fields"] = {k: v.strip() for k, v in zip(parts[1::2], parts[2::2])}
        it["meta"] = [f"{k}: {it['fields'][k]}" for k in FIELDS if k in it["fields"]]
    return items

def write(p, items):
    out = [HEADER]
    for it in items:
        out.append(f"- [{'x' if it['done'] else ' '}] {it['id']}. {it['text']}\n")
        for m in it["meta"]: out.append(f"  - {m}\n")
        out.append("\n")
    open(p, "w", encoding="utf-8").write("".join(out).rstrip("\n") + "\n")

def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("add"); a.add_argument("wt"); a.add_argument("text"); a.add_argument("--from", dest="src", required=True)
    a.add_argument("--contract"); a.add_argument("--finding")
    l = sp.add_parser("list"); l.add_argument("wt"); l.add_argument("--open", action="store_true")
    c = sp.add_parser("close"); c.add_argument("wt"); c.add_argument("fid"); c.add_argument("--ref")
    r = sp.add_parser("reopen"); r.add_argument("wt"); r.add_argument("fid")
    args = ap.parse_args()
    p = path(args.wt); items = read(p); today = datetime.date.today().isoformat()
    if args.cmd == "add":
        n = max([int(i["id"][1:]) for i in items] or [0]) + 1
        meta = [f"From: {args.src}"] + ([f"Contract: {args.contract}"] if args.contract else []) + ([f"Finding: {args.finding}"] if args.finding else []) + [f"Added: {today}"]
        items.append({"done": False, "id": f"F{n}", "text": args.text.rstrip("."), "meta": meta})
        items[-1]["text"] += "."
        write(p, items); print(f"F{n} added to {p}")
    elif args.cmd == "list":
        for i in items:
            if args.open and i["done"]: continue
            print(f"{'x' if i['done'] else ' '} {i['id']}. {i['text']}  [{'; '.join(i['meta'])}]")
    else:
        it = next((i for i in items if i["id"] == args.fid), None)
        if not it: sys.exit(f"{args.fid} not found in {p}")
        it["done"] = args.cmd == "close"
        it["meta"] = [m for m in it["meta"] if not m.startswith("Done:")]
        if it["done"]: it["meta"].append(f"Done: {today}" + (f" in {args.ref}" if args.ref else ""))
        write(p, items); print(f"{args.fid} {'closed' if it['done'] else 'reopened'}")

if __name__ == "__main__": main()

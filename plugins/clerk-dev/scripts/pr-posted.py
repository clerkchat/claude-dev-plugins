#!/usr/bin/env python3
"""Record the pull request posted from a worktree's branch.

Usage:
  pr-posted.py record WORKTREE --number N --url URL   # write the number and link (paths.py pr-posted)
  pr-posted.py show WORKTREE                          # print "N<TAB>URL", or nothing when none was posted

The file is one line, "number<TAB>url", replaced on each record. Readers call
read(wt), which gives (number, url) or None.
"""
import argparse, os, sys
import paths

def read(wt):
    try:
        with open(paths.pr_posted(wt)) as f: number, url = f.read().rstrip("\n").split("\t")
    except (OSError, ValueError): return None
    return (int(number), url) if number.isdecimal() else None

def record(wt, number, url):
    os.makedirs(paths.ledger(wt), exist_ok=True)
    with open(paths.pr_posted(wt), "w") as f: f.write(f"{number}\t{url}\n")

def main(argv=None):
    ap = argparse.ArgumentParser(prog="pr-posted.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record"); rec.add_argument("wt"); rec.add_argument("--number", type=int, required=True); rec.add_argument("--url", required=True)
    sub.add_parser("show").add_argument("wt")
    a = ap.parse_args(argv)
    wt = os.path.abspath(a.wt)
    if a.cmd == "record": record(wt, a.number, a.url)
    elif posted := read(wt): print(*posted, sep="\t")

if __name__ == "__main__": main()

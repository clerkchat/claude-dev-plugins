#!/usr/bin/env python3
import os, sys
from records import git
import paths

def in_real_dir(p): return os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p))

def link_latest(worktree, run):
    runs = os.path.realpath(paths.runs_dir(worktree))
    target = os.path.realpath(run)
    label = os.path.basename(target)
    if os.path.dirname(target) != runs or not os.path.isdir(target) or label in ("latest", "latest-feature"):
        sys.exit(f"not linked: {run} is not a run directory directly under {runs}")
    link = in_real_dir(paths.latest(worktree, feature=label.endswith("-feature")))
    if os.path.lexists(link) and not os.path.islink(link):
        sys.exit(f"not linked: {link} exists and is not a link")
    staged = os.path.join(os.path.dirname(link), f".{os.path.basename(link)}.{os.getpid()}")
    os.symlink(os.path.relpath(target, os.path.dirname(link)), staged)
    os.replace(staged, link)
    return link

def main(argv):
    if len(argv) != 1: sys.exit("usage: link-latest.py RUN_DIR")
    link = link_latest(git(".", "rev-parse", "--show-toplevel") or ".", argv[0])
    print(f"{os.path.basename(link)} -> {os.readlink(link)}")

if __name__ == "__main__": main(sys.argv[1:])

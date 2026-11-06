#!/usr/bin/env python3
import os, sys
from records import git

def link_name(label):
    return "latest-feature" if label.endswith("-feature") else "latest"

def link_latest(worktree, run):
    clerk_dev = os.path.realpath(os.path.join(worktree, ".clerk-dev"))
    target = os.path.realpath(run)
    label = os.path.basename(target)
    if os.path.dirname(target) != clerk_dev or not os.path.isdir(target) or label in ("latest", "latest-feature"):
        sys.exit(f"not linked: {run} is not a run directory directly under {clerk_dev}")
    link = os.path.join(clerk_dev, link_name(label))
    if os.path.lexists(link) and not os.path.islink(link):
        sys.exit(f"not linked: {link} exists and is not a link")
    staged = os.path.join(clerk_dev, f".{link_name(label)}.{os.getpid()}")
    os.symlink(label, staged)
    os.replace(staged, link)
    return link

def main(argv):
    if len(argv) != 1: sys.exit("usage: link-latest.py RUN_DIR")
    link = link_latest(git(".", "rev-parse", "--show-toplevel") or ".", argv[0])
    print(f"{os.path.basename(link)} -> {os.readlink(link)}")

if __name__ == "__main__": main(sys.argv[1:])

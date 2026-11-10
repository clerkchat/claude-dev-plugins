#!/usr/bin/env python3
"""Point latest (latest-feature for a -feature run) at a run under the ledger's
runs directory, and the top-level review.md (review-feature.md) at the run's
report.md once it exists; a review link left on an earlier run is removed until then.
"""
import os, sys
from records import git
import paths

def in_real_dir(p): return os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p))

def refuse_non_link(link):
    if os.path.lexists(link) and not os.path.islink(link):
        sys.exit(f"not linked: {link} exists and is not a link")

def replace_link(link, target):
    staged = os.path.join(os.path.dirname(link), f".{os.path.basename(link)}.{os.getpid()}")
    os.symlink(os.path.relpath(target, os.path.dirname(link)), staged)
    os.replace(staged, link)

def link_latest(worktree, run):
    runs = os.path.realpath(paths.runs_dir(worktree))
    target = os.path.realpath(run)
    if os.path.dirname(target) != runs or not os.path.isdir(target):
        sys.exit(f"not linked: {run} is not a run directory directly under {runs}")
    feature = os.path.basename(target).endswith("-feature")
    latest, review = in_real_dir(paths.latest(worktree, feature)), in_real_dir(paths.review_link(worktree, feature))
    refuse_non_link(latest); refuse_non_link(review)
    replace_link(latest, target)
    report = os.path.join(target, "report.md")
    if os.path.exists(report): replace_link(review, report)
    elif os.path.lexists(review): os.remove(review)
    return [l for l in (latest, review) if os.path.lexists(l)]

def main(argv):
    if len(argv) != 1: sys.exit("usage: link-latest.py RUN_DIR")
    for link in link_latest(git(".", "rev-parse", "--show-toplevel") or ".", argv[0]):
        print(f"{os.path.basename(link)} -> {os.readlink(link)}")

if __name__ == "__main__": main(sys.argv[1:])

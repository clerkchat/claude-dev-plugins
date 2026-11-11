#!/usr/bin/env python3
"""Move worktrees' plugin files from the old layout, where they sat directly in
.clerk-dev/, to where paths.py keeps them, then make review.md,
review-feature.md, and feature.md. One-off: delete it once no active worktree
has the old layout.

Usage: migrate-layout.py WORKTREE... [--dry-run]

Prints one line per move or link. Only the plugin's old names move; anything
else in .clerk-dev/ is the user's and stays. A destination that already holds
something else is a conflict: both are left, and the script exits 1.
"""
import argparse, filecmp, os, re, shutil, sys
from typing import Callable, NamedTuple
import paths, records

link = records.load_script("link-latest.py")

RUN = re.compile(r"\d{8}-\d{4}-.+")
LEDGER_FILES = (paths.build_log, paths.passes, paths.deferred, paths.seen_backlog, paths.pr_body, paths.pr_generated, paths.pr_notes)
GENERATED = re.compile(r"^## (Records|Ideas|Checks|History)\n.*?(?=^## |\Z)", re.S | re.M)

class Step(NamedTuple):
    lines: list
    do: Callable[[], None]

def old(wt, new): return os.path.join(paths.clerk_dev(wt), os.path.basename(new))

def old_runs(wt):
    top = paths.clerk_dev(wt)
    names = sorted(os.listdir(top)) if os.path.isdir(top) else []
    return [paths.run(wt, n) for n in names if RUN.fullmatch(n) and os.path.isdir(os.path.join(top, n)) and not os.path.islink(os.path.join(top, n))]

def pointers(wt): return [paths.latest(wt), paths.latest(wt, feature=True)]

def moved(wt): return [*old_runs(wt), *(f(wt) for f in LEDGER_FILES), paths.workspace(wt), paths.feature_dir(wt), *pointers(wt)]

def old_names(wt):
    """The plugin's old-layout names directly in the worktree's .clerk-dev/."""
    return [os.path.basename(new) for new in moved(wt) if os.path.lexists(old(wt, new))]

def same(a, b):
    if os.path.islink(a) or os.path.islink(b): return os.path.islink(a) and os.path.islink(b) and os.readlink(a) == os.readlink(b)
    if os.path.isdir(a) or os.path.isdir(b):
        return os.path.isdir(a) and os.path.isdir(b) and sorted(os.listdir(a)) == sorted(os.listdir(b)) and all(same(os.path.join(a, n), os.path.join(b, n)) for n in os.listdir(a))
    return filecmp.cmp(a, b, shallow=False)

def remove(p):
    if os.path.isdir(p) and not os.path.islink(p): shutil.rmtree(p)
    else: os.remove(p)

def target_of(p): return os.path.normpath(os.path.join(os.path.dirname(p), os.readlink(p)))

def workspace_target(src):
    """Where a workspace.md link goes in the new layout: another worktree's old manifest becomes its ledger path."""
    target = target_of(src)
    other = os.path.dirname(os.path.dirname(target))
    return paths.workspace(other) if target == old(other, paths.workspace(other)) else target

def run_now(wt, run):
    """Where a run is before this migration's moves: in the ledger already, or at its old place."""
    return run if os.path.lexists(run) else old(wt, run)

class Plan:
    def __init__(self, wt):
        self.wt, self.steps, self.conflicts = wt, [], []

    def rel(self, p): return os.path.relpath(p, self.wt)

    def conflict(self, why): self.conflicts.append(f"conflict: {why}; left as it is")

    def place(self, src, dst, lines=None, do=None, holds=None):
        """Put src's content at dst unless dst holds something else; True unless that is a conflict."""
        if not os.path.lexists(dst):
            self.steps.append(Step(lines or [f"move {self.rel(src)} -> {self.rel(dst)}"], do or (lambda: os.rename(src, dst))))
        elif (holds or (lambda: same(src, dst)))():
            self.steps.append(Step([f"remove {self.rel(src)}, already at {self.rel(dst)}"], lambda: remove(src)))
        else:
            self.conflict(f"{self.rel(dst)} exists and differs from {self.rel(src)}")
            return False
        return True

    def runs_and_files(self):
        for dst in [*old_runs(self.wt), *(f(self.wt) for f in LEDGER_FILES)]:
            src = old(self.wt, dst)
            if os.path.lexists(src): self.place(src, dst)

    def workspace(self):
        dst = paths.workspace(self.wt); src = old(self.wt, dst)
        if not os.path.islink(src):
            if os.path.lexists(src): self.place(src, dst)
            return
        target = workspace_target(src)
        def relink(): os.symlink(target, dst); os.remove(src)
        self.place(src, dst, [f"link {self.rel(dst)} -> {target}"], relink, lambda: os.path.islink(dst) and target_of(dst) == target)

    def feature(self):
        dst = paths.feature_dir(self.wt); src = old(self.wt, dst)
        if not os.path.lexists(src): return
        overview = os.path.join(src, os.path.basename(paths.overview(self.wt)))
        if os.path.lexists(overview) and not self.place(overview, paths.overview(self.wt)): return
        if not self.place(src, dst) or os.path.lexists(dst): return
        meta = os.path.join(src, os.path.basename(paths.feature_meta(self.wt)))
        if not os.path.exists(meta): return
        if GENERATED.search(open(meta, encoding="utf-8").read()):
            self.steps.append(Step([f"trim the generated sections from {self.rel(paths.feature_meta(self.wt))}"], lambda: trim(paths.feature_meta(self.wt))))
        self.steps.append(Step([f"make {self.rel(paths.feature_md(self.wt))}"], lambda: records.concatenate(self.wt, self.wt)))

    def pointer(self, dst):
        src = old(self.wt, dst)
        if not os.path.lexists(src): return
        if not os.path.islink(src): return self.conflict(f"{self.rel(src)} is not a link")
        label = os.path.basename(os.path.normpath(os.readlink(src)))
        run = paths.run(self.wt, label)
        if not os.path.isdir(run_now(self.wt, run)): return self.conflict(f"{self.rel(src)} points at {label}, which is not a run here")
        review = paths.review_link(self.wt, label.endswith("-feature"))
        if os.path.lexists(review) and not os.path.islink(review): return self.conflict(f"{self.rel(review)} exists and is not a link")
        lines = [f"link {self.rel(dst)} -> {os.path.relpath(run, os.path.dirname(dst))}"]
        report = os.path.join(run, "report.md")
        if os.path.exists(os.path.join(run_now(self.wt, run), "report.md")): lines.append(f"link {self.rel(review)} -> {os.path.relpath(report, os.path.dirname(review))}")
        def relink(): link.link_latest(self.wt, run); os.remove(src)
        self.place(src, dst, lines, relink, lambda: os.path.islink(dst) and os.path.basename(os.readlink(dst)) == label)

    def build(self):
        self.runs_and_files(); self.workspace(); self.feature()
        for p in pointers(self.wt): self.pointer(p)
        return self

def trim(meta):
    text = open(meta, encoding="utf-8").read()
    records.write_atomic(meta, GENERATED.sub("", text).replace("Edit freely above Records.", "Edit freely.").rstrip("\n") + "\n")

def refusal(wt):
    top = records.git(wt, "rev-parse", "--show-toplevel") if os.path.isdir(wt) else ""
    if not top or os.path.realpath(top) != os.path.realpath(wt): return f"{wt} is not a git worktree"
    if not os.path.isdir(paths.clerk_dev(wt)): return f"{wt} has no .clerk-dev/ directory"

def migrate(wt, dry_run=False):
    """Lines saying what was (or would be) done in one worktree, and whether all of it could be."""
    plan = Plan(wt).build()
    if not plan.steps and not plan.conflicts: return [f"{wt}: already in the new layout; nothing to move"], True
    if plan.steps and not dry_run: paths.ensure(wt)
    out = []
    for s in plan.steps:
        if not dry_run: s.do()
        out += [f"{wt}: {line}" for line in s.lines]
    return out + [f"{wt}: {c}" for c in plan.conflicts], not plan.conflicts

def main(argv):
    ap = argparse.ArgumentParser(prog="migrate-layout.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("worktrees", nargs="+"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    wts = [os.path.realpath(w) for w in a.worktrees]
    refused = [r for r in map(refusal, wts) if r]
    if refused: sys.exit("not migrated: " + "; ".join(refused))
    clean = True
    for wt in wts:
        lines, ok = migrate(wt, a.dry_run)
        print("\n".join(lines)); clean = clean and ok
    if a.dry_run: print("dry run: nothing changed")
    if not clean: sys.exit(1)

if __name__ == "__main__": main(sys.argv[1:])

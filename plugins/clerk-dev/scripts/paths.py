#!/usr/bin/env python3
"""Every path the plugin owns under a worktree's .clerk-dev/.

Usage:
  paths.py WORKTREE NAME [LABEL] [--feature]   print a path: NAME is a function below with - for _;
                                               run takes the run's LABEL, latest and review-link take --feature
  paths.py ensure WORKTREE                     create .clerk-dev/, its ledger, and its .git/info/exclude entry

The top of .clerk-dev/ holds only the files the user opens; everything the
plugin keeps for itself is under .clerk-dev/.ledger/. Anything else under
.clerk-dev/ is the user's.

Feature paths (feature-dir and below) take the hub worktree (records.py hub).
"""
import argparse, os, subprocess, sys

CLERK_DEV = ".clerk-dev"
LEDGER = os.path.join(CLERK_DEV, ".ledger")
FEATURE = os.path.join(LEDGER, "feature")

def clerk_dev(wt): return os.path.join(wt, CLERK_DEV)
def ledger(wt): return os.path.join(wt, LEDGER)
def runs_dir(wt): return os.path.join(ledger(wt), "runs")
def run(wt, label): return os.path.join(runs_dir(wt), label)
def latest(wt, feature=False): return os.path.join(ledger(wt), "latest-feature" if feature else "latest")
def review_link(wt, feature=False): return os.path.join(clerk_dev(wt), "review-feature.md" if feature else "review.md")
def notes(wt): return os.path.join(clerk_dev(wt), "branch-notes.md")
def pr_description(wt): return os.path.join(clerk_dev(wt), "pr-description.md")
def pr_generated(wt): return os.path.join(ledger(wt), "pr-description.generated.md")
def pr_body(wt): return os.path.join(ledger(wt), "pr-body.md")
def pr_notes(wt): return os.path.join(ledger(wt), "pr-draft-notes.md")
def build_log(wt): return os.path.join(ledger(wt), "build.md")
def passes(wt): return os.path.join(ledger(wt), "passes.md")
def deferred(wt): return os.path.join(ledger(wt), "deferred.md")
def workspace(wt): return os.path.join(ledger(wt), "workspace.md")
def seen_backlog(wt): return os.path.join(ledger(wt), "status-seen-backlog")

def feature_dir(hub): return os.path.join(hub, FEATURE)
def feature_meta(hub): return os.path.join(feature_dir(hub), "feature.md")
def records_dir(hub): return os.path.join(feature_dir(hub), "records")
def checks_dir(hub): return os.path.join(feature_dir(hub), "checks")
def feature_md(hub): return os.path.join(clerk_dev(hub), "feature.md")
def overview(hub): return os.path.join(clerk_dev(hub), "overview.md")

def hub_of(d):
    d = os.path.normpath(d)
    if not d.endswith(os.sep + FEATURE): raise ValueError(f"{d} is not a feature directory")
    return d[:-len(os.sep + FEATURE)] or os.sep

def run_name(wt, run, feature=False):
    """A run as named to the user: the top-level review link when it resolves to the run's report, else the report, else the run."""
    report = os.path.realpath(os.path.join(run, "report.md"))
    if not os.path.exists(report): return os.path.relpath(os.path.realpath(run), os.path.realpath(wt))
    link = review_link(wt, feature)
    return os.path.relpath(link if os.path.realpath(link) == report else report, os.path.realpath(wt))

def ensure(wt):
    os.makedirs(runs_dir(wt), exist_ok=True)
    if subprocess.run(["git", "-C", wt, "check-ignore", "-q", CLERK_DEV]).returncode == 0: return
    r = subprocess.run(["git", "-C", wt, "rev-parse", "--git-common-dir"], capture_output=True, text=True)
    common = r.stdout.strip() if r.returncode == 0 else ""
    if not common: return
    exf = os.path.join(common if os.path.isabs(common) else os.path.join(wt, common), "info", "exclude")
    os.makedirs(os.path.dirname(exf), exist_ok=True)
    with open(exf, "a") as fh: fh.write(f"{CLERK_DEV}/\n")

PRINTABLE = {f.__name__.replace("_", "-"): f for f in (
    clerk_dev, ledger, runs_dir, run, latest, review_link, notes, pr_description, pr_generated, pr_body, pr_notes,
    build_log, passes, deferred, workspace, seen_backlog, feature_dir, feature_meta, records_dir, checks_dir, feature_md, overview)}

def main(argv):
    if argv[:1] == ["ensure"]:
        if len(argv) != 2: sys.exit("usage: paths.py ensure WORKTREE")
        ensure(argv[1]); return
    ap = argparse.ArgumentParser(prog="paths.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wt"); ap.add_argument("name", choices=PRINTABLE); ap.add_argument("label", nargs="?")
    ap.add_argument("--feature", action="store_true")
    a = ap.parse_args(argv)
    if (a.name == "run") != bool(a.label): ap.error("run takes a LABEL, and only run does")
    if a.feature and a.name not in ("latest", "review-link"): ap.error("--feature goes with latest or review-link")
    wt = os.path.abspath(a.wt)
    if a.name == "run": print(run(wt, a.label))
    elif a.feature: print(PRINTABLE[a.name](wt, feature=True))
    else: print(PRINTABLE[a.name](wt))

if __name__ == "__main__": main(sys.argv[1:])

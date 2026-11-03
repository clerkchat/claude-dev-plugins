#!/usr/bin/env python3
import argparse, os, sys
from collections import Counter
from records import git, load_script

DEFAULT_CAP = 40
measure_patch = load_script("measure-patch.py")

def tracked(repo, rel): return [f for f in git(repo, "ls-files", "-z", "--", rel, check=True).split("\0") if f]

def repo_relative(repo, path):
    rel = os.path.relpath(os.path.realpath(os.path.join(repo, path)), repo)
    if rel == ".." or rel.startswith(".." + os.sep): sys.exit(f"{path} is not under {repo}")
    return rel

def expand(repo, path):
    rel = repo_relative(repo, path)
    full = os.path.join(repo, rel)
    if os.path.isfile(full): return [rel], True
    if os.path.isdir(full): return tracked(repo, rel), False
    sys.exit(f"{path} does not exist under {repo}")

def as_added(repo, rel):
    full = os.path.join(repo, rel)
    try:
        with open(full, "rb") as fh: lines = fh.read().count(b"\n")
    except OSError as e: sys.exit(f"cannot read {full}: {e.strerror}")
    return {"file": rel, "bytes": os.path.getsize(full), "added": lines, "removed": 0}

def kept(repo, rel, globs):
    return os.path.isfile(os.path.join(repo, rel)) and not measure_patch.reason(as_added(repo, rel), globs)

def resolve(repo, paths, extra):
    files = set()
    for path in paths:
        found, named = expand(repo, path)
        globs = measure_patch.DEFAULT_GLOBS + ([] if named else extra)
        files.update(rel for rel in found if kept(repo, rel, globs))
    return sorted(os.path.join(repo, rel) for rel in files)

def directory_counts(repo, files):
    counts = Counter(os.path.relpath(os.path.dirname(f), repo) for f in files)
    return [f"  {d}/: {n}" for d, n in sorted(counts.items())]

def main():
    ap = argparse.ArgumentParser(prog="survey-files.py")
    ap.add_argument("repo"); ap.add_argument("paths", nargs="+")
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP)
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out): os.remove(a.out)
    if a.cap < 1: ap.error("--cap must be at least 1")
    repo = os.path.realpath(a.repo)
    files = resolve(repo, a.paths, a.exclude)
    if not files: sys.exit("no files to survey after exclusions")
    if len(files) > a.cap:
        print("\n".join([f"{len(files)} files, over the cap of {a.cap}; narrow the target:"] + directory_counts(repo, files)))
        sys.exit(1)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh: fh.write("\n".join(files) + "\n")
    print(f"{len(files)} file{'' if len(files) == 1 else 's'} in {a.out}")

if __name__ == "__main__": main()

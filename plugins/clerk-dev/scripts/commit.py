#!/usr/bin/env python3
"""Commit named files with a Conventional Commits subject and the Assisted-by trailer.

Usage: commit.py WORKTREE FILE... < message

The only way skills commit. Refuses, committing nothing, a subject that is not
`<type>(<area>)!?: <text>` with a type from the table in skills/review/commits.md,
and any file or staged change under .clerk-dev/. Stages exactly the named files
(deletions included), commits only them, and prints the new short sha.
"""
import os, re, subprocess, sys

import records

COMMITS_MD = os.path.join(records.PLUGIN_ROOT, "skills", "review", "commits.md")
TRAILER_LINE = re.compile(r"^[A-Za-z][A-Za-z-]*: \S")

def allowed_types(path=COMMITS_MD):
    with open(path, encoding="utf-8") as fh: rows = [l for l in fh if l.startswith("|")]
    return [m.group(1) for l in rows[2:] if (m := re.match(r"\|\s*`([a-z]+)`\s*\|", l))]

def subject_error(subject, types):
    if re.fullmatch(rf"(?:{'|'.join(types)})\([^()\s][^()]*\)!?: \S.*", subject): return None
    return f"subject does not match <type>(<area>)!?: <text> with type one of {', '.join(types)}\n  offending subject: {subject}"

def with_trailer(message, version):
    line = "Assisted-by: Matthias' clerk-dev" + (f" {version}" if version else "")
    paras = message.strip().split("\n\n")
    last = [l for l in paras[-1].split("\n") if not l.startswith("Assisted-by:")]
    if len(paras) > 1 and all(TRAILER_LINE.match(l) for l in last): paras[-1:] = ["\n".join([line, *last])]
    else: paras.append(line)
    return "\n\n".join(paras) + "\n"

def in_clerk_dev(path): return ".clerk-dev" in os.path.normpath(path).split(os.sep)

def git(wt, *args, stdin=None):
    r = subprocess.run(["git", "-C", wt, *args], capture_output=True, text=True, input=stdin)
    if r.returncode != 0: sys.exit(f"git {' '.join(args)} failed: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()

def main():
    if len(sys.argv) < 3: sys.exit(__doc__)
    wt, names = os.path.abspath(sys.argv[1]), sys.argv[2:]
    files = [os.path.relpath(os.path.join(wt, n), wt) for n in names]
    message = sys.stdin.read()
    if not message.strip(): sys.exit("empty commit message on stdin")
    err = subject_error(message.strip().split("\n")[0], allowed_types())
    if err: sys.exit(err)
    bad = [f for f in files + git(wt, "diff", "--cached", "--name-only").split("\n") if f and in_clerk_dev(f)]
    if bad: sys.exit(f"refusing to commit under .clerk-dev/: {', '.join(bad)}")
    gone = [f for f in files if not os.path.lexists(os.path.join(wt, f))]
    if gone: git(wt, "rm", "-q", "--cached", "--ignore-unmatch", "--", *gone)
    if len(gone) < len(files): git(wt, "add", "-A", "--", *[f for f in files if f not in gone])
    git(wt, "commit", "-q", "-F", "-", "--", *files, stdin=with_trailer(message, records.plugin_version()))
    print(git(wt, "rev-parse", "--short", "HEAD"))

if __name__ == "__main__": main()

#!/usr/bin/env python3
"""What a review needs to know about a worktree before it starts, in one call.

Usage: preflight.py [WORKTREE ...] [--log N]

For each worktree (default: the current directory) prints a Markdown block:
  - the worktree root, branch, HEAD, and git common directory;
  - the repository's setup lines (<common dir>/clerk-dev/setup) and repo context;
  - the remote main (origin/HEAD), or that it is missing;
  - when the last fetch was (FETCH_HEAD in the common directory);
  - the merge base with the remote main and the commit count since it;
  - the branch's commit messages (newest N, default 50), `diff --stat`
    against the merge base, and `status --short`;
  - the plugin's files under .clerk-dev/: branch notes and whether they have a
    Purpose, the review workspace and its rows, open follow-ups, and the
    latest run with whether it is unfinished and still at HEAD.

Never fetches, writes nothing, and always exits 0: a missing piece is
printed as missing rather than failing the call.
"""
import argparse, datetime, os, re, subprocess, time
from records import load_script

rs = load_script("status.py")
git = rs.git

def git_raw(repo, *args):
    """Like git(), but keeps leading whitespace, which aligns `--stat` and `status --short`."""
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return r.stdout.rstrip() if r.returncode == 0 else ""

def age(seconds):
    if seconds < 3600: return f"{int(seconds // 60)} minutes ago"
    if seconds < 2 * 86400: return f"{int(seconds // 3600)} hours ago"
    return f"{int(seconds // 86400)} days ago"

def fence(text):
    return ["```", text.rstrip() or "(none)", "```"]

def purpose_state(path):
    if not os.path.exists(path): return "missing"
    text = open(path, encoding="utf-8").read()
    m = re.search(r"^## Purpose\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m: return "present, no Purpose section"
    return "present, Purpose filled in" if m.group(1).strip() else "present, Purpose empty"

def latest_run(wt, head):
    run = os.path.realpath(os.path.join(wt, ".clerk-dev", "latest"))
    if not os.path.isdir(run): return "none"
    label = os.path.basename(run)
    if not os.path.exists(os.path.join(run, "target.txt")): return f"`.clerk-dev/{label}`, stopped before scoping finished"
    target = open(os.path.join(run, "target.txt")).read().splitlines()
    what = target[0] if target else "?"
    at = target[2].strip() if len(target) > 2 else ""
    progress = os.path.join(run, "progress.md")
    unchecked = len(re.findall(r"^\s*- \[ \]", open(progress, encoding="utf-8").read(), re.M)) if os.path.exists(progress) else 0
    if os.path.exists(os.path.join(run, "report.md")) and not unchecked: state = "finished"
    elif unchecked: state = f"unfinished ({unchecked} unchecked progress items)"
    else: state = "unfinished (no report yet)"
    where = "at current HEAD" if at and at == head else (f"at `{at[:9]}`, HEAD has moved" if at else "HEAD unknown")
    return f"`.clerk-dev/{label}` of {what}, {state}, {where}"

def block(path, log_n):
    out = []
    wt = git(path, "rev-parse", "--show-toplevel")
    if not wt:
        return [f"## {path}", "", "Not a git worktree (or the path does not exist).", ""]
    load_script("records.py").guard(wt)
    rows = rs.workspace_rows(wt)
    branch = git(wt, "rev-parse", "--abbrev-ref", "HEAD")
    head = git(wt, "rev-parse", "HEAD")
    common = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir")
    out += [f"## {rs.repo_name(wt, rows)} ({branch})", "",
            f"- Worktree: `{wt}`", f"- HEAD: `{head[:9]}`", f"- Common dir: `{common}`"]

    rec = load_script("records.py")
    setup = rec.setup_path(wt)
    lines = open(setup, encoding="utf-8").read().strip().splitlines() if os.path.exists(setup) else []
    out.append(f"- Setup: {'; '.join(lines) if lines else 'none'}")
    context = rec.repo_context_path(wt)
    out.append(f"- Repo context: `{context}`" if os.path.exists(context) else "- Repo context: none")

    main = git(wt, "rev-parse", "--abbrev-ref", "origin/HEAD")
    out.append(f"- Remote main: `{main}`" if main else "- Remote main: missing (origin/HEAD is not set)")
    fh = os.path.join(common, "FETCH_HEAD")
    if os.path.exists(fh):
        mtime = os.path.getmtime(fh)
        stamp = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        out.append(f"- Last fetch: {stamp} ({age(time.time() - mtime)})")
    else:
        out.append("- Last fetch: never (no FETCH_HEAD)")

    base = git(wt, "merge-base", "HEAD", main) if main else ""
    if base:
        count = git(wt, "rev-list", "--count", f"{base}..HEAD")
        out.append(f"- Merge base: `{base[:9]}` ({count} commit{'' if count == '1' else 's'} on the branch)")
    else:
        out.append("- Merge base: unknown")

    review = os.path.join(wt, ".clerk-dev")
    out.append(f"- Branch notes: {purpose_state(os.path.join(review, 'branch-notes.md'))}")
    if rows:
        out.append("- Workspace: " + ", ".join(f"{n} `{p}`" + ("" if os.path.isdir(p) else " (missing)") for n, p in rows))
    else:
        out.append("- Workspace: none")
    open_fu = [i for i in rs.parse_followups(wt) if not i["done"]]
    out.append(f"- Open follow-ups: {len(open_fu)}")
    out.append(f"- Latest run: {latest_run(wt, head)}")

    if base:
        out += ["", f"### Commits (newest {log_n})", ""]
        out += fence(git_raw(wt, "log", f"-{log_n}", "--format=%h %s%n%b", f"{base}..HEAD"))
        out += ["", "### Changed files", ""]
        out += fence(git_raw(wt, "diff", "--stat=120", f"{base}...HEAD"))
    out += ["", "### Uncommitted", ""]
    out += fence(git_raw(wt, "status", "--short"))
    out.append("")
    return out

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("worktrees", nargs="*", default=["."])
    ap.add_argument("--log", type=int, default=50)
    a = ap.parse_args()
    out = []
    for path in a.worktrees:
        try:
            out += block(os.path.expanduser(path), a.log)
        except (Exception, SystemExit) as e:  # report and go on; one bad worktree should not hide the others
            out += [f"## {path}", "", f"preflight failed: {e}", ""]
    print("\n".join(out))

if __name__ == "__main__":
    main()

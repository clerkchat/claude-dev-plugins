#!/usr/bin/env python3
"""Find open review findings whose code moved after the review.

A review run judges the code at the HEAD recorded in RUN/target.txt. Commits
made since then (follow-ups, the user's own edits) can resolve a finding or
change what its fix should be. This script finds the candidates cheaply, by
file: an open finding is a candidate when a commit since the review touched
its file, leaving out commits recorded as the fix of any finding (in
RUN/status.tsv, RUN/commits.tsv, or RUN/resolution/). Commits are followed along the first parent, so a merge from
the main branch counts as one commit. It reads no diff content; judging the candidates is the
caller's job.

Usage:
  stale-findings.py RUN [--repo .] [--queued]
      Candidates, as TSV: number, merged_id, instruction, file, commits
      (short shas, oldest first), labels (follow-up ids those commits closed).
      --queued keeps only findings marked fix, noted, or discuss.
  stale-findings.py RUN --open-in FILE [FILE ...]
      Open findings that point at any of the given files, as TSV: number,
      merged_id, instruction, file, line, claim. For a fixer that wants to
      know which findings sit in the code it is about to change.
  stale-findings.py RUN --delta [--repo .]
      Every commit since the review, first parent, oldest first, as TSV:
      sha, kind, files (comma-separated), subject. Kind is follow-up, fix,
      narrow (read by a narrow review), merge, format (layout only), or
      unreviewed. Only the unreviewed ones are new to every review; an
      incremental review reads those, and the fixes wait for the final pass.
  stale-findings.py RUN --record ID=VERDICT[:NOTE] [...] --through SHA
      Remember a judgment (still, resolved, or changed) in RUN/stale.tsv, so
      the commits up to SHA are not offered for that finding again. ID is a
      finding number, or #<merged id>.

Open means a status other than fixed, wont-fix, or deferred, and an
instruction other than defer or ignore.
"""
import argparse, datetime, os, re, subprocess, sys
from records import load_script

CLOSED_STATUS = {"fixed", "wont-fix", "deferred"}
CLOSED_CHOICE = {"defer", "ignore"}
QUEUED_CHOICE = {"fix", "noted", "discuss"}
VERDICTS = {"still", "resolved", "changed"}

def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip() if r.returncode == 0 else ""

def tsv(path):
    if not os.path.exists(path): return []
    rows = open(path, encoding="utf-8").read().splitlines()
    return [r.split("\t") for r in rows[1:] if r.strip()]

def load_findings(run):
    mf = load_script("merge-findings.py")
    out = {}
    text = open(os.path.join(run, "merged.md"), encoding="utf-8").read()
    for block in mf.parse_blocks(text):
        for e in mf.parse_entries(block, "merged"):
            mid = re.sub(r"\D", "", str(e.get("id", "")))
            if mid: out[int(mid)] = e
    return out

def state(run):
    status = {int(r[0]): r for r in tsv(os.path.join(run, "status.tsv")) if r[0].isdigit()}
    instr = {int(r[0]): (r[1] if len(r) > 1 else "") for r in tsv(os.path.join(run, "instructions.tsv")) if r[0].isdigit()}
    numbers = {int(r[1]): r[0] for r in tsv(os.path.join(run, "numbers.tsv")) if len(r) > 1 and r[1].isdigit()}
    return status, instr, numbers

def is_open(mid, status, instr):
    st = status.get(mid, [str(mid), "open"])[1] if mid in status else "open"
    choice = re.sub(r"\(.*\)$", "", instr.get(mid, ""))
    return st not in CLOSED_STATUS and choice not in CLOSED_CHOICE

def fix_commits(repo, status, run=None):
    """Every commit made to fix a finding. status.tsv keeps one ref per
    finding, so a fix that took two commits (a second attempt after a partial
    recheck) is only complete from RUN/commits.tsv, which keeps every commit
    a status ever named, and RUN/resolution/, which names each attempt."""
    text = [row[2] for row in status.values() if len(row) > 2]
    if run:
        text += [r[1] for r in tsv(os.path.join(run, "commits.tsv")) if len(r) > 1]
        rdir = os.path.join(run, "resolution")
        for name in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
            text.append(open(os.path.join(rdir, name), encoding="utf-8").read())
    toks = {t for ref in text for t in re.findall(r"\b[0-9a-f]{7,40}\b", ref)}
    if not toks: return set()
    r = subprocess.run(["git", "-C", repo, "cat-file", "--batch-check=%(objectname) %(objecttype)"],
                       input="".join(t + "^{commit}\n" for t in sorted(toks)), capture_output=True, text=True)
    return {p[0] for p in (l.split() for l in r.stdout.splitlines()) if len(p) == 2 and p[1] == "commit"}

def followup_labels(repo):
    """Commits that closed a follow-up, by full sha, to its id (F3)."""
    fu = load_script("followups.py")
    labels = {}
    for it in fu.read(os.path.join(repo, ".clerk-dev", "followups.md")):
        m = re.search(r"\bin ([0-9a-f]{7,40})\b", it["fields"].get("Outcome", "") or it["fields"].get("Done", ""))
        if not m: continue
        full = git(repo, "rev-parse", "--verify", "-q", m.group(1) + "^{commit}", check=False)
        if full: labels[full] = it["id"]
    return labels

def narrow_covered(repo):
    """Commits read by narrow reviews of this branch."""
    covered = set()
    root = os.path.join(repo, ".clerk-dev")
    for d in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        p = os.path.join(root, d, "narrow.txt")
        if d in ("latest", "latest-feature") or d.endswith("-feature") or not os.path.exists(p): continue
        lines = open(p).read().splitlines()
        if len(lines) < 3: continue
        base, head = lines[1].strip(), lines[2].split()[0].strip()
        if base == "HEAD" or not head: continue
        covered.update(git(repo, "rev-list", f"{base}..{head}", check=False).splitlines())
    return covered

def format_only(repo, sha):
    """True when a commit changes layout only: with whitespace and the
    trailing commas a formatter adds or drops removed, each file's removed
    lines read the same as its added lines."""
    diff = git(repo, "show", "--format=", "--unified=0", "--no-color", sha, check=False)
    if not diff: return False
    files, cur = {}, None
    for line in diff.splitlines():
        if line.startswith("diff --git"): cur = files.setdefault(line, [[], []]); continue
        if cur is None or line.startswith(("---", "+++")): continue
        if line.startswith("-"): cur[0].append(line[1:])
        elif line.startswith("+"): cur[1].append(line[1:])
    norm = lambda ls: re.sub(r",(?=[)\]}])", "", re.sub(r"\s+", "", "".join(ls)))
    return bool(files) and all(norm(old) == norm(new) for old, new in files.values())

def classify_since(repo, run, reviewed, head):
    """Each first-parent commit in reviewed..head, oldest first, as (sha,
    kind, subject). Follow-up and fix commits were read by the fixer and a
    recheck, narrow ones by a narrow review; merges bring in the main
    branch. What is left is unreviewed."""
    status, _, _ = state(run)
    fixes = fix_commits(repo, status, run)
    fups = set(followup_labels(repo))
    narrow = narrow_covered(repo)
    out = []
    log = git(repo, "log", "--first-parent", "--reverse", "--format=%H%x09%P%x09%s", f"{reviewed}..{head}", check=False)
    for line in log.splitlines():
        sha, parents, subj = (line.split("\t") + ["", ""])[:3]
        if sha in fups: kind = "follow-up"
        elif sha in fixes: kind = "fix"
        elif sha in narrow: kind = "narrow"
        elif len(parents.split()) > 1: kind = "merge"
        elif format_only(repo, sha): kind = "format"
        else: kind = "unreviewed"
        out.append((sha, kind, subj))
    return out

def cmd_delta(a, run, repo):
    target = open(os.path.join(run, "target.txt")).read().splitlines()
    if len(target) < 3: sys.exit("target.txt has no HEAD line")
    reviewed, head = target[2].strip(), git(repo, "rev-parse", "HEAD")
    if subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", reviewed, head]).returncode != 0:
        sys.exit(f"the reviewed commit {reviewed[:9]} is not an ancestor of HEAD (rebased?)")
    rows = classify_since(repo, run, reviewed, head)
    print("sha\tkind\tfiles\tsubject")
    for sha, kind, subj in rows:
        files = git(repo, "show", "--format=", "--name-only", "-m", "--first-parent", sha, check=False).split()
        print(f"{sha}\t{kind}\t{','.join(dict.fromkeys(files))}\t{subj}")
    kinds = [k for _, k, _ in rows]
    print(f"{len(rows)} commits since {reviewed[:9]}: " + ", ".join(f"{kinds.count(k)} {k}" for k in dict.fromkeys(kinds)), file=sys.stderr)

def through_map(run):
    return {int(r[0]): r[1] for r in tsv(os.path.join(run, "stale.tsv")) if r[0].isdigit() and len(r) > 1}

def resolve_id(spec, numbers):
    by_num = {v: k for k, v in numbers.items()}
    if spec.startswith("#"): return int(spec[1:])
    if spec not in by_num: sys.exit(f"finding {spec} not in numbers.tsv")
    return by_num[spec]

def candidates(run, repo, queued=False):
    """(reviewed commit, rows): one row per open finding whose file a commit
    since the review touched, as (number, merged_id, instruction, file,
    commits, follow-up labels). Exits when the reviewed commit is not an
    ancestor of HEAD."""
    findings = load_findings(run)
    status, instr, numbers = state(run)
    target = open(os.path.join(run, "target.txt")).read().splitlines()
    if len(target) < 3: sys.exit("target.txt has no HEAD line")
    reviewed = target[2].strip()
    head = git(repo, "rev-parse", "HEAD")
    if subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", reviewed, head]).returncode != 0:
        sys.exit(f"the reviewed commit {reviewed[:9]} is not an ancestor of HEAD (rebased?); compare by hand or re-review")
    skip = fix_commits(repo, status, run)
    labels = followup_labels(repo)
    through = through_map(run)
    rows = []
    for mid in sorted(findings, key=lambda m: int(numbers.get(m, 10**6))):
        if mid not in numbers or not is_open(mid, status, instr): continue
        choice = instr.get(mid, "")
        if queued and re.sub(r"\(.*\)$", "", choice) not in QUEUED_CHOICE: continue
        f = str(findings[mid].get("file", "")).strip()
        if not f: continue
        start = reviewed
        if mid in through and subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", reviewed, through[mid]]).returncode == 0:
            start = through[mid]
        log = git(repo, "log", "--first-parent", "--reverse", "--format=%H", f"{start}..{head}", "--", f, check=False)
        commits = [c for c in log.splitlines() if c and c not in skip]
        if not commits: continue
        tags = sorted({labels[c] for c in commits if c in labels})
        rows.append((numbers[mid], str(mid), choice or "-", f, ",".join(c[:9] for c in commits), ",".join(tags) or "-"))
    return reviewed, rows

def cmd_candidates(a, run, repo):
    reviewed, rows = candidates(run, repo, a.queued)
    print("number\tmerged_id\tinstruction\tfile\tcommits\tlabels")
    for r in rows: print("\t".join(r))
    print(f"{len(rows)} open findings with code changed since {reviewed[:9]}", file=sys.stderr)

def cmd_open_in(a, run, repo):
    findings = load_findings(run)
    status, instr, numbers = state(run)
    wanted = {os.path.normpath(p) for p in a.open_in}
    print("number\tmerged_id\tinstruction\tfile\tline\tclaim")
    for mid in sorted(findings, key=lambda m: int(numbers.get(m, 10**6))):
        e = findings[mid]
        f = os.path.normpath(str(e.get("file", "")).strip() or ".")
        if mid not in numbers or f not in wanted or not is_open(mid, status, instr): continue
        claim = re.sub(r"\s+", " ", str(e.get("claim", "")))[:200]
        print("\t".join([numbers[mid], str(mid), instr.get(mid, "") or "-", f, str(e.get("line", "")), claim]))

def cmd_record(a, run, repo):
    if not a.through: sys.exit("--record needs --through <sha>")
    _, _, numbers = state(run)
    sha = git(repo, "rev-parse", a.through)
    path = os.path.join(run, "stale.tsv")
    rows = {int(r[0]): r for r in tsv(path) if r[0].isdigit()}
    today = datetime.date.today().isoformat()
    for spec in a.record:
        m = re.match(r"^(#?\d+)=([a-z]+)(?::(.*))?$", spec.strip())
        if not m or m.group(2) not in VERDICTS:
            sys.exit(f"bad --record {spec!r}; use N=still, N=resolved:<note>, N=changed:<note>")
        mid = resolve_id(m.group(1), numbers)
        rows[mid] = [str(mid), sha, m.group(2), (m.group(3) or "").replace("\t", " "), today]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("merged_id\tthrough\tverdict\tnote\tdate\n")
        for mid in sorted(rows): fh.write("\t".join(rows[mid]) + "\n")
    print(f"recorded {len(a.record)} in {path}")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run"); ap.add_argument("--repo", default=".")
    ap.add_argument("--queued", action="store_true")
    ap.add_argument("--open-in", nargs="+", metavar="FILE")
    ap.add_argument("--record", action="append", default=[], metavar="ID=VERDICT[:NOTE]")
    ap.add_argument("--through", metavar="SHA")
    ap.add_argument("--delta", action="store_true")
    a = ap.parse_args()
    run, repo = os.path.realpath(a.run), a.repo
    if a.record: cmd_record(a, run, repo)
    elif a.open_in: cmd_open_in(a, run, repo)
    elif a.delta: cmd_delta(a, run, repo)
    else: cmd_candidates(a, run, repo)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Where a worktree's review work stands, from files and git only.

Usage: review-status.py [WORKTREE] [--run LABEL] [--no-mark]

Prints a short Markdown summary:
  - the review run (label, target, reviewed commit, date), and the feature
    run's report when .review/latest-feature points at one;
  - commits since the review that no review has read: not a follow-up's
    commit, not the fix of a finding (status.tsv, commits.tsv, or a
    resolution note names it), not covered by a narrow review, not
    formatting only, not a merge; plus staged and unstaged changes;
  - this worktree's open follow-ups, marking the ones added since the last
    status (remembered in .review/status-seen);
  - open follow-ups in the other worktrees of .review/review-workspace.md;
  - findings: unmarked ones by report section, the unmarked ones added
    since the first report (tagged [new] in the report), the fix queue, discussions,
    in-progress fixes, and open findings whose code moved since the review;
  - a numbered list of next steps, most pressing first; once triage is done
    and fixes have landed, the last step is the final pass.

--no-mark leaves .review/status-seen untouched.
"""
import argparse, datetime, importlib.util, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sf", os.path.join(HERE, "stale-findings.py"))
assert spec and spec.loader
sf = importlib.util.module_from_spec(spec); spec.loader.exec_module(sf)

SECTION_NAMES = {"fix": "Fix before merging", "look": "Worth a look", "existing": "Already on main", "debt": "Cleanup and refactoring"}

def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""

def plural(x):
    n = x if isinstance(x, int) else len(x)
    return "" if n == 1 else "s"

def short(text, n=90):
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"

def parse_followups(wt):
    spec = importlib.util.spec_from_file_location("fu", os.path.join(HERE, "followups.py"))
    assert spec and spec.loader
    fu = importlib.util.module_from_spec(spec); spec.loader.exec_module(fu)
    return [{"id": int(it["id"][1:]), "done": it["done"], "text": it["text"],
             "from": it["fields"].get("From", ""), "added": it["fields"].get("Added", "")}
            for it in fu.read(os.path.join(wt, ".review", "followups.md"))]

def workspace_rows(wt):
    """(repo name, real worktree path) for each row of the review workspace
    table in .review/review-workspace.md; empty when there is no such file."""
    p = os.path.join(wt, ".review", "review-workspace.md")
    if not os.path.exists(p): return []
    rows = []
    for line in open(p, encoding="utf-8"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.lstrip().startswith("|") else []
        if len(cells) < 2 or cells[0] in ("", "Repo") or set(cells[0]) <= set("-: "): continue
        rows.append((cells[0], os.path.realpath(os.path.expanduser(cells[1]))))
    return rows

def repo_name(wt, rows):
    """The repository's name in follow-up `From:` lines: its row in the review
    workspace, else the last segment of its origin URL, else the directory of
    its main checkout."""
    real = os.path.realpath(wt)
    for name, path in rows:
        if path == real: return name
    url = git(wt, "remote", "get-url", "origin")
    if url: return re.sub(r"\.git$", "", url.rstrip("/")).rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    common = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return os.path.basename(os.path.dirname(common)) if common else os.path.basename(real)

def related_worktrees(wt, rows):
    real = os.path.realpath(wt)
    return [(name, path) for name, path in rows if path != real and os.path.isdir(path)]

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("worktree", nargs="?", default=".")
    ap.add_argument("--run"); ap.add_argument("--no-mark", action="store_true")
    a = ap.parse_args()
    wt = git(a.worktree, "rev-parse", "--show-toplevel") or os.path.realpath(a.worktree)
    run = os.path.realpath(os.path.join(wt, ".review", a.run or "latest"))
    have_run = os.path.exists(os.path.join(run, "merged.md")) and os.path.exists(os.path.join(run, "target.txt"))
    branch = git(wt, "rev-parse", "--abbrev-ref", "HEAD")
    head = git(wt, "rev-parse", "HEAD")
    out, steps = [], []
    rows = workspace_rows(wt)
    out.append(f"## Where {repo_name(wt, rows)} stands ({branch})\n")

    # Review run and commits since it
    status = instr = numbers = {}
    reviewed = ""
    if have_run:
        target = open(os.path.join(run, "target.txt")).read().splitlines()
        reviewed = target[2].strip() if len(target) > 2 else ""
        status, instr, numbers = sf.state(run)
        label = os.path.basename(run)
        when = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(run, "report.md"))).strftime("%Y-%m-%d %H:%M") \
            if os.path.exists(os.path.join(run, "report.md")) else "not finished"
        out.append(f"**Review:** `.review/{label}` of {target[0] if target else '?'}, reviewed up to `{reviewed[:9]}`, report from {when}.")
    else:
        out.append("**Review:** none yet in this worktree.")
        steps.append("Run a review: `/clerk-dev:review` (or \"review the branch\").")
    feature = os.path.realpath(os.path.join(wt, ".review", "latest-feature"))
    if os.path.exists(os.path.join(feature, "report.md")):
        out.append(f"**Feature review:** `.review/{os.path.basename(feature)}/report.md` (the cross-repository check; `.review/latest-feature`).")

    unreviewed, counts_fix = [], 0
    if reviewed and subprocess.run(["git", "-C", wt, "merge-base", "--is-ancestor", reviewed, head]).returncode == 0:
        counts = {"fix": 0, "follow-up": 0, "narrow": 0, "format": 0, "merge": 0}
        for sha, kind, subj in sf.classify_since(wt, run, reviewed, head):
            if kind == "unreviewed": unreviewed.append((sha, subj))
            else: counts[kind] += 1
        total = sum(counts.values()) + len(unreviewed)
        counts_fix = counts["fix"]
        names = {"fix": ("fix", "fixes"), "follow-up": ("follow-up", "follow-ups"), "narrow": ("covered by a narrow review", "covered by narrow reviews"),
                 "format": ("formatting only", "formatting only"), "merge": ("merge", "merges")}
        parts = [f"{v} {names[k][v != 1]}" for k, v in counts.items() if v]
        out.append(f"**Since the review:** {total} commits ({', '.join(parts + ([f'{len(unreviewed)} not reviewed'] if unreviewed else [])) if total else 'none'}).")
        for sha, subj in unreviewed[-5:]:
            out.append(f"- not reviewed: `{sha[:9]}` {short(subj, 80)}")
        if len(unreviewed) > 5: out.append(f"- and {len(unreviewed) - 5} earlier")
    elif reviewed:
        out.append(f"**Since the review:** the reviewed commit `{reviewed[:9]}` is not an ancestor of HEAD (rebased?); a full review is needed.")
        steps.append("The branch was rebased since the review: run `/clerk-dev:review --full`.")

    staged = git(wt, "diff", "--cached", "--name-only").splitlines()
    unstaged = git(wt, "diff", "--name-only").splitlines()
    if staged or unstaged:
        out.append(f"**Working tree:** {len(staged)} files staged, {len(unstaged)} with unstaged changes.")

    # Follow-ups here
    items = parse_followups(wt)
    seen_path = os.path.join(wt, ".review", "status-seen")
    seen = int(open(seen_path).read().strip() or 0) if os.path.exists(seen_path) else 0
    open_items = [i for i in items if not i["done"]]
    out.append("")
    if open_items:
        new = [i for i in open_items if i["id"] > seen]
        out.append(f"**Follow-ups owed here:** {len(open_items)} open" + (f", {len(new)} new since the last status" if seen and new else "") + ".")
        for i in open_items:
            tag = " (new)" if seen and i["id"] > seen else ""
            out.append(f"- F{i['id']}{tag}: {short(i['text'])} ({i['from'] or 'source unknown'})")
    else:
        out.append(f"**Follow-ups owed here:** none open ({len(items)} done)." if items else "**Follow-ups owed here:** none.")
    if items and not a.no_mark:
        try: open(seen_path, "w").write(str(max(i["id"] for i in items)) + "\n")
        except OSError: pass

    # Follow-ups elsewhere
    me = repo_name(wt, rows)
    rel = []
    for name, other in related_worktrees(wt, rows):
        its = [i for i in parse_followups(other) if not i["done"]]
        mine = [i for i in its if re.split(r"[ @]", i["from"])[0] == me]
        rel.append(f"{name} {len(its)} open" + (f" ({len(mine)} from {me})" if its else ""))
    if rel: out.append(f"**Follow-ups owed by related worktrees:** {'; '.join(rel)}.")

    # Findings
    if have_run:
        findings = sf.load_findings(run)
        sections = {}
        for r in sf.tsv(os.path.join(run, "numbers.tsv")):
            if len(r) > 2 and r[1].isdigit(): sections[int(r[1])] = r[2]
        unmarked, queue, discuss, inprog, new = {}, [], [], [], []
        ap = os.path.join(run, "reconcile", "appended.tsv")
        appended = {int(x) for x in open(ap).read().split()[1:] if x.isdigit()} if os.path.exists(ap) else set()
        for mid in findings:
            if mid not in numbers or not sf.is_open(mid, status, instr): continue
            choice = re.sub(r"\(.*\)$", "", instr.get(mid, ""))
            st = status[mid][1] if mid in status else "open"
            sec = sections.get(mid, "")
            if st == "in-progress": inprog.append(numbers[mid])
            if choice in ("fix", "noted"): queue.append(numbers[mid])
            elif choice == "discuss": discuss.append(numbers[mid])
            elif not choice and sec in SECTION_NAMES: unmarked.setdefault(sec, []).append(numbers[mid])
            if not choice and st == "open" and mid in appended: new.append(numbers[mid])
        try:
            _, moved = sf.candidates(run, wt)
        except SystemExit:
            moved = []
        closed = sum(1 for m in findings if m in numbers and not sf.is_open(m, status, instr))
        out.append("")
        out.append(f"**Findings:** {len(numbers)} in the report, {closed} closed (fixed, won't fix, deferred, ignored).")
        for sec, nums in unmarked.items():
            nums.sort(key=int)
            out.append(f"- unmarked in {SECTION_NAMES[sec]}: {len(nums)} ({', '.join(nums[:12])}{', …' if len(nums) > 12 else ''})")
        if new:
            new.sort(key=int)
            out.append(f"- new since the first report, unmarked: {len(new)} ({', '.join(new[:12])}{', …' if len(new) > 12 else ''}); `grep -n '\\[new\\]' report.md` finds them")
        if queue: out.append(f"- marked to fix, not yet fixed: {len(queue)}")
        if discuss: out.append(f"- marked to discuss: {len(discuss)}")
        if inprog: out.append(f"- fix in progress (partly fixed or tests failed): {', '.join(sorted(inprog, key=int))}")
        if moved: out.append(f"- open findings whose code changed since the review and not yet cross-checked: {len(moved)}")

        if open_items: steps.insert(0, f"Work the open follow-up{plural(open_items)} ({len(open_items)}): \"go through the follow-ups\".")
        if staged: steps.append("Review the staged changes before committing: \"review the staged changes\".")
        if unreviewed and len(unreviewed) <= 3:
            cmds = ", ".join(f"`/clerk-dev:review {'HEAD' if sha == head else sha[:9]}`" for sha, _ in unreviewed)
            steps.append(f"Review the unreviewed commit{plural(unreviewed)}, each added to this review: {cmds}.")
        elif unreviewed:
            steps.append(f"Review the {len(unreviewed)} unreviewed commits with an incremental review of the branch: \"re-review the branch\".")
        if moved: steps.append(f"Cross-check the finding{plural(moved)} whose code moved ({len(moved)}): \"cross-check the findings\".")
        n_unmarked = sum(len(v) for v in unmarked.values())
        if n_unmarked: steps.append(f"Mark the unmarked finding{plural(n_unmarked)} ({n_unmarked}) in `.review/{os.path.basename(run)}/report.md`.")
        if queue: steps.append(f"Fix the finding{plural(queue)} marked to fix ({len(queue)}): \"work the queue\".")
        if discuss: steps.append(f"Decide the finding{plural(discuss)} marked for discussion ({len(discuss)}): \"go through the discussions\".")
        if inprog: steps.append(f"Look at the fixes left in progress: {', '.join(sorted(inprog, key=int))}.")
        # Fixes are rechecked one finding at a time, never re-reviewed as a
        # branch; once triage is done, the final pass reads them all together.
        triage_left = sum(len(v) for v in unmarked.values()) + len(queue) + len(discuss) + len(inprog)
        if counts_fix and not triage_left and not unreviewed and not open_items:
            steps.append(f"Triage is done and {counts_fix} fix{'es' if counts_fix != 1 else ''} landed since the review: \"do a final review pass\" reads the branch once more at the merge bar.")

    out.append("")
    if steps:
        out.append("**Next:**")
        out.extend(f"{n}. {s}" for n, s in enumerate(steps, 1))
    else:
        out.append("**Next:** nothing pending.")
    print("\n".join(out))

if __name__ == "__main__":
    main()

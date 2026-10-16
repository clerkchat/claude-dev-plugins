#!/usr/bin/env python3
"""Where a worktree's review work stands, from files and git only.

Usage: review-status.py [WORKTREE] [--run LABEL] [--no-mark]

Prints a short Markdown summary:
  - the review run (label, target, reviewed commit, date), and the feature
    run's report when .clerk-dev/latest-feature points at one;
  - commits since the review that no review has read: not a follow-up's
    commit, not the fix of a finding (status.tsv, commits.tsv, or a
    resolution note names it), not covered by a narrow review, not
    formatting only, not a merge; plus staged and unstaged changes;
  - this worktree's open follow-ups, marking the ones added since the last
    status (remembered in .clerk-dev/status-seen);
  - open follow-ups in the other worktrees of .clerk-dev/review-workspace.md;
  - findings: unmarked ones by report section, the unmarked ones added
    since the first report (tagged [new] in the report), the fix queue, discussions,
    in-progress fixes, and open findings whose code moved since the review;
  - this worktree's passes (.clerk-dev/passes.md): open, ended but unchecked,
    and checked ones whose check run still has open findings;
  - the feature, when the hub (records.py hub) holds one: records by type,
    open design questions (settle-first ones named), open items in active
    specs, and passes in progress in the other worktrees, by repository;
  - a numbered list of next steps, most pressing first; once triage is done
    and fixes have landed, the last step is the final pass.

--no-mark leaves .clerk-dev/status-seen untouched.
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
            for it in fu.read(os.path.join(wt, ".clerk-dev", "followups.md"))]

def workspace_rows(wt):
    """(repo name, real worktree path) for each row of the review workspace
    table in .clerk-dev/review-workspace.md; empty when there is no such file."""
    p = os.path.join(wt, ".clerk-dev", "review-workspace.md")
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

def load(name):
    s = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), os.path.join(HERE, name))
    assert s and s.loader
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m

def read_passes(wt):
    """The pass log's entries, or None with the reason when it cannot be read."""
    p = os.path.join(wt, ".clerk-dev", "passes.md")
    if not os.path.exists(p): return [], None
    try: return load("passes.py").read(p), None
    except SystemExit as e: return [], str(e)

def pass_word(e):
    """A pass's state in a few words: open, ended, or its check's result."""
    f = e["f"]; st = f.get("Status", "")
    if st == "ended": return "ended, not checked" + (" (no commits)" if f.get("Note") == "no commits" else "")
    if st != "checked": return st
    check = f.get("Check") or ""
    cs = load("passes.py").counts(check)
    if cs is None: return "checked, " + check.split(";")[-1].strip()
    n = sum(cs.values())
    return "checked, clean" if n == 0 else f"checked, {n} finding{plural(n)} in `{check.split(';')[0].strip()}`"

def pass_line(e):
    return f"{e['id']} {e['title']} {pass_word(e)}"

def feature_block(wt, rows, out):
    """Feature records, open design questions, spec open items, and passes in
    the other worktrees, when the hub holds a feature. Returns the steps that
    come before anything else (settle-first questions) and those that come
    last."""
    first, later = [], []
    rc = load("records.py"); it = load("items.py")
    try: d = rc.fdir(wt)
    except SystemExit as e:
        out.append(f"**Feature:** {e}"); return first, later
    fp = os.path.join(d, "feature.md")
    if not os.path.exists(fp): return first, later
    name = (open(fp, encoding="utf-8").readline().strip().split(":", 1) + [""])[1].strip() or "feature"
    recs = rc.records(d)
    active = {}
    for r in recs:
        if r.get("type") != "brainstorm" and r.get("status") == "active": active[r["type"]] = active.get(r["type"], 0) + 1
    order = ("design", "decision", "capabilities", "plan", "spec")
    hub = rc.hub(wt)
    where = "" if os.path.realpath(hub) == os.path.realpath(wt) else f", records in {hub}"
    out.append("")
    out.append(f"**Feature:** {name}: {len(recs)} record{plural(recs)} ({', '.join(f'{active[k]} active {k}' + ('s' if active[k] != 1 and k != 'capabilities' else '') for k in order if k in active) or 'none active'}){where}.")
    settle, open_q = [], 0
    for c in rc.checks(d):
        if not c["open"]: continue
        qs = [q for q in it.read(os.path.join(d, "checks", c["name"] + ".md")) if not q["done"]]
        sf_ = [q["id"] for q in qs if q["fields"].get("Weight", "").startswith("settle-first")]
        open_q += len(qs)
        out.append(f"- design questions open in {c['name']}: {len(qs)}" + (f", settle-first: {', '.join(sf_)}" if sf_ else ""))
        if sf_: settle.append(f"{c['name']} ({', '.join(sf_)})")
    for r in recs:
        if r.get("type") == "spec" and r.get("status") == "active":
            body = open(r["path"], encoding="utf-8").read()
            m = re.search(r"^## Open items\n(.*?)(?=^## |\Z)", body, re.S | re.M)
            n = len(re.findall(r"^\s*[-*] \[ \]", m.group(1), re.M)) if m else 0
            if n: out.append(f"- {r['id']} {short(r.get('title', ''), 50)}: {n} open item{plural(n)}")
    if settle: first.append(f"Settle the design questions marked settle-first before building on them: {'; '.join(settle)} (\"walk the design questions\").")
    elif open_q: later.append(f"Decide or defer the {open_q} open design question{plural(open_q)} when convenient (\"walk the design questions\").")
    others = []
    for rname, other in related_worktrees(wt, rows):
        ps, err = read_passes(other)
        if err: others.append(f"{rname}: pass log unreadable"); continue
        live = [e for e in ps if e["f"].get("Status") in ("open", "ended")]
        if live: others.append(", ".join(f"{rname} {e['id']} {e['title']} ({pass_word(e)})" for e in live))
    if others: out.append(f"- passes in progress elsewhere: {'; '.join(others)}")
    return first, later

def related_worktrees(wt, rows):
    real = os.path.realpath(wt)
    return [(name, path) for name, path in rows if path != real and os.path.isdir(path)]

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("worktree", nargs="?", default=".")
    ap.add_argument("--run"); ap.add_argument("--no-mark", action="store_true")
    a = ap.parse_args()
    wt = git(a.worktree, "rev-parse", "--show-toplevel") or os.path.realpath(a.worktree)
    run = os.path.realpath(os.path.join(wt, ".clerk-dev", a.run or "latest"))
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
        out.append(f"**Review:** `.clerk-dev/{label}` of {target[0] if target else '?'}, reviewed up to `{reviewed[:9]}`, report from {when}.")
    else:
        out.append("**Review:** none yet in this worktree.")
        steps.append("Run a review: `/clerk-dev:review` (or \"review the branch\").")
    feature = os.path.realpath(os.path.join(wt, ".clerk-dev", "latest-feature"))
    if os.path.exists(os.path.join(feature, "report.md")):
        out.append(f"**Feature review:** `.clerk-dev/{os.path.basename(feature)}/report.md` (the cross-repository check; `.clerk-dev/latest-feature`).")

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
    seen_path = os.path.join(wt, ".clerk-dev", "status-seen")
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

    # Passes here
    passes, perr = read_passes(wt)
    pass_steps = []
    if perr:
        out.append(f"**Passes:** the log could not be read: {perr}")
    elif passes:
        recent = passes[-5:]
        more = "; earlier ones in `.clerk-dev/passes.md`" if len(passes) > 5 else ""
        out.append(f"**Passes:** {len(passes)} ({'; '.join(pass_line(e) for e in passes[-5:])}{more}).")
        for e in passes:
            st = e["f"].get("Status")
            if st == "open": pass_steps.append(f"Finish pass {e['id']} ({e['title']}), then \"end the pass\".")
            elif st == "ended" and e["f"].get("Note") != "no commits": pass_steps.append(f"Check pass {e['id']}: \"check the pass\".")
            elif st == "checked":
                label = (e["f"].get("Check") or "").split(";")[0].strip()
                prun = os.path.join(wt, ".clerk-dev", label)
                if label and os.path.exists(os.path.join(prun, "merged.md")):
                    pst, pin, pnum = sf.state(prun)
                    left = [m for m in sf.load_findings(prun) if m in pnum and sf.is_open(m, pst, pin)]
                    if left: pass_steps.append(f"Triage pass {e['id']}'s {len(left)} open finding{plural(left)}: \"work the queue {label}\", or `fix N {label}`.")
    first, later = feature_block(wt, rows, out)
    steps[0:0] = pass_steps + first
    steps.extend(later)

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
        if n_unmarked: steps.append(f"Mark the unmarked finding{plural(n_unmarked)} ({n_unmarked}) in `.clerk-dev/{os.path.basename(run)}/report.md`.")
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

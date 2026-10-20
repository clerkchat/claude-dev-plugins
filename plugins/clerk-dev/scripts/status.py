#!/usr/bin/env python3
"""Where a worktree's review work stands, from files and git only.

Usage: status.py [WORKTREE] [--run LABEL] [--no-mark] [--focus all|design|implementation|review] [--area NAME|R52]

--focus design prints whether the feature is ready to build: readiness per
piece of the overview's plan (spec, design check, settle-first questions,
Baseline, how far built), each area's decisions and design, open questions by
area (flagging checks of superseded records), and the overview's gaps and
disagreements. --area prints one area, or one spec (a piece) and its area:
the overview's summary of it, its records, open questions, the disagreements
that name its records, build progress and passes on its specs.

--focus implementation prints only the building: progress per spec here and in
the worktrees building the same feature, commits not in the build log, passes
in progress, the design questions and open items of the specs being built, and
next steps about building. --focus review leaves out the feature and the build.

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
  - implementation progress from the build log (.clerk-dev/build.md): per
    spec, requirements done, partial, in progress, and not started; pieces
    stopped on a question or not landed; pieces built since the last review;
    and the other worktrees' progress;
  - this worktree's passes (.clerk-dev/passes.md): open, ended but unchecked,
    and checked ones whose check run still has open findings;
  - the feature, when the hub (records.py hub) holds one: records by type,
    open design questions (settle-first ones named), open items in active
    specs, and passes in progress in the other worktrees, by repository;
  - a numbered list of next steps, most pressing first; once triage is done
    and fixes have landed, the last step is the final pass.

--no-mark leaves .clerk-dev/status-seen untouched.
"""
import argparse, datetime, importlib.util, os, re, subprocess, sys

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

def emit(wt, text):
    try: text = load("records.py").gloss(wt, text)
    except SystemExit: pass
    print(text)

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

def build_block(wt, rows, out, unreviewed):
    """Implementation progress from the build log here, and a line per other
    worktree of the workspace. Returns (first, later) next steps."""
    bd = load("build.py")
    first, later = [], []
    try:
        entries = bd.read(os.path.join(wt, ".clerk-dev", "build.md"))
        lines = bd.progress_lines(wt) if entries else []
    except SystemExit as e:
        out.append(""); out.append(f"**Implementation:** the build log could not be read: {e}"); return first, later
    others = []
    for rname, other in builders(wt, rows):
        try:
            if bd.read(os.path.join(other, ".clerk-dev", "build.md")):
                others += [f"{rname}: {l.strip()}" for l in bd.progress_lines(other) if not l.startswith(" ")]
        except SystemExit: others.append(f"{rname}: build log unreadable")
    if not entries and not others: return first, later
    out.append("")
    out.append("**Implementation:**" + ("" if entries else " nothing built in this worktree yet."))
    out += [f"- {l.strip()}" if not l.startswith(" ") else f"  - {l.strip()}" for l in lines]
    out += [f"- {o}" for o in others]
    mlines, msteps = bd.milestone_lines(wt) if entries else ([], [])
    if mlines:
        out += ["", "**Milestones:**"] + [f"- {l}" if not l.startswith(" ") else f"  - {l.strip()}" for l in mlines]
        first += msteps
    for e in entries:
        st = e["f"].get("Status")
        if st == "stopped":
            q = e["multi"]["Question"][-1] if e["multi"]["Question"] else "its question"
            first.append(f"Answer {e['id']} ({e['title']})'s question, record the answer, then resend it: {q}")
        elif st == "briefed":
            first.append(f"Land {e['id']} ({e['title']}): briefed and not committed; finish it, resend it, or abandon it.")
    shas = [s for s, _ in unreviewed]
    built = [e for e in entries if e["f"].get("Status") == "done" and e["f"].get("Commit") and any(s.startswith(e["f"]["Commit"]) for s in shas)]
    if built:
        later.insert(0, f"Check the {len(built)} piece{plural(built)} built since the last review ({', '.join(e['id'] for e in built)}): a pass's narrow check, or \"re-review the branch\".")
    for s, r, items, state, mine in bd.progress(wt) if entries else []:
        busy = {n for e in mine if e["f"].get("Status") in ("briefed", "stopped") for n, _, _ in bd.reqs_of(e)}
        left = [n for n in sorted(items) if n not in state and n not in busy]
        partial = sorted(n for n, (st, _, _) in state.items() if st == "partial")
        if partial: later.append(f"Finish the partial requirement{plural(partial)} of {s}: {bd.compress(s, partial)}.")
        if left and not busy:
            nxt = "; ".join(f"{s}.{n} {short(items[n], 70).rstrip('.')}" for n in left[:3])
            later.append(f"Next piece for {s}, from what is not started ({len(left)} requirement{plural(left)}; the plan and the spec's order decide): {nxt}.")
    return first, later

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
        ar = next((r.get("area") for r in recs if c["records"] and r["id"] == c["records"][0] and r.get("area")), "")
        out.append(f"- design questions open in {c['name']}{' (' + ar + ')' if ar else ''}: {len(qs)}" + (f", settle-first: {', '.join(sf_)}" if sf_ else ""))
        if sf_: settle.append(f"{c['name']} ({', '.join(sf_)})")
    for r in recs:
        if r.get("type") == "spec" and r.get("status") == "active":
            body = open(r["path"], encoding="utf-8").read()
            m = re.search(r"^## Open items\n(.*?)(?=^## |\Z)", body, re.S | re.M)
            n = len(re.findall(r"^\s*[-*] \[ \]", m.group(1), re.M)) if m else 0
            if n: out.append(f"- {r['id']} {short(r.get('title', ''), 50)}{' (' + r['area'] + ')' if r.get('area') else ''}: {n} open item{plural(n)}")
    if settle: first.append(f"Settle the design questions marked settle-first before building on them: {'; '.join(settle)} (\"walk the design questions\").")
    elif open_q: later.append(f"Decide or defer the {open_q} open design question{plural(open_q)} when convenient (\"walk the design questions\").")
    others = []
    for rname, other in related_worktrees(wt, rows):
        ps, err = read_passes(other)
        if err: others.append(f"{rname}: pass log unreadable"); continue
        live = [e for e in ps if e["f"].get("Status") in ("open", "ended")]
        if live: others.append(", ".join(f"{rname} {e['id']} {e['title']} ({pass_word(e)})" for e in live))
    if others: out.append(f"- passes in progress elsewhere: {'; '.join(others)}")
    if len(recs) >= 5: out.append("- " + re.sub(r"\[overview.md\]\(overview.md\)", "`overview.md`", rc.overview_line(d)))
    for s in [s for s in rc.suggestions(d) if not s.startswith("The overview")][:2]:
        later.append(f"Records: {s}")
    if any(s.startswith("The overview") for s in rc.suggestions(d)):
        later.append("Refresh the feature overview: \"refresh the overview\".")
    return first, later

def builders(wt, rows):
    """(name, path) of the other worktrees building this feature: the
    workspace's rows, and any worktree of this repository whose workspace
    file names this worktree's hub."""
    rc = load("records.py")
    try: hub = os.path.realpath(rc.hub(wt))
    except SystemExit: hub = ""
    out = list(related_worktrees(wt, rows))
    seen = {os.path.realpath(p) for _, p in out} | {os.path.realpath(wt)}
    for line in git(wt, "worktree", "list", "--porcelain").splitlines():
        if not line.startswith("worktree "): continue
        p = os.path.realpath(line[9:])
        if p in seen or not os.path.isdir(p): continue
        try: theirs = os.path.realpath(rc.hub(p))
        except SystemExit: continue
        if hub and theirs == hub and p != hub:
            out.append((f"{repo_name(p, [])} ({os.path.basename(p)})", p)); seen.add(p)
    return out

def branch_base(wt):
    """The merge base with the remote main branch, or "" when there is none."""
    main = git(wt, "rev-parse", "--abbrev-ref", "origin/HEAD") or next((r for r in ("origin/main", "origin/master") if git(wt, "rev-parse", "--verify", "-q", r)), "")
    return git(wt, "merge-base", "HEAD", main) if main else ""

def implementation_view(wt, rows, out, unreviewed, pass_steps, passes):
    """Where the building stands: progress per spec this worktree builds (from
    the build log, or the spec's size when nothing is logged), commits not in
    the log, passes, and the design questions and open items of those specs.
    Returns the next steps, building only."""
    bd = load("build.py"); rc = load("records.py"); it = load("items.py")
    first, later = build_block(wt, rows, out, unreviewed)
    try: entries = bd.read(os.path.join(wt, ".clerk-dev", "build.md"))
    except SystemExit: entries = []
    if entries:
        i = next((k for k, l in enumerate(out) if l.startswith("**Implementation:**")), None)
        if i is not None:
            j = i + 1
            while j < len(out) and (out[j].startswith("- R") or out[j].startswith("  - ")): j += 1
            out[i + 1:j] = bd.checklist_lines(wt)
    me = repo_name(wt, rows)
    try: d = rc.fdir(wt)
    except SystemExit: d = None
    recs = rc.records(d) if d and os.path.exists(os.path.join(d, "feature.md")) else []
    logged = {e["f"].get("Spec") for e in entries}
    specs = [r for r in recs if r.get("type") == "spec" and r.get("status") == "active" and (r.get("repo") in ("", None, me) or r["id"] in logged)]
    unlogged_specs = [r for r in specs if r["id"] not in logged]
    elsewhere = {l.split(": ", 1)[1].split(" ", 1)[0] for l in out if l.startswith("- ") and ": R" in l}
    unlogged_specs = [r for r in unlogged_specs if r["id"] not in elsewhere]
    if unlogged_specs:
        if not entries and not any(l.startswith("**Implementation:**") for l in out): out += ["", "**Implementation:** no pieces logged in this worktree."]
        for r in unlogged_specs:
            _, items = bd.spec_requirements(d, r["id"])
            out.append(f"- {r['id']} {short(r.get('title', ''), 60)}: {len(items or {})} requirements, none logged as built")
    base = branch_base(wt)
    done_shas = [e["f"]["Commit"] for e in entries if e["f"].get("Commit")]
    builds_elsewhere = not entries and any(os.path.exists(os.path.join(p, ".clerk-dev", "build.md")) for _, p in builders(wt, rows))
    commits = [l.split("\t", 1) for l in git(wt, "log", "--no-merges", "--format=%H\t%s", f"{base}..HEAD").splitlines()] if base and not builds_elsewhere else []
    unlogged = [(s, subj) for s, subj in commits if not any(s.startswith(c) for c in done_shas)]
    if commits:
        out.append(f"- Commits on the branch: {len(commits)}, {len(unlogged)} not in the build log" + (":" if unlogged else "."))
        for s, subj in unlogged[:5]: out.append(f"  - `{s[:9]}` {short(subj, 80)}")
        if len(unlogged) > 5: out.append(f"  - and {len(unlogged) - 5} earlier")
    if passes:
        live = [e for e in passes if e["f"].get("Status") in ("open", "ended")]
        live = [e for e in live if not (e["f"].get("Status") == "ended" and e["f"].get("Note") == "no commits")]
        if live: out.append(f"- Passes in progress: {'; '.join(pass_line(e) for e in live)}")
    spec_ids = {r["id"] for r in specs}
    areas = {r.get("area") for r in specs if r.get("area")}
    area_of = {r["id"]: r.get("area") for r in recs}
    settle = []
    for c in rc.checks(d) if d else []:
        if not c["open"] or not (set(c["records"]) & spec_ids or {area_of.get(x) for x in c["records"]} & areas): continue
        qs = [q for q in it.read(os.path.join(d, "checks", c["name"] + ".md")) if not q["done"]]
        sfq = [q["id"] for q in qs if q["fields"].get("Weight", "").startswith("settle-first")]
        out.append(f"- Design questions open in {c['name']}: {len(qs)}" + (f", settle-first: {', '.join(sfq)}" if sfq else ""))
        if sfq: settle.append(f"{c['name']} ({', '.join(sfq)})")
    for r in specs:
        body = open(r["path"], encoding="utf-8").read()
        m = re.search(r"^## Open items\n(.*?)(?=^## |\Z)", body, re.S | re.M)
        n = len(re.findall(r"^\s*[-*] \[ \]", m.group(1), re.M)) if m else 0
        if n: out.append(f"- {r['id']} open items: {n}")
    mspecs = {m["f"].get("Spec") for m in bd.milestones(entries)}
    pass_steps = [s for s in pass_steps if not any(e["id"] in s and e["f"].get("Piece") in mspecs for e in (passes or []))]
    steps = first + pass_steps
    if settle: steps.append(f"Settle the design questions marked settle-first that bear on what is being built: {'; '.join(settle)} (\"walk the design questions\").")
    if unlogged and specs:
        steps.append(f"Log the {len(unlogged)} commit{plural(unlogged)} already built against the specs' requirements, so progress is counted: \"log the built work\".")
        later = [s for s in later if not s.startswith("Next piece")]
    steps += later
    if builds_elsewhere:
        where = ", ".join(os.path.basename(p) for _, p in builders(wt, rows) if os.path.exists(os.path.join(p, ".clerk-dev", "build.md")))
        steps.append(f"The building happens in {where}; its next steps are in a status asked there.")
    elif not entries and not unlogged and unlogged_specs:
        steps.append(f"Start building {unlogged_specs[0]['id']}: cut its requirements into pieces and brief the first (the writing-code skill).")
    return steps

def section(text, heading, level=2):
    m = re.search(rf"^{'#' * level} {re.escape(heading)}\n(.*?)(?=^#{{1,{level}}} |\Z)", text, re.S | re.M)
    return m.group(1) if m else ""

def bullets(text):
    out, cur = [], None
    for line in text.splitlines():
        if re.match(r"^[-*] ", line): cur = line[2:].strip(); out.append(cur)
        elif cur is not None and line.startswith("  ") and line.strip(): out[-1] += " " + line.strip()
        elif not line.strip(): cur = None
    return out

def overview_parts(d):
    """From overview.md: the Plan table's rows, the Open subsections, and each
    area's summary under By area. Older overviews without the Open subsections
    are read for a paragraph about disagreement."""
    p = os.path.join(d, "overview.md")
    parts = {"plan": [], "gaps": [], "disagreements": [], "areas": {}}
    if not os.path.exists(p): return parts
    text = open(p, encoding="utf-8").read()
    plan = section(text, "Plan")
    rows = [l for l in plan.splitlines() if l.strip().startswith("|")]
    if len(rows) > 2:
        head = [c.strip().lower() for c in rows[0].strip().strip("|").split("|")]
        for l in rows[2:]:
            cells = [c.strip() for c in l.strip().strip("|").split("|")]
            parts["plan"].append(dict(zip(head, cells)))
    op = section(text, "Open")
    if "### Disagreements" in op:
        parts["disagreements"] = [b for b in bullets(section(op, "Disagreements", 3)) if b.lower() != "none."]
        parts["gaps"] = [b for b in bullets(section(op, "Gaps", 3)) if b.lower() != "none."]
    else:
        for m in re.finditer(r"^([^\n-][^\n]*)\n+((?:[-*] .*\n(?:  .*\n)*)+)", op, re.M):
            head = m.group(1).lower()
            key = "mixed" if "gap" in head and "disagree" in head else "disagreements" if "disagree" in head else "gaps" if "gap" in head else None
            if key: parts.setdefault(key, []).extend(bullets(m.group(2)))
    by = section(text, "By area")
    for m in re.finditer(r"^### ([^\n]+)\n(.*?)(?=^### |\Z)", by, re.S | re.M):
        para = next((b.strip() for b in re.split(r"\n\s*\n", m.group(2)) if b.strip() and not b.strip().startswith(("-", "*"))), "")
        parts["areas"][m.group(1).strip().lower()] = re.sub(r"\s+", " ", para)
    return parts

def spec_facts(d, r, cs, it):
    """Readiness facts of one spec: its checks, open settle-first questions in
    them, whether its Baseline is filled, and its open items."""
    body = open(r["path"], encoding="utf-8").read()
    mine = [c for c in cs if r["id"] in c["records"]]
    settle = []
    for c in mine:
        settle += [f"{c['name']}.{q['id']}" for q in it.read(os.path.join(d, "checks", c["name"] + ".md")) if not q["done"] and q["fields"].get("Weight", "").startswith("settle-first")]
    base = section(body, "Baseline").strip()
    m = re.search(r"^## Open items\n(.*?)(?=^## |\Z)", body, re.S | re.M)
    items = len(re.findall(r"^\s*[-*] \[ \]", m.group(1), re.M)) if m else 0
    missing = ([] if mine else ["no design check"]) + ([f"{len(settle)} settle-first open"] if settle else []) + ([] if base else ["no Baseline"])
    return {"checks": mine, "settle": settle, "baseline": bool(base), "items": items, "missing": missing}

def area_states(recs):
    """[(area, decisions, design note)] for every area with active records."""
    live = [r for r in recs if r.get("status") == "active"]
    out = []
    for a in sorted({r.get("area", "") for r in live}, key=lambda a: (a != "", a)):
        decs = [r for r in live if r.get("area", "") == a and r.get("type") == "decision"]
        des = [r for r in live if r.get("area", "") == a and r.get("type") == "design"]
        if des:
            newest = max(int(x["id"][1:]) for x in des)
            later = [x["id"] for x in decs if int(x["id"][1:]) > newest]
            note = f"design R{newest}" + (f", older than {len(later)} decision{plural(later)}" if later else ", current")
        else: note = "no design"
        out.append((a or "feature-wide", decs, note))
    return out

def design_view(wt, rows, out):
    """Whether the feature is ready to build: readiness per piece, each area's
    decisions and design, open questions by area, and the overview's gaps and
    disagreements. Returns the next steps, design only."""
    rc = load("records.py"); it = load("items.py"); bd = load("build.py")
    d = rc.fdir(wt)
    if not os.path.exists(os.path.join(d, "feature.md")):
        out += ["", "**Design:** no feature records here or in a hub."]; return ["Start a feature: \"start a feature for <name>\"."]
    recs = rc.records(d); cs = rc.checks(d); ov = overview_parts(d)
    specs = {r["id"]: r for r in recs if r.get("type") == "spec" and r.get("status") == "active"}
    built = {}
    for _, p in [("", wt)] + builders(wt, rows):
        try:
            for s, _, items, state, _ in bd.progress(p):
                built[s] = f"{sum(1 for v in state.values() if v[0] == 'done')} of {len(items)} built"
        except SystemExit: pass
    steps, settle_all, nospec = [], [], []
    out += ["", "**Readiness:**" + ("" if ov["plan"] else " (no Plan table in the overview; by spec)")]
    named = set()
    for row in ov["plan"]:
        piece = row.get("piece", "?"); sid = next(iter(re.findall(r"\bR\d+\b", row.get("spec", ""))), "")
        r = specs.get(sid)
        if not r:
            out.append(f"- {piece}: no spec"); nospec.append(piece); continue
        named.add(sid); f = spec_facts(d, r, cs, it)
        word = "ready" if not f["missing"] else "not ready: " + ", ".join(f["missing"])
        out.append(f"- {piece} ({sid}): {word}" + (f"; {built[sid]}" if sid in built else "") + (f"; {f['items']} open items" if f["items"] else ""))
        settle_all += f["settle"]
        if "no design check" in f["missing"]: steps.append(f"Design-check {sid} ({short(r.get('title', ''), 40)}): \"design-check {sid}\".")
        if not f["baseline"]: steps.append(f"Fill {sid}'s Baseline: the refactor to do first, or \"Clean\" with why.")
    for sid, r in specs.items():
        if sid in named: continue
        f = spec_facts(d, r, cs, it)
        word = "ready" if not f["missing"] else "not ready: " + ", ".join(f["missing"])
        out.append(f"- {sid} {short(r.get('title', ''), 50)}: {word}" + (f"; {built[sid]}" if sid in built else "") + (f"; {f['items']} open items" if f["items"] else ""))
        settle_all += f["settle"]
        if "no design check" in f["missing"]: steps.append(f"Design-check {sid}: \"design-check {sid}\".")
        if not f["baseline"]: steps.append(f"Fill {sid}'s Baseline: the refactor to do first, or \"Clean\" with why.")
    if nospec:
        steps.insert(0, f"Write the spec for {nospec[0]}, next in the plan without one" + (f" ({len(nospec) - 1} more after it)." if len(nospec) > 1 else "."))
    out += ["", "**Areas:**"]
    for a, decs, note in area_states(recs):
        out.append(f"- {a}: {len(decs)} active decision{plural(decs)}, {note}")
    area_of = {r["id"]: r.get("area") or "feature-wide" for r in recs}
    qlines, other = [], 0
    for c in cs:
        if not c["open"]: continue
        qs = [q for q in it.read(os.path.join(d, "checks", c["name"] + ".md")) if not q["done"]]
        sfq = [q["id"] for q in qs if q["fields"].get("Weight", "").startswith("settle-first")]
        other += len(qs) - len(sfq)
        status_of = {r["id"]: r for r in recs}
        gone = [x for x in c["records"] if status_of.get(x, {}).get("status") == "superseded"]
        note = "; on " + ", ".join(f"superseded {x} (now {status_of[x].get('superseded_by')})" for x in gone) if gone else ""
        qlines.append(f"- {area_of.get(c['records'][0], '?') if c['records'] else '?'}: {c['name']}, {len(qs)} open" + (f" (settle-first: {', '.join(sfq)})" if sfq else "") + note)
        settle_all += [f"{c['name']}.{q}" for q in sfq]
    if qlines: out += ["", "**Open questions:**"] + qlines
    mixed = ov.get("mixed", [])
    if ov["gaps"] or ov["disagreements"] or mixed:
        state = re.sub(r"^Overview: \[overview.md\]\(overview.md\), ", "", rc.overview_line(d)).rstrip(".")
        out += ["", f"**From the overview** ({state}):"]
        for label, xs in (("gaps", ov["gaps"]), ("disagreements", ov["disagreements"]), ("gaps and disagreements", mixed)):
            if not xs: continue
            out.append(f"- {label}: {len(xs)}")
            if label != "gaps": out += [f"  - {short(x, 110)}" for x in xs[:6]] + ([f"  - and {len(xs) - 6} more"] if len(xs) > 6 else [])
    else:
        out += ["", "- " + re.sub(r"\[overview.md\]\(overview.md\)", "`overview.md`", rc.overview_line(d))]
    gl = rc.rules(d)
    if gl: out += ["", f"**Guidance:** {len(gl)} active rule{plural(gl)}; say \"what guidance have I given\" to list them."]
    parked = [i for i in rc.ideas(d) if not i["done"]]
    if parked:
        by = {}
        for i in parked: by.setdefault(i["fields"].get("Area") or "feature-wide", []).append(i["id"])
        out += ["", f"**Parked ideas:** {len(parked)} ({'; '.join(f'{a}: {len(v)}' for a, v in by.items())}); say \"what ideas did we park\" to list them with why and when."]
    settle_all = list(dict.fromkeys(settle_all))
    first = [f"Settle the settle-first design questions: {', '.join(settle_all)} (\"walk the design questions\")."] if settle_all else []
    if ov["disagreements"] or mixed:
        n = len(ov["disagreements"]) + len(mixed)
        first.append(f"Resolve the {n} {'disagreements' if not mixed else 'gaps and disagreements'} the overview lists, each with a new or superseding record, then refresh it.")
    rolls = [s for s in rc.suggestions(d) if not s.startswith("The overview")]
    tail = rolls + ([f"Decide or defer the {other} other open design question{plural(other)}."] if other else [])
    if any(s.startswith("The overview") for s in rc.suggestions(d)): tail.append("Refresh the overview: \"refresh the overview\".")
    return first + list(dict.fromkeys(steps)) + tail

def area_view(wt, rows, out, name):
    """One area, or one spec (a piece) and its area: the overview's summary of
    it, its records, open questions, disagreements that name its records, build
    progress and passes on its specs. Returns the next steps for it."""
    rc = load("records.py"); it = load("items.py"); bd = load("build.py")
    d = rc.fdir(wt); recs = rc.records(d)
    spec = None
    if re.fullmatch(r"[Rr]\d+", name):
        spec = next((r for r in recs if r["id"] == name.upper()), None)
        if not spec: sys.exit(f"{name.upper()} is not a record of this feature")
        area = spec.get("area", "")
    else:
        area = rc.slug(name)
        known = sorted({r.get("area") for r in recs if r.get("area")})
        if area not in known and area != "feature-wide": sys.exit(f"no area {name}; the areas are: {', '.join(known) or 'none'}")
        if area == "feature-wide": area = ""
    label = (f"{spec['id']} {spec.get('title', '')}" if spec else "") + (f" (area {area or 'feature-wide'})" if spec else area or "feature-wide")
    out[0] = f"## Where {label} stands\n"
    mine = [r for r in recs if r.get("area", "") == area]
    ids = {r["id"] for r in mine}
    ov = overview_parts(d)
    summ = ov["areas"].get((area or "feature-wide").lower())
    if summ: out += [summ, ""]
    live = [r for r in mine if r.get("status") == "active"]
    counts_by_type = {k: sum(1 for r in live if r.get("type") == k) for k in ("design", "spec", "plan", "decision")}
    out.append(f"**Records:** {len(live)} active ({', '.join(f'{counts_by_type[k]} {k}{'s' if counts_by_type[k] != 1 else ''}' for k in ('design', 'spec', 'plan', 'decision') if any(r.get('type') == k for r in live))}), {len(mine) - len(live)} history.")
    for r in rc.ordered([r for r in live if r.get("type") != "decision"]):
        out.append(f"- {r['id']} {r['type']}: {short(r.get('title', ''), 70)}")
    decs = [r for r in live if r.get("type") == "decision"]
    if decs: out.append(f"- decisions: {', '.join(r['id'] for r in decs)}")
    steps, settle = [], []
    qs_lines = []
    for c in rc.checks(d):
        if not c["open"] or not set(c["records"]) & ids: continue
        qs = [q for q in it.read(os.path.join(d, "checks", c["name"] + ".md")) if not q["done"]]
        sfq = [q["id"] for q in qs if q["fields"].get("Weight", "").startswith("settle-first")]
        qs_lines.append(f"- {c['name']}: {len(qs)} open" + (f" (settle-first: {', '.join(sfq)})" if sfq else ""))
        settle += [f"{c['name']}.{q}" for q in sfq]
    if qs_lines: out += ["", "**Open questions:**"] + qs_lines
    dis = [x for x in ov["disagreements"] + ov.get("mixed", []) if set(re.findall(r"\bR\d+\b", x)) & ids]
    if dis: out += ["", f"**Disagreements touching it:** {len(dis)}"] + [f"- {short(x, 110)}" for x in dis]
    gl = [(r, rule) for r, rule in rc.rules(d, area or None) if (r.get("area") or "") == area]
    if gl: out += ["", f"**Guidance:** {len(gl)}"] + [f"- {r['id']}: {short(rule, 110)}" for r, rule in gl]
    parked = [i for i in rc.ideas(d) if not i["done"] and (i["fields"].get("Area") or "") == area]
    if parked: out += ["", f"**Parked ideas:** {len(parked)}"] + [f"- {i['id']}: {short(i['text'], 90)}" + (f" When: {i['fields']['When']}." if i["fields"].get("When") else "") for i in parked]
    specs = [spec] if spec else [r for r in live if r.get("type") == "spec"]
    prog, pas = [], []
    for wname, p in [("", wt)] + builders(wt, rows):
        try:
            for s, r, items, state, pieces in bd.progress(p):
                if s not in {x["id"] for x in specs}: continue
                where = f" ({wname})" if wname else ""
                prog += [f"- {l.strip()}{where if not l.startswith(' ') else ''}" if not l.startswith(" ") else f"  - {l.strip()}" for l in bd.progress_lines(p, s)]
                for e in pieces:
                    if e["f"].get("Status") == "stopped": steps.insert(0, f"Answer {e['id']}'s question{where}: {e['multi']['Question'][-1] if e['multi']['Question'] else ''}")
        except SystemExit: pass
        ps, _ = read_passes(p)
        pas += [f"- {pass_line(e)}" for e in ps if e["f"].get("Piece") in {x["id"] for x in specs} and e["f"].get("Status") in ("open", "ended", "checked")]
    if specs:
        out += ["", "**Build:**"] + (prog or [f"- {x['id']}: nothing logged as built" for x in specs])
    if pas: out += ["", "**Passes:**"] + pas
    if settle: steps.insert(0, f"Settle {', '.join(settle)} (\"walk the design questions\").")
    if dis: steps.append(f"Resolve the {len(dis)} disagreement{plural(dis)} touching it, each with a new or superseding record.")
    for x in specs:
        f = spec_facts(d, x, rc.checks(d), it)
        if "no design check" in f["missing"]: steps.append(f"Design-check {x['id']}.")
        if not f["baseline"]: steps.append(f"Fill {x['id']}'s Baseline.")
    if not specs and not spec: steps.append(f"No spec in {area or 'feature-wide'} yet; write one for its first piece when it is ready to build.")
    if decs and not any(r.get("type") == "design" for r in live) and len(decs) >= 3:
        steps.append(f"Roll its {len(decs)} decisions into a design that cites them.")
    return steps

def related_worktrees(wt, rows):
    real = os.path.realpath(wt)
    return [(name, path) for name, path in rows if path != real and os.path.isdir(path)]

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("worktree", nargs="?", default=".")
    ap.add_argument("--run"); ap.add_argument("--no-mark", action="store_true")
    ap.add_argument("--focus", choices=("all", "design", "implementation", "review"), default="all",
                    help="design: readiness to build; implementation: building progress and its next steps only; review: the review only")
    ap.add_argument("--area", help="one area, or a spec id for one piece and its area")
    a = ap.parse_args()
    wt = git(a.worktree, "rev-parse", "--show-toplevel") or os.path.realpath(a.worktree)
    load("records.py").guard(wt)
    run = os.path.realpath(os.path.join(wt, ".clerk-dev", a.run or "latest"))
    have_run = os.path.exists(os.path.join(run, "merged.md")) and os.path.exists(os.path.join(run, "target.txt"))
    branch = git(wt, "rev-parse", "--abbrev-ref", "HEAD")
    head = git(wt, "rev-parse", "HEAD")
    out, steps = [], []
    rows = workspace_rows(wt)
    out.append(f"## Where {'the implementation in ' if a.focus == 'implementation' else 'the design of ' if a.focus == 'design' else ''}{repo_name(wt, rows)} stands ({branch})\n")
    if a.focus == "design" or a.area:
        steps = area_view(wt, rows, out, a.area) if a.area else design_view(wt, rows, out)
        out.append("")
        out += ["**Next:**"] + [f"{n}. {s}" for n, s in enumerate(dict.fromkeys(steps), 1)] if steps else ["**Next:** nothing pending."]
        emit(wt, re.sub(r"\n{3,}", "\n\n", "\n".join(out))); return

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
    if a.focus == "implementation":
        out[:] = [out[0]] + [l for l in out[1:] if l.startswith("**Working tree")]
        steps = implementation_view(wt, rows, out, unreviewed, pass_steps, passes)
        out.append("")
        out += ["**Next:**"] + [f"{n}. {s}" for n, s in enumerate(steps, 1)] if steps else ["**Next:** nothing pending in the building."]
        emit(wt, re.sub(r"\n{3,}", "\n\n", "\n".join(out))); return
    if a.focus == "all":
        bfirst, blater = build_block(wt, rows, out, unreviewed)
        first, later = feature_block(wt, rows, out)
        steps[0:0] = bfirst + pass_steps + first
        steps.extend(blater + later)

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
    emit(wt, "\n".join(out))

if __name__ == "__main__":
    main()

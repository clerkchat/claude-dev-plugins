#!/usr/bin/env python3
"""Where a worktree's review work stands, from files and git only.

Usage: status.py [WORKTREE] [--run LABEL] [--no-mark] [--focus all|design|implementation|review] [--area NAME|R52]
       status.py [WORKTREE] --setup

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

  - the setup gaps first, under Setup, when there are any (see --setup);
  - open deferred items (.clerk-dev/deferred.md) after the follow-ups: the
    count, and each item's id, text, and Revisit;
  - the Note of each open pass and open piece, the handoff a checkpoint left.
  - Rerouted, when a record's note or the branch notes has a note starting
    `rerouted:` (an answer recorded in the wrong place): the count, and which.

--setup prints only what a feature work session is missing, one line each with
what to do, or "Setup: complete.": a Purpose in the branch notes; a hub and
feature when the worktree has a build log or passes, or another worktree names
it in its workspace and holds feature records; a review workspace when
records, specs, or follow-ups name other repositories (or it lacks a row for
one); workspace rows whose worktree is missing; a plan with a done line on
every step when active specs exist; a milestone under way whose Plan step is
gone or whose plan was superseded or discarded. It changes nothing.

--no-mark leaves .clerk-dev/status-seen untouched.
"""
import argparse, datetime, os, re, subprocess, sys
from records import git, load_script

sf = load_script("stale-findings.py")

SECTION_NAMES = {"fix": "Fix before merging", "look": "Worth a look", "existing": "Already on main", "debt": "Cleanup and refactoring"}

def plural(x):
    n = x if isinstance(x, int) else len(x)
    return "" if n == 1 else "s"

def emit(wt, text):
    try: text = load_script("records.py").gloss(wt, text)
    except SystemExit: pass
    print(text)

def short(text, n=90):
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"

def parse_followups(wt):
    fu = load_script("followups.py")
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

def has_feature(p):
    return os.path.exists(os.path.join(p, ".clerk-dev", "feature", "feature.md"))

def hub_feature_elsewhere(wt, rows):
    """A worktree holding feature records that names this one in its review
    workspace, or that this one's workspace names: the hub it should point at."""
    real = os.path.realpath(wt)
    near = [os.path.realpath(l[9:]) for l in git(wt, "worktree", "list", "--porcelain").splitlines() if l.startswith("worktree ")]
    mine = {p for _, p in rows}
    for p in dict.fromkeys([p for _, p in rows] + near):
        if p != real and os.path.isdir(p) and has_feature(p) and (p in mine or real in {q for _, q in workspace_rows(p)}): return p

def other_repos(wt, rows, d):
    """Repositories other than this one that its active records and open
    follow-ups name."""
    rc = load_script("records.py"); me = repo_name(wt, rows)
    named = {r.get("repo") for r in (rc.records(d) if d and os.path.exists(os.path.join(d, "feature.md")) else []) if r.get("type") != "brainstorm" and r.get("status") == "active"}
    named |= {re.split(r"[ @]", i["from"])[0] for i in parse_followups(wt) if not i["done"] and i["from"]}
    return sorted(n for n in named if n and n != me)

def plan_gaps(d):
    """Steps of the active plans without a done line, when active specs exist."""
    rc = load_script("records.py"); recs = rc.records(d)
    if not any(r.get("type") == "spec" and r.get("status") == "active" for r in recs): return []
    plans = [r for r in recs if r.get("type") == "plan" and r.get("status") == "active"]
    if not plans: return ["no active plan: propose the milestones to the user and record them as a plan (the feature skill)"]
    out = []
    for r in plans:
        steps = rc.plan_steps(r)
        if not steps: out.append(f"plan {r['id']} has no numbered steps: add the milestones in a new plan superseding it (the feature skill)"); continue
        bare = [str(n) for n, t in steps.items() if not re.search(r"\bdone\b", t, re.I)]
        if bare: out.append(f"plan {r['id']} has no done line on step{plural(bare)} {', '.join(bare)}: supersede it with a plan that gives each step one (the feature skill)")
    return out

def milestone_drift(wt, d, entries):
    rc, bd = load_script("records.py"), load_script("build.py")
    out = []
    try:
        for m in bd.milestones(entries):
            ref = m["f"].get("Plan")
            if not ref or m["f"].get("Status") == "abandoned" or bd.milestone_view(wt, m)[2]: continue
            r, text = rc.plan_step(d, ref)
            who, fix = f"{m['id']} points at plan step {ref}", "; point its Plan line in .clerk-dev/build.md at the current plan's step, or abandon it (build.py abandon)"
            if not r: out.append(f"{who}, but no plan has that id{fix}")
            elif r.get("status") != "active": out.append(f"{who}, but {r['id']} is {r.get('status')}" + (f" by {r['superseded_by']}" if r.get("superseded_by") else "") + fix)
            elif text is None: out.append(f"{who}, but {r['id']} has no such step{fix}")
    except SystemExit: pass
    return out

def setup_gaps(wt, rows, built):
    """What a feature work session in this worktree is missing, one line each
    with what to do. Reads only; never writes."""
    rc = load_script("records.py"); gaps = []
    purpose, _ = rc.branch_notes(wt)
    if not purpose: gaps.append("Purpose: " + ("the branch notes have no Purpose" if purpose is not None else "no .clerk-dev/branch-notes.md") + "; draft it as tracking.md's Branch notes describes and show it to the user")
    missing = [(n, p) for n, p in rows if not os.path.isdir(p)]
    gaps += [f"workspace row {n}: {p} does not exist; fix the row in .clerk-dev/review-workspace.md or create the worktree" for n, p in missing]
    declared, _ = rc.workspace(wt)
    if declared and os.path.realpath(os.path.expanduser(declared)) not in {p for _, p in rows} and not os.path.isdir(os.path.expanduser(declared)):
        gaps.append(f"hub {declared} (the Hub line of .clerk-dev/review-workspace.md) does not exist; fix the line")
    try: d = rc.fdir(wt)
    except SystemExit: d = None
    featured = bool(d) and os.path.exists(os.path.join(d, "feature.md"))
    if d and not featured:
        elsewhere = hub_feature_elsewhere(wt, rows)
        passes, _ = read_passes(wt)
        if elsewhere: gaps.append(f"feature records are in {elsewhere} but this worktree has no hub; add a `Hub:` line to .clerk-dev/review-workspace.md (skills/review/workspace-manifest.md)")
        elif built or passes: gaps.append("this worktree has a " + ("build log" if built else "pass log") + " but no feature; start one: records.py start <worktree> \"<name>\" (the feature skill)")
    named = other_repos(wt, rows, d)
    if named:
        have = {n for n, _ in rows}
        if not rows: gaps.append(f"records or follow-ups name {', '.join(named)} but there is no review workspace; set one up as skills/review/workspace-manifest.md describes")
        elif set(named) - have: gaps.append(f"records or follow-ups name {', '.join(sorted(set(named) - have))} but the review workspace has no row for {'it' if len(set(named) - have) == 1 else 'them'}; add {'one' if len(set(named) - have) == 1 else 'rows'}")
    if featured: gaps += plan_gaps(d) + milestone_drift(wt, d, built)
    return gaps

def setup_lines(gaps):
    return ["**Setup:**"] + [f"- {g}" for g in gaps] + [""] if gaps else []

def handoff_lines(passes, pieces):
    """The Note of each open pass and open piece."""
    live = [e for e in passes if e["f"].get("Status") == "open"] + [e for e in pieces if e["f"].get("Status") in ("briefed", "stopped")]
    notes = [f"- {e['id']} {e['title']}: {e['f']['Note']}" for e in live if e["f"].get("Note")]
    return ["", "**Handoff notes:**"] + notes if notes else []

def deferred_lines(wt):
    its = [i for i in load_script("items.py").read(os.path.join(wt, ".clerk-dev", "deferred.md")) if not i["done"]]
    return [f"**Deferred items:** {len(its)} open."] + [f"- {i['id']}: {short(i['text'])}" + (f" (revisit: {i['fields']['Revisit']})" if i["fields"].get("Revisit") else "") for i in its] if its else []

REROUTED_RE = re.compile(r"^\s*(?:[-*]\s+)?(?:\d{4}-\d{2}-\d{2}\.?\s+)?rerouted:", re.I)

def rerouted_lines(wt):
    rc = load_script("records.py")
    try: recs = rc.records(rc.fdir(wt))
    except SystemExit: recs = []
    ids = [r["id"] for r in recs if REROUTED_RE.match(r.get("note", "")) or any(REROUTED_RE.match(l) for l in rc.parse(r["path"])[1].splitlines())]
    p = rc.notes_path(wt)
    in_notes = sum(1 for l in open(p, encoding="utf-8").read().splitlines() if REROUTED_RE.match(l)) if os.path.exists(p) else 0
    where = ids + ([f"{in_notes} in the branch notes"] if in_notes else [])
    return ["", f"**Rerouted:** {len(ids) + in_notes}: {', '.join(where)}."] if where else []

def read_passes(wt):
    """The pass log's entries, or None with the reason when it cannot be read."""
    p = os.path.join(wt, ".clerk-dev", "passes.md")
    if not os.path.exists(p): return [], None
    try: return load_script("passes.py").read(p), None
    except SystemExit as e: return [], str(e)

def read_build(wt):
    try: return load_script("build.py").log_entries(wt), None
    except SystemExit as e: return [], str(e)

def builder_logs(wt, rows):
    return [(name, p, *read_build(p)) for name, p in builders(wt, rows)]

def pass_word(e):
    """A pass's state in a few words: open, ended, or its check's result."""
    f = e["f"]; st = f.get("Status", "")
    if st == "ended": return "ended, not checked" + (" (no commits)" if f.get("Note") == "no commits" else "")
    if st != "checked": return st
    check = f.get("Check") or ""
    cs = load_script("passes.py").counts(check)
    if cs is None: return "checked, " + check.split(";")[-1].strip()
    n = sum(cs.values())
    return "checked, clean" if n == 0 else f"checked, {n} finding{plural(n)} in `{check.split(';')[0].strip()}`"

def pass_line(e):
    return f"{e['id']} {e['title']} {pass_word(e)}"

def as_bullets(lines, suffix=""):
    return [f"- {l.strip()}{suffix}" if not l.startswith(" ") else f"  - {l.strip()}" for l in lines]

def progress_list(wt, entries):
    return as_bullets(load_script("build.py").progress_lines(wt, entries))

def build_block(wt, out, unreviewed, mine, theirs, render=progress_list):
    bd = load_script("build.py")
    first, later, elsewhere = [], [], {}
    others = []
    for rname, other, es, err in theirs:
        try: heads = [l for l in bd.progress_lines(other, es) if not l.startswith(" ")] if es else []
        except SystemExit as e: heads, err = [], str(e)
        if es: elsewhere[other] = {l.split(" ", 1)[0] for l in heads}
        others += [f"{rname}: build log unreadable"] if err else [f"{rname}: {l.strip()}" for l in heads]
    entries, err = mine
    if not err:
        try: lines = render(wt, entries) if entries else []
        except SystemExit as e: err = str(e)
    if err:
        out.append(""); out.append(f"**Implementation:** the build log could not be read: {err}"); return first, later, elsewhere
    if not entries and not others: return first, later, elsewhere
    out.append("")
    out.append("**Implementation:**" + ("" if entries else " nothing built in this worktree yet."))
    out += lines
    out += [f"- {o}" for o in others]
    mlines, msteps = bd.milestone_lines(wt, entries) if entries else ([], [])
    if mlines:
        out += ["", "**Milestones:**"] + as_bullets(mlines)
        first += msteps
    for e in entries:
        st = e["f"].get("Status")
        if st == "stopped":
            q = e["multi"]["Question"][-1] if e["multi"]["Question"] else "its question"
            first.append(f"Answer {e['id']} ({e['title']})'s question, record the answer, then resend it: {q}")
        elif st == "briefed":
            first.append(f"Land {e['id']} ({e['title']}): briefed and not committed; finish it, resend it, or abandon it.")
    built = [e for e in entries if e["f"].get("Status") == "done" and any(bd.names_commit(e, s) for s, _ in unreviewed)]
    if built:
        later.insert(0, f"Check the {len(built)} piece{plural(built)} built since the last review ({', '.join(e['id'] for e in built)}): a pass's narrow check, or \"re-review the branch\".")
    for s, r, items, state, mine in bd.progress(wt, entries) if entries else []:
        busy = {n for e in mine if e["f"].get("Status") in ("briefed", "stopped") for n, _, _ in bd.reqs_of(e)}
        left = [n for n in sorted(items) if n not in state and n not in busy]
        partial = sorted(n for n, (st, _, _) in state.items() if st == "partial")
        if partial: later.append(f"Finish the partial requirement{plural(partial)} of {s}: {bd.compress(s, partial)}.")
        if left and not busy:
            nxt = "; ".join(f"{s}.{n} {short(items[n], 70).rstrip('.')}" for n in left[:3])
            later.append(f"Next piece for {s}, from what is not started ({len(left)} requirement{plural(left)}; the plan and the spec's order decide): {nxt}.")
    return first, later, elsewhere

def feature_block(wt, rows, out):
    """Feature records, open design questions, spec open items, and passes in
    the other worktrees, when the hub holds a feature. Returns the steps that
    come before anything else (settle-first questions) and those that come
    last."""
    first, later = [], []
    rc = load_script("records.py"); it = load_script("items.py")
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
    rc = load_script("records.py")
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

def implementation_view(wt, rows, out, unreviewed, pass_steps, passes, mine, theirs):
    """Where the building stands: progress per spec this worktree builds (from
    the build log, or the spec's size when nothing is logged), commits not in
    the log, passes, and the design questions and open items of those specs.
    Returns the next steps, building only."""
    bd = load_script("build.py"); rc = load_script("records.py"); it = load_script("items.py")
    first, later, elsewhere = build_block(wt, out, unreviewed, mine, theirs, render=bd.checklist_lines)
    entries = mine[0]
    me = repo_name(wt, rows)
    try: d = rc.fdir(wt)
    except SystemExit: d = None
    recs = rc.records(d) if d and os.path.exists(os.path.join(d, "feature.md")) else []
    logged = {e["f"].get("Spec") for e in entries}
    specs = [r for r in recs if r.get("type") == "spec" and r.get("status") == "active" and (r.get("repo") in ("", None, me) or r["id"] in logged)]
    accounted = logged.union(*elsewhere.values())
    unlogged_specs = [r for r in specs if r["id"] not in accounted]
    if unlogged_specs:
        if not entries and not any(l.startswith("**Implementation:**") for l in out): out += ["", "**Implementation:** no pieces logged in this worktree."]
        for r in unlogged_specs:
            _, items = bd.spec_requirements(d, r["id"])
            out.append(f"- {r['id']} {short(r.get('title', ''), 60)}: {len(items or {})} requirements, none logged as built")
    base = bd.branch_base(wt)
    builds_elsewhere = not entries and bool(elsewhere)
    commits = [l.split("\t", 1) for l in git(wt, "log", "--no-merges", "--format=%H\t%s", f"{base}..HEAD").splitlines()] if base and not builds_elsewhere else []
    unlogged = [(s, subj) for s, subj in commits if not any(bd.names_commit(e, s) for e in entries)]
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
        where = ", ".join(os.path.basename(p) for p in elsewhere)
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

def design_view(wt, out, logs):
    """Whether the feature is ready to build: readiness per piece, each area's
    decisions and design, open questions by area, and the overview's gaps and
    disagreements. Returns the next steps, design only."""
    rc = load_script("records.py"); it = load_script("items.py"); bd = load_script("build.py")
    d = rc.fdir(wt)
    if not os.path.exists(os.path.join(d, "feature.md")):
        out += ["", "**Design:** no feature records here or in a hub."]; return ["Start a feature: \"start a feature for <name>\"."]
    recs = rc.records(d); cs = rc.checks(d); ov = overview_parts(d)
    specs = {r["id"]: r for r in recs if r.get("type") == "spec" and r.get("status") == "active"}
    built = {}
    for _, p, entries, _ in logs:
        try:
            for s, _, items, state, _ in bd.progress(p, entries):
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

def area_view(wt, out, name, logs):
    """One area, or one spec (a piece) and its area: the overview's summary of
    it, its records, open questions, disagreements that name its records, build
    progress and passes on its specs. Returns the next steps for it."""
    rc = load_script("records.py"); it = load_script("items.py"); bd = load_script("build.py")
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
    for wname, p, entries, _ in logs:
        try:
            for s, r, items, state, pieces in bd.progress(p, entries):
                if s not in {x["id"] for x in specs}: continue
                where = f" ({wname})" if wname else ""
                prog += as_bullets(bd.progress_lines(p, entries, s), where)
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
    ap.add_argument("--setup", action="store_true", help="only what the worktree is missing for a feature work session")
    a = ap.parse_args()
    wt = git(a.worktree, "rev-parse", "--show-toplevel") or os.path.realpath(a.worktree)
    load_script("records.py").guard(wt)
    run = os.path.realpath(os.path.join(wt, ".clerk-dev", a.run or "latest"))
    have_run = os.path.exists(os.path.join(run, "merged.md")) and os.path.exists(os.path.join(run, "target.txt"))
    branch = git(wt, "rev-parse", "--abbrev-ref", "HEAD")
    head = git(wt, "rev-parse", "HEAD")
    out, steps = [], []
    rows = workspace_rows(wt)
    mine = read_build(wt)
    gaps = setup_gaps(wt, rows, mine[0])
    if a.setup:
        emit(wt, "\n".join(f"- {g}" for g in gaps) if gaps else "Setup: complete."); return
    out.append(f"## Where {'the implementation in ' if a.focus == 'implementation' else 'the design of ' if a.focus == 'design' else ''}{repo_name(wt, rows)} stands ({branch})\n")
    out += setup_lines(gaps)
    if a.focus == "design" or a.area:
        logs = [("", wt, *mine)] + builder_logs(wt, rows)
        steps = area_view(wt, out, a.area, logs) if a.area else design_view(wt, out, logs)
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
            out.append(f"- F{i['id']}: {short(i['text'])} ({i['from'] or 'source unknown'}){tag}")
    else:
        out.append(f"**Follow-ups owed here:** none open ({len(items)} done)." if items else "**Follow-ups owed here:** none.")
    if items and not a.no_mark:
        try: open(seen_path, "w").write(str(max(i["id"] for i in items)) + "\n")
        except OSError: pass
    out += deferred_lines(wt)

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
    notes = handoff_lines(passes, mine[0])
    if a.focus == "implementation":
        out[:] = [out[0]] + setup_lines(gaps) + [l for l in out[1:] if l.startswith("**Working tree")]
        steps = implementation_view(wt, rows, out, unreviewed, pass_steps, passes, mine, builder_logs(wt, rows))
        out += notes
        out.append("")
        out += ["**Next:**"] + [f"{n}. {s}" for n, s in enumerate(steps, 1)] if steps else ["**Next:** nothing pending in the building."]
        emit(wt, re.sub(r"\n{3,}", "\n\n", "\n".join(out))); return
    out += notes
    if a.focus == "all":
        bfirst, blater, _ = build_block(wt, out, unreviewed, mine, builder_logs(wt, rows))
        first, later = feature_block(wt, rows, out)
        out += rerouted_lines(wt)
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

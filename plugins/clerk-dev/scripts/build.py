#!/usr/bin/env python3
"""Keep a worktree's build log, <worktree>/.clerk-dev/build.md, and report
progress against the feature's specs.

The build log records each delegated piece of implementation: the spec
requirements it covers, the model and effort it ran at, where it stands, the
commit it landed in, and the questions it stopped on. Requirement status lives
here, not in the specs: a spec states intent, and "done" is what the log's
landed pieces say. A requirement is cited as `R52.7`: spec record R52, item 7
of its Requirements list. The log is read strictly: a line it does not
recognize stops the script rather than being dropped on the next write.

Usage:
  build.py add WORKTREE "title" --spec R52 --reqs 4,5 [--model sonnet] [--effort medium]
  build.py done WORKTREE B3 --commit SHA [--covered "4:done,5:partial: no retry yet"] [--deviation "..."]
  build.py stop WORKTREE B3 --question "..."
  build.py resend WORKTREE B3 [--note "..."] [--model opus] [--effort high]
  build.py abandon WORKTREE B3 [--note "..."]
  build.py note WORKTREE B3 "what to do next"       (a briefed or stopped piece only; "" clears it)
  build.py drop WORKTREE --spec R18 --reqs 17 --why "R24 moved it to R23.3"
  build.py list WORKTREE [--open]
  build.py progress WORKTREE [--spec R52]
  build.py milestone WORKTREE --spec R52 --piece "C core harness" --passes prep,happy-path,security,edge-cases,tests [--required security]
  build.py skip WORKTREE M1 edge-cases --why "..."     (never a required pass)
  build.py milestones WORKTREE
  build.py checklist WORKTREE [--spec R52]          progress as a checklist, one line per requirement

Without --covered, `done` marks every requirement of the piece done. Statuses:
briefed (handed to an implementer), stopped (it stopped on a question),
done (landed in a commit), abandoned, dropped (requirements a later decision
took out of the spec; they leave its count). `resend` puts a stopped or rejected piece
back to briefed and counts the attempt.

Entry format:
  - [ ] B3. Executor and record
    - Spec: R52
    - Requirements: 4 done, 5 partial (no retry yet), 6
    - Model: sonnet medium
    - Status: done
    - Commit: 1a2b3c4
    - Attempts: 2
    - Question: does TurnContext carry the clock?
    - Deviation: kept the reference's retry count
    - Started: 2026-10-16
    - Note: log it with --covered 4:done once the retry test passes   (the handoff of an open piece; status shows it)
"""
import argparse, datetime, importlib.util, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
STATES = ("briefed", "stopped", "done", "abandoned", "dropped")
FIELDS = ("Spec", "Piece", "Requirements", "Passes", "Required", "Model", "Status", "Commit", "Attempts", "Question", "Deviation", "Skipped", "Started", "Note")
REPEATABLE = ("Question", "Deviation", "Skipped")
HEADER = """# Build log

Each piece of implementation delegated on this branch: the spec requirements it
covers and where it stands. Kept by build.py; it reads this file strictly, so
edit with care.

"""
ENTRY_RE = re.compile(r"^- \[( |x)\] ([BM]\d+)\. (.+)$")
FIELD_RE = re.compile(r"^  - (" + "|".join(FIELDS) + r"): ?(.*)$")

def load(name):
    s = importlib.util.spec_from_file_location(name.replace(".py", "").replace("-", "_"), os.path.join(HERE, name))
    assert s and s.loader
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m

def path(wt):
    d = os.path.join(wt, ".clerk-dev"); os.makedirs(d, exist_ok=True)
    if subprocess.run(["git", "-C", wt, "check-ignore", "-q", ".clerk-dev"]).returncode != 0:
        common = subprocess.run(["git", "-C", wt, "rev-parse", "--git-common-dir"], capture_output=True, text=True).stdout.strip()
        if common:
            exf = os.path.join(common if os.path.isabs(common) else os.path.join(wt, common), "info", "exclude")
            os.makedirs(os.path.dirname(exf), exist_ok=True)
            with open(exf, "a") as fh: fh.write(".clerk-dev/\n")
    return os.path.join(d, "build.md")

def read(p):
    if not os.path.exists(p): return []
    out, cur = [], None
    for n, raw in enumerate(open(p, encoding="utf-8"), 1):
        line = raw.rstrip("\n")
        if not line.strip(): continue
        m = ENTRY_RE.match(line)
        if m:
            cur = {"id": m.group(2), "title": m.group(3), "f": {}, "multi": {k: [] for k in REPEATABLE}}; out.append(cur); continue
        if cur is None:
            if line.startswith("#") or not line.startswith((" ", "-")): continue
            sys.exit(f"{p}:{n}: unrecognized line before the first piece: {line!r}")
        m = FIELD_RE.match(line)
        if not m: sys.exit(f"{p}:{n}: unrecognized line in {cur['id']}: {line!r}; fix it by hand, nothing was written")
        if m.group(1) in REPEATABLE: cur["multi"][m.group(1)].append(m.group(2).strip())
        else: cur["f"][m.group(1)] = m.group(2).strip()
    return out

def write(p, entries):
    out = [HEADER]
    for e in entries:
        out.append(f"- [{'x' if e['f'].get('Status') in ('done', 'abandoned', 'ready') else ' '}] {e['id']}. {e['title']}\n")
        for k in FIELDS:
            if k in REPEATABLE: out += [f"  - {k}: {v}\n" for v in e["multi"][k]]
            elif e["f"].get(k): out.append(f"  - {k}: {e['f'][k]}\n")
        out.append("\n")
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), prefix=".build.")
    with os.fdopen(fd, "w", encoding="utf-8") as fh: fh.write("".join(out).rstrip("\n") + "\n")
    os.replace(tmp, p)

def reqs_of(e):
    """[(number, state or None, note)] from a Requirements field such as
    "4 done, 5 partial (no retry yet), 6"."""
    out = []
    for part in re.findall(r"\d+(?:\s+\w+)?(?:\s*\([^)]*\))?", e["f"].get("Requirements", "")):
        m = re.match(r"(\d+)(?:\s+(done|partial))?(?:\s*\(([^)]*)\))?", part)
        if m: out.append((int(m.group(1)), m.group(2), m.group(3) or ""))
    return out

def fmt_reqs(rs):
    return ", ".join(f"{n}" + (f" {st}" if st else "") + (f" ({note})" if note else "") for n, st, note in rs)

def find(entries, bid):
    bid = bid.upper() if re.match(r"[BMbm]\d+$", bid) else f"B{bid}"
    e = next((e for e in entries if e["id"] == bid), None)
    if not e: sys.exit(f"{bid} not found")
    return e

def spec_requirements(hub_dir, spec_id):
    """{number: text} of a spec's top-level numbered Requirements, or None
    when the spec is not found."""
    rc = load("records.py")
    r = next((r for r in rc.records(hub_dir) if r["id"] == spec_id), None)
    if not r: return None, None
    _, body = rc.parse(r["path"])
    m = re.search(r"^## Requirements\n(.*?)(?=^## |\Z)", body, re.S | re.M)
    items, cur = {}, None
    for line in (m.group(1) if m else "").splitlines():
        mm = re.match(r"^(\d+)\.\s+(.*)", line)
        if mm: cur = int(mm.group(1)); items[cur] = mm.group(2).strip()
        elif cur and line.startswith(" ") and line.strip(): items[cur] += " " + line.strip()
    return r, items

def dropped_of(mine):
    return {n: e for e in mine if e["f"].get("Status") == "dropped" for n, _, _ in reqs_of(e)}

def progress(wt, spec=None):
    """Per spec: (record, {n: text}, {n: (state, note, piece id)}, pieces) from
    this worktree's log, for every spec the log names (or the one given)."""
    rc = load("records.py")
    d = rc.fdir(wt)
    entries = pieces(read(os.path.join(wt, ".clerk-dev", "build.md")))
    specs = [spec] if spec else sorted({e["f"].get("Spec") for e in entries if e["f"].get("Spec")}, key=lambda s: int(s[1:]))
    out = []
    for s in specs:
        r, items = spec_requirements(d, s)
        state = {}
        mine = [e for e in entries if e["f"].get("Spec") == s]
        items = {n: t for n, t in (items or {}).items() if n not in dropped_of(mine)}
        for e in mine:
            if e["f"].get("Status") != "done": continue
            for n, st, note in reqs_of(e):
                st = st or "done"
                if state.get(n, ("",))[0] != "done": state[n] = (st, note, e["id"])
        out.append((s, r, items, state, mine))
    return out

def progress_lines(wt, spec=None):
    lines = []
    for s, r, items, state, mine in progress(wt, spec):
        title = r.get("title", "") if r else "(not found in the hub)"
        total = len(items)
        done = [n for n, (st, _, _) in state.items() if st == "done"]
        partial = [n for n, (st, _, _) in state.items() if st == "partial"]
        live = [e for e in mine if e["f"].get("Status") in ("briefed", "stopped")]
        busy = {n for e in live for n, _, _ in reqs_of(e)}
        left = [n for n in sorted(items) if n not in state and n not in busy]
        head = f"{s} {title}: {len(done)} of {total} requirements done" if total else f"{s} {title}: {len(done)} requirements done (the spec lists none)"
        if partial: head += f", {len(partial)} partial ({', '.join(f'{s}.{n}' for n in sorted(partial))})"
        if dropped_of(mine): head += f", {len(dropped_of(mine))} dropped"
        lines.append(head)
        if busy - set(state): lines.append(f"  in progress: {compress(s, sorted(busy - set(state)))}")
        if left: lines.append(f"  not started: {compress(s, left)}")
        for e in live:
            q = e["multi"]["Question"][-1] if e["multi"]["Question"] else ""
            lines.append(f"  {e['id']} {e['title']}: {e['f'].get('Status')}" + (f", on: {q}" if e["f"].get("Status") == "stopped" and q else ""))
    return lines

def label(text, limit=72):
    """A requirement's text cut to its first clause, for one checklist line."""
    text = re.sub(r"\s+", " ", text).strip()
    spans = []
    hidden = re.sub(r"`[^`]*`", lambda m: spans.append(m.group(0)) or f"\x00{len(spans) - 1}\x00", text)
    m = re.match(r"(.+?)(?:[.;:](?:\s|$)|$)", hidden)
    hidden = m.group(1) if m else hidden
    text = re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], hidden)
    if text.count("(") > text.count(")"): text = text[:text.rfind("(")].rstrip()
    if len(text) <= limit: return text
    cut = text[:limit].rsplit(" ", 1)[0]
    if cut.count("`") % 2: cut = cut[:cut.rfind("`")].rstrip()
    if cut.count("(") > cut.count(")"): cut = cut[:cut.rfind("(")].rstrip()
    return cut.rstrip(",;:(") + "…"

def checklist_lines(wt, spec=None):
    """Per spec: a heading line with the count, then one checkbox per
    requirement: [x] done (and the piece), [ ] partial, in progress, or not
    started, with what is missing or which piece is on it."""
    out = []
    for s, r, items, state, mine in progress(wt, spec):
        title = r.get("title", "") if r else "(not found in the hub)"
        live = [e for e in mine if e["f"].get("Status") in ("briefed", "stopped")]
        busy = {n: e for e in live for n, _, _ in reqs_of(e)}
        done = sum(1 for v in state.values() if v[0] == "done")
        out.append(f"{s} {title}: {done} of {len(items)} done")
        _, all_items = spec_requirements(load("records.py").fdir(wt), s)
        gone = dropped_of(mine)
        for n in sorted(set(items) | set(gone)):
            if n in gone:
                out.append(f"- [-] {n}. {label((all_items or {}).get(n, ''))} (dropped, {gone[n]['id']}: {gone[n]['f'].get('Note', '')})"); continue
            st, note, by = state.get(n, (None, "", None))
            if st == "done": out.append(f"- [x] {n}. {label(items[n])} ({by})")
            elif n in busy:
                e = busy[n]; word = "stopped on a question" if e["f"].get("Status") == "stopped" else "in progress"
                out.append(f"- [ ] {n}. {label(items[n])} ({word}, {e['id']})")
            elif st == "partial": out.append(f"- [ ] {n}. {label(items[n])} (partial, {by}: {note or 'not finished'})")
            else: out.append(f"- [ ] {n}. {label(items[n])}")
        out.append("")
    return out[:-1] if out else out

def compress(s, nums):
    """R52.3, R52.5 to R52.9"""
    runs = []
    for n in nums:
        if runs and n == runs[-1][1] + 1: runs[-1][1] = n
        else: runs.append([n, n])
    return ", ".join(f"{s}.{a}" if a == b else f"{s}.{a}, {s}.{b}" if b == a + 1 else f"{s}.{a} to {s}.{b}" for a, b in runs)

# Milestones: a row of the feature's plan, worked as a sequence of passes
# (prep, the draft as happy-path, then one focus each). Only the plan is
# stored; where each pass stands is read from the pass log.

def pieces(entries): return [e for e in entries if e["id"].startswith("B")]
def milestones(entries): return [e for e in entries if e["id"].startswith("M")]

def pass_states(wt, spec):
    """{focus: latest pass entry} for passes on this spec in the pass log."""
    p = os.path.join(wt, ".clerk-dev", "passes.md")
    if not os.path.exists(p): return {}
    out = {}
    for e in load("passes.py").read(p):
        if e["f"].get("Piece") != spec: continue
        out[e["title"].split(" on ")[0].strip()] = e
    return out

def open_findings(wt, e):
    """Open findings in a checked pass's run, or None when it cannot tell."""
    label = (e["f"].get("Check") or "").split(";")[0].strip()
    run = os.path.join(wt, ".clerk-dev", label)
    if not label or not os.path.exists(os.path.join(run, "merged.md")): return None
    sf = load("stale-findings.py")
    st, ins, num = sf.state(run)
    return sum(1 for m in sf.load_findings(run) if m in num and sf.is_open(m, st, ins))

def milestone_view(wt, m):
    """(rows of (focus, word, required), next step or None, ready)."""
    plan = [x.strip() for x in m["f"].get("Passes", "").split(",") if x.strip()]
    req = {x.strip() for x in m["f"].get("Required", "").split(",") if x.strip()}
    skipped = {s.split(":", 1)[0].strip(): s.split(":", 1)[1].strip() if ":" in s else "" for s in m["multi"]["Skipped"]}
    states = pass_states(wt, m["f"].get("Spec"))
    rows, nxt, ready = [], None, True
    for f in plan:
        e = states.get(f)
        if f in skipped:
            rows.append((f, f"skipped: {skipped[f]}", f in req)); continue
        if not e or e["f"].get("Status") == "abandoned":
            rows.append((f, "not run" if not e else "abandoned", f in req)); ready = False
            nxt = nxt or (f"draft {m['title']}: start the happy-path pass and build its pieces" if f == "happy-path" else f"run the {f} pass on {m['f'].get('Spec')}" + (" (required)" if f in req else ""))
            continue
        st = e["f"].get("Status")
        if st == "open":
            rows.append((f, f"{e['id']} open", f in req)); ready = False
            nxt = nxt or (f"finish the draft ({e['id']}), then end it" if f == "happy-path" else f"finish pass {e['id']} ({f}), then end it")
        elif st == "ended" and e["f"].get("Note") != "no commits":
            rows.append((f, f"{e['id']} ended, not checked", f in req)); ready = False
            nxt = nxt or f"check pass {e['id']} ({f})"
        else:
            word = f"{e['id']} " + ("no changes" if e["f"].get("Note") == "no commits" and st == "ended" else "checked")
            n = open_findings(wt, e) if st == "checked" else 0
            if n: word += f", {n} open finding{'s' if n != 1 else ''}"
            if n and f in req:
                ready = False
                label = (e["f"].get("Check") or "").split(";")[0].strip()
                nxt = nxt or f"triage the {f} pass's {n} open finding{'s' if n != 1 else ''} (required): \"work the queue {label}\""
            rows.append((f, word, f in req))
    return rows, nxt, ready

def milestone_lines(wt):
    entries = read(os.path.join(wt, ".clerk-dev", "build.md"))
    out, steps = [], []
    for m in milestones(entries):
        if m["f"].get("Status") == "abandoned": continue
        rows, nxt, ready = milestone_view(wt, m)
        out.append(f"{m['id']} {m['title']} ({m['f'].get('Spec')}): " + ("ready to merge" if ready else "in progress"))
        out.append("  " + "; ".join(f"{f}{' (required)' if r else ''}: {w}" for f, w, r in rows))
        if nxt: steps.append(f"{m['id']} {m['title']}: {nxt}.")
        elif ready: steps.append(f"{m['id']} {m['title']} is ready to merge: its planned passes ran and required findings are triaged.")
    return out, steps

def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    a_ = sp.add_parser("add"); a_.add_argument("wt"); a_.add_argument("title"); a_.add_argument("--spec", required=True)
    a_.add_argument("--reqs", required=True); a_.add_argument("--model", default="sonnet"); a_.add_argument("--effort", default="medium")
    d_ = sp.add_parser("done"); d_.add_argument("wt"); d_.add_argument("bid"); d_.add_argument("--commit", required=True)
    d_.add_argument("--covered"); d_.add_argument("--deviation", action="append", default=[])
    s_ = sp.add_parser("stop"); s_.add_argument("wt"); s_.add_argument("bid"); s_.add_argument("--question", required=True)
    r_ = sp.add_parser("resend"); r_.add_argument("wt"); r_.add_argument("bid"); r_.add_argument("--note"); r_.add_argument("--model"); r_.add_argument("--effort")
    dr = sp.add_parser("drop"); dr.add_argument("wt"); dr.add_argument("--spec", required=True); dr.add_argument("--reqs", required=True); dr.add_argument("--why", required=True)
    ab = sp.add_parser("abandon"); ab.add_argument("wt"); ab.add_argument("bid"); ab.add_argument("--note")
    nt = sp.add_parser("note"); nt.add_argument("wt"); nt.add_argument("bid"); nt.add_argument("text")
    l_ = sp.add_parser("list"); l_.add_argument("wt"); l_.add_argument("--open", action="store_true")
    pr = sp.add_parser("progress"); pr.add_argument("wt"); pr.add_argument("--spec")
    cl = sp.add_parser("checklist"); cl.add_argument("wt"); cl.add_argument("--spec")
    ms = sp.add_parser("milestone"); ms.add_argument("wt"); ms.add_argument("--spec", required=True); ms.add_argument("--piece", required=True)
    ms.add_argument("--passes", required=True); ms.add_argument("--required")
    sk = sp.add_parser("skip"); sk.add_argument("wt"); sk.add_argument("mid"); sk.add_argument("focus"); sk.add_argument("--why", required=True)
    mst = sp.add_parser("milestones"); mst.add_argument("wt")
    a = ap.parse_args()
    load("records.py").guard(a.wt)
    p = path(a.wt); entries = read(p); today = datetime.date.today().isoformat()

    if a.cmd == "add":
        spec = a.spec.upper() if a.spec.upper().startswith("R") else f"R{a.spec}"
        nums = sorted({int(x) for x in re.findall(r"\d+", a.reqs.replace(spec + ".", ""))})
        if not nums: sys.exit("--reqs names no requirement numbers")
        n = max([int(e["id"][1:]) for e in pieces(entries)] or [0]) + 1
        entries.append({"id": f"B{n}", "title": a.title.rstrip("."), "multi": {k: [] for k in REPEATABLE}, "f": {
            "Spec": spec, "Requirements": ", ".join(map(str, nums)), "Model": f"{a.model} {a.effort}",
            "Status": "briefed", "Attempts": "1", "Started": today}})
        write(p, entries); print(f"B{n} briefed: {spec} requirements {', '.join(map(str, nums))}")
        return
    if a.cmd == "drop":
        spec = a.spec.upper() if a.spec.upper().startswith("R") else f"R{a.spec}"
        nums = sorted({int(x) for x in re.findall(r"\d+", a.reqs.replace(spec + ".", ""))})
        if not nums: sys.exit("--reqs names no requirement numbers")
        _, items = spec_requirements(load("records.py").fdir(a.wt), spec)
        if items is None: sys.exit(f"{spec} not found in the hub")
        unknown = [n for n in nums if n not in items]
        if unknown: sys.exit(f"{spec} has no requirement {', '.join(map(str, unknown))}")
        n = max([int(e["id"][1:]) for e in pieces(entries)] or [0]) + 1
        entries.append({"id": f"B{n}", "title": f"Drop {compress(spec, nums)}", "multi": {k: [] for k in REPEATABLE}, "f": {
            "Spec": spec, "Requirements": ", ".join(map(str, nums)), "Status": "dropped", "Started": today, "Note": a.why}})
        write(p, entries); print(f"B{n} dropped: {compress(spec, nums)}")
        return
    if a.cmd == "milestone":
        spec = a.spec.upper() if a.spec.upper().startswith("R") else f"R{a.spec}"
        plan = [x.strip() for x in a.passes.split(",") if x.strip()]
        known = catalogue()
        bad = [x for x in plan if known and x not in known]
        if bad: sys.exit(f"not in the pass catalogue: {', '.join(bad)}; known: {', '.join(known)}")
        req = [x.strip() for x in a.required.split(",")] if a.required else [x for x in plan if x == "security"]
        n = max([int(e["id"][1:]) for e in milestones(entries)] or [0]) + 1
        entries.append({"id": f"M{n}", "title": a.piece.rstrip("."), "multi": {k: [] for k in REPEATABLE}, "f": {
            "Spec": spec, "Passes": ", ".join(plan), "Required": ", ".join(req), "Started": today}})
        write(p, entries); print(f"M{n} planned: {', '.join(plan)}" + (f"; required: {', '.join(req)}" if req else ""))
        return
    if a.cmd == "skip":
        m = find(entries, a.mid)
        if a.focus in [x.strip() for x in m["f"].get("Required", "").split(",")]: sys.exit(f"{a.focus} is required for {m['id']}; it cannot be skipped")
        m["multi"]["Skipped"].append(f"{a.focus}: {a.why}"); write(p, entries); print(f"{m['id']}: {a.focus} skipped")
        return
    if a.cmd == "checklist":
        print("\n".join(checklist_lines(a.wt, a.spec.upper() if a.spec else None)) or "no pieces logged")
        return
    if a.cmd == "milestones":
        lines, steps = milestone_lines(a.wt)
        print("\n".join(lines + [""] + steps) if lines else "no milestones")
        return
    if a.cmd in ("list", "progress"):
        if a.cmd == "list":
            for e in pieces(entries):
                st = e["f"].get("Status")
                if a.open and st in ("done", "abandoned", "dropped"): continue
                print(f"{e['id']} {e['title']}  [{e['f'].get('Spec')}: {e['f'].get('Requirements')}; {st}; {e['f'].get('Model')}"
                      + (f"; {e['f']['Commit']}" if e["f"].get("Commit") else "") + "]")
        else:
            print("\n".join(progress_lines(a.wt, a.spec.upper() if a.spec else None)) or "no pieces logged")
        return
    e = find(entries, a.bid)
    if a.cmd == "done":
        if e["f"].get("Status") in ("abandoned", "dropped"): sys.exit(f"{e['id']} is {e['f']['Status']}")
        if subprocess.run(["git", "-C", a.wt, "cat-file", "-e", a.commit + "^{commit}"], capture_output=True).returncode != 0: sys.exit(f"{a.commit} is not a commit here")
        planned = {n for n, _, _ in reqs_of(e)}
        cov = {}
        if a.covered:
            for part in re.split(r",(?=\s*(?:R\d+\.)?\d+\s*:)", a.covered):
                m = re.match(r"\s*(?:R\d+\.)?(\d+)\s*:\s*(done|partial)\s*(?::\s*(.*))?$", part.strip())
                if not m: sys.exit(f"cannot read {part!r} in --covered; use \"4:done,5:partial: what is missing\"")
                cov[int(m.group(1))] = (m.group(2), (m.group(3) or "").strip())
        rs = [(n, *cov.get(n, ("done", ""))) for n in sorted(planned | set(cov))]
        e["f"]["Requirements"] = fmt_reqs(rs)
        e["f"]["Commit"] = git_short(a.wt, a.commit); e["f"]["Status"] = "done"
        e["multi"]["Deviation"] += a.deviation
        write(p, entries); print(f"{e['id']} done in {e['f']['Commit']}: {e['f']['Requirements']}")
    elif a.cmd == "stop":
        e["f"]["Status"] = "stopped"; e["multi"]["Question"].append(a.question)
        write(p, entries); print(f"{e['id']} stopped: {a.question}")
    elif a.cmd == "resend":
        if e["f"].get("Status") in ("done", "abandoned", "dropped"): sys.exit(f"{e['id']} is {e['f'].get('Status')}")
        e["f"]["Status"] = "briefed"; e["f"]["Attempts"] = str(int(e["f"].get("Attempts", "1")) + 1)
        if a.model or a.effort:
            m0, e0 = (e["f"].get("Model", "sonnet medium").split() + ["medium"])[:2]
            e["f"]["Model"] = f"{a.model or m0} {a.effort or e0}"
        if a.note: e["f"]["Note"] = a.note
        write(p, entries); print(f"{e['id']} briefed again (attempt {e['f']['Attempts']}, {e['f']['Model']})")
    elif a.cmd == "note":
        if e["f"].get("Status") not in ("briefed", "stopped"): sys.exit(f"{e['id']} is {e['f'].get('Status') or 'a milestone'}, not an open piece")
        text = " ".join(a.text.split())
        if text: e["f"]["Note"] = text
        else: e["f"].pop("Note", None)
        write(p, entries); print(f"{e['id']} note " + ("set" if text else "cleared"))
    elif a.cmd == "abandon":
        e["f"]["Status"] = "abandoned"
        if a.note: e["f"]["Note"] = a.note
        write(p, entries); print(f"{e['id']} abandoned")

def catalogue():
    """Pass names from the catalogue table in skills/pass/passes.md."""
    p = os.path.join(HERE, "..", "skills", "pass", "passes.md")
    if not os.path.exists(p): return []
    names = []
    for line in open(p, encoding="utf-8"):
        m = re.match(r"^\|\s*([a-z][a-z-]*)\s*\|", line)
        if m and m.group(1) not in ("pass", "category"): names.append(m.group(1))
    return names

def git_short(wt, sha):
    return subprocess.run(["git", "-C", wt, "rev-parse", "--short", sha], capture_output=True, text=True).stdout.strip() or sha

if __name__ == "__main__": main()

#!/usr/bin/env python3
"""Manage a feature's records, <hub worktree>/.clerk-dev/feature/.

A feature's records are point-in-time documents: brainstorms, designs,
decisions, capabilities, plans, and specs. Each is one Markdown file under
records/ with YAML-like frontmatter, numbered on one sequence (R1, R2, ...) so
any record can be cited by id. A record is written once; afterwards only its
status changes, and a revision is a new record that supersedes it. feature.md
holds the feature's name and summary, and an index this script regenerates.

A record may carry an area, a short name for the part of the problem it is
about (auth, delivery). There is no list of areas: they are whatever the records
use, and the index groups records by them. The area is a label, not content, so
it can be changed at any time (tag, rename-area).

The hub is the worktree that holds the records: the worktree named on the
`Hub:` line of .clerk-dev/review-workspace.md, or else this worktree.

Usage:
  records.py hub WORKTREE
  records.py start WORKTREE "Feature name" [--summary "..."]
  records.py new WORKTREE TYPE "title" [--area A] [--repo R] [--from R2,R4] [--supersedes R3]
  records.py list WORKTREE [--type T] [--active] [--repo R] [--area A | --area -]
  records.py areas WORKTREE
  records.py tag WORKTREE R7 [--area A]       (no --area: feature-wide)
  records.py rename-area WORKTREE OLD NEW
  records.py path WORKTREE R7
  records.py discard WORKTREE R7 [--note "..."]
  records.py reactivate WORKTREE R7
  records.py index WORKTREE
  records.py digest WORKTREE            what an overview is written from
  records.py stamp-overview WORKTREE    after writing overview.md
  records.py overview-status WORKTREE
  records.py suggest WORKTREE           roll-up designs, plans, stale overview

Record frontmatter:
  ---
  id: R7
  type: decision
  title: Poll export status instead of pushing it over the websocket
  date: 2026-10-16
  repo: api
  area: delivery
  status: active
  from: R2, R5
  supersedes: R3
  ---
"""
import argparse, datetime, os, re, subprocess, sys

TYPES = ("brainstorm", "design", "decision", "capabilities", "plan", "spec")
STATUSES = ("active", "superseded", "discarded")
FIELDS = ("id", "type", "title", "date", "repo", "area", "status", "from", "supersedes", "superseded_by", "note")

def git(wt, *args):
    r = subprocess.run(["git", "-C", wt, *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""

def exclude(wt):
    """Create .clerk-dev/ and its .git/info/exclude entry, as followups.py does."""
    os.makedirs(os.path.join(wt, ".clerk-dev"), exist_ok=True)
    if subprocess.run(["git", "-C", wt, "check-ignore", "-q", ".clerk-dev"]).returncode != 0:
        common = git(wt, "rev-parse", "--git-common-dir")
        if common:
            exf = os.path.join(common if os.path.isabs(common) else os.path.join(wt, common), "info", "exclude")
            os.makedirs(os.path.dirname(exf), exist_ok=True)
            with open(exf, "a") as fh: fh.write(".clerk-dev/\n")

def workspace(wt):
    """(hub worktree or None, {repo: worktree}) from .clerk-dev/review-workspace.md."""
    p = os.path.join(wt, ".clerk-dev", "review-workspace.md")
    if not os.path.exists(p): return None, {}
    text = open(p, encoding="utf-8").read()
    repos = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and len(cells) >= 2 and cells[0] not in ("Repo", "") and not set(cells[0]) <= set("-: "):
            repos[cells[0]] = cells[1]
    m = re.search(r"^Hub:\s*(\S+)", text, re.M)
    hub = None
    if m: hub = repos.get(m.group(1), m.group(1))
    return hub, repos

def this_repo(wt, repos):
    real = os.path.realpath(wt)
    for name, path in repos.items():
        if os.path.realpath(path) == real: return name
    url = git(wt, "remote", "get-url", "origin")
    if url: return re.sub(r"\.git$", "", url.rstrip("/").split("/")[-1].split(":")[-1])
    return os.path.basename(real)

def hub(wt):
    h, _ = workspace(wt)
    if h and not os.path.isdir(h): sys.exit(f"hub worktree {h} (from .clerk-dev/review-workspace.md) does not exist")
    return os.path.abspath(h or wt)

def fdir(wt): return os.path.join(hub(wt), ".clerk-dev", "feature")

def parse(p):
    text = open(p, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    meta = {}
    if m:
        for line in m.group(1).splitlines():
            k, _, v = line.partition(":")
            if k.strip(): meta[k.strip()] = v.strip()
    meta["path"] = p
    return meta, text[m.end():] if m else text

def render(meta, body):
    head = "".join(f"{k}: {meta[k]}\n" for k in FIELDS if meta.get(k))
    return f"---\n{head}---\n{body}"

def records(d):
    rd = os.path.join(d, "records")
    if not os.path.isdir(rd): return []
    out = [parse(os.path.join(rd, f))[0] for f in os.listdir(rd) if f.endswith(".md")]
    return sorted((r for r in out if re.fullmatch(r"R\d+", r.get("id", ""))), key=lambda r: int(r["id"][1:]))

def find(d, rid):
    rid = rid.upper() if rid.upper().startswith("R") else f"R{rid}"
    r = next((r for r in records(d) if r["id"] == rid), None)
    if not r: sys.exit(f"{rid} not found in {d}/records")
    return r

def set_fields(r, **kw):
    meta, body = parse(r["path"])
    for k, v in kw.items():
        if v is None: meta.pop(k, None)
        else: meta[k] = v
    open(r["path"], "w", encoding="utf-8").write(render(meta, body))

def checks(d):
    """Design-check files in checks/: name, records covered (from the Checked line), open and closed counts."""
    cd = os.path.join(d, "checks")
    if not os.path.isdir(cd): return []
    out = []
    for f in sorted(os.listdir(cd), key=lambda f: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", f)]):
        if not f.endswith(".md"): continue
        text = open(os.path.join(cd, f), encoding="utf-8").read()
        m = re.search(r"^Checked [^:]*:\s*(.*?)(?:\.\s|\.$|$)", text, re.M)
        recs = re.findall(r"\bR\d+\b", m.group(1)) if m else []
        out.append({"name": f[:-3], "records": recs, "open": len(re.findall(r"^[-*] \[ \]", text, re.M)),
                    "closed": len(re.findall(r"^[-*] \[[xX]\]", text, re.M))})
    return out

def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower())[:50].strip("-") or "untitled"

GIST_SECTION = {"decision": "Decision", "spec": "Goal", "design": "Shape", "brainstorm": "Leaning"}
TYPE_ORDER = ("design", "capabilities", "plan", "spec", "decision", "brainstorm")

LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")

def first_sentences(para, at_least=40):
    """Sentences from the start until at least `at_least` characters. Periods
    inside code spans and in e.g., i.e., etc., and vs. do not end a sentence."""
    spans = []
    def hide(m):
        spans.append(m.group(0)); return f"\x00{len(spans) - 1}\x00"
    s = re.sub(r"`[^`]*`", hide, para)
    s = re.sub(r"\b(e\.g|i\.e|etc|vs|cf)\.", lambda m: m.group(0).replace(".", "\x01"), s)
    parts = re.split(r"(?<=[.!?])\s+", s)
    out = ""
    for part in parts:
        out = (out + " " + part).strip()
        if len(out) >= at_least: break
    out = out.replace("\x01", ".")
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], out)

def gist(r, limit=220):
    """The record's first sentences of substance: the start of its Decision,
    Goal, Shape, or Leaning section, else of its body; the first item of a
    list; when that ends in a colon, the first item of the list it
    introduces. Tables, headings, and code blocks are skipped."""
    _, body = parse(r["path"])
    body = re.sub(r"^# .*\n", "", body.lstrip("\n"), count=1)
    sec = GIST_SECTION.get(r.get("type", ""))
    m = re.search(rf"^## {sec}\n(.*?)(?=^## |\Z)", body, re.S | re.M) if sec else None
    text = m.group(1) if m else re.sub(r"^## .*$", "", body, flags=re.M)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    blocks = []
    for block in re.split(r"\n\s*\n", text):
        lines = [l for l in block.strip().splitlines() if l.strip() and not l.lstrip().startswith(("|", "#"))]
        if not lines: continue
        if LIST_RE.match(lines[0]):
            item = [LIST_RE.sub("", lines[0])]
            for l in lines[1:]:
                if LIST_RE.match(l): break
                item.append(l.strip())
            blocks.append(" ".join(item))
        else:
            blocks.append(" ".join(l.strip() for l in lines))
        if len(blocks) == 2: break
    if not blocks: return ""
    para = re.sub(r"\s+", " ", blocks[0]).strip()
    para = para if para.endswith(":") else first_sentences(para)
    if para.endswith(":") and len(blocks) > 1:
        para += " " + first_sentences(re.sub(r"\s+", " ", blocks[1]).strip())
    if len(para) > limit: para = para[:limit].rsplit(" ", 1)[0].rstrip(",;:") + " …"
    return para

def ordered(rs):
    return sorted(rs, key=lambda r: (TYPE_ORDER.index(r.get("type")) if r.get("type") in TYPE_ORDER else 9, int(r["id"][1:])))

def entry(r, d, repos):
    where = f" ({r.get('repo')})" if repos else ""
    line = f"- **{r['id']}** {r.get('type', '')}{where}: [{r.get('title', '')}]({os.path.relpath(r['path'], d)})"
    g = gist(r)
    return [line] + ([f"  - {g}"] if g else [])

def overview_state(d):
    """(through id or None, basis in the file or None, current basis, ids added since)."""
    rs = records(d)
    basis = basis_of(rs)
    p = os.path.join(d, "overview.md")
    if not os.path.exists(p): return None, None, basis, [r["id"] for r in rs]
    head = open(p, encoding="utf-8").read(600)
    m = re.search(r"through (R\d+) \(basis ([0-9a-f]+)\)", head)
    if not m: return None, None, basis, [r["id"] for r in rs]
    through = int(m.group(1)[1:])
    return m.group(1), m.group(2), basis, [r["id"] for r in rs if int(r["id"][1:]) > through]

def basis_of(rs):
    import hashlib
    key = "|".join(f"{r['id']}:{r.get('status', '')}:{r.get('area', '')}:{r.get('title', '')}" for r in rs)
    return hashlib.sha1(key.encode()).hexdigest()[:10]

def overview_line(d):
    through, old, basis, added = overview_state(d)
    if through is None:
        missing = not os.path.exists(os.path.join(d, "overview.md"))
        return ("No overview yet" if missing else "The overview has no stamp") + "; say \"refresh the overview\"."
    if old == basis: return f"Overview: [overview.md](overview.md), current (through {through})."
    since = f"; {', '.join(added)} came after" if added else "; statuses or areas changed since"
    return f"Overview: [overview.md](overview.md), stale (through {through}{since}); say \"refresh the overview\"."

def index(d):
    p = os.path.join(d, "feature.md")
    if not os.path.exists(p): return
    text = open(p, encoding="utf-8").read()
    rs = records(d)
    repos = len({r.get("repo") for r in rs}) > 1
    live = [r for r in rs if r.get("status") == "active"]
    past = [r for r in rs if r.get("status") != "active"]
    rows = ["## Records", "", "Regenerated by records.py; edits here are lost. Active records, each with its",
            "first line; brainstorms and superseded or discarded records are under History.", ""]
    if len(rs) >= 5: rows += [overview_line(d), ""]
    if not rs: rows.append("None yet.")
    else:
        areas = []
        for r in live:
            if r.get("area") and r["area"] not in areas: areas.append(r["area"])
        groups = ([("Feature-wide", [r for r in live if not r.get("area")])] if any(not r.get("area") for r in live) else []) + [(a, [r for r in live if r.get("area") == a]) for a in areas]
        for name, grp in groups:
            if len(groups) > 1 or areas: rows += [f"### {name}", ""]
            for r in ordered(grp): rows += entry(r, d, repos)
            rows.append("")
        if not live: rows += ["No active records.", ""]
    cs = checks(d)
    if cs:
        rows += ["## Checks", "", "| Check | Records | Open | Closed |", "| --- | --- | --- | --- |"]
        rows += [f"| [{c['name']}](checks/{c['name']}.md) | {', '.join(c['records'])} | {c['open']} | {c['closed']} |" for c in cs] + [""]
    if past:
        rows += ["## History", "", "Brainstorms, and records no longer active, oldest first.", ""]
        for r in past:
            st = r.get("status", "")
            note = f", superseded by {r['superseded_by']}" if r.get("superseded_by") else (f", discarded: {r['note']}" if st == "discarded" and r.get("note") else (", discarded" if st == "discarded" else ""))
            where = r.get("area") or "feature-wide"
            rows.append(f"- **{r['id']}** {r.get('type', '')} ({where}): [{r.get('title', '')}]({os.path.relpath(r['path'], d)}){note}")
        rows.append("")
    block = "\n".join(rows).rstrip("\n") + "\n"
    text = re.sub(r"^## (Records|Checks|History)\n.*?(?=^## |\Z)", "", text, flags=re.S | re.M).rstrip("\n")
    open(p, "w", encoding="utf-8").write(text + "\n\n" + block)

def suggestions(d):
    """Records worth writing: roll-up designs, plans, and a stale overview."""
    rs = records(d); live = [r for r in rs if r.get("status") == "active"]
    out = []
    areas = sorted({r.get("area", "") for r in live}, key=lambda a: (a != "", a))
    for a in areas:
        decs = [r for r in live if r.get("area", "") == a and r.get("type") == "decision"]
        des = [r for r in live if r.get("area", "") == a and r.get("type") == "design"]
        name = a or "the feature-wide records"
        if len(decs) >= 3 and not des:
            out.append(f"{name}: {len(decs)} active decisions and no design; roll them up into a design that cites them.")
        elif des:
            newest = max(int(x["id"][1:]) for x in des)
            later = [x["id"] for x in decs if int(x["id"][1:]) > newest]
            if len(later) >= 3: out.append(f"{name}: design R{newest} predates {len(later)} active decisions ({', '.join(later)}); supersede it with one that includes them.")
    plans = [r for r in live if r.get("type") in ("plan", "capabilities")]
    planlike = [r for r in live if r.get("type") == "decision" and re.search(r"\b(chunks|ordering|order of|sequenc\w*|dependencies|phases|milestones|pieces|plan|roadmap|breakdown)\b", r.get("title", ""), re.I)]
    if not plans:
        if planlike:
            ids = ", ".join(r["id"] for r in planlike)
            out.append(f"No plan yet, but {ids} set pieces or their order; file a plan (or capabilities) record from {'them' if len(planlike) > 1 else 'it'}, so the order of work has one home.")
        if not planlike and (len({r.get('area', '') for r in live}) > 2 or len(live) >= 10):
            out.append("No plan or capabilities record yet; write one for the order of work.")
    if len(rs) >= 5:
        through, old, basis, added = overview_state(d)
        if through is None or old != basis: out.append("The overview is missing or stale; refresh it.")
    return out

def digest(d):
    """What the overview writer reads: the summary, every active record in full
    (brainstorms as one line each), open design questions, and spec open items."""
    rs = records(d)
    out = []
    fp = os.path.join(d, "feature.md")
    m = re.search(r"^## Summary\n(.*?)(?=^## |\Z)", open(fp, encoding="utf-8").read(), re.S | re.M)
    out += ["# Summary", "", (m.group(1).strip() if m else "(none)"), ""]
    live = [r for r in rs if r.get("status") == "active" and r.get("type") != "brainstorm"]
    for r in sorted(live, key=lambda r: (r.get("area", ""), TYPE_ORDER.index(r["type"]) if r["type"] in TYPE_ORDER else 9, int(r["id"][1:]))):
        _, body = parse(r["path"])
        out += [f"===== {r['id']} {r['type']} (area: {r.get('area') or 'feature-wide'}; from: {r.get('from') or '-'}; supersedes: {r.get('supersedes') or '-'})", body.strip(), ""]
    out += ["# Brainstorms (history; one line each)", ""]
    out += [f"- {r['id']} ({r.get('area') or 'feature-wide'}): {r.get('title', '')}. {gist(r)}" for r in rs if r.get("type") == "brainstorm"] + [""]
    out += ["# Superseded or discarded (ids only)", "", ", ".join(f"{r['id']} {r.get('status')}" for r in rs if r.get("status") in ("superseded", "discarded")) or "none", ""]
    out += ["# Open design questions", ""]
    for c in checks(d):
        text = open(os.path.join(d, "checks", c["name"] + ".md"), encoding="utf-8").read()
        for q in re.finditer(r"^- \[ \] (Q\d+)\. (.*)$", text, re.M):
            w = re.search(r"Weight: (\S+)", text[q.end():q.end() + 800])
            out.append(f"- {c['name']}.{q.group(1)} ({w.group(1) if w else '?'}): {q.group(2)}")
    out += ["", "# Open items in active specs", ""]
    for r in live:
        if r["type"] != "spec": continue
        _, body = parse(r["path"])
        m = re.search(r"^## Open items\n(.*?)(?=^## |\Z)", body, re.S | re.M)
        for item in re.findall(r"^\s*[-*] \[ \] (.*)$", m.group(1) if m else "", re.M): out.append(f"- {r['id']}: {item}")
    return "\n".join(out) + "\n"

def stamp_overview(d):
    p = os.path.join(d, "overview.md")
    if not os.path.exists(p): sys.exit(f"{p} does not exist; write it first")
    rs = records(d)
    last = rs[-1]["id"] if rs else "R0"
    text = open(p, encoding="utf-8").read()
    text = re.sub(r"^Generated .* \(basis [0-9a-f]+\)\..*\n+", "", text, flags=re.M)
    lines = text.split("\n", 1)
    stamp = (f"Generated {datetime.date.today().isoformat()} through {last} (basis {basis_of(rs)}). Do not edit:"
             " regenerate it by saying \"refresh the overview\"; a change of substance is a new record.\n\n")
    text = lines[0] + "\n\n" + stamp + (lines[1].lstrip("\n") if len(lines) > 1 else "")
    open(p, "w", encoding="utf-8").write(text)
    index(d)
    return last

def area_of(d, ids):
    """The area records share, or "" when they have none or differ."""
    got = {find(d, i).get("area", "") for i in ids}
    return got.pop() if len(got) == 1 else ""

def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("hub").add_argument("wt")
    s = sp.add_parser("start"); s.add_argument("wt"); s.add_argument("name"); s.add_argument("--summary", default="")
    n = sp.add_parser("new"); n.add_argument("wt"); n.add_argument("type", choices=TYPES); n.add_argument("title")
    n.add_argument("--repo"); n.add_argument("--from", dest="src"); n.add_argument("--supersedes"); n.add_argument("--area")
    l = sp.add_parser("list"); l.add_argument("wt"); l.add_argument("--type", choices=TYPES); l.add_argument("--active", action="store_true"); l.add_argument("--repo"); l.add_argument("--area")
    sp.add_parser("areas").add_argument("wt")
    tg = sp.add_parser("tag"); tg.add_argument("wt"); tg.add_argument("rid"); tg.add_argument("--area")
    ra = sp.add_parser("rename-area"); ra.add_argument("wt"); ra.add_argument("old"); ra.add_argument("new")
    pa = sp.add_parser("path"); pa.add_argument("wt"); pa.add_argument("rid")
    di = sp.add_parser("discard"); di.add_argument("wt"); di.add_argument("rid"); di.add_argument("--note")
    re_ = sp.add_parser("reactivate"); re_.add_argument("wt"); re_.add_argument("rid")
    sp.add_parser("index").add_argument("wt")
    for c in ("digest", "stamp-overview", "overview-status", "suggest"): sp.add_parser(c).add_argument("wt")
    a = ap.parse_args()
    today = datetime.date.today().isoformat()

    if a.cmd == "hub":
        print(hub(a.wt)); return
    d = fdir(a.wt)
    if a.cmd == "start":
        h = hub(a.wt); exclude(h); os.makedirs(os.path.join(d, "records"), exist_ok=True)
        p = os.path.join(d, "feature.md")
        if os.path.exists(p): sys.exit(f"{p} already exists")
        _, repos = workspace(a.wt)
        open(p, "w", encoding="utf-8").write(
            f"# Feature: {a.name}\n\nStarted {today} in {this_repo(h, repos)} ({h}). Edit freely above Records.\n\n"
            f"## Summary\n\n{a.summary or 'One paragraph: what the feature is for and who it serves.'}\n")
        index(d); print(p); return
    if not os.path.exists(os.path.join(d, "feature.md")):
        sys.exit(f"no feature in {d}; start one with: records.py start {a.wt} \"name\"")

    if a.cmd == "new":
        rs = records(d); num = max([int(r["id"][1:]) for r in rs] or [0]) + 1
        _, repos = workspace(a.wt)
        old = find(d, a.supersedes) if a.supersedes else None
        src = [x.strip() for x in a.src.split(",")] if a.src else []
        area = a.area if a.area is not None else (old.get("area", "") if old else area_of(d, src) if src else "")
        meta = {"id": f"R{num}", "type": a.type, "title": a.title.rstrip("."), "date": today,
                "repo": a.repo or this_repo(a.wt, repos), "area": slug(area) if area else "",
                "status": "" if a.type == "brainstorm" else "active",
                "from": ", ".join(x.strip().upper() for x in a.src.split(",")) if a.src else "",
                "supersedes": old["id"] if old else ""}
        p = os.path.join(d, "records", f"{num:03d}-{a.type}-{slug(a.title)}.md")
        open(p, "w", encoding="utf-8").write(render(meta, f"\n# {meta['id']}. {meta['title']}\n\n"))
        if old: set_fields(old, status="superseded", superseded_by=meta["id"])
        index(d); print(f"{meta['id']} {p}" + (f" (area {meta['area']})" if meta["area"] else "") + (f" (supersedes {old['id']})" if old else ""))
    elif a.cmd == "list":
        for r in records(d):
            if a.type and r.get("type") != a.type: continue
            if a.repo and r.get("repo") != a.repo: continue
            if a.area is not None and r.get("area", "") != ("" if a.area == "-" else a.area): continue
            if a.active and (r.get("type") == "brainstorm" or r.get("status") != "active"): continue
            extra = "; ".join(f"{k}: {r[k]}" for k in ("from", "supersedes", "superseded_by", "note") if r.get(k))
            print(f"{r['id']} {r.get('type','')}: {r.get('title','')}  [{r.get('repo','')}{' ' + r['area'] if r.get('area') else ''} {r.get('date','')} {r.get('status','') or 'record'}{'; ' + extra if extra else ''}]  {os.path.relpath(r['path'], hub(a.wt))}")
    elif a.cmd == "path":
        print(find(d, a.rid)["path"])
    elif a.cmd == "discard":
        r = find(d, a.rid)
        if r.get("type") == "brainstorm": sys.exit("brainstorms have no status; they stay as history")
        set_fields(r, status="discarded", note=a.note); index(d); print(f"{r['id']} discarded")
    elif a.cmd == "reactivate":
        r = find(d, a.rid); set_fields(r, status="active", superseded_by=None, note=None); index(d); print(f"{r['id']} active")
    elif a.cmd == "areas":
        by = {}
        for r in records(d):
            k = r.get("area") or "(feature-wide)"
            s = by.setdefault(k, {"n": 0, "active": 0, "last": ""})
            s["n"] += 1; s["active"] += r.get("status") == "active"; s["last"] = max(s["last"], r.get("date", ""))
        for k, s in by.items(): print(f"{k}\t{s['n']} record{'s' if s['n'] != 1 else ''}, {s['active']} active, last {s['last']}")
    elif a.cmd == "tag":
        r = find(d, a.rid); set_fields(r, area=slug(a.area) if a.area else None); index(d)
        print(f"{r['id']} " + (f"area {slug(a.area)}" if a.area else "feature-wide"))
    elif a.cmd == "rename-area":
        hit = [r for r in records(d) if r.get("area") == a.old]
        if not hit: sys.exit(f"no record has area {a.old}")
        for r in hit: set_fields(r, area=slug(a.new))
        index(d); print(f"{len(hit)} records moved from {a.old} to {slug(a.new)}")
    elif a.cmd == "index":
        index(d); print(os.path.join(d, "feature.md"))
    elif a.cmd == "digest":
        sys.stdout.write(digest(d))
    elif a.cmd == "stamp-overview":
        print(f"overview stamped through {stamp_overview(d)}")
    elif a.cmd == "overview-status":
        print(re.sub(r"\[overview.md\]\(overview.md\)", os.path.join(d, "overview.md"), overview_line(d)))
    elif a.cmd == "suggest":
        print("\n".join(suggestions(d)) or "nothing to suggest")

if __name__ == "__main__": main()

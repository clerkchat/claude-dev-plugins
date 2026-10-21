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
  records.py names WORKTREE R31 S C R52.19 B15 ...   a short name for each id or code
  records.py guidance WORKTREE [--area A | --for R33|R33.4|R18-1.Q6] [--context REVIEW-CONTEXT.md] [--out FILE]
                                        branch scope, branch guidance, the feature's active guidance, and the repository's Known noise
  records.py idea WORKTREE "text" [--area A] [--from R12|"this session"] [--why ...] [--when ...]
  records.py ideas WORKTREE [--all] [--area A | --area -]
  records.py adopt WORKTREE I3 --by R60   the record the idea became
  records.py drop WORKTREE I3 --why "..."
  records.py unpark WORKTREE I3           back to parked

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
import argparse, datetime, importlib.util, os, re, subprocess, sys

TYPES = ("brainstorm", "design", "decision", "guidance", "capabilities", "plan", "spec")
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

def record_id(text):
    return text.upper() if text.upper().startswith("R") else f"R{text}"

def find(d, rid):
    rid = record_id(rid)
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

GIST_SECTION = {"decision": "Decision", "guidance": "Rule", "spec": "Goal", "design": "Shape", "brainstorm": "Leaning"}
TYPE_ORDER = ("guidance", "design", "capabilities", "plan", "spec", "decision", "brainstorm")

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
    parked = [i for i in ideas(d) if not i["done"]]
    if parked:
        rows += ["## Ideas", "", f"Parked, {len(parked)}; all of them, with why and when, in [ideas.md](ideas.md).", ""]
        rows += [f"- **{i['id']}**{' (' + i['fields']['Area'] + ')' if i['fields'].get('Area') else ''}: {i['text']}" for i in parked] + [""]
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
    stale = os.path.join(d, "guidance.md")
    if os.path.exists(stale): os.remove(stale)
    block = "\n".join(rows).rstrip("\n") + "\n"
    text = re.sub(r"^## (Records|Ideas|Checks|History)\n.*?(?=^## |\Z)", "", text, flags=re.S | re.M).rstrip("\n")
    open(p, "w", encoding="utf-8").write(text + "\n\n" + block)

def rules(d, area=None):
    """Active guidance as (record, rule) pairs, feature-wide first, filtered
    to an area plus the feature-wide ones when one is given."""
    rs = [r for r in records(d) if r.get("type") == "guidance" and r.get("status") == "active"]
    if area is not None: rs = [r for r in rs if not r.get("area") or r.get("area") == area]
    return [(r, gist(r, limit=400)) for r in sorted(rs, key=lambda r: (bool(r.get("area")), r.get("area", ""), int(r["id"][1:])))]

def body_section(body, heading):
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", body, re.S | re.M)
    return m.group(1).strip() if m else ""

def labeled(label, text):
    """A bold label and its text: inline for one paragraph, below it for lists
    or several paragraphs."""
    if not text: return []
    if "\n\n" in text or re.match(r"^\s*(?:[-*+]|\d+\.)\s", text): return [f"**{label}:**", "", text, ""]
    return [f"**{label}:** {re.sub(r'\s*\n\s*', ' ', text)}", ""]

def rule_lines(heading, body, rule):
    return [f"### {heading}", "", body_section(body, "Rule") or rule, ""] + labeled("Why", body_section(body, "Why")) + labeled("Applies to", body_section(body, "Applies to"))

def notes_path(wt): return os.path.join(wt, ".clerk-dev", "branch-notes.md")

def guard(wt):
    p = notes_path(wt)
    if os.path.exists(p) and {"## Review", "## Fixes"} & set(open(p, encoding="utf-8").read().splitlines()):
        sys.exit(f'{p} still has the old "## Review"/"## Fixes" sections; run /clerk-dev:migrate in this worktree first.')

def guard_file(path):
    parts = os.path.abspath(path).split(os.sep)
    if ".clerk-dev" in parts: guard(os.sep.join(parts[:parts.index(".clerk-dev")]) or os.sep)

def headings(text, marker):
    parts = re.split(rf"^{marker} (.+?)[ \t]*$", text, flags=re.M)
    return list(zip(parts[1::2], (b.strip() for b in parts[2::2])))

def branch_notes(wt):
    p = notes_path(wt)
    if not os.path.exists(p): return None, []
    sections = dict(headings(open(p, encoding="utf-8").read(), "##"))
    return sections.get("Purpose", ""), headings(sections.get("Guidance", ""), "###")

BRANCH_NAME_RE = re.compile(r"\b(?:feat|fix|chore|refactor|docs|test|hotfix|release)/[\w.-]+")

def code_named(text):
    for tok in re.findall(r"`([^`]+)`", text):
        if re.search(r"[/.(_]|[a-z][A-Z]", tok): return tok
    m = BRANCH_NAME_RE.search(text)
    return m.group(0) if m else None

def lint(label, text):
    tok = code_named(text)
    if not tok: return []
    start = re.sub(r"\s+", " ", text).strip()
    start = start if len(start) <= 60 else start[:60].rsplit(" ", 1)[0] + "..."
    return [f'warning: {label}: "{start}" names {tok}; guidance is for principles, consider a decision, requirement, or Purpose']

def noise(context):
    if not context or not os.path.exists(context): return ""
    return body_section(open(context, encoding="utf-8").read(), "Known noise")

def guidance(wt, area=None, context=None):
    purpose, branch_rules = branch_notes(wt)
    out = ["# Guidance", "", "These are the user's standing rules for this worktree, narrowest scope first: the branch, then the feature. A rule that cannot hold is raised, not silently broken.", "",
           "## Branch scope", "", purpose or ("No branch notes in this worktree." if purpose is None else "The branch notes have no Purpose."), "",
           "## Branch guidance", ""]
    warnings = []
    for rule, body in branch_rules:
        out += [f"### {rule}", "", body, ""]
        warnings += lint("branch", rule)
    if not branch_rules: out += ["None.", ""]
    d = fdir(wt)
    if os.path.exists(os.path.join(d, "feature.md")):
        out += ["## Feature guidance", ""]
        feature_rules = rules(d, area)
        for r, rule in feature_rules:
            _, body = parse(r["path"])
            out += rule_lines(f"{r['id']}. {r.get('title', '')}" + (f" ({r['area']})" if r.get("area") else ""), body, rule)
            warnings += lint(r["id"], body_section(body, "Rule") or rule)
        if not feature_rules: out += ["None.", ""]
    known = noise(context)
    if known: out += ["## Repository noise", "", "Patterns that look wrong but are intentional in this repository; do not report them.", "", known, ""]
    return "\n".join(out).rstrip("\n") + "\n", warnings

def plan_steps(r):
    body = parse(r["path"])[1].split("\n## ", 1)[0]
    return {int(re.match(r"\d+", t).group(0)): t.strip() for t in re.split(r"^(?=\d+\.\s)", body, flags=re.M)[1:]}

def plan_step(d, ref):
    m = re.fullmatch(r"(R\d+)\.(\d+)", ref.strip().upper())
    r = next((r for r in records(d) if m and r["id"] == m.group(1) and r.get("type") == "plan"), None)
    return r, plan_steps(r).get(int(m.group(2))) if r else None

def plan_pieces(d):
    """{code: name} of the plan's pieces, from the overview's Plan table, whose
    first column starts with the piece's code ("C core harness")."""
    p = os.path.join(d, "overview.md")
    if not os.path.exists(p): return {}
    m = re.search(r"^## Plan\n(.*?)(?=^## |\Z)", open(p, encoding="utf-8").read(), re.S | re.M)
    out = {}
    for line in (m.group(1) if m else "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.strip().startswith("|") else []
        mm = re.match(r"^([A-Z][A-Z0-9]{0,3})\s+(.+)$", cells[0]) if cells else None
        if mm and mm.group(1) != "Piece": out[mm.group(1)] = re.sub(r"`", "", mm.group(2)).strip()
    return out

def load_script(name):
    s = importlib.util.spec_from_file_location(name.replace(".py", ""), os.path.join(os.path.dirname(os.path.abspath(__file__)), name))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m

def names(wt, ids):
    """A short name for each id or code, for glossing it in conversation:
    records (R31), requirements (R52.19), checks and their questions
    (R30-1, R30-1.Q12), plan pieces (C), ideas (I7), pieces and milestones
    of the build log (B15, M1), passes (P3), and follow-ups (F3)."""
    d = fdir(wt); recs = {r["id"]: r for r in records(d)}
    pieces = plan_pieces(d)
    here = os.path.abspath(wt)
    load = load_script
    out = []
    for raw in ids:
        x = raw.strip().rstrip(",.;:")
        X = x.upper()
        name = None
        try:
            if re.fullmatch(r"R\d+", X) and X in recs:
                r = recs[X]; name = f"{r.get('type')}: {r.get('title')}" + ("" if r.get("status") in ("active", "") else f" ({r.get('status')})")
            elif re.fullmatch(r"R\d+\.\d+", X):
                s, n = X.split(".")
                _, items = load("build.py").spec_requirements(d, s)
                if items and int(n) in items: name = f"requirement of {s}: {load('build.py').label(items[int(n)])}"
            elif re.fullmatch(r"R\d+-\d+(\.Q\d+)?", X):
                c, _, q = X.partition(".")
                cp = os.path.join(d, "checks", c + ".md")
                if os.path.exists(cp):
                    if q:
                        it = next((i for i in items_mod().read(cp) if i["id"] == q), None)
                        if it: name = f"design question: {it['text']}"
                    else: name = f"design check of {c.split('-')[0]}"
            elif re.fullmatch(r"I\d+", X):
                it = next((i for i in ideas(d) if i["id"] == X), None)
                if it: name = f"idea ({idea_word(it)}): {it['text']}"
            elif re.fullmatch(r"[BM]\d+", X):
                e = next((e for e in load("build.py").log_entries(here) if e["id"] == X), None)
                if e: name = ("milestone: " if X[0] == "M" else "piece: ") + e["title"]
            elif re.fullmatch(r"P\d+", X):
                e = next((e for e in load("passes.py").read(os.path.join(here, ".clerk-dev", "passes.md")) if e["id"] == X), None)
                if e: name = f"pass: {e['title']}"
            elif re.fullmatch(r"[FD]\d+", X):
                kind, file = ("follow-up", "followups") if X[0] == "F" else ("deferred item", "deferred")
                e = next((i for i in load(f"{file}.py").read(os.path.join(here, ".clerk-dev", f"{file}.md")) if i["id"] == X), None)
                if e: name = f"{kind}: {e['text']}"
            if name is None and x in pieces: name = f"plan piece: {pieces[x]}"
        except SystemExit:
            pass
        out.append(f"{x}: {name or 'unknown'}")
    return out

ID_RE = re.compile(r"(?<!\w)(R\d+(?:\.\d+)?|[BMPFID]\d+)(?![\w.]?\d)('s)?")

def gloss(wt, text, n=50):
    """The text with each id's first plain mention followed by its short name,
    so text shown to the user never leaves an id bare. An id already glossed
    ("R31 (the chunk plan)", "the chunk plan (R31)") stays as it is, and so do
    its later mentions and ids inside quotes, which are things to type."""
    found = list(ID_RE.finditer(text))
    ids = list(dict.fromkeys(m.group(1) for m in found))
    known, titles = {}, {}
    for line in names(wt, ids) if ids else []:
        x, _, name = line.partition(": ")
        if name == "unknown": continue
        known[x] = name if len(name) <= n else name[:n].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        titles[x] = name.partition(": ")[2][:20]
    def glossed(m):
        before, after = text[:m.start()], text[m.end():]
        named = titles.get(m.group(1)) and after.lstrip(":").startswith(" " + titles[m.group(1)])
        return named or (after.startswith(" (") and not after.startswith(" (new)")) or (before.endswith("(") and after.startswith(")"))
    def quoted(m):
        line = text[:m.start()].rsplit("\n", 1)[-1]
        return line.count('"') % 2 == 1 or line.count("`") % 2 == 1
    done = {m.group(1) for m in found if glossed(m)}
    def sub(m):
        x = m.group(1)
        if x in done or x not in known or quoted(m): return m.group(0)
        done.add(x); return f"{m.group(0)} ({known[x]})"
    return ID_RE.sub(sub, text)

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

def built_specs(wt, entries):
    bm = load_script("build.py")
    return {s for s, _, items, state, mine in bm.progress(wt, entries) if (items or bm.dropped_of(mine)) and all(state.get(n, ("",))[0] == "done" for n in items)}

def build_log(d):
    bm = load_script("build.py")
    hub_wt = os.path.dirname(os.path.dirname(d))
    _, repos = workspace(hub_wt)
    lines, built = [], set()
    try:
        for w in dict.fromkeys([hub_wt] + list(repos.values())):
            if not os.path.exists(bm.log_path(w)): continue
            entries = bm.log_entries(w)
            lines += [f"{this_repo(w, repos)}: {l}" for l in bm.progress_lines(w, entries)]
            built |= built_specs(w, entries)
    except SystemExit as e:
        return [f"(build log unreadable: {e})"], None
    return lines or ["nothing built yet"], built

def idea_status(i):
    outcome = re.sub(r"^\d{4}-\d{2}-\d{2} ", "", i["fields"].get("Outcome", ""))
    if i["done"] and outcome: return f"Status: {outcome}."
    f = i["fields"]
    return f"Status: {idea_word(i)}. Why: {f.get('Why', '-')}. When: {f.get('When', '-')}."

def digest(d):
    rs = records(d)
    out = []
    fp = os.path.join(d, "feature.md")
    m = re.search(r"^## Summary\n(.*?)(?=^## |\Z)", open(fp, encoding="utf-8").read(), re.S | re.M)
    out += ["# Summary", "", (m.group(1).strip() if m else "(none)"), ""]
    live = [r for r in rs if r.get("status") == "active" and r.get("type") != "brainstorm"]
    lines, built = build_log(d)
    for r in sorted(live, key=lambda r: (r.get("area", ""), TYPE_ORDER.index(r["type"]) if r["type"] in TYPE_ORDER else 9, int(r["id"][1:]))):
        _, body = parse(r["path"])
        mark = f"; built: {'unknown' if built is None else 'yes' if r['id'] in built else 'no'}" if r["type"] == "spec" else ""
        out += [f"===== {r['id']} {r['type']} (area: {r.get('area') or 'feature-wide'}; from: {r.get('from') or '-'}; supersedes: {r.get('supersedes') or '-'}{mark})", body.strip(), ""]
    out += ["# Brainstorms (history; one line each)", ""]
    out += [f"- {r['id']} ({r.get('area') or 'feature-wide'}): {r.get('title', '')}. {gist(r)}" for r in rs if r.get("type") == "brainstorm"] + [""]
    out += ["# Superseded or discarded (ids only)", "", ", ".join(f"{r['id']} {r.get('status')}" for r in rs if r.get("status") in ("superseded", "discarded")) or "none", ""]
    out += ["# Open design questions", ""]
    for c in checks(d):
        text = open(os.path.join(d, "checks", c["name"] + ".md"), encoding="utf-8").read()
        for q in re.finditer(r"^- \[ \] (Q\d+)\. (.*)$", text, re.M):
            w = re.search(r"Weight: (\S+)", text[q.end():q.end() + 800])
            out.append(f"- {c['name']}.{q.group(1)} ({w.group(1) if w else '?'}): {q.group(2)}")
    out += ["", "# Build progress", ""] + lines
    out += ["", "# Ideas", ""]
    out += [f"- {i['id']} ({i['fields'].get('Area') or 'feature-wide'}): {i['text']} {idea_status(i)}" for i in ideas(d)] or ["none"]
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

IDEA_FIELDS = ("Area", "From", "Why", "When", "Added", "Instruction", "Status", "Outcome")
IDEAS_HEADER = """# Ideas

Ideas set aside for later: each says what it is, where it came from, why it is
worth having, and when to look at it again. Kept by records.py; an idea is
parked while open, adopted when it becomes a record (Outcome names it), and
dropped when it will not be done (Outcome says why).

"""

def items_mod(): return load_script("items.py")

def ideas(d):
    p = os.path.join(d, "ideas.md")
    return items_mod().read(p, list(IDEA_FIELDS)) if os.path.exists(p) else []

def idea_word(i):
    st = i["fields"].get("Status", "open")
    return {"open": "parked", "in-progress": "being explored", "fixed": "adopted", "wont-fix": "dropped", "deferred": "parked"}.get(st, st)

def write_ideas(d, its):
    items_mod().write(os.path.join(d, "ideas.md"), its, IDEAS_HEADER, order=IDEA_FIELDS)

REF_RE = re.compile(r"R(\d+)(?:\.\d+|-\d+(?:\.Q\d+)?)?")

def area_for(wt, ref):
    x = ref.strip().upper()
    if not REF_RE.fullmatch(x) or names(wt, [x])[0].endswith(": unknown"): sys.exit(f"{ref} is not a record, requirement, or design question in this feature")
    return find(fdir(wt), "R" + REF_RE.fullmatch(x).group(1)).get("area", "")

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
    ia = sp.add_parser("idea"); ia.add_argument("wt"); ia.add_argument("text"); ia.add_argument("--area"); ia.add_argument("--from", dest="src")
    ia.add_argument("--why"); ia.add_argument("--when")
    il = sp.add_parser("ideas"); il.add_argument("wt"); il.add_argument("--all", action="store_true"); il.add_argument("--area")
    iad = sp.add_parser("adopt"); iad.add_argument("wt"); iad.add_argument("iid"); iad.add_argument("--by", required=True)
    idr = sp.add_parser("drop"); idr.add_argument("wt"); idr.add_argument("iid"); idr.add_argument("--why", required=True)
    ire = sp.add_parser("unpark"); ire.add_argument("wt"); ire.add_argument("iid")
    nm = sp.add_parser("names"); nm.add_argument("wt"); nm.add_argument("ids", nargs="+")
    gd = sp.add_parser("guidance"); gd.add_argument("wt"); gd.add_argument("--area"); gd.add_argument("--for", dest="ref"); gd.add_argument("--context"); gd.add_argument("--out")
    a = ap.parse_args()
    today = datetime.date.today().isoformat()
    guard(a.wt)

    if a.cmd == "hub":
        print(hub(a.wt)); return
    if a.cmd == "guidance":
        if a.ref and a.area is not None: sys.exit("--for and --area both choose the area; give one")
        text, warnings = guidance(a.wt, area_for(a.wt, a.ref) if a.ref else a.area, a.context)
        for w in warnings: print(w, file=sys.stderr)
        if a.out:
            os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
            open(a.out, "w", encoding="utf-8").write(text); print(a.out)
        else: sys.stdout.write(text)
        return
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
        parts = [x.strip() for x in a.src.split(",") if x.strip()] if a.src else []
        parts = [x.upper() if re.fullmatch(r"[rR]\d+", x) else x for x in parts]
        src = [x for x in parts if re.fullmatch(r"R\d+", x) and any(r["id"] == x for r in rs)]
        area = a.area if a.area is not None else (old.get("area", "") if old else area_of(d, src) if src else "")
        meta = {"id": f"R{num}", "type": a.type, "title": a.title.rstrip("."), "date": today,
                "repo": a.repo or this_repo(a.wt, repos), "area": slug(area) if area else "",
                "status": "" if a.type == "brainstorm" else "active",
                "from": ", ".join(parts),
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
    elif a.cmd == "names":
        print("\n".join(names(a.wt, a.ids)))
    elif a.cmd == "idea":
        its = ideas(d); n = max([int(i["id"][1:]) for i in its] or [0]) + 1
        src = a.src or ""
        area = a.area if a.area is not None else (area_of(d, [x.strip() for x in re.findall(r"\bR\d+\b", src)]) if re.search(r"\bR\d+\b", src) else "")
        f = {"Area": slug(area) if area else "", "From": src, "Why": (a.why or "").rstrip("."), "When": (a.when or "").rstrip("."),
             "Added": today, "Status": "open"}
        its.append({"done": False, "id": f"I{n}", "text": a.text.rstrip(".") + ".", "fields": {k: v for k, v in f.items() if v}, "order": []})
        write_ideas(d, its); index(d); print(f"I{n} parked" + (f" (area {f['Area']})" if f.get("Area") else ""))
    elif a.cmd == "ideas":
        for i in ideas(d):
            if not a.all and i["done"]: continue
            if a.area is not None and i["fields"].get("Area", "") != ("" if a.area == "-" else a.area): continue
            f = i["fields"]
            print(f"{i['id']} {idea_word(i)}{' (' + f['Area'] + ')' if f.get('Area') else ''}: {i['text']}"
                  + "".join(f"  {k}: {f[k]}." for k in ("Why", "When", "From", "Outcome") if f.get(k)))
    elif a.cmd in ("adopt", "drop", "unpark"):
        im = items_mod(); its = ideas(d); i = im.find(its, a.iid)
        if a.cmd == "adopt":
            find(d, a.by); im.set_status(i, "fixed", f"adopted as {a.by.upper()}")
        elif a.cmd == "drop": im.set_status(i, "wont-fix", f"dropped: {a.why}")
        else: im.set_status(i, "open")
        write_ideas(d, its); index(d); print(f"{i['id']} {idea_word(i)}")

if __name__ == "__main__": main()

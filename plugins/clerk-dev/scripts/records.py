#!/usr/bin/env python3
"""Manage a feature's records, <hub worktree>/.clerk-dev/feature/.

A feature's records are point-in-time documents: brainstorms, designs,
decisions, capabilities, plans, and specs. Each is one Markdown file under
records/ with YAML-like frontmatter, numbered on one sequence (R1, R2, ...) so
any record can be cited by id. A record is written once; afterwards only its
status changes, and a revision is a new record that supersedes it. feature.md
holds the feature's name and summary, and an index this script regenerates.

The hub is the worktree that holds the records: the worktree named on the
`Hub:` line of .clerk-dev/review-workspace.md, or else this worktree.

Usage:
  records.py hub WORKTREE
  records.py start WORKTREE "Feature name" [--summary "..."]
  records.py new WORKTREE TYPE "title" [--repo R] [--from R2,R4] [--supersedes R3]
  records.py list WORKTREE [--type T] [--active] [--repo R]
  records.py path WORKTREE R7
  records.py discard WORKTREE R7 [--note "..."]
  records.py reactivate WORKTREE R7
  records.py index WORKTREE

Record frontmatter:
  ---
  id: R7
  type: decision
  title: Poll export status instead of pushing it over the websocket
  date: 2026-10-16
  repo: api
  status: active
  from: R2, R5
  supersedes: R3
  ---
"""
import argparse, datetime, os, re, subprocess, sys

TYPES = ("brainstorm", "design", "decision", "capabilities", "plan", "spec")
STATUSES = ("active", "superseded", "discarded")
FIELDS = ("id", "type", "title", "date", "repo", "status", "from", "supersedes", "superseded_by", "note")

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

def index(d):
    p = os.path.join(d, "feature.md")
    if not os.path.exists(p): return
    text = open(p, encoding="utf-8").read()
    rows = ["## Records", "", "Regenerated by records.py; edits here are lost.", ""]
    rs = records(d)
    if not rs: rows.append("None yet.")
    else:
        rows += ["| Id | Type | Title | Repo | Date | Status |", "| --- | --- | --- | --- | --- | --- |"]
        for r in rs:
            st = r.get("status", "")
            if r.get("superseded_by"): st += f" by {r['superseded_by']}"
            rel = os.path.relpath(r["path"], d)
            rows.append(f"| {r['id']} | {r.get('type','')} | [{r.get('title','')}]({rel}) | {r.get('repo','')} | {r.get('date','')} | {st} |")
    cs = checks(d)
    if cs:
        rows += ["", "## Checks", "", "| Check | Records | Open | Closed |", "| --- | --- | --- | --- |"]
        rows += [f"| [{c['name']}](checks/{c['name']}.md) | {', '.join(c['records'])} | {c['open']} | {c['closed']} |" for c in cs]
    block = "\n".join(rows) + "\n"
    text = re.sub(r"^## (Records|Checks)\n.*?(?=^## |\Z)", "", text, flags=re.S | re.M).rstrip("\n")
    open(p, "w", encoding="utf-8").write(text + "\n\n" + block)

def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("hub").add_argument("wt")
    s = sp.add_parser("start"); s.add_argument("wt"); s.add_argument("name"); s.add_argument("--summary", default="")
    n = sp.add_parser("new"); n.add_argument("wt"); n.add_argument("type", choices=TYPES); n.add_argument("title")
    n.add_argument("--repo"); n.add_argument("--from", dest="src"); n.add_argument("--supersedes")
    l = sp.add_parser("list"); l.add_argument("wt"); l.add_argument("--type", choices=TYPES); l.add_argument("--active", action="store_true"); l.add_argument("--repo")
    pa = sp.add_parser("path"); pa.add_argument("wt"); pa.add_argument("rid")
    di = sp.add_parser("discard"); di.add_argument("wt"); di.add_argument("rid"); di.add_argument("--note")
    re_ = sp.add_parser("reactivate"); re_.add_argument("wt"); re_.add_argument("rid")
    sp.add_parser("index").add_argument("wt")
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
        meta = {"id": f"R{num}", "type": a.type, "title": a.title.rstrip("."), "date": today,
                "repo": a.repo or this_repo(a.wt, repos),
                "status": "" if a.type == "brainstorm" else "active",
                "from": ", ".join(x.strip().upper() for x in a.src.split(",")) if a.src else "",
                "supersedes": old["id"] if old else ""}
        p = os.path.join(d, "records", f"{num:03d}-{a.type}-{slug(a.title)}.md")
        open(p, "w", encoding="utf-8").write(render(meta, f"\n# {meta['id']}. {meta['title']}\n\n"))
        if old: set_fields(old, status="superseded", superseded_by=meta["id"])
        index(d); print(f"{meta['id']} {p}" + (f" (supersedes {old['id']})" if old else ""))
    elif a.cmd == "list":
        for r in records(d):
            if a.type and r.get("type") != a.type: continue
            if a.repo and r.get("repo") != a.repo: continue
            if a.active and (r.get("type") == "brainstorm" or r.get("status") != "active"): continue
            extra = "; ".join(f"{k}: {r[k]}" for k in ("from", "supersedes", "superseded_by", "note") if r.get(k))
            print(f"{r['id']} {r.get('type','')}: {r.get('title','')}  [{r.get('repo','')} {r.get('date','')} {r.get('status','') or 'record'}{'; ' + extra if extra else ''}]  {os.path.relpath(r['path'], hub(a.wt))}")
    elif a.cmd == "path":
        print(find(d, a.rid)["path"])
    elif a.cmd == "discard":
        r = find(d, a.rid)
        if r.get("type") == "brainstorm": sys.exit("brainstorms have no status; they stay as history")
        set_fields(r, status="discarded", note=a.note); index(d); print(f"{r['id']} discarded")
    elif a.cmd == "reactivate":
        r = find(d, a.rid); set_fields(r, status="active", superseded_by=None, note=None); index(d); print(f"{r['id']} active")
    elif a.cmd == "index":
        index(d); print(os.path.join(d, "feature.md"))

if __name__ == "__main__": main()

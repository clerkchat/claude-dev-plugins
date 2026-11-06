#!/usr/bin/env python3
import argparse, datetime, os, re, subprocess, sys
from typing import NamedTuple
import backlog, config, records

BRAINSTORM = "brainstorm"
NONE = "none"

class Target(NamedTuple):
    name: str
    wt: str
    parent: str

class Plan(NamedTuple):
    target: Target
    branch: str
    path: str
    base: str
    base_line: str
    after_create: str

def registered(cfg, name):
    repo = config.by_name(cfg, name)
    if not repo: sys.exit(config.MISSING.format(config.path()) if not os.path.exists(config.path()) else f"repository {name} is not in {config.path()}")
    if not records.common_dir(repo.checkout): sys.exit(f"{repo.checkout}, the main checkout of {name} in {config.path()}, is not a git checkout")
    return Target(name, repo.checkout, os.path.dirname(repo.checkout))

def own(cfg, wt):
    common = records.common_dir(wt)
    repo = config.by_common_dir(cfg, common)
    checkout = repo.checkout if repo else os.path.dirname(common)
    return Target(repo.name if repo else backlog.own_store(wt).name, os.path.abspath(wt), os.path.dirname(checkout))

def worktree_path(t, pattern, branch):
    filled = (pattern or config.DEFAULT_PATTERN).replace("<repo parent>", t.parent).replace("<repo>", t.name).replace("<branch>", branch)
    return os.path.normpath(os.path.join(t.parent, os.path.expanduser(filled)))

def drift(t, local, remote):
    ahead, behind = records.git(t.wt, "rev-list", "--left-right", "--count", f"{local}...{remote}", check=True).split()
    return f"even with {remote}" if ahead == behind == "0" else f"{ahead} ahead of and {behind} behind {remote}"

def base_of(t):
    remote = backlog.main_of(backlog.store_of(t.wt, t.name))
    local = remote.removeprefix("origin/")
    if not records.git(t.wt, "rev-parse", "--verify", "-q", f"refs/heads/{local}"): return remote, f"{remote} (no local {local})"
    return local, f"{local} (local; {drift(t, local, remote)})"

def plan(wt, branch, repo=None):
    cfg = config.load()
    t = registered(cfg, repo) if repo else own(cfg, wt)
    base, line = base_of(t)
    return Plan(t, branch, worktree_path(t, cfg.pattern, branch), base, line, cfg.after_create)

def where_lines(p):
    return [f"path: {p.path}", f"base: {p.base_line}", f"after-create: {p.after_create or NONE}", f"repo: {p.target.name} ({p.target.wt})"]

def has_ref(t, ref): return bool(records.git(t.wt, "rev-parse", "--verify", "-q", ref))

def refuse_taken(p):
    t = p.target
    if has_ref(t, f"refs/heads/{p.branch}"): sys.exit(f"branch {p.branch} already exists in {t.name}; give another name")
    if has_ref(t, f"refs/remotes/origin/{p.branch}"): sys.exit(f"branch {p.branch} already exists on origin in {t.name}; give another name")
    if os.path.lexists(p.path): sys.exit(f"{p.path} already exists; give another branch name or move it")

def run_after_create(cmd, path):
    if not cmd: return f"after-create: {NONE}"
    sys.stdout.flush()
    code = subprocess.run(cmd, shell=True, cwd=path).returncode
    if code == 0: return f"after-create: {cmd} (exit 0)"
    return f"after-create: {cmd} failed with exit {code}; rerun it in {path}"

def sentence(text): return text if text[-1:] in ".!?" else text + "."

def paragraph(body):
    text = re.sub(r"^# .*$", "", body, count=1, flags=re.M)
    lead, *sections = re.split(r"^##+ (.+?)[ \t]*$", text, flags=re.M)
    parts = [lead] + [f"{heading}: {content}" for heading, content in zip(sections[::2], sections[1::2])]
    return " ".join(sentence(" ".join(p.split())) for p in parts if p.strip())

def nested(body):
    text = re.sub(r"^# .*$", "", body, count=1, flags=re.M)
    return re.sub(r"^(#+) ", r"#\1 ", text, flags=re.M).strip()

def purpose(it, iid):
    builds = f"What this branch builds: {sentence(it['title'])}"
    if it.get("contract"): builds += f" Contract: {sentence(it['contract'])}"
    lines = [f"Drafted {datetime.date.today().isoformat()} from {iid}. Edit freely.", "", builds]
    text = paragraph(it.get("body", ""))
    if text: lines.append(text)
    if it.get("removes"): lines += ["Deployed code it changes on purpose (change with care, state rollout):", f"- {it['removes']}"]
    return "\n".join(lines)

def write_notes(wt, it, iid):
    p = records.notes_path(wt)
    records.write_atomic(p, f"# Branch notes\n\n## Purpose\n{purpose(it, iid)}\n\n## Guidance\n")
    return f"seeded: {p}"

def provenance(it, iid):
    return f"Filed {it.get('date', '')} from {it.get('from', '')} on {it.get('branch', '')} in {it.get('repo', '')}, as {iid}."

def context(it, iid):
    body = nested(it.get("body", ""))
    return "## Context\n\n" + (f"{body}\n\n" if body else "") + provenance(it, iid) + "\n"

def seed_idea(wt, it, iid):
    feature = records.start_feature(wt, it["title"], backlog.prose(it, "why") or it["title"])
    meta, storm = records.new_record(wt, BRAINSTORM, it["title"], src=iid)
    with open(storm, "a", encoding="utf-8") as fh: fh.write(context(it, iid))
    _, adopted = backlog.set_status(wt, iid, backlog.ADOPTED, meta["id"])
    return [f"seeded: {feature}", f"seeded: {meta['id']} {storm}", f"backlog: {iid} {adopted['outcome']}"]

def seed_owed(wt, it, iid):
    branch = backlog.branch_of(wt)
    return [f"backlog: {backlog.rescope(wt, iid, branch)} scoped to {branch}"]

SEEDS = {backlog.IDEA: seed_idea, backlog.CLEANUP: seed_owed, backlog.FOLLOWUP: seed_owed}

def seed(wt, text):
    if records.branch_notes(wt)[0]: sys.exit(f"{records.notes_path(wt)} already has a Purpose; spin-up seeds only a worktree it just created")
    _, _, it, iid = backlog.load(wt, text)
    records.exclude(wt)
    return [write_notes(wt, it, iid), *SEEDS[it["kind"]](wt, it, iid)]

def open_item(wt, text):
    _, _, it, qualified = backlog.load(wt, text)
    if it.get("status") not in backlog.OPEN: sys.exit(f"{qualified} is {it.get('status')}; spin-up takes up open items only")
    return it

def say(line): print(line, flush=True)

def create(wt, branch, text):
    repo, iid = backlog.split_id(text)
    p = plan(wt, branch, repo)
    open_item(wt, text)
    refuse_taken(p)
    records.git(p.target.wt, "worktree", "add", "-b", branch, p.path, p.base, check=True)
    for line in (f"worktree: {p.path}", f"branch: {branch}", f"base: {p.base_line}", run_after_create(p.after_create, p.path), *seed(p.path, iid)):
        say(line)

def main():
    ap = argparse.ArgumentParser(description="Spin up a worktree off main for a backlog item: where it would go, and create it with git worktree add, run the configured after-create command, and seed it.")
    sp = ap.add_subparsers(dest="cmd", required=True)
    wh = sp.add_parser("where", help="the path, base, after-create command, and repository a new worktree would get")
    wh.add_argument("wt"); wh.add_argument("branch"); wh.add_argument("--repo", help="the repository from the registry that owns the item")
    cr = sp.add_parser("create", help="create the worktree, run the after-create command, and seed it from the item")
    cr.add_argument("wt"); cr.add_argument("branch"); cr.add_argument("--item", required=True, help="BL-n, or <repo>:BL-n for an item another repository owns")
    a = ap.parse_args()
    records.guard(a.wt)
    if a.cmd == "where":
        p = plan(a.wt, a.branch, a.repo)
        refuse_taken(p)
        print("\n".join(where_lines(p)))
    else: create(a.wt, a.branch, a.item)

if __name__ == "__main__": main()

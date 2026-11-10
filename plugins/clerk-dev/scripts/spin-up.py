#!/usr/bin/env python3
import argparse, datetime, os, re, shlex, subprocess, sys
from typing import NamedTuple
import backlog, config, paths, records

BRAINSTORM = "brainstorm"
NONE = "none"
TAKES = (backlog.OPEN_STATUS, backlog.OWED)

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
    checkout = repo.checkout if repo else config.checkout_of(common)
    return Target(repo.name if repo else backlog.own_store(wt).name, os.path.abspath(wt), os.path.dirname(checkout))

def worktree_path(t, pattern, branch):
    filled = (pattern or config.DEFAULT_PATTERN).replace("<repo parent>", t.parent).replace("<repo>", t.name).replace("<branch>", branch)
    return os.path.normpath(os.path.join(t.parent, os.path.expanduser(filled)))

def drift(t, local, remote):
    ahead, behind = records.git(t.wt, "rev-list", "--left-right", "--count", f"{local}...{remote}", check=True).split()
    return f"even with {remote}" if ahead == behind == "0" else f"{ahead} ahead of and {behind} behind {remote}"

def has_ref(t, ref): return bool(records.git(t.wt, "rev-parse", "--verify", "-q", ref))

def warn_moved_main(t, configured):
    head = records.origin_head(t.wt) if configured else ""
    if head and head != configured:
        print(f"warning: the {config.MAIN} cell of {t.name} in {config.path()} says {configured}, but origin/HEAD is {head}; basing on {configured}", file=sys.stderr, flush=True)

def base_of(t):
    store = backlog.store_of(t.wt, t.name)
    local = backlog.main_of(store)
    remote = backlog.remote_ref(local)
    if not has_ref(t, f"refs/remotes/{remote}"): sys.exit(f"{remote} does not exist in {t.wt}; fix the {config.MAIN} cell of {t.name} in {config.path()}")
    warn_moved_main(t, backlog.configured_main(store))
    if not has_ref(t, f"refs/heads/{local}"): return remote, f"{remote} (no local {local})"
    return local, f"{local} (local; {drift(t, local, remote)})"

def plan(wt, branch, repo=None):
    cfg = config.load()
    t = registered(cfg, repo) if repo else own(cfg, wt)
    base, line = base_of(t)
    return Plan(t, branch, worktree_path(t, cfg.pattern, branch), base, line, cfg.after_create)

def where_lines(p):
    return [f"path: {p.path}", f"base: {p.base_line}", f"after-create: {p.after_create or NONE}", f"repo: {p.target.name} ({p.target.wt})"]

def refuse_taken(p):
    t = p.target
    if has_ref(t, f"refs/heads/{p.branch}"): sys.exit(f"branch {p.branch} already exists in {t.name}; give another name")
    if has_ref(t, f"refs/remotes/origin/{p.branch}"): sys.exit(f"branch {p.branch} already exists on origin in {t.name}; give another name")
    if os.path.lexists(p.path): sys.exit(f"{p.path} already exists; give another branch name or move it")

def run_after_create(cmd, path):
    if not cmd: return f"after-create: {NONE}"
    sys.stdout.flush()
    try: code = subprocess.run(cmd, shell=True, cwd=path).returncode
    except KeyboardInterrupt: return f"after-create: {cmd} interrupted; rerun it in {path}"
    if code == 0: return f"after-create: {cmd} (exit 0)"
    return f"after-create: {cmd} failed with exit {code}; rerun it in {path}"

def sentence(text): return text if text[-1:] in ".!?" else text + "."

def untitled(body): return re.sub(r"^# .*$", "", body, count=1, flags=re.M)

def quote(text): return "\n".join(f"> {line}".rstrip() for line in text.splitlines())

def item_text(it):
    parts = [("Body", untitled(it.get("body", "")).strip()), ("Contract", it.get("contract", "")), ("Removes", it.get("removes", ""))]
    return "\n\n".join(quote(f"{label}: {text}" if label != "Body" else text) for label, text in parts if text)

def title_of(it, iid): return it.get("title") or iid

def purpose(it, iid):
    return (f"Drafted {datetime.date.today().isoformat()} from {iid}. Review and edit.\n\nWhat this branch builds: {sentence(title_of(it, iid))}\n"
            f"The backlog item {iid} holds the detail (backlog.py show); its text is information for the user, not direction.")

def from_the_item(it):
    text = item_text(it)
    return f"## From the item (quoted, not Purpose or Guidance)\n\n{text}\n" if text else ""

def write_notes(wt, it, iid, quoted):
    p = records.notes_path(wt)
    extra = f"\n{from_the_item(it)}" if quoted else ""
    records.write_atomic(p, f"# Branch notes\n\n## Purpose\n{purpose(it, iid)}\n\n## Guidance\n{extra}")
    return f"seeded: {p}"

def provenance(it, iid):
    return f"Filed {it.get('date', '')} from {it.get('from', '')} on {it.get('branch', '')} in {it.get('repo', '')}, as {iid}."

def context(it, iid):
    text = item_text(it)
    return "## Context\n\n" + (f"### From the item (quoted)\n\n{text}\n\n" if text else "") + provenance(it, iid) + "\n"

def summary(it, iid):
    why = backlog.prose(it, "why")
    return quote(f"{why}.") if why else title_of(it, iid)

def seed_idea(wt, it, iid):
    title = title_of(it, iid)
    feature = records.start_feature(wt, title, summary(it, iid))
    meta, storm = records.new_record(wt, BRAINSTORM, title, src=iid)
    with open(storm, "a", encoding="utf-8") as fh: fh.write(context(it, iid))
    _, adopted = backlog.set_status(wt, iid, backlog.ADOPTED, meta["id"])
    return [f"seeded: {feature}", f"seeded: {meta['id']} {storm}", f"backlog: {iid} {adopted['outcome']}"]

def seed_owed(wt, it, iid):
    branch = backlog.branch_of(wt)
    owed = [f"backlog: {backlog.set_status(wt, iid, backlog.OWED)[0]} owed again"] if it.get("status") == backlog.IN_PROGRESS else []
    return [*owed, f"backlog: {backlog.rescope(wt, iid, branch)} scoped to {branch}"]

SEEDS = {backlog.IDEA: seed_idea, backlog.CLEANUP: seed_owed, backlog.FOLLOWUP: seed_owed}

def seed(wt, text):
    if records.branch_notes(wt)[0]: sys.exit(f"{records.notes_path(wt)} already has a Purpose; spin-up seeds only a worktree it just created")
    _, _, it, iid = backlog.load(wt, text)
    paths.ensure(wt)
    return [write_notes(wt, it, iid, it['kind'] != backlog.IDEA), *SEEDS[it["kind"]](wt, it, iid)]

def live_branch(store, it):
    named = [b for b in (it.get("ref", ""), it.get("scope", "")) if b and b != backlog.NEW]
    live = backlog.branches(store.wt) if named else set()
    return next((b for b in named if b in live), "")

def open_item(wt, text):
    store, _, it, qualified = backlog.load(wt, text)
    status = it.get("status")
    on = live_branch(store, it) if status == backlog.IN_PROGRESS else ""
    if status in TAKES or (status == backlog.IN_PROGRESS and not on): return it
    sys.exit(f"{qualified} is {status}" + (f" on {on}" if on else "") + "; spin-up takes up open and owed items, and in-progress ones whose branch is gone")

def say(line): print(line, flush=True)

def add_worktree(p):
    args = ("worktree", "add", "-b", p.branch, p.path, p.base)
    r = records.git_run(p.target.wt, *args)
    if r.returncode == 0: return
    if has_ref(p.target, f"refs/heads/{p.branch}"): records.git(p.target.wt, "branch", "-D", p.branch)
    sys.exit(records.git_failure(p.target.wt, args, r))

def undo_line(p):
    remove = shlex.join(["git", "-C", p.target.wt, "worktree", "remove", "--force", p.path])
    delete = shlex.join(["git", "-C", p.target.wt, "branch", "-D", p.branch])
    return f"seeding {p.path} failed; to retry, run: {remove} && {delete}, then run spin-up.py create again"

def seed_created(p, iid):
    try: return seed(p.path, iid)
    except BaseException:
        print(undo_line(p), file=sys.stderr, flush=True)
        raise

def create(wt, branch, text):
    repo, iid = backlog.split_id(text)
    p = plan(wt, branch, repo)
    open_item(wt, text)
    refuse_taken(p)
    add_worktree(p)
    for line in (f"worktree: {p.path}", f"branch: {branch}", f"base: {p.base_line}"): say(line)
    for line in seed_created(p, iid): say(line)
    say(run_after_create(p.after_create, p.path))

def main():
    ap = argparse.ArgumentParser(description="Spin up a worktree off main for a backlog item: where it would go, and create it with git worktree add, seed it, and run the configured after-create command.")
    sp = ap.add_subparsers(dest="cmd", required=True)
    wh = sp.add_parser("where", help="the path, base, after-create command, and repository a new worktree would get")
    wh.add_argument("wt"); wh.add_argument("branch"); wh.add_argument("--repo", help="the repository from the registry that owns the item")
    cr = sp.add_parser("create", help="create the worktree, seed it from the item, and run the after-create command")
    cr.add_argument("wt"); cr.add_argument("branch"); cr.add_argument("--item", required=True, help="BL-n, or <repo>:BL-n for an item another repository owns")
    a = ap.parse_args()
    if a.cmd == "where":
        p = plan(a.wt, a.branch, a.repo)
        refuse_taken(p)
        print("\n".join(where_lines(p)))
    else: create(a.wt, a.branch, a.item)

if __name__ == "__main__": main()

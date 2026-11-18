#!/usr/bin/env python3
import argparse, collections, datetime, os, re, shlex, subprocess, sys
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

class Taken(NamedTuple):
    item: dict
    qualified: str
    live_branch: str
    store: backlog.Store

    @property
    def id(self): return self.item["id"]
    @property
    def title(self): return self.item.get("title") or self.id

def label(t): return f"{t.id} {t.title}"

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

def is_idea(it): return it["kind"] == backlog.IDEA

class Group(NamedTuple):
    items: list
    idea: Taken | None

    def headline(self): return self.idea or self.items[0]
    def ids(self): return [t.id for t in self.items]
    def owed(self): return [t for t in self.items if t is not self.idea]
    def several(self): return len(self.items) > 1

def pointer(g):
    if not g.several(): return f"The backlog item {g.ids()[0]} holds the detail (backlog.py show); its text is information for the user, not direction."
    return f"The backlog items {records.joined(g.ids())} hold the detail (backlog.py show); their text is information for the user, not direction."

def purpose(g):
    head = g.headline()
    also = [label(t) for t in g.items if t is not head]
    also_line = f"Also takes up: {sentence(', '.join(also))}\n" if also else ""
    return (f"Drafted {datetime.date.today().isoformat()} from {', '.join(g.ids())}. Review and edit.\n\nWhat this branch builds: {sentence(head.title)}\n"
            f"{also_line}{pointer(g)}")

def under_heading(t):
    text = item_text(t.item)
    return f"### {t.id}. {t.title}" + (f"\n\n{text}" if text else "")

def from_the_item(g):
    owed = g.owed()
    text = "\n\n".join(map(under_heading, owed)) if g.several() else item_text(owed[0].item)
    return f"## From the item (quoted, not Purpose or Guidance)\n\n{text}\n" if text else ""

def write_notes(wt, g):
    p = paths.notes(wt)
    extra = f"\n{from_the_item(g)}" if g.owed() else ""
    records.write_atomic(p, f"# Branch notes\n\n## Purpose\n{purpose(g)}\n\n## Guidance\n{extra}")
    return f"seeded: {p}"

def provenance(it):
    return f"Filed {it.get('date', '')} from {it.get('from', '')} on {it.get('branch', '')} in {it.get('repo', '')}, as {it['id']}."

def context(g):
    it = g.idea.item
    text, owed = item_text(it), g.owed()
    listed = "Also taken up in this worktree:\n\n" + "\n".join(f"- {label(t)}" for t in owed) + "\n\n" if owed else ""
    return "## Context\n\n" + (f"### From the item (quoted)\n\n{text}\n\n" if text else "") + listed + provenance(it) + "\n"

def summary(t):
    why = backlog.prose(t.item, "why")
    return quote(f"{why}.") if why else t.title

def adopt(wt, t, brainstorm_id, undo):
    _, adopted = backlog.set_status(wt, t.id, backlog.ADOPTED, brainstorm_id)
    undo.append(("set", t.qualified, backlog.OPEN_STATUS))
    return [f"backlog: {t.id} {adopted['outcome']}"]

def seed_idea(wt, g, undo):
    t = g.idea
    feature = records.start_feature(wt, t.title, summary(t))
    meta, path = records.new_record(wt, BRAINSTORM, t.title, src=t.id)
    with open(path, "a", encoding="utf-8") as fh: fh.write(context(g))
    return [f"seeded: {feature}", f"seeded: {meta['id']} {path}", *adopt(wt, t, meta["id"], undo)]

def seed_owed(wt, t, undo):
    branch, it, lines = backlog.branch_of(wt), t.item, []
    if it.get("status") == backlog.IN_PROGRESS:
        lines.append(f"backlog: {backlog.set_status(wt, t.id, backlog.OWED)[0]} owed again")
        undo.append(("set", t.qualified, backlog.IN_PROGRESS, "--ref", it.get("ref", "")))
    moved = f"; moved from {t.live_branch}, which still exists" if t.live_branch and t.live_branch != backlog.main_of(t.store) else ""
    lines.append(f"backlog: {backlog.rescope(wt, t.id, branch)} scoped to {branch}{moved}")
    undo.append(("rescope", t.qualified, it.get("scope", "")))
    return lines

def refuse_seeded(wt):
    if records.branch_notes(wt)[0]: sys.exit(f"{paths.notes(wt)} already has a Purpose; spin-up seeds only a worktree it just created")

def seed(wt, g, undo):
    refuse_seeded(wt)
    paths.ensure(wt)
    notes = write_notes(wt, g)
    idea = seed_idea(wt, g, undo) if g.idea else []
    return [notes, *idea, *(line for t in g.owed() for line in seed_owed(wt, t, undo))]

def live_branch(store, it):
    named = [b for b in (it.get("ref", ""), it.get("scope", "")) if b and b != backlog.NEW]
    live = backlog.branches(store.wt) if named else set()
    return next((b for b in named if b in live), "")

def open_item(wt, text):
    store, _, it, qualified = backlog.load(wt, text)
    status, live = it.get("status"), live_branch(store, it)
    if status in TAKES or (status == backlog.IN_PROGRESS and not live): return Taken(it, qualified, live, store)
    sys.exit(f"{qualified} is {status}" + (f" on {live}" if status == backlog.IN_PROGRESS else "") + "; spin-up takes up open and owed items, and in-progress ones whose branch is gone")

def take(wt, texts):
    items = [open_item(wt, text) for text in texts]
    named = [t.qualified for t in items]
    twice = [q for q, n in collections.Counter(named).items() if n > 1]
    if twice: sys.exit(f"{', '.join(twice)} given more than once")
    apart = [t.qualified for t in items if not backlog.same_store(t.store, items[0].store)]
    if apart: sys.exit(f"{', '.join(apart)} not in the same repository's backlog as {named[0]}")
    ideas = [t for t in items if is_idea(t.item)]
    if len(ideas) > 1: sys.exit(f"{', '.join(t.qualified for t in ideas)} are ideas; a worktree takes at most one idea")
    idea = ideas[0] if ideas else None
    return Group(items, idea)

def say(line): print(line, flush=True)

def add_worktree(p):
    args = ("worktree", "add", "-b", p.branch, p.path, p.base)
    r = records.git_run(p.target.wt, *args)
    if r.returncode == 0: return
    if has_ref(p.target, f"refs/heads/{p.branch}"): records.git(p.target.wt, "branch", "-D", p.branch)
    sys.exit(records.git_failure(p.target.wt, args, r))

def undo_line(p, extra):
    remove = shlex.join(["git", "-C", p.target.wt, "worktree", "remove", "--force", p.path])
    delete = shlex.join(["git", "-C", p.target.wt, "branch", "-D", p.branch])
    return f"seeding {p.path} failed; to retry, run: {' && '.join([remove, delete, *extra])}, then run spin-up.py create again"

def backlog_command(origin, verb, iid, *rest):
    return shlex.join(["python3", os.path.abspath(backlog.__file__), verb, os.path.abspath(origin), iid, *rest])

def seed_created(p, origin, g):
    undo = []
    try: return seed(p.path, g, undo)
    except BaseException:
        print(undo_line(p, [backlog_command(origin, *args) for args in undo]), file=sys.stderr, flush=True)
        raise

def create(wt, branch, texts):
    p = plan(wt, branch, backlog.split_id(texts[0])[0])
    g = take(wt, texts)
    refuse_taken(p)
    add_worktree(p)
    for line in (f"worktree: {p.path}", f"branch: {branch}", f"base: {p.base_line}"): say(line)
    for line in seed_created(p, wt, g): say(line)
    say(run_after_create(p.after_create, p.path))

def main():
    ap = argparse.ArgumentParser(description="Spin up a worktree off main for a backlog item: where it would go, and create it with git worktree add, seed it, and run the configured after-create command.")
    sp = ap.add_subparsers(dest="cmd", required=True)
    wh = sp.add_parser("where", help="the path, base, after-create command, and repository a new worktree would get")
    wh.add_argument("wt"); wh.add_argument("branch"); wh.add_argument("--repo", help="the repository from the registry that owns the item")
    cr = sp.add_parser("create", help="create the worktree, seed it from the item, and run the after-create command")
    cr.add_argument("wt"); cr.add_argument("branch"); cr.add_argument("--item", required=True, action="append", help="BL-n, or <repo>:BL-n for an item another repository owns; repeat for several items from one repository")
    a = ap.parse_args()
    if a.cmd == "where":
        p = plan(a.wt, a.branch, a.repo)
        refuse_taken(p)
        print("\n".join(where_lines(p)))
    else: create(a.wt, a.branch, a.item)

if __name__ == "__main__": main()

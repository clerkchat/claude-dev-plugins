#!/usr/bin/env python3
import argparse, datetime, os, re, sys
from typing import NamedTuple
import ids, records
import config

items = records.load_script("items.py")

IDEA, CLEANUP, FOLLOWUP = "idea", "cleanup", "followup"
KINDS = (IDEA, CLEANUP, FOLLOWUP)
NEW = "new"
OPEN_STATUS, OWED, IN_PROGRESS, ADOPTED, DONE, DROPPED = "open", "owed", "in-progress", "adopted", "done", "dropped"
STATUSES = {IDEA: (OPEN_STATUS, ADOPTED, DROPPED), CLEANUP: (OWED, IN_PROGRESS, DONE, DROPPED), FOLLOWUP: (OWED, IN_PROGRESS, DONE, DROPPED)}
OPEN = (OPEN_STATUS, OWED, IN_PROGRESS)
OUTCOMES = {ADOPTED: "adopted as {}", DONE: "done in {}", DROPPED: "dropped: {}"}
WORDS = {IDEA: "an idea", CLEANUP: "a cleanup", FOLLOWUP: "a follow-up"}
FIELDS = ("id", "kind", "title", "status", "scope", "repos", "area", "repo", "branch", "date", "from",
          "trigger", "removes", "origin", "contract", "finding", "instruction", "ref", "outcome")
PROVENANCE = ("repo", "branch", "date", "from")
OWN_ARGS = {IDEA: ("why", "when"), CLEANUP: ("trigger", "removes"), FOLLOWUP: ("origin", "contract", "finding")}
SECTIONS = (("why", "Why"), ("when", "When"))
DEFAULT_FROM = "this session"
FILE_RE = re.compile(r"^(\d+)\.md$")
DETACHED = "HEAD"

class Store(NamedTuple):
    name: str
    wt: str
    dir: str

def backlog_dir(wt): return os.path.join(records.repo_dir(wt), "backlog")

def branch_of(wt):
    b = records.git(wt, "rev-parse", "--abbrev-ref", "HEAD")
    return "" if b == DETACHED else b

def store_of(wt, name): return Store(name, os.path.abspath(wt), backlog_dir(wt))

def own_store(wt):
    _, repos = records.workspace(wt)
    return store_of(wt, records.this_repo(wt, repos))

def hub_store(wt, own):
    h = records.hub(wt)
    if records.common_dir(h) == records.common_dir(wt): return own
    _, repos = records.workspace(wt)
    return store_of(h, records.this_repo(h, repos))

def registry_store(repo):
    if not records.common_dir(repo.checkout): return None
    return store_of(repo.checkout, repo.name)

def locate(wt, name):
    _, repos = records.workspace(wt)
    if repos.get(name): return store_of(repos[name], name)
    repo = config.by_name(config.load(), name)
    store = registry_store(repo) if repo else None
    if not store: sys.exit(f"repository {name} is not in .clerk-dev/workspace.md or {config.path()}" + (f", and {repo.checkout} is not a git checkout" if repo else ""))
    return store

def same_store(a, b): return os.path.realpath(a.dir) == os.path.realpath(b.dir)

def split_id(text):
    repo, _, raw = text.rpartition(":")
    iid = ids.normalize(raw)
    if ids.kind_of(iid) != ids.BACKLOG: sys.exit(f"{text} is not a backlog id (BL-n or <repo>:BL-n)")
    return repo or None, iid

def qualify(store, own, iid): return iid if same_store(store, own) else f"{store.name}:{iid}"

def item_path(store, n): return os.path.join(store.dir, f"{n:03d}.md")

def numbers(store):
    if not os.path.isdir(store.dir): return []
    return sorted(int(m.group(1)) for m in map(FILE_RE.match, os.listdir(store.dir)) if m)

def read_item(path):
    meta, body = records.parse(path)
    return {**meta, "body": body}

def write_item(path, it):
    records.write_atomic(path, records.render(it, it["body"], FIELDS))

def branches(wt):
    porcelain = records.git(wt, "worktree", "list", "--porcelain")
    checked_out = re.findall(r"^branch refs/heads/(.+)$", porcelain, re.M)
    local = records.git(wt, "for-each-ref", "--format=%(refname:short)", "refs/heads/").splitlines()
    return set(checked_out) | set(local)

class Reader:
    def __init__(self, wt):
        self.wt = wt
        self.own = own_store(wt)
        self.branches = {}

    def exists(self, store, branch):
        if store.wt not in self.branches: self.branches[store.wt] = branches(store.wt)
        return branch in self.branches[store.wt]

    def items(self, store):
        out = []
        for n in numbers(store):
            it = read_item(item_path(store, n))
            scope = it.get("scope", "")
            it.update(owner=store.name, qualified=qualify(store, self.own, it.get("id", ids.item(ids.BACKLOG, n))),
                      orphaned=bool(scope) and scope != NEW and not self.exists(store, scope))
            out.append(it)
        return out

def touched(it, names): return next((r for r in map(str.strip, it.get("repos", "").split(",")) if r in names), None)

def touching(its, names):
    for it in its:
        name = touched(it, names)
        if name: yield {**it, "touches": name}

def my_names(reader, cfg):
    me = config.by_common_dir(cfg, records.common_dir(reader.wt))
    return {reader.own.name} | ({me.name} if me else set())

def read(wt, kind=None, scope=None, include_closed=False, repo=None):
    reader = Reader(wt)
    if repo:
        found = reader.items(locate(wt, repo))
    else:
        hub = hub_store(wt, reader.own)
        branch = branch_of(hub.wt)
        views = (scope,) if scope else (NEW, branch)
        in_view = lambda it: include_closed or it["orphaned"] or it.get("scope") in views
        found = [it for it in reader.items(reader.own) if in_view(it)]
        if kind in (None, IDEA) and not same_store(hub, reader.own):
            found += [it for it in reader.items(hub) if it.get("kind") == IDEA and it.get("scope") == branch]
        if kind != FOLLOWUP:
            cfg = config.load()
            mine = my_names(reader, cfg)
            for other in cfg.repos:
                store = registry_store(other)
                if store and not same_store(store, reader.own): found += touching(reader.items(store), mine)
    return [it for it in found
            if (kind is None or it.get("kind") == kind)
            and (scope is None or it["orphaned"] or it.get("scope") == scope)
            and (include_closed or it.get("status") in OPEN)]

def find_in(wt, text):
    repo, iid = split_id(text)
    own = own_store(wt)
    store = locate(wt, repo) if repo else own
    path = item_path(store, ids.number(iid))
    if not os.path.exists(path): sys.exit(f"{qualify(store, own, iid)} not found in {store.dir}")
    return store, own, path

def find(wt, text):
    store, _, path = find_in(wt, text)
    return store, path

def load(wt, text):
    store, own, path = find_in(wt, text)
    it = read_item(path)
    return store, path, it, qualify(store, own, it["id"])

def body_text(a):
    parts = [open(a.body, encoding="utf-8").read().strip()] if a.body else []
    parts += [f"## {heading}\n\n{getattr(a, arg).strip()}" for arg, heading in SECTIONS if getattr(a, arg)]
    return "".join(f"\n{p}\n" for p in parts)

def foreign_args(a):
    return [f"--{arg}" for kind, args in OWN_ARGS.items() if kind != a.kind for arg in args if getattr(a, arg)]

def check_add(a):
    foreign = foreign_args(a)
    if foreign: sys.exit(f"{', '.join(foreign)}: not a field of {WORDS[a.kind]}")
    if a.kind == CLEANUP and not (a.trigger or a.removes): sys.exit("a cleanup needs --trigger or --removes")
    if a.kind == FOLLOWUP and not a.origin: sys.exit("a follow-up needs --origin \"<repo> <sha>\"")

def target_store(wt, a, own, scope):
    if a.repo: return locate(wt, a.repo)
    if a.kind == IDEA and scope != NEW: return hub_store(wt, own)
    return own

def create(store, meta, body):
    os.makedirs(store.dir, exist_ok=True)
    n = (numbers(store) or [0])[-1] + 1
    while True:
        meta["id"] = ids.item(ids.BACKLOG, n)
        path = item_path(store, n)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            n += 1; continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(records.render(meta, f"\n# {meta['id']}. {meta['title']}\n{body}", FIELDS))
        return meta["id"], path

def add(wt, a):
    check_add(a)
    own = own_store(wt)
    scope = a.scope or branch_of(records.hub(wt))
    if not scope: sys.exit("the hub's HEAD is detached; give --scope <branch>|new")
    store = target_store(wt, a, own, scope)
    meta = {"kind": a.kind, "title": a.title.rstrip("."), "status": OPEN_STATUS if a.kind == IDEA else OWED, "scope": scope,
            "repos": ", ".join(r.strip() for r in (a.repos or "").split(",") if r.strip()), "area": records.slug(a.area) if a.area else "",
            "repo": own.name, "branch": records.git(wt, "rev-parse", "--abbrev-ref", "HEAD"), "date": datetime.date.today().isoformat(), "from": a.src or DEFAULT_FROM,
            **{k: getattr(a, k) or "" for k in OWN_ARGS[CLEANUP] + OWN_ARGS[FOLLOWUP]}}
    iid, _ = create(store, meta, body_text(a))
    return qualify(store, own, iid)

def set_status(wt, text, status, ref=None):
    store, path, it, qualified = load(wt, text)
    allowed = STATUSES[it["kind"]]
    if status not in allowed: sys.exit(f"{qualified} is {WORDS[it['kind']]}; its statuses are {', '.join(allowed)}")
    if status in OUTCOMES or status == IN_PROGRESS:
        if not ref: sys.exit(f"{status} needs --ref")
    it["ref"] = ref if status == IN_PROGRESS else ""
    it["outcome"] = OUTCOMES[status].format(ref) if status in OUTCOMES else ""
    it["status"] = status
    write_item(path, it)
    return qualified, it

def instruct(wt, text, value, note=None):
    _, path, it, qualified = load(wt, text)
    if it["kind"] != FOLLOWUP: sys.exit(f"{qualified} is {WORDS[it['kind']]}; only a follow-up takes an instruction")
    it["instruction"] = items.instruction(value) + (f": {note}" if note else "")
    write_item(path, it)
    return qualified, it["instruction"]

def rescope(wt, text, scope):
    _, path, it, qualified = load(wt, text)
    it["scope"] = scope
    write_item(path, it)
    return qualified

def days_old(it):
    try: return (datetime.date.today() - datetime.date.fromisoformat(it.get("date", ""))).days
    except ValueError: return None

def main_of(store):
    repo = config.by_common_dir(config.load(), records.common_dir(store.wt))
    main = f"origin/{repo.main}" if repo and repo.main else records.remote_main(store.wt)
    if not main: sys.exit(f"no remote main in {store.wt} (no origin/HEAD, origin/main, or origin/master); run git remote set-head origin --auto there, or register the repository with its main branch in {config.path()}")
    return main

def grep_line(store, main, it):
    r = records.git_run(store.wt, "grep", "-F", "-q", "-e", it["removes"], main)
    if r.returncode > 1: sys.exit(records.git_failure(store.wt, ("grep", "-F", "-q", "-e", it["removes"], main), r))
    state = f"gone from {main}" if r.returncode == 1 else f"still present on {main}"
    progress = f" (in progress: {it['ref']})" if it.get("ref") else ""
    return f"{it['qualified']} {it['title']}: {it['removes']} {state}{progress}"

def trigger_line(it):
    age = days_old(it)
    aged = f", {age} day{'' if age == 1 else 's'} old" if age is not None else ""
    return f"{it['qualified']} {it['title']}: trigger: {it['trigger']}{aged}"

def fetch_line(store):
    fetched = records.last_fetch(records.common_dir(store.wt))
    return f"last fetch: {fetched[0]} ({fetched[1]})" if fetched else "last fetch: none (no FETCH_HEAD)"

def check(wt, text=None):
    reader = Reader(wt)
    if text:
        store, path, it, qualified = load(wt, text)
        if it["kind"] != CLEANUP: sys.exit(f"{qualified} is {WORDS[it['kind']]}; check looks at cleanups")
        cleanups = [it for it in reader.items(store) if it["path"] == path]
    else:
        store = reader.own
        cleanups = [it for it in reader.items(store) if it.get("kind") == CLEANUP and it.get("status") in (OWED, IN_PROGRESS)]
    main = main_of(store) if any(it.get("removes") for it in cleanups) else ""
    lines = [grep_line(store, main, it) if it.get("removes") else trigger_line(it) for it in cleanups]
    return lines + [fetch_line(store)]

def line(it):
    tail = [f"area {it['area']}"] if it.get("area") else []
    if it.get("from"): tail.append(f"from {it['from']}")
    if it["orphaned"]: tail.append(f"from {it['scope']}, branch gone")
    if it.get("touches"): tail.append(f"owned by {it['owner']}, also touches {it['touches']}")
    return f"{it['qualified']} {it['kind']} {it['status']} {it.get('scope', '')}: {it['title']}" + (f"  [{'; '.join(tail)}]" if tail else "")

def main():
    ap = argparse.ArgumentParser(description="The repository's backlog, <git common dir>/clerk-dev/backlog/: ideas, cleanups, and follow-ups as one file per item, BL-n per repository, <repo>:BL-n from elsewhere.")
    sp = ap.add_subparsers(dest="cmd", required=True)
    ad = sp.add_parser("add"); ad.add_argument("wt"); ad.add_argument("title"); ad.add_argument("--kind", required=True, choices=KINDS)
    ad.add_argument("--scope", help="<branch>|new; defaults to the hub's branch"); ad.add_argument("--repos", help="other repositories it touches, comma-separated")
    ad.add_argument("--area"); ad.add_argument("--from", dest="src", help=f"the record, finding, or session it came from (default: {DEFAULT_FROM})")
    ad.add_argument("--body", help="a file holding the body, written under the heading")
    for kind, args in OWN_ARGS.items():
        for arg in args: ad.add_argument(f"--{arg}", help=f"{kind} only")
    ad.add_argument("--repo", help="file into this repository's backlog, from workspace.md or the registry")
    li = sp.add_parser("list"); li.add_argument("wt"); li.add_argument("--kind", choices=KINDS); li.add_argument("--scope"); li.add_argument("--all", action="store_true"); li.add_argument("--repo")
    for c in ("show", "path"): p = sp.add_parser(c); p.add_argument("wt"); p.add_argument("iid")
    st = sp.add_parser("set"); st.add_argument("wt"); st.add_argument("iid"); st.add_argument("status"); st.add_argument("--ref")
    ins = sp.add_parser("instruct"); ins.add_argument("wt"); ins.add_argument("iid"); ins.add_argument("instruction"); ins.add_argument("--note")
    rs = sp.add_parser("rescope"); rs.add_argument("wt"); rs.add_argument("iid"); rs.add_argument("scope")
    ck = sp.add_parser("check"); ck.add_argument("wt"); ck.add_argument("iid", nargs="?")
    a = ap.parse_args()
    records.guard(a.wt)
    if a.cmd == "add": print(add(a.wt, a))
    elif a.cmd == "list":
        for it in read(a.wt, a.kind, a.scope, a.all, a.repo): print(line(it))
    elif a.cmd == "show": sys.stdout.write(open(find(a.wt, a.iid)[1], encoding="utf-8").read())
    elif a.cmd == "path": print(find(a.wt, a.iid)[1])
    elif a.cmd == "set":
        qualified, it = set_status(a.wt, a.iid, a.status, a.ref)
        print(f"{qualified} {it['status']}" + (f" ({it['outcome']})" if it.get("outcome") else f" ({it['ref']})" if it.get("ref") else ""))
    elif a.cmd == "instruct":
        qualified, instruction = instruct(a.wt, a.iid, a.instruction, a.note); print(f"{qualified}: {instruction}")
    elif a.cmd == "rescope": print(f"{rescope(a.wt, a.iid, a.scope)} scoped to {a.scope}")
    elif a.cmd == "check": print("\n".join(check(a.wt, a.iid)))

if __name__ == "__main__": main()

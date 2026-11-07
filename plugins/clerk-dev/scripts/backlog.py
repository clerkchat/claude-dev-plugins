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
NAMES = {IDEA: "idea", CLEANUP: "cleanup", FOLLOWUP: "follow-up"}
WORDS = {kind: ("an " if name[0] in "aeiou" else "a ") + name for kind, name in NAMES.items()}
FIELDS = ("id", "kind", "title", "status", "scope", "repos", "area", "repo", "branch", "date", "from",
          "trigger", "removes", "origin", "contract", "finding", "instruction", "ref", "outcome")
PROVENANCE = ("repo", "branch", "date", "from")
OWN_ARGS = {IDEA: ("why", "when"), CLEANUP: ("trigger", "removes"), FOLLOWUP: ("origin", "contract", "finding")}
SECTIONS = (("why", "Why"), ("when", "When"))
DETAILS = {**OWN_ARGS, FOLLOWUP: ("contract", "finding", "instruction")}
DEFAULT_FROM = "this session"
FILE_RE = re.compile(r"^(\d+)\.md$")
DETACHED = "HEAD"
REMOTE = "origin/"

class Store(NamedTuple):
    name: str
    wt: str
    dir: str

def backlog_dir(wt): return os.path.join(records.repo_dir(wt), "backlog") if records.common_dir(wt) else ""

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
    store = store_of(repo.checkout, repo.name)
    return store if store.dir else None

def locate(wt, name):
    _, repos = records.workspace(wt)
    row = store_of(repos[name], name) if repos.get(name) else None
    if row and row.dir: return row
    if not os.path.exists(config.path()): sys.exit(config.MISSING.format(config.path()))
    repo = config.by_name(config.load(), name)
    store = registry_store(repo) if repo else None
    if not store: sys.exit(f"repository {name} is not in .clerk-dev/workspace.md or {config.path()}" + (f", and {repo.checkout} is not a git checkout" if repo else ""))
    return store

def same_store(a, b): return os.path.realpath(a.dir) == os.path.realpath(b.dir)

def split_id(text):
    p = ids.parse(ids.normalize(text))
    if not p or p.kind != ids.BACKLOG: sys.exit(f"{text} is not a backlog id (BL-n or <repo>:BL-n)")
    return p.repo, ids.item(ids.BACKLOG, p.n)

def qualify(store, own, iid): return ids.qualified(None if same_store(store, own) else store.name, iid)

def item_path(store, n): return os.path.join(store.dir, f"{n:03d}.md")

def holds(store, n): return bool(store.dir) and os.path.exists(item_path(store, n))

def numbers(store):
    if not os.path.isdir(store.dir): return []
    return sorted(int(m.group(1)) for m in map(FILE_RE.match, os.listdir(store.dir)) if m)

def read_item(path):
    meta, body = records.parse(path)
    return {**meta, "body": body}

def prose(it, arg): return re.sub(r"\s+", " ", records.body_section(it.get("body", ""), dict(SECTIONS)[arg])).rstrip(".")

def kind_name(it): return NAMES.get(it.get("kind"), it.get("kind", ""))

def write_item(path, it):
    records.write_atomic(path, records.render(it, it["body"], FIELDS))

def branches(wt):
    checked_out = {w.branch for w in records.worktrees(wt, check=True) if w.branch}
    local = records.git(wt, "for-each-ref", "--format=%(refname:short)", "refs/heads/", check=True).splitlines()
    return checked_out | set(local)

class Reader:
    def __init__(self, wt):
        self.wt = wt
        self.own = own_store(wt)
        self.own_branch = branch_of(wt)
        self.branches = {}

    def exists(self, store, branch):
        if branch == self.own_branch and same_store(store, self.own): return True
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

def not_in(found, its):
    known = {os.path.realpath(it["path"]) for it in found}
    return [it for it in its if os.path.realpath(it["path"]) not in known]

def my_names(reader, cfg):
    me = config.by_common_dir(cfg, records.common_dir(reader.wt))
    return {reader.own.name} | ({me.name} if me else set())

def is_open(it): return it.get("status") in OPEN

def scoped(reader, store, kind, branch):
    if not branch: return []
    return [it for it in reader.items(store) if it.get("kind") == kind and it.get("scope") == branch]

def feature_ideas(wt, include_closed=False):
    reader = Reader(wt)
    hub = hub_store(wt, reader.own)
    return [it for it in scoped(reader, hub, IDEA, branch_of(hub.wt)) if include_closed or is_open(it)]

def owed_followups(wt, include_closed=False):
    reader = Reader(wt)
    return [it for it in scoped(reader, reader.own, FOLLOWUP, reader.own_branch) if include_closed or is_open(it)]

def matching(found, kind=None, scope=None, include_closed=False):
    return [it for it in found
            if (kind is None or it.get("kind") == kind)
            and (scope is None or it["orphaned"] or it.get("scope") == scope)
            and (include_closed or is_open(it))]

def repo_items(wt, name): return Reader(wt).items(locate(wt, name))

def read(wt, kind=None, scope=None, include_closed=False):
    reader = Reader(wt)
    hub = hub_store(wt, reader.own)
    branch = branch_of(hub.wt)
    views = (scope,) if scope else (NEW, branch, reader.own_branch)
    in_view = lambda it: include_closed or it["orphaned"] or it.get("scope") in views
    found = [it for it in reader.items(reader.own) if in_view(it)]
    if kind in (None, IDEA) and not same_store(hub, reader.own):
        found += scoped(reader, hub, IDEA, branch)
    if kind != FOLLOWUP:
        cfg = config.load()
        mine = my_names(reader, cfg)
        for other in cfg.repos:
            store = registry_store(other)
            if store and not same_store(store, reader.own): found += not_in(found, touching(reader.items(store), mine))
    return matching(found, kind, scope, include_closed)

def stores_for(wt, repo, own):
    if repo: return [locate(wt, repo)]
    hub = hub_store(wt, own)
    return [own] if same_store(hub, own) else [own, hub]

def find_in(wt, text):
    repo, iid = split_id(text)
    own = own_store(wt)
    stores = stores_for(wt, repo, own)
    held = [s for s in stores if holds(s, ids.number(iid))]
    if not held: sys.exit(f"{qualify(stores[0], own, iid)} not found in {' or '.join(s.dir or s.wt for s in stores)}")
    if len(held) > 1: sys.exit(f"{iid} is in more than one backlog; name one: {' or '.join(ids.qualified(s.name, iid) for s in held)}")
    return held[0], own, item_path(held[0], ids.number(iid))

def lookup(wt, text): return read_item(find_in(wt, text)[2])

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

def title_of(a): return a.title.strip().rstrip(".")

def check_add(a):
    if not title_of(a): sys.exit("the title is blank; give the item a title")
    foreign = foreign_args(a)
    if foreign: sys.exit(f"{', '.join(foreign)}: not a field of {WORDS[a.kind]}")
    if a.kind == CLEANUP and not (a.trigger or a.removes): sys.exit("a cleanup needs --trigger or --removes")
    if a.kind == FOLLOWUP and not a.origin: sys.exit("a follow-up needs --origin \"<repo> <sha>\"")

def target_store(wt, a, own, scope):
    if a.repo: return locate(wt, a.repo)
    if a.kind == IDEA and scope != NEW: return hub_store(wt, own)
    return own

def create(store, meta, body):
    if not store.dir: sys.exit(f"{store.wt} is not a git checkout, so {store.name} has no backlog there")
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
    meta = {"kind": a.kind, "title": title_of(a), "status": OPEN_STATUS if a.kind == IDEA else OWED, "scope": scope,
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

def configured_main(store):
    repo = config.by_common_dir(config.load(), records.common_dir(store.wt))
    return repo.main if repo else ""

def main_of(store):
    main = configured_main(store) or records.remote_main(store.wt).removeprefix(REMOTE)
    if not main: sys.exit(f"no remote main in {store.wt} (no origin/HEAD, origin/main, or origin/master); run git remote set-head origin --auto there, or register the repository with its main branch in {config.path()}")
    return main

def remote_ref(main): return REMOTE + main

def removed(store, main, it):
    ref = remote_ref(main)
    r = records.git_run(store.wt, "grep", "-F", "-q", "-e", it["removes"], ref)
    if r.returncode > 1: sys.exit(records.git_failure(store.wt, ("grep", "-F", "-q", "-e", it["removes"], ref), r))
    return r.returncode == 1

def grep_line(store, main, it):
    state = f"gone from {remote_ref(main)}" if removed(store, main, it) else f"still present on {remote_ref(main)}"
    progress = f" (in progress: {it['ref']})" if it.get("ref") else ""
    return f"{it['qualified']} {it.get('title', '')}: {it['removes']} {state}{progress}"

def trigger_line(it):
    age = days_old(it)
    aged = f", {age} day{'' if age == 1 else 's'} old" if age is not None else ""
    return f"{it['qualified']} {it.get('title', '')}: trigger: {it['trigger']}{aged}"

def fetch_line(store):
    fetched = records.last_fetch(records.common_dir(store.wt))
    return f"last fetch: {fetched[0]} ({fetched[1]})" if fetched else "last fetch: none (no FETCH_HEAD)"

def owed_cleanups(reader, store):
    return [it for it in reader.items(store) if it.get("kind") == CLEANUP and is_open(it)]

def gone_cleanups(reader):
    greppable = [it for it in owed_cleanups(reader, reader.own) if it.get("removes")]
    main = main_of(reader.own) if greppable else ""
    return main, [it for it in greppable if removed(reader.own, main, it)]

def check(wt, text=None):
    reader = Reader(wt)
    if text:
        store, path, it, qualified = load(wt, text)
        if it["kind"] != CLEANUP: sys.exit(f"{qualified} is {WORDS[it['kind']]}; check looks at cleanups")
        cleanups = [it for it in reader.items(store) if it["path"] == path]
    else:
        store = reader.own
        cleanups = owed_cleanups(reader, store)
    main = main_of(store) if any(it.get("removes") for it in cleanups) else ""
    lines = [grep_line(store, main, it) if it.get("removes") else trigger_line(it) for it in cleanups]
    return lines + [fetch_line(store)]

def source(it): return it.get("origin") if it.get("kind") == FOLLOWUP else it.get("from")

def field(it, arg): return prose(it, arg) if arg in dict(SECTIONS) else it.get(arg, "")

def details(it):
    values = ((arg, field(it, arg)) for arg in DETAILS.get(it.get("kind"), ()))
    return [f"  {arg}: {value}" for arg, value in values if value]

def line(it):
    tail = [f"area {it['area']}"] if it.get("area") else []
    if source(it): tail.append(f"from {source(it)}")
    if it["orphaned"]: tail.append(f"from {it['scope']}, branch gone")
    if it.get("touches"): tail.append(f"owned by {it['owner']}, also touches {it['touches']}")
    return f"{it['qualified']} {it['kind']} {it['status']} {it.get('scope', '')}: {it.get('title', '')}" + (f"  [{'; '.join(tail)}]" if tail else "")

def listing(a):
    if a.owed: return owed_followups(a.wt, a.all)
    if a.parked: return feature_ideas(a.wt, a.all)
    if a.repo: return matching(repo_items(a.wt, a.repo), a.kind, a.scope, a.all)
    return read(a.wt, a.kind, a.scope, a.all)

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
    view = li.add_mutually_exclusive_group()
    view.add_argument("--owed", action="store_true", help="the follow-ups this branch owes: scoped to its branch, without new work or orphans")
    view.add_argument("--parked", action="store_true", help="the feature's parked ideas: scoped to the hub's branch, as status counts them")
    li.add_argument("--full", action="store_true", help="each item's own fields under its line: why and when, trigger and removes, contract, finding, and instruction")
    for c in ("show", "path"): p = sp.add_parser(c); p.add_argument("wt"); p.add_argument("iid")
    st = sp.add_parser("set"); st.add_argument("wt"); st.add_argument("iid"); st.add_argument("status"); st.add_argument("--ref")
    ins = sp.add_parser("instruct"); ins.add_argument("wt"); ins.add_argument("iid"); ins.add_argument("instruction"); ins.add_argument("--note")
    rs = sp.add_parser("rescope"); rs.add_argument("wt"); rs.add_argument("iid"); rs.add_argument("scope")
    ck = sp.add_parser("check"); ck.add_argument("wt"); ck.add_argument("iid", nargs="?")
    a = ap.parse_args()
    records.guard(a.wt)
    if a.cmd == "add": print(add(a.wt, a))
    elif a.cmd == "list":
        if (a.owed or a.parked) and (a.kind or a.scope or a.repo): sys.exit("--owed and --parked take no --kind, --scope, or --repo")
        for it in listing(a): print("\n".join([line(it)] + (details(it) if a.full else [])))
    elif a.cmd == "show": sys.stdout.write(open(find_in(a.wt, a.iid)[2], encoding="utf-8").read())
    elif a.cmd == "path": print(find_in(a.wt, a.iid)[2])
    elif a.cmd == "set":
        qualified, it = set_status(a.wt, a.iid, a.status, a.ref)
        print(f"{qualified} {it['status']}" + (f" ({it['outcome']})" if it.get("outcome") else f" ({it['ref']})" if it.get("ref") else ""))
    elif a.cmd == "instruct":
        qualified, instruction = instruct(a.wt, a.iid, a.instruction, a.note); print(f"{qualified}: {instruction}")
    elif a.cmd == "rescope": print(f"{rescope(a.wt, a.iid, a.scope)} scoped to {a.scope}")
    elif a.cmd == "check": print("\n".join(check(a.wt, a.iid)))

if __name__ == "__main__": main()

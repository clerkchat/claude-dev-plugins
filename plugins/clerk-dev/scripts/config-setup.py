#!/usr/bin/env python3
import argparse, datetime, os, sys
import config, records

DEPTH = 3
WORKSPACE_SOURCE = "workspace.md"

def real(p): return os.path.realpath(os.path.expanduser(p))

def unique(xs): return list(dict.fromkeys(xs))

def holds_home(root):
    home = real("~")
    return home == root or home.startswith(root.rstrip(os.sep) + os.sep)

def home_refusal(root): return f"search root {root} is or contains $HOME; name a directory below it"

def common_of(p):
    d = p if os.path.isdir(p) else os.path.dirname(p)
    common = records.common_dir(d) if os.path.isdir(d) else ""
    return os.path.realpath(common) if common else ""

def checkout_of(common): return os.path.dirname(common)

def walk(root, depth=DEPTH):
    if os.path.exists(os.path.join(root, ".git")):
        yield root
        return
    if depth == 0: return
    try: entries = sorted(os.scandir(root), key=lambda e: e.name)
    except OSError: return
    for e in entries:
        if not e.name.startswith(".") and e.is_dir(follow_symlinks=False): yield from walk(e.path, depth - 1)

def main_branch(checkout): return records.git(checkout, "rev-parse", "--abbrev-ref", "origin/HEAD").removeprefix("origin/")

def follows_default(checkout, w): return w.path == os.path.join(os.path.dirname(checkout), w.branch)

class Scan:
    def __init__(self):
        self.commons, self.seen, self.notes, self.read, self.walked = [], [], [], set(), set()
        self.workspace_names, self.listed = {}, {}

    def add(self, p):
        common = common_of(p)
        if common and common not in self.commons: self.commons.append(common)
        return common

    def worktrees_of(self, common):
        if common not in self.listed: self.listed[common] = records.worktrees(checkout_of(common))
        return self.listed[common]

    def walk(self, root):
        if root in self.walked: return []
        self.walked.add(root)
        found = list(walk(root))
        self.seen += found
        return [self.add(d) for d in found]

    def path(self, p):
        if not self.add(real(p)): self.notes.append(f"not a repository: {p}")

    def workspace(self, d):
        ws = os.path.realpath(records.workspace_path(d))
        if ws in self.read or not os.path.exists(ws): return
        self.read.add(ws)
        for name, p in records.workspace(d)[1].items():
            common = self.add(real(p)) if p and os.path.exists(real(p)) else ""
            if common: self.workspace_names.setdefault(common, []).append(name)
            else: self.notes.append(f"{WORKSPACE_SOURCE} in {d}: row {name} names {p or 'no path'}, which does not exist; skipped")

    def workspaces(self):
        listed = [w.path for common in list(self.commons) for w in self.worktrees_of(common)]
        for d in unique(self.seen + listed): self.workspace(d)

    def repo(self, common):
        checkout = checkout_of(common)
        from_git = records.this_repo(checkout, {})
        given = unique(self.workspace_names.get(common, []))
        name = given[0] if given else from_git
        others = [n for n in unique(given + [from_git]) if n != name]
        if given and others: self.notes.append(f"name {name} for {checkout} is from {WORKSPACE_SOURCE}; also called {', '.join(others)}")
        main = main_branch(checkout)
        if not main: self.notes.append(f"no origin/HEAD in {checkout}: run git remote set-head origin --auto there or fill in its {config.MAIN} cell")
        return config.Repo(name, checkout, main)

    def pattern(self):
        wts = [(checkout_of(c), w) for c in self.commons for w in self.worktrees_of(c) if w.path != checkout_of(c) and w.branch]
        if not all(follows_default(checkout, w) for checkout, w in wts):
            self.notes.append(f"worktree paths do not all follow {config.DEFAULT_PATTERN}: " + ", ".join(f"{w.path} ({w.branch})" for _, w in wts))
        return config.DEFAULT_PATTERN

def proposed_roots(scan, own, extra):
    base = os.path.dirname(checkout_of(own))
    if holds_home(base):
        scan.notes.append(f"not proposing {base}: it is or contains $HOME")
        return extra
    roots = [base]
    parent = os.path.dirname(base)
    if set(scan.walk(base)) <= {own} and not holds_home(parent):
        scan.notes.append(f"proposed root {parent}: {base} holds only this repository's worktrees")
        roots.append(parent)
    return roots + extra

def merged_roots(scan, existing, proposed, had):
    kept = {real(r) for r in existing.search_roots}
    new = [r for r in unique(proposed) if r not in kept]
    if had: scan.notes += [f"new: {r}" for r in new]
    return existing.search_roots + new

def merged_repos(scan, existing, had):
    kept = {real(r.checkout) for r in existing.repos}
    scan.notes += [f"missing: {r.name} {r.checkout} no longer exists" for r in existing.repos if not os.path.isdir(real(r.checkout))]
    new = [scan.repo(c) for c in scan.commons if checkout_of(c) not in kept]
    if had: scan.notes += [f"new: {r.name}" for r in new]
    return existing.repos + new

def scan(wt, roots, paths, out):
    wt = os.path.abspath(wt)
    own = common_of(wt)
    if not own: sys.exit(f"{wt} is not in a git repository")
    extra = [real(r) for r in roots]
    refused = next((r for r in extra if holds_home(r)), None)
    if refused: sys.exit(home_refusal(refused))
    had = os.path.exists(config.path())
    existing = config.read_raw(config.path())
    s = Scan()
    proposed = proposed_roots(s, own, extra)
    for root in unique(proposed + [real(r) for r in existing.search_roots]):
        if holds_home(root): s.notes.append(f"not walking {root}: it is or contains $HOME")
        else: s.walk(root)
    for p in paths: s.path(p)
    s.add(wt)
    s.seen.append(wt)
    s.workspaces()
    cfg = config.Config(merged_roots(s, existing, proposed, had), merged_repos(s, existing, had),
                        existing.pattern or s.pattern(), existing.after_create)
    header = f"Proposed {datetime.date.today().isoformat()} from {wt}. Edit freely."
    records.write_atomic(out, config.render(cfg, header))
    for line in [os.path.abspath(out), *unique(s.notes)]: print(line)

def write(f):
    if not os.path.exists(f): sys.exit(f"{f} does not exist")
    text = open(f, encoding="utf-8").read()
    missing = config.missing_sections(text)
    if missing: sys.exit(f"{f} does not parse: no " + ", ".join(f"## {m}" for m in missing) + " section")
    gone = [r.checkout for r in config.load(f).repos if not os.path.isdir(r.checkout)]
    if gone: sys.exit(f"main checkout {', '.join(gone)} does not exist; fix or remove its row in {f}")
    dest = config.path()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    records.write_atomic(dest, text)
    print(dest)

def main():
    ap = argparse.ArgumentParser(description=f"Propose the per-user clerk-dev config from a scan, and write it once confirmed, at {config.DEFAULT_PATH} or ${config.ENV}.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="write a proposed config to --out; print its path, then one note per line")
    s.add_argument("worktree")
    s.add_argument("--root", action="append", default=[], help="another search root, walked three levels down")
    s.add_argument("--path", action="append", default=[], help="a path anywhere inside a repository to register")
    s.add_argument("--out", required=True)
    w = sub.add_parser("write", help="check a proposal and write it as the config")
    w.add_argument("file")
    a = ap.parse_args()
    if a.cmd == "scan": scan(a.worktree, a.root, a.path, a.out)
    else: write(a.file)

if __name__ == "__main__": main()

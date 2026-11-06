#!/usr/bin/env python3
import argparse, os, re
from typing import NamedTuple
import records

ENV = "CLERK_DEV_CONFIG"
DEFAULT_PATH = os.path.join("~", ".claude", "clerk-dev", "local.md")
SEARCH_ROOTS, REPOSITORIES, WORKTREES = "Search roots", "Repositories", "Worktrees"
NAME, CHECKOUT, MAIN = "Name", "Main checkout", "Main branch"
PATTERN, AFTER_CREATE = "Pattern", "After create"

class Repo(NamedTuple):
    name: str
    checkout: str
    main: str

class Config(NamedTuple):
    search_roots: list[str]
    repos: list[Repo]
    pattern: str
    after_create: str

EMPTY = Config([], [], "", "")

def path(): return os.path.expanduser(os.environ.get(ENV) or DEFAULT_PATH)

def list_items(text):
    return [records.LIST_RE.sub("", line).strip() for line in text.splitlines() if records.LIST_RE.match(line)]

def labeled_line(text, label):
    m = re.search(rf"^{re.escape(label)}:[ \t]*(.*?)[ \t]*$", text, re.M)
    return m.group(1) if m else ""

def repo_rows(text):
    return [Repo(r[NAME], os.path.expanduser(r[CHECKOUT]), r.get(MAIN, "")) for r in records.table_rows(text) if r.get(NAME) and r.get(CHECKOUT)]

def load(p=None):
    p = p or path()
    if not os.path.exists(p): return EMPTY
    sections = dict(records.headings(open(p, encoding="utf-8").read(), "##"))
    worktrees = sections.get(WORKTREES, "")
    return Config([os.path.expanduser(root) for root in list_items(sections.get(SEARCH_ROOTS, ""))],
                  repo_rows(sections.get(REPOSITORIES, "")),
                  labeled_line(worktrees, PATTERN), labeled_line(worktrees, AFTER_CREATE))

def by_name(cfg, name): return next((r for r in cfg.repos if r.name == name), None)

def owns(repo, real_common):
    common = records.common_dir(repo.checkout)
    return bool(common) and os.path.realpath(common) == real_common

def by_common_dir(cfg, common):
    real = os.path.realpath(common)
    return next((r for r in cfg.repos if owns(r, real)), None)

def repo_line(r): return f"repository: {r.name} {r.checkout}" + (f" (main branch {r.main})" if r.main else "")

def show(cfg):
    lines = [f"search root: {root}" for root in cfg.search_roots] + [repo_line(r) for r in cfg.repos]
    if cfg.pattern: lines.append(f"pattern: {cfg.pattern}")
    if cfg.after_create: lines.append(f"after create: {cfg.after_create}")
    return lines

def main():
    ap = argparse.ArgumentParser(description=f"The per-user clerk-dev config, {DEFAULT_PATH} or ${ENV}.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="what the reader sees, one line per search root, repository, and Worktrees line")
    sub.add_parser("path", help="the config file's path")
    a = ap.parse_args()
    if a.cmd == "path": print(path())
    else:
        for line in show(load()): print(line)

if __name__ == "__main__": main()

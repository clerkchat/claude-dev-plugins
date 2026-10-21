#!/usr/bin/env python3
"""Keep a worktree's pass log, <worktree>/.clerk-dev/passes.md.

A pass is a bounded stretch of writing with one focus on one piece of work,
ending in commits and a narrow check with only the pass's lenses over only the
pass's commits. The log holds each pass's focus, lenses, piece, mode, commit
range, checklist, and check result. It is read strictly: a line it does not
recognize stops the script rather than being dropped on the next write.

Usage:
  passes.py start WORKTREE FOCUS --lenses a,b [--mode claude|guide] [--piece BRIEF-9] [--leave-out FILE ...]
  passes.py item WORKTREE PASS-3 "what to do, with path:line"
  passes.py done WORKTREE PASS-3 N [--na "why not applicable"]
  passes.py end WORKTREE PASS-3
  passes.py note WORKTREE PASS-3 "what to do next"      (an open pass only; "" clears it)
  passes.py range WORKTREE PASS-3
  passes.py check WORKTREE PASS-3 --run LABEL --ran a,b (--findings a=2,b=0 | --result empty|error) [--note "..."]
  passes.py abandon WORKTREE PASS-3 [--note "..."]
  passes.py show WORKTREE PASS-3
  passes.py list WORKTREE [--open]
  passes.py stats WORKTREE

Entry format:
  - [ ] PASS-3. edge-cases on BRIEF-9
    - Mode: claude
    - Lenses: edge-cases, error-handling
    - Piece: BRIEF-9
    - Status: ended
    - Start: 1a2b3c4
    - End: 5d6e7f8
    - Plugin: 9a8b7c6
    - Left out: src/scratch.ts
    - Started: 2026-10-16
    - Items:
      - [x] 1. Empty contact list returns early (src/import.ts:40)
      - [-] 2. Unicode names: not applicable, names are opaque here
      - [ ] 3. Provider timeout leaves the import running (src/import.ts:88)
    - Check: pass-p3-1016; ran edge-cases, error-handling; edge-cases 2, error-handling 0
    - Note: log item 3 once the timeout test passes   (the handoff of an open pass; status shows it)
"""
import argparse, datetime, json, os, re, subprocess, sys, tempfile
from records import load_script
import ids

STATES = ("open", "ended", "checked", "abandoned")
FIELDS = ("Mode", "Lenses", "Piece", "Status", "Start", "End", "Plugin", "Left out", "Started", "Check", "Note")
HEADER = """# Passes

Each pass is one focus on one piece of work, checked with only its own lenses.
Kept by passes.py; it reads this file strictly, so edit with care.

"""
ENTRY_RE = re.compile(rf"^- \[( |x)\] ({ids.pattern(ids.PASS)})\. (.+)$")
FIELD_RE = re.compile(r"^  - (" + "|".join(FIELDS) + r"): ?(.*)$")
ITEMS_RE = re.compile(r"^  - Items:\s*$")
ITEM_RE = re.compile(r"^    - \[( |x|-)\] (\d+)\. (.+)$")

def git(wt, *args, check=True):
    r = subprocess.run(["git", "-C", wt, *args], capture_output=True, text=True)
    if check and r.returncode != 0: sys.exit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()

def path(wt):
    d = os.path.join(wt, ".clerk-dev"); os.makedirs(d, exist_ok=True)
    if subprocess.run(["git", "-C", wt, "check-ignore", "-q", ".clerk-dev"]).returncode != 0:
        common = git(wt, "rev-parse", "--git-common-dir", check=False)
        if common:
            exf = os.path.join(common if os.path.isabs(common) else os.path.join(wt, common), "info", "exclude")
            os.makedirs(os.path.dirname(exf), exist_ok=True)
            with open(exf, "a") as fh: fh.write(".clerk-dev/\n")
    return os.path.join(d, "passes.md")

def read(p):
    if not os.path.exists(p): return []
    passes, cur, in_items = [], None, False
    for n, raw in enumerate(open(p, encoding="utf-8"), 1):
        line = raw.rstrip("\n")
        if not line.strip(): continue
        m = ENTRY_RE.match(line)
        if m:
            cur = {"id": m.group(2), "title": m.group(3), "f": {}, "items": []}; passes.append(cur); in_items = False; continue
        if cur is None:
            if line.startswith("#") or not line.startswith((" ", "-")): continue  # header prose
            sys.exit(f"{p}:{n}: unrecognized line before the first pass: {line!r}")
        if ITEMS_RE.match(line): in_items = True; continue
        m = ITEM_RE.match(line)
        if m and in_items:
            cur["items"].append({"mark": m.group(1), "n": int(m.group(2)), "text": m.group(3)}); continue
        m = FIELD_RE.match(line)
        if m: cur["f"][m.group(1)] = m.group(2).strip(); in_items = False; continue
        sys.exit(f"{p}:{n}: unrecognized line in {cur['id']}: {line!r}; fix it by hand, nothing was written")
    return passes

def write(p, passes):
    out = [HEADER]
    for e in passes:
        out.append(f"- [{'x' if e['f'].get('Status') in ('checked', 'abandoned') else ' '}] {e['id']}. {e['title']}\n")
        for k in FIELDS:
            if e["f"].get(k): out.append(f"  - {k}: {e['f'][k]}\n")
            if k == "Started" and e["items"]:
                out.append("  - Items:\n")
                out += [f"    - [{i['mark']}] {i['n']}. {i['text']}\n" for i in e["items"]]
        out.append("\n")
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), prefix=".passes.")
    with os.fdopen(fd, "w", encoding="utf-8") as fh: fh.write("".join(out).rstrip("\n") + "\n")
    os.replace(tmp, p)

def find(passes, pid):
    pid = ids.complete(pid, ids.PASS)
    e = next((e for e in passes if ids.same(e["id"], pid)), None)
    if not e: sys.exit(f"{pid} not found")
    return e

def dirty(wt, leave_out=()):
    lines = subprocess.run(["git", "-C", wt, "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.splitlines()
    files = [l[3:].split(" -> ")[-1] for l in lines]
    return [f for f in files if f not in leave_out]

def plugin_version():
    root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    sha = subprocess.run(["git", "-C", root, "log", "-1", "--format=%h", "--", "agents"], capture_output=True, text=True).stdout.strip()
    if sha: return sha
    try: return "v" + json.load(open(os.path.join(root, ".claude-plugin", "plugin.json")))["version"]
    except Exception: return "unknown"

def counts(check):
    """{lens: findings} from a Check field, or None when it holds no counts."""
    m = re.search(r";\s*((?:[a-z-]+ \d+(?:, )?)+)\s*(?:;|$)", check or "")
    return {k: int(v) for k, v in re.findall(r"([a-z-]+) (\d+)", m.group(1))} if m else None

def guard(wt):
    load_script("records.py").guard(wt)

def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("start"); s.add_argument("wt"); s.add_argument("focus"); s.add_argument("--lenses", required=True)
    s.add_argument("--mode", choices=("claude", "guide"), default="claude"); s.add_argument("--piece"); s.add_argument("--leave-out", nargs="*", default=[])
    i = sp.add_parser("item"); i.add_argument("wt"); i.add_argument("pid"); i.add_argument("text")
    d = sp.add_parser("done"); d.add_argument("wt"); d.add_argument("pid"); d.add_argument("n", type=int); d.add_argument("--na")
    e_ = sp.add_parser("end"); e_.add_argument("wt"); e_.add_argument("pid")
    n_ = sp.add_parser("note"); n_.add_argument("wt"); n_.add_argument("pid"); n_.add_argument("text")
    r = sp.add_parser("range"); r.add_argument("wt"); r.add_argument("pid")
    sh = sp.add_parser("show"); sh.add_argument("wt"); sh.add_argument("pid")
    c = sp.add_parser("check"); c.add_argument("wt"); c.add_argument("pid"); c.add_argument("--run", required=True); c.add_argument("--ran", required=True)
    g = c.add_mutually_exclusive_group(required=True); g.add_argument("--findings"); g.add_argument("--result", choices=("empty", "error"))
    c.add_argument("--note")
    ab = sp.add_parser("abandon"); ab.add_argument("wt"); ab.add_argument("pid"); ab.add_argument("--note")
    l = sp.add_parser("list"); l.add_argument("wt"); l.add_argument("--open", action="store_true")
    sp.add_parser("stats").add_argument("wt")
    a = ap.parse_args()
    guard(a.wt)
    p = path(a.wt); passes = read(p); today = datetime.date.today().isoformat()

    if a.cmd == "start":
        op = [e["id"] for e in passes if e["f"].get("Status") == "open"]
        if op: sys.exit(f"{', '.join(op)} still open; end or abandon it first")
        dl = dirty(a.wt, a.leave_out)
        if dl: sys.exit("tracked files have uncommitted changes: " + ", ".join(dl) + "\ncommit them, or name them with --leave-out to keep them out of this pass")
        pid = ids.item(ids.PASS, ids.next_number([e["id"] for e in passes], ids.PASS))
        lenses = ", ".join(x.strip() for x in a.lenses.split(",") if x.strip())
        title = f"{a.focus} on {a.piece}" if a.piece else a.focus
        passes.append({"id": pid, "title": title, "items": [], "f": {
            "Mode": a.mode, "Lenses": lenses, "Piece": a.piece or "", "Status": "open",
            "Start": git(a.wt, "rev-parse", "--short", "HEAD"), "Plugin": plugin_version(),
            "Left out": ", ".join(a.leave_out), "Started": today}})
        write(p, passes); print(f"{pid} started at {passes[-1]['f']['Start']}")
        return
    e = find(passes, a.pid) if a.cmd not in ("list", "stats") else {"f": {}, "items": []}
    if a.cmd == "item":
        k = max([i["n"] for i in e["items"]] or [0]) + 1
        e["items"].append({"mark": " ", "n": k, "text": a.text.rstrip()}); write(p, passes); print(f"{e['id']} item {k}")
    elif a.cmd == "done":
        it = next((i for i in e["items"] if i["n"] == a.n), None)
        if not it: sys.exit(f"{e['id']} has no item {a.n}")
        it["mark"] = "-" if a.na else "x"
        if a.na: it["text"] = re.sub(r":? not applicable.*$", "", it["text"]) + f": not applicable, {a.na}"
        write(p, passes); print(f"{e['id']} item {a.n} {'not applicable' if a.na else 'done'}")
    elif a.cmd == "note":
        if e["f"].get("Status") != "open": sys.exit(f"{e['id']} is {e['f'].get('Status')}, not open")
        text = " ".join(a.text.split())
        if text: e["f"]["Note"] = text
        else: e["f"].pop("Note", None)
        write(p, passes); print(f"{e['id']} note " + ("set" if text else "cleared"))
    elif a.cmd == "end":
        if e["f"].get("Status") != "open": sys.exit(f"{e['id']} is {e['f'].get('Status')}, not open")
        dl = dirty(a.wt, [x.strip() for x in e["f"].get("Left out", "").split(",") if x.strip()])
        if dl: sys.exit("tracked changes are not committed: " + ", ".join(dl))
        left = [i["n"] for i in e["items"] if i["mark"] == " "]
        e["f"]["End"] = git(a.wt, "rev-parse", "--short", "HEAD"); e["f"]["Status"] = "ended"
        if e["f"]["End"] == e["f"]["Start"]: e["f"]["Note"] = "no commits"
        write(p, passes)
        print(f"{e['id']} ended at {e['f']['End']}" + (" with no commits" if e["f"]["End"] == e["f"]["Start"] else "")
              + (f"; items not done: {', '.join(map(str, left))}" if left else ""))
    elif a.cmd == "range":
        if e["f"].get("Status") not in ("ended", "checked"): sys.exit(f"{e['id']} is {e['f'].get('Status')}; end it first")
        st, en = e["f"]["Start"], e["f"]["End"]
        if st == en: sys.exit(f"{e['id']} has no commits; nothing to check")
        for ref in (st, en):
            if subprocess.run(["git", "-C", a.wt, "merge-base", "--is-ancestor", ref, "HEAD"]).returncode != 0:
                sys.exit(f"{ref} of {e['id']} is not an ancestor of HEAD; the pass was rebased, squashed, or amended. Re-anchor it by hand or abandon it")
        print(f"{st}..{en}")
    elif a.cmd == "check":
        want = [x.strip() for x in e["f"].get("Lenses", "").split(",") if x.strip()]
        ran = [x.strip() for x in a.ran.split(",") if x.strip()]
        missing = [x for x in want if x not in ran]
        if a.findings:
            fc = dict(kv.split("=") for kv in a.findings.split(","))
            res = ", ".join(f"{k} {int(fc.get(k, 0))}" for k in ran)
        else: res = a.result
        e["f"]["Check"] = f"{a.run}; ran {', '.join(ran)}; {res}" + (f"; did not run: {', '.join(missing)}" if missing else "")
        if a.note: e["f"]["Note"] = a.note
        e["f"]["Status"] = "checked"; write(p, passes)
        print(f"{e['id']} checked: {e['f']['Check']}")
        if missing: sys.exit(1)
    elif a.cmd == "abandon":
        e["f"]["Status"] = "abandoned"
        if a.note: e["f"]["Note"] = a.note
        write(p, passes); print(f"{e['id']} abandoned")
    elif a.cmd == "show":
        print(open(p, encoding="utf-8").read().split(f"] {e['id']}. ", 1)[1].split("\n- [", 1)[0].rstrip())
    elif a.cmd == "list":
        for x in passes:
            st = x["f"].get("Status", "")
            if a.open and st not in ("open", "ended"): continue
            done = sum(1 for i in x["items"] if i["mark"] != " ")
            rng = f"{x['f'].get('Start', '')}..{x['f'].get('End', '')}" if x["f"].get("End") else f"from {x['f'].get('Start', '')}"
            print(f"{x['id']} {x['title']}  [{st}; {x['f'].get('Mode', '')}; {rng}; items {done}/{len(x['items'])}"
                  + (f"; {x['f']['Check']}" if x["f"].get("Check") else "") + "]")
    elif a.cmd == "stats":
        by = {}
        for x in passes:
            cs = counts(x["f"].get("Check"))
            if cs is None: continue
            for lens, k in cs.items():
                s = by.setdefault(lens, {"passes": 0, "findings": 0, "clean": 0, "plugins": set()})
                s["passes"] += 1; s["findings"] += k; s["clean"] += k == 0; s["plugins"].add(x["f"].get("Plugin", "?"))
        if not by: print("no checked passes yet"); return
        print("lens\tpasses\tclean\tfindings\tplugin versions")
        for lens, s in sorted(by.items()):
            print(f"{lens}\t{s['passes']}\t{s['clean']}\t{s['findings']}\t{', '.join(sorted(s['plugins']))}")

if __name__ == "__main__": main()

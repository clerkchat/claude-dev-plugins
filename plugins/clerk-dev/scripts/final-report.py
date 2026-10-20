#!/usr/bin/env python3
"""Write RUN/final-review-report.md, the verdict of a final pass.

Usage:
  final-report.py RUN [--routing routing.md]
      One repository's final pass.
  final-report.py RUN --child NAME=CHILD_RUN [...] [--routing routing.md]
      A feature's final pass: RUN is the feature run (the cross-repository
      check), each CHILD_RUN a repository's final run, whose own
      final-review-report.md is written first if missing.

The first line is the verdict. A pass passes when nothing new meets the
final bar, no fixed finding was reopened, and no finding in Fix before
merging is still open; a feature passes when every repository and the
cross-repository check pass. Findings themselves stay in report.md, where
triage works on them; this file names them by number with the report line.
Then: what was checked (the eleven bar categories, each with what was found
there, and the lenses that ran or did not), the earlier findings' state, what
was raised below the bar (final/below.md), and the run's summary.md.

Reads: target.txt, numbers.tsv, status.tsv, instructions.tsv, merged.md,
reconcile/appended.tsv and appended-map.tsv and append-judged.tsv,
final/verify/<new id>.md (the `bar:` line), final/below.md, raw/, report.md,
summary.md.
"""
import argparse, datetime, os, re
from records import load_script

HERE = os.path.dirname(os.path.abspath(__file__))
sf = load_script("stale-findings.py")

CATEGORIES = [
    ("correctness", "Breaking correctness", "crashes on common paths, silently wrong results, data loss"),
    ("security", "Security", "auth bypass, injection, secret exposure, sandbox escape"),
    ("performance", "Performance or scaling", "unbounded queries, N+1 on hot paths, missing indexes"),
    ("tenant", "Tenant isolation", "reads or writes that can cross tenants"),
    ("side effect", "Real-world side effects", "messages, calls, or charges from paths users think are safe"),
    ("rollout", "Rollout and rollback", "deploy order, migration locks, in-flight jobs"),
    ("client", "Breaking deployed clients", "contract changes that break a deployed client"),
    ("cost", "Cost runaway", "unbounded LLM loops, retry storms"),
    ("concurrency", "Concurrency corruption", "lost updates, duplicate sends or charges"),
    ("privacy", "Privacy and compliance", "personal data in logs or third parties, opt-out and consent"),
    ("silent", "Silent failure of something new", "new failure paths invisible in production"),
]
FINAL_LENSES = ["security", "tenancy", "data-privacy", "side-effects", "rollout", "sql", "scaling",
                "capacity", "concurrency", "contracts", "error-handling", "llm-agent", "completeness"]
BELOW_LENSES = ["design", "naming-concepts", "user-facing-text", "tests", "performance",
                "observability-cost", "spec-conformance"]

def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""

def plain_names(routing):
    names, inside = {}, False
    for line in read(routing).splitlines():
        if line.startswith("## "): inside = line.strip() == "## Plain names"; continue
        if not inside: continue
        m = re.match(r"^\|\s*`([a-z-]+)`\s*\|\s*([^|]+?)\s*\|", line)
        if m: names[m.group(1)] = m.group(2)
    return names

def category_of(text):
    t = text.lower()
    for key, name, _ in CATEGORIES:
        if key in t or name.lower() in t: return name
    return ""

def report_line(run, num):
    for i, line in enumerate(read(os.path.join(run, "report.md")).splitlines(), 1):
        if re.match(rf"^#### {num}\. ", line): return i
    return None

def ref(run, num, title):
    line = report_line(run, num)
    return f"{num}. {title} (`report.md:{line}`)" if line else f"{num}. {title}"

def analyze(run):
    findings = sf.load_findings(run)
    status, instr, numbers = sf.state(run)
    sections = {int(r[1]): r[2] for r in sf.tsv(os.path.join(run, "numbers.tsv")) if len(r) > 2 and r[1].isdigit()}
    rd = os.path.join(run, "reconcile")
    appended = {int(r[0]) for r in sf.tsv(os.path.join(rd, "appended.tsv")) if r and r[0].isdigit()}
    new_of = {int(r[1]): int(r[0]) for r in sf.tsv(os.path.join(rd, "appended-map.tsv")) if len(r) > 1 and r[0].isdigit() and r[1].isdigit()}
    judged = [r for r in sf.tsv(os.path.join(rd, "append-judged.tsv")) if len(r) > 2]
    title = lambda mid: re.sub(r"\s+", " ", str(findings.get(mid, {}).get("title", ""))).strip() or f"merged {mid}"

    kept = []
    for mid in sorted(appended, key=lambda m: int(numbers.get(m, 10**6))):
        if mid not in numbers: continue
        bar = ""
        for p in (os.path.join(run, "final", "verify", f"{new_of.get(mid, '')}.md"), os.path.join(run, "verify", f"{mid}.md")):
            m = re.search(r"^bar:\s*(.*)$", read(p), re.M)
            if m: bar = m.group(1); break
        cat = category_of(bar) or category_of(str(findings[mid].get("context", "")))
        kept.append((numbers[mid], mid, title(mid), cat or "category not stated"))
    reopened = [(numbers[int(r[1])], int(r[1]), title(int(r[1]))) for r in judged
                if r[2] == "regressed" and r[1].isdigit() and int(r[1]) in numbers and status.get(int(r[1]), ["", ""])[1] != "fixed"]
    open_fix = [(numbers[m], m, title(m)) for m in findings
                if m in numbers and sections.get(m) == "fix" and sf.is_open(m, status, instr) and m not in appended]
    counts = {}
    for m in findings:
        if m not in numbers: continue
        st = status[m][1] if m in status else "open"
        choice = re.sub(r"\(.*\)$", "", instr.get(m, ""))
        key = st if st != "open" else {"defer": "deferred", "ignore": "declined"}.get(choice, "open")
        counts[key] = counts.get(key, 0) + 1
    below = re.findall(r"^\s*title:\s*(.+)$", read(os.path.join(run, "final", "below.md")), re.M)
    lenses = sorted({re.sub(r"(-part\d+|-\d+)$", "", os.path.splitext(f)[0]) for f in os.listdir(os.path.join(run, "raw"))}) \
        if os.path.isdir(os.path.join(run, "raw")) else []
    passed = not kept and not reopened and not open_fix
    rp = os.path.join(run, "report.md")
    when = datetime.date.fromtimestamp(os.path.getmtime(rp)).isoformat() if os.path.exists(rp) else datetime.date.today().isoformat()
    return dict(when=when, kept=kept, reopened=reopened, open_fix=open_fix, counts=counts, below=below,
                lenses=lenses, passed=passed, target=read(os.path.join(run, "target.txt")).splitlines())

def verdict_line(a):
    if a["passed"]: return "PASSED"
    parts = []
    if a["kept"]: parts.append(f"{len(a['kept'])} new finding{'s' if len(a['kept']) != 1 else ''} would hold the merge")
    if a["reopened"]: parts.append(f"{len(a['reopened'])} fixed finding{'s' if len(a['reopened']) != 1 else ''} reopened")
    if a["open_fix"]: parts.append(f"{len(a['open_fix'])} still open in Fix before merging")
    return "NOT PASSED: " + "; ".join(parts)

def body(run, a, names, heading="##"):
    out = []
    if not a["passed"]:
        out += [f"{heading} What holds the merge", ""]
        for num, _, t, cat in a["kept"]: out.append(f"- New, {cat}: " + ref(run, num, t))
        for num, _, t in a["reopened"]: out.append("- Reopened: " + ref(run, num, t))
        for num, _, t in sorted(a["open_fix"], key=lambda x: int(x[0])): out.append("- Still open: " + ref(run, num, t))
        out += ["", "Triage these in `report.md` as usual" + ("; the new ones carry `[new]` until marked." if a["kept"] else "."), ""]
    out += [f"{heading} What was checked", "",
            "Every lens read the whole branch fresh and reported only what a senior reviewer would hold the merge for, with a concrete path to it in production:", ""]
    found = {}
    for num, _, _, cat in a["kept"]: found.setdefault(cat, []).append(num)
    for _, name, desc in CATEGORIES:
        nums = found.get(name)
        out.append(f"- {name} ({desc}): " + (f"findings {', '.join(nums)}" if nums else "nothing found"))
    other = [c for c in found if c not in {n for _, n, _ in CATEGORIES}]
    for c in other: out.append(f"- {c}: findings {', '.join(found[c])}")
    if a["lenses"]:
        out += ["", "Lenses that ran: " + ", ".join(names.get(l, l) for l in a["lenses"]) + "."]
        skipped = [l for l in FINAL_LENSES if l not in a["lenses"] and l != "cross-repo"]
        if skipped and "cross-repo" not in a["lenses"]:
            out.append("Not routed (no matching files): " + ", ".join(names.get(l, l) for l in skipped) + ".")
        if "cross-repo" not in a["lenses"]:
            out.append("Left out by design, below the final bar: " + ", ".join(names.get(l, l) for l in BELOW_LENSES) + ".")
    c = a["counts"]
    if c:
        order = ["fixed", "wont-fix", "deferred", "declined", "in-progress", "open"]
        label = {"wont-fix": "won't fix", "in-progress": "fix in progress"}
        out += ["", f"{heading} Earlier findings", "", ", ".join(f"{c[k]} {label.get(k, k)}" for k in order if c.get(k)) + "."]
    out += ["", f"{heading} Below the bar", ""]
    if a["below"]:
        out += [f"{len(a['below'])} raised and set aside, kept in `final/below.md`:", ""] + [f"- {t.strip()}" for t in a["below"]]
    else:
        out.append("Nothing raised below the bar.")
    summary = read(os.path.join(run, "summary.md")).strip()
    if summary: out += ["", f"{heading} Summary", "", summary]
    return out

def scope_line(a):
    t = a["target"]
    if len(t) >= 3 and t[0] != "feature":
        return f"Whole branch `{t[1][:9]}...{t[2][:9]}`, read fresh on {a['when']}."
    return ""

def write(run, lines):
    p = os.path.join(run, "final-review-report.md")
    open(p, "w", encoding="utf-8").write("\n".join(lines).rstrip() + "\n")
    return p

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--child", action="append", default=[], metavar="NAME=CHILD_RUN")
    ap.add_argument("--routing", default=os.path.join(HERE, "..", "skills", "review", "routing.md"))
    a = ap.parse_args()
    names = plain_names(a.routing)
    run = os.path.realpath(a.run)
    res = analyze(run)
    if not a.child:
        p = write(run, [f"# Final review: {verdict_line(res)}", "", scope_line(res), ""] + body(run, res, names))
        print(f"{verdict_line(res)}: {p}")
        return
    kids, all_pass = [], res["passed"]
    for spec_ in a.child:
        name, _, crun = spec_.partition("=")
        crun = os.path.realpath(crun)
        cres = analyze(crun)
        write(crun, [f"# Final review: {verdict_line(cres)}", "", scope_line(cres), ""] + body(crun, cres, names))
        all_pass = all_pass and cres["passed"]
        kids.append((name, crun, cres))
    head = "PASSED" if all_pass else "NOT PASSED"
    out = [f"# Final review of the feature: {head}", "", "| Repository | Verdict | Report |", "| --- | --- | --- |"]
    for name, crun, cres in kids:
        out.append(f"| {name} | {verdict_line(cres)} | `{os.path.join(crun, 'final-review-report.md')}` |")
    out.append(f"| cross-repository check | {verdict_line(res)} | below |")
    out += ["", "Each repository's file lists what was checked there; findings are triaged in that repository's `report.md`.", ""]
    out += body(run, res, names)
    p = write(run, out)
    print(f"{head}: {p}")

if __name__ == "__main__":
    main()

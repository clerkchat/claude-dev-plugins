#!/usr/bin/env python3
"""Total the real usage a review run recorded, by lens and model.

Usage: usage.py RUN_DIR [--append]

Reads the `usage:` line the orchestrator writes into each reviewer's raw file
header and each verifier's verify/<id>.md, as reported by Claude Code when the
subagent finished ("45.2k tokens", "1m 30s"). Prints a table of reviewers per
lens and model and of verifiers per model, with instance counts, tokens, and
total and median duration. With --append, also writes the table to the run's
plan.md under "## Actual usage", replacing an earlier one, so the next run of
the branch can size its plan from it. Files without a usage line are counted
as unknown. Only files written by this run count: verdicts an incremental run
carried from an earlier one keep their old timestamps and are left out, as is
anything older than the run's scope.md.
"""
import argparse, os, re, statistics

def tokens(text):
    m = re.search(r"usage:\s*([\d.,]+)\s*([kKmM]?)\s*tokens", text)
    if not m: return None
    n = float(m.group(1).replace(",", ""))
    return int(n * {"k": 1e3, "m": 1e6}.get(m.group(2).lower(), 1))

def seconds(text):
    m = re.search(r"usage:[^\n]*tokens,\s*([^\n]+)", text)
    if not m: return None
    d = m.group(1)
    parts = re.findall(r"([\d.]+)\s*(h|m|s)", d)
    if not parts: return None
    return sum(float(v) * {"h": 3600, "m": 60, "s": 1}[u] for v, u in parts)

def fmt_t(n): return f"{n / 1000:,.0f}k"
def fmt_s(s): return f"{int(s // 60)}m {int(s % 60):02d}s"

def table(title, rows):
    out = [f"### {title}", "", "| scope | model | instances | tokens | total time | median time | unknown |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for (scope, model), r in sorted(rows.items(), key=lambda kv: -sum(kv[1]["tokens"])):
        t, d = r["tokens"], r["secs"]
        out.append(f"| {scope} | {model} | {r['n']} | {fmt_t(sum(t)) if t else '-'} | {fmt_s(sum(d)) if d else '-'} | {fmt_s(statistics.median(d)) if d else '-'} | {r['unknown']} |")
    tok = sum(sum(r["tokens"]) for r in rows.values())
    out += ["", f"Total: {sum(r['n'] for r in rows.values())} instances, {fmt_t(tok)} tokens.", ""]
    return out

def collect(paths, key):
    rows = {}
    for p in paths:
        text = open(p, encoding="utf-8", errors="ignore").read(800)
        scope, model = key(p, text)
        r = rows.setdefault((scope, model), {"n": 0, "tokens": [], "secs": [], "unknown": 0})
        r["n"] += 1
        t, s = tokens(text), seconds(text)
        if t is None: r["unknown"] += 1
        else: r["tokens"].append(t)
        if s is not None: r["secs"].append(s)
    return rows

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run"); ap.add_argument("--append", action="store_true")
    a = ap.parse_args()
    scope = os.path.join(a.run, "scope.md")
    since = os.path.getmtime(scope) if os.path.exists(scope) else 0
    def files(d):
        d = os.path.join(a.run, d)
        if not os.path.isdir(d): return []
        return [p for p in (os.path.join(d, n) for n in sorted(os.listdir(d)) if n.endswith(".md")) if os.path.getmtime(p) >= since]
    def raw_key(p, text):
        lens = re.search(r"^# (\S+) on", text, re.M); model = re.search(r"model:\s*(\S+)", text)
        return (lens.group(1) if lens else os.path.basename(p)[:-3]), (model.group(1) if model else "?")
    def verify_key(_p, text):
        model = re.search(r"model:\s*(\S+)", text)
        return "verifier", (model.group(1) if model else "?")
    out = ["## Actual usage", ""]
    out += table("Reviewers", collect(files("raw"), raw_key))
    out += table("Verifiers", collect(files("verify"), verify_key))
    text = "\n".join(out).rstrip() + "\n"
    print(text, end="")
    if a.append:
        p = os.path.join(a.run, "plan.md")
        old = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
        old = re.split(r"\n## Actual usage\n", old)[0].rstrip("\n")
        open(p, "w", encoding="utf-8").write(old + "\n\n" + text)

if __name__ == "__main__":
    main()

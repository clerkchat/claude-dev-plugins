#!/usr/bin/env python3
"""Measure a unified diff per file and decide exclusions.

Usage: measure-patch.py PATCH [--exclude GLOB ...] [--tsv files.tsv] [--md scope-table.md]

For each file in the patch: bytes of its hunks, added and removed lines, an
estimated token count (bytes / 4), and an exclusion reason when one applies.
Default exclusions: lockfiles, build output, generated and minified files,
snapshots, files over 10,000 bytes averaging more than 300 bytes per changed
line, and data files (json, csv, yaml, yml, sql, txt, tsv, ndjson) over 500
changed lines or 40,000 bytes. Extra globs come from --exclude and match the
full repo-relative path (fnmatch, so ** behaves like *).
"""
import argparse, fnmatch, re, sys

DEFAULT_GLOBS = ["**/*.lock","*.lock","**/*-lock.json","*-lock.json","**/yarn.lock","yarn.lock","**/dist/**","dist/**","**/build/**","build/**","**/*.generated.*","*.generated.*","**/__snapshots__/**","**/*.snap","*.snap","**/*.min.*","*.min.*"]
DATA_EXT = (".json",".csv",".yaml",".yml",".sql",".txt",".tsv",".ndjson")

def measure(path):
    files, cur = [], None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = re.match(r"^diff --git a/(.*?) b/(.*)$", line)
            if m:
                cur = {"file": m.group(2).strip(), "bytes": 0, "added": 0, "removed": 0}
                files.append(cur); continue
            if cur is None: continue
            cur["bytes"] += len(line.encode("utf-8"))
            if line.startswith("+") and not line.startswith("+++"): cur["added"] += 1
            elif line.startswith("-") and not line.startswith("---"): cur["removed"] += 1
    return files

def reason(f, globs):
    p = f["file"]
    for g in globs:
        if fnmatch.fnmatch(p, g): return f"glob {g}"
    changed = f["added"] + f["removed"]
    if f["bytes"] > 10000 and changed and f["bytes"] / changed > 300: return "generated or minified (bytes per line)"
    if p.lower().endswith(DATA_EXT) and (changed > 500 or f["bytes"] > 40000): return "data file over size limit"
    return ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patch"); ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--tsv"); ap.add_argument("--md")
    a = ap.parse_args()
    globs = DEFAULT_GLOBS + a.exclude
    files = measure(a.patch)
    for f in files:
        f["tokens"] = f["bytes"] // 4
        f["excluded"] = reason(f, globs)
    inc = [f for f in files if not f["excluded"]]; exc = [f for f in files if f["excluded"]]
    rows = ["file\tbytes\tadded\tremoved\ttokens\texcluded"] + [f"{f['file']}\t{f['bytes']}\t{f['added']}\t{f['removed']}\t{f['tokens']}\t{f['excluded']}" for f in sorted(files, key=lambda x: -x['tokens'])]
    if a.tsv: open(a.tsv,"w").write("\n".join(rows)+"\n")
    md = [f"files: {len(files)}, included: {len(inc)} (~{sum(f['tokens'] for f in inc):,} tokens), excluded: {len(exc)} (~{sum(f['tokens'] for f in exc):,} tokens)", "", "## Excluded", "| file | tokens | lines | reason |", "| --- | --- | --- | --- |"]
    md += [f"| {f['file']} | {f['tokens']:,} | +{f['added']} -{f['removed']} | {f['excluded']} |" for f in sorted(exc, key=lambda x:-x['tokens'])] or ["| none | | | |"]
    md += ["", "## Included", "| file | tokens | lines |", "| --- | --- | --- |"] + [f"| {f['file']} | {f['tokens']:,} | +{f['added']} -{f['removed']} |" for f in sorted(inc, key=lambda x:-x['tokens'])]
    text = "\n".join(md)
    if a.md: open(a.md,"w").write(text+"\n")
    print(md[0])
    if not a.tsv and not a.md: print(text)

if __name__ == "__main__": main()

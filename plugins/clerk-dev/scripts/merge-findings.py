#!/usr/bin/env python3
"""Parse ```findings blocks from lens agent output files and merge duplicates.

Usage: merge-findings.py RAW_DIR [-o merged.md] [--json merged.json]
       [--readable so-far.md --title "..." --pending "part a, part b"]

--readable renders the merged findings as prose for a reader, grouped by
severity, with no scores or tags, in the same shape as the final report. It is
meant for a mid-run "what have we found so far" view, so it states that the
findings are unverified and lists the parts still pending.

Findings are the list entries inside fenced blocks that open with ```findings.
Each entry starts with "- lens:" and continues with "  key: value" lines; a value
may wrap onto following lines that are indented deeper than the key. Two
findings merge when they name the same file and their line ranges overlap or
sit within 3 lines of each other. The merged entry keeps the highest severity
and confidence, the union of lenses, slices, and evidence, and the claim of the
highest-confidence source. Of the scope labels it keeps the origin closest to
the branch (new, then worsened, then existing), the largest fix size, and every
distinct follow-up. Merged tech-debt findings keep the larger `saves`
estimate. A tech-debt finding (one with a `debt` label) never merges
with a finding about a defect, so a cleanup proposal cannot hide a bug on the
same lines or take over its text. Output is Markdown in the same entry format plus a
per-lens merge count, so a verifier or a human can read it unchanged.
"""
import argparse, json, os, re, sys
from collections import defaultdict

SEVERITY_RANK = {"blocker": 3, "major": 2, "minor": 1}
FIELDS = ["id","sources","source","author","url","github_id","replies","github_state","duplicate_of","related_to","lens","slice","severity","confidence","file","line","end_line","title","surfaced_by","origin","fix_size","follow_up","debt","saves","claim","context","what_changed","scenario","steps","impact","uncertainty","snippet","fix","evidence","caveat"]
LIST_FIELDS = {"steps"}
ORIGIN_RANK = {"new": 3, "worsened": 2, "existing": 1}
SIZE_RANK = {"trivial": 1, "small": 2, "medium": 3, "large": 4}
DEBT_KINDS = ("cleanup", "simplify", "refactor")

def parse_blocks(text):
    blocks, inside, buf = [], False, []
    for line in text.splitlines():
        if not inside and re.match(r"^```\s*findings\s*$", line):
            inside, buf = True, []
            continue
        if inside and re.match(r"^```\s*$", line):
            inside = False
            blocks.append(buf)
            continue
        if inside:
            buf.append(line)
    return blocks

def value(text):
    """A field's inline text. Reviewers sometimes open a multi-line field the
    YAML way (`steps: |`); the indicator is markup, not content."""
    text = text.strip()
    return "" if re.fullmatch(r"[|>][-+]?", text) else text

def parse_entries(lines, source):
    entries, cur, key = [], None, None
    for raw in lines:
        if not raw.strip():
            continue
        m = re.match(r"^-\s+([a-z_]+):\s*(.*)$", raw)
        if m:
            if cur: entries.append(cur)
            cur, key = {"_source": source}, m.group(1)
            cur[key] = value(m.group(2))
            continue
        m = re.match(r"^\s{1,4}([a-z_]+):\s*(.*)$", raw)
        if m and cur is not None and m.group(1) in FIELDS:
            key = m.group(1)
            cur[key] = value(m.group(2))
            continue
        if cur is not None and key:
            if key in LIST_FIELDS and re.match(r"^\s*(\d+[.)]|-)\s+", raw):
                cur[key] = (cur[key] + "\n" + raw.strip()).strip()
            else:
                cur[key] = (cur[key] + " " + raw.strip()).strip()
    if cur: entries.append(cur)
    return entries

def norm(e):
    e["file"] = re.sub(r"^\./", "", e.get("file","")).strip("`")
    try: e["confidence"] = int(re.sub(r"\D","", str(e.get("confidence","0"))) or 0)
    except ValueError: e["confidence"] = 0
    def num(v):
        m = re.search(r"\d+", str(v or ""))
        return int(m.group()) if m else None
    line = e.get("line","")
    rng = re.match(r"^\s*(\d+)\s*(?:-|to)\s*(\d+)", str(line))
    e["line"] = int(rng.group(1)) if rng else num(line)
    e["end_line"] = int(rng.group(2)) if rng else (num(e.get("end_line")) or e["line"])
    e["severity"] = (e.get("severity","minor").lower().strip())
    if e["severity"] not in SEVERITY_RANK: e["severity"] = "minor"
    e["lenses"] = {l.strip() for l in re.split(r"[,/]", e.get("lens","?")) if l.strip()}
    e["slices"] = {s.strip() for s in re.split(r"[,/]", e.get("slice","whole")) if s.strip()}
    e["evidence_all"] = [e.get("evidence","")] if e.get("evidence") else []
    e["sources"] = [e["_source"]]
    o = str(e.get("origin", "")).lower().strip()
    e["origin"] = o if o in ORIGIN_RANK else ""
    z = str(e.get("fix_size", "")).lower().strip()
    e["fix_size"] = z if z in SIZE_RANK else ""
    f = str(e.get("follow_up", "")).strip()
    e["follow_up"] = "" if f.lower() in ("", "none", "n/a") else f
    d = str(e.get("debt", "")).lower().strip()
    e["debt"] = d if d in DEBT_KINDS else ""
    sv = re.search(r"\d+", str(e.get("saves", "")))
    e["saves"] = int(sv.group()) if sv and e["debt"] else 0
    return e

def overlaps(a, b, slack=3):
    if a["file"] != b["file"] or a["line"] is None or b["line"] is None: return False
    if bool(a["debt"]) != bool(b["debt"]): return False
    return a["line"] <= b["end_line"] + slack and b["line"] <= a["end_line"] + slack

def merge(into, e):
    if e["confidence"] > into["confidence"]:
        for k in ("title","claim","context","what_changed","scenario","steps","impact","uncertainty","snippet","fix","debt"):
            if e.get(k): into[k] = e[k]
        into["confidence"] = e["confidence"]
    if SEVERITY_RANK[e["severity"]] > SEVERITY_RANK[into["severity"]]: into["severity"] = e["severity"]
    into["lenses"] |= e["lenses"]; into["slices"] |= e["slices"]
    into["evidence_all"] += e["evidence_all"]; into["sources"] += e["sources"]
    into["line"] = min(into["line"], e["line"]); into["end_line"] = max(into["end_line"], e["end_line"])
    if ORIGIN_RANK.get(e["origin"], 0) > ORIGIN_RANK.get(into["origin"], 0): into["origin"] = e["origin"]
    if SIZE_RANK.get(e["fix_size"], 0) > SIZE_RANK.get(into["fix_size"], 0): into["fix_size"] = e["fix_size"]
    into["saves"] = max(into["saves"], e["saves"])
    if e["follow_up"] and e["follow_up"] not in into["follow_up"]:
        into["follow_up"] = "; ".join(x for x in (into["follow_up"], e["follow_up"]) if x)

def render_readable(merged, title, pending, per_file):
    out=[f"# {title}", "", "Unverified. These are the reviewers' raw findings before the verification pass; some will be rejected or downgraded. An area with no findings may simply not have been reviewed yet.", ""]
    if pending.strip():
        out += [f"Still to review: {pending.strip()}.", ""]
    done = sum(1 for v in per_file.values())
    out += [f"Reviewers finished: {done}. Findings: {len(merged)}.", ""]
    groups=[("Fix before merging", lambda m: m["severity"] in ("blocker","major")), ("Worth a look", lambda m: m["severity"]=="minor")]
    for heading, pred in groups:
        items=[m for m in merged if pred(m)]
        if not items: continue
        out += [f"## {heading}", ""]
        for m in items:
            loc = f"{m['file']}:{m['line']}" if m['line'] else m['file']
            out += [f"**{m.get('claim','').rstrip('.')}**", loc, m.get("scenario",""), ""]
            if m.get("fix") and m["fix"].lower() != "none obvious":
                out += [f"Suggested: {m['fix']}", ""]
    out += ["Scores, lens attribution, and evidence: merged.md. Raw reviewer output: raw/.", ""]
    return "\n".join(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw_dir"); ap.add_argument("-o","--out"); ap.add_argument("--json")
    ap.add_argument("--readable"); ap.add_argument("--title", default="Findings so far"); ap.add_argument("--pending", default="")
    a = ap.parse_args()
    findings, per_file = [], {}
    for name in sorted(os.listdir(a.raw_dir)):
        if not name.endswith(".md"): continue
        text = open(os.path.join(a.raw_dir, name), encoding="utf-8").read()
        n = 0
        for block in parse_blocks(text):
            for e in parse_entries(block, name):
                findings.append(norm(e)); n += 1
        per_file[name] = n
    merged, merges_by_lens = [], defaultdict(int)
    for e in sorted(findings, key=lambda x: (x["file"], x["line"] or 0)):
        target = next((m for m in merged if overlaps(m, e)), None)
        if target:
            merge(target, e)
            for l in e["lenses"]: merges_by_lens[l] += 1
        else:
            merged.append(e)
    merged.sort(key=lambda x: (-SEVERITY_RANK[x["severity"]], -x["confidence"], x["file"], x["line"] or 0))
    out = []
    out.append(f"# Merged findings\n\nparsed: {len(findings)} findings from {sum(1 for v in per_file.values() if v)} of {len(per_file)} files; merged into {len(merged)}\n")
    out.append("per file: " + ", ".join(f"{k} {v}" for k,v in per_file.items()) + "\n")
    out.append("merges per lens: " + (", ".join(f"{k} {v}" for k,v in sorted(merges_by_lens.items())) or "none") + "\n")
    out.append("```findings")
    for i, m in enumerate(merged, 1):
        rng = f"{m['line']}" + (f"\n  end_line: {m['end_line']}" if m["end_line"] and m["end_line"] != m["line"] else "")
        debt = (f"\n  debt: {m['debt']}" if m["debt"] else "") + (f"\n  saves: ~{m['saves']}" if m["saves"] else "")
        out.append(f"- id: {i}\n  lens: {', '.join(sorted(m['lenses']))}\n  slice: {', '.join(sorted(m['slices']))}\n  severity: {m['severity']}\n  confidence: {m['confidence']}\n  file: {m['file']}\n  line: {rng}\n  title: {m.get('title','')}\n  origin: {m['origin']}\n  fix_size: {m['fix_size']}\n  follow_up: {m['follow_up'] or 'none'}{debt}\n  claim: {m.get('claim','')}\n  context: {m.get('context','') or m.get('what_changed','')}\n  scenario: {m.get('scenario','')}\n  steps: {m.get('steps','').replace(chr(10), chr(10)+'    ')}\n  impact: {m.get('impact','')}\n  uncertainty: {m.get('uncertainty','')}\n  snippet: {m.get('snippet','')}\n  fix: {m.get('fix','')}\n  evidence: {' | '.join(m['evidence_all'])}\n  sources: {', '.join(m['sources'])}\n")
    out.append("```")
    text = "\n".join(out)
    if a.out: open(a.out,"w",encoding="utf-8").write(text)
    else: print(text)
    if a.readable:
        open(a.readable,"w",encoding="utf-8").write(render_readable(merged, a.title, a.pending, per_file))
    if a.json:
        json.dump([{k:(sorted(v) if isinstance(v,set) else v) for k,v in m.items() if not k.startswith("_")} for m in merged], open(a.json,"w"), indent=1)
    print(f"parsed {len(findings)} findings from {len(per_file)} files, merged into {len(merged)}", file=sys.stderr)

if __name__ == "__main__": main()

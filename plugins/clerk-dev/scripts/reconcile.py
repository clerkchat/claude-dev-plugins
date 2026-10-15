#!/usr/bin/env python3
"""Match a review run's merged findings against a previous run's.

Usage:
  reconcile.py PREV_RUN CUR_RUN                 # propose matches
  reconcile.py PREV_RUN CUR_RUN --judged FILE   # apply judge decisions, finalize
  reconcile.py PREV_RUN CUR_RUN --seed          # carry statuses and resolutions
  reconcile.py --append NEW_MERGED CUR_RUN [--judged FILE]  # fold in delta findings

Reviewers never see this; it runs after merge. Matching is mechanical first:
same file and either lines within 15 of each other or claim text overlap of
at least 0.5 is a match; weaker overlaps (0.25 to 0.5 in the same file, or at
least 0.6 across files) become candidates for a judge to decide.

Writes CUR_RUN/reconcile/:
  matches.tsv     cur_id, prev_id, how, prev_number, prev_status, prev_ref
  candidates.tsv  cur_id, prev_id, score (only before --judged)
  unmatched.tsv   prev findings with no match: prev_id, prev_number,
                  prev_status, prev_ref, file:line, title
  previous.txt    the previous run's label
--judged FILE takes lines "cur_id<TAB>prev_id<TAB>same|different" and moves
"same" pairs into matches.tsv.
--append (incremental runs after carry.py, and recheck findings): two
phases, see append_mode. Phase 2 also writes reconcile/appended-map.tsv
(new_id in NEW_MERGED, merged_id it was given). Nothing is folded or reopened without a judged
verdict; the mechanical match only proposes candidates.
Use --append for every finding added to a run after the merge step (a
recheck's new findings too), never a hand edit: it keeps every entry inside
the findings block, picks ids after the highest one in the file, and repairs
entries an earlier edit left outside the block.
--seed writes CUR_RUN/status.tsv rows for matches whose previous status was
in-progress, wont-fix, or deferred (open needs no row) (a previous "fixed" that is found
again is reopened, so it is not carried), and copies previous resolution
text into CUR_RUN/resolution/ prefixed with the previous run's label.
"""
import argparse, importlib.util, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mf", os.path.join(HERE, "merge-findings.py"))
mf = importlib.util.module_from_spec(spec); spec.loader.exec_module(mf)

STOP = set("the a an and or of to in on for is are be by with that this it as at from not no when so then than its into".split())

def load(run):
    text = open(os.path.join(run, "merged.md"), encoding="utf-8").read()
    out = {}
    for block in mf.parse_blocks(text):
        for e in mf.parse_entries(block, "m"):
            e = mf.norm(e)
            e["id"] = int(re.sub(r"\D", "", str(e.get("id", "0"))) or 0)
            out[e["id"]] = e
    # overrides carry better titles
    od = os.path.join(run, "overrides")
    if os.path.isdir(od):
        for n in os.listdir(od):
            m = re.match(r"^(\d+)\.md$", n)
            if m and int(m.group(1)) in out:
                t = re.search(r"^title:\s*(.+)$", open(os.path.join(od, n)).read(), re.M)
                if t: out[int(m.group(1))]["title"] = t.group(1).strip()
    tt = os.path.join(run, "titles.tsv")
    if os.path.exists(tt):
        for line in open(tt):
            f = line.rstrip("\n").split("\t", 1)
            if len(f) == 2 and f[0].isdigit() and int(f[0]) in out and not out[int(f[0])].get("title"):
                out[int(f[0])]["title"] = f[1]
    return out

def tsv(path, skip_header=True):
    if not os.path.exists(path): return []
    rows = [l.rstrip("\n").split("\t") for l in open(path, encoding="utf-8")]
    return rows[1:] if skip_header and rows and not rows[0][0].isdigit() else rows

def words(e):
    t = (e.get("title", "") + " " + e.get("claim", "")).lower()
    return {w for w in re.findall(r"[a-z_][a-z0-9_]{2,}", t) if w not in STOP}

def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0

def normalize_merged(text):
    """Return (header, entries) with every `- id:` entry in the file, inside
    or outside a fenced block, in id order. Entries written after the closing
    fence by an earlier hand edit are recovered here."""
    i = text.find("```findings")
    header = text[:i] if i >= 0 else ""
    body = text[i:] if i >= 0 else text
    body = re.sub(r"^```[a-z]*\s*$", "", body, flags=re.M)
    chunks = [c.strip("\n") for c in re.split(r"\n(?=- id: \d+\n)", "\n" + body) if re.match(r"^- id: \d+\n", c.strip("\n") + "\n")]
    byid = {}
    for c in chunks:
        byid[int(re.match(r"^- id: (\d+)", c).group(1))] = c
    return header, [byid[k] for k in sorted(byid)]

def write_merged(path, header, entries):
    open(path, "w", encoding="utf-8").write(header.rstrip("\n") + "\n\n```findings\n" + "\n\n".join(entries) + "\n```\n")

VERDICTS = ("duplicate", "regressed", "stale", "different")

def _cause(n):
    claim = re.split(r"(?<=[.!?])\s", str(n["_raw"].get("claim", "")).strip())[0]
    return f"{n['_raw'].get('lens','')}|{n['file']}:{n['line'] or ''}|{claim}".replace("\t", " ")

def append_mode(new_path, cur, judged=None):
    """Fold findings from a delta review (or a recheck) into a run.

    Phase 1, without --judged: write reconcile/append-candidates.tsv, the
    carried findings each new one might duplicate (same file and near lines,
    or wording overlap), with the carried status and any recheck outcome.
    Nothing changes. If there are no candidates at all, phase 2 runs at once
    with every new finding appended.

    Phase 2, with --judged FILE (new_id, carried_id, verdict): duplicate folds
    the new evidence into the carried finding; regressed does that and reopens
    a carried finding marked fixed, recording what was found; stale drops the
    new finding (the fix already covered it); different, or no row, appends it
    as a new finding with related_to set when it had a candidate. A recheck
    that found the carried finding resolved (reconcile/since.tsv) wins over
    regressed: the new finding is appended as different instead."""
    header, entries = normalize_merged(open(os.path.join(cur, "merged.md"), encoding="utf-8").read())
    carried = load(cur)
    new = {}
    for block in mf.parse_blocks(open(new_path, encoding="utf-8").read()):
        for e in mf.parse_entries(block, "n"):
            raw = e.copy()
            e = mf.norm(e); e["id"] = int(re.sub(r"\D", "", str(e.get("id", "0"))) or 0); e["_raw"] = raw
            new[e["id"]] = e
    rd = os.path.join(cur, "reconcile"); os.makedirs(rd, exist_ok=True)
    st_path = os.path.join(cur, "status.tsv")
    st_lines = open(st_path).read().splitlines() if os.path.exists(st_path) else ["merged_id\tstatus\tref\tdate"]
    status = {int(l.split("\t")[0]): l for l in st_lines[1:] if l and l.split("\t")[0].isdigit()}
    since = {}
    sp = os.path.join(rd, "since.tsv")
    if os.path.exists(sp):
        for l in open(sp):
            f = l.rstrip("\n").split("\t")
            if f and f[0].isdigit(): since[int(f[0])] = f[1] if len(f) > 1 else ""
    # candidates
    cands = {}
    for nid, n in new.items():
        nw = words(n); scored = []
        for cid, c in carried.items():
            sim = jac(nw, words(c))
            same = n["file"] == c["file"]
            near = same and n["line"] and c["line"] and abs(n["line"] - c["line"]) <= 15
            if (same and (near or sim >= 0.25)) or sim >= 0.5:
                scored.append((sim + (0.5 if near else 0) + (0.2 if same else 0), cid))
        if scored: cands[nid] = [cid for _, cid in sorted(scored, reverse=True)[:3]]
    if judged is None and cands:
        with open(os.path.join(rd, "append-candidates.tsv"), "w") as fh:
            fh.write("new_id\tcarried_id\tcarried_status\trecheck\n")
            for nid in sorted(cands):
                for cid in cands[nid]:
                    st = status.get(cid, f"{cid}\topen").split("\t")[1]
                    fh.write(f"{nid}\t{cid}\t{st}\t{since.get(cid, '')}\n")
        print(f"{len(cands)} of {len(new)} new findings have candidate carried matches; judge reconcile/append-candidates.tsv, then rerun with --judged", file=sys.stderr)
        return
    verdict = {}
    if judged:
        for l in open(judged):
            f = l.rstrip("\n").split("\t")
            if len(f) >= 3 and f[0].isdigit() and f[2].strip() in VERDICTS: verdict[int(f[0])] = (int(f[1]), f[2].strip())
    mpath = os.path.join(rd, "matches.tsv")
    mrows = [l.rstrip("\n").split("\t") for l in open(mpath)] if os.path.exists(mpath) else [["cur_id","prev_id","how","prev_number","prev_status","prev_ref","cause"]]
    if len(mrows[0]) < 7: mrows[0] = mrows[0][:6] + ["cause"]
    next_id = max([int(re.match(r"^- id: (\d+)", c).group(1)) for c in entries] or [0]) + 1
    appended, dropped, counts, amap = [], [], {v: 0 for v in VERDICTS}, []
    for nid, n in sorted(new.items()):
        cid, v = verdict.get(nid, (None, "different"))
        if v == "regressed" and since.get(cid) == "resolved":
            print(f"new finding {nid}: judged a regression of {cid}, but its recheck found it resolved; adding it as a separate finding", file=sys.stderr)
            v = "different"
        counts[v] += 1
        if v in ("duplicate", "regressed"):
            ev = str(n["_raw"].get("evidence", "")).strip()
            for k, c in enumerate(entries):
                if c.startswith(f"- id: {cid}\n") and ev:
                    entries[k] = re.sub(r"(\n  evidence: )([^\n]*)", lambda m: m.group(1) + m.group(2) + " | " + ev, c, count=1)
            if v == "regressed" and cid in status and status[cid].split("\t")[1] == "fixed":
                status[cid] = f"{cid}\topen\t\t"
                for r in mrows:
                    if r[0] == str(cid):
                        r[:] = (r + [""] * 7)[:7]; r[2] = "reopened"; r[6] = _cause(n)
            continue
        if v == "stale":
            dropped.append((nid, cid)); continue
        raw = n["_raw"]; raw["id"] = str(next_id)
        rel = cid if cid is not None else (cands.get(nid) or [None])[0]
        if rel is not None and v == "different" and nid in cands: raw["related_to"] = str(rel)
        lines = [f"- id: {next_id}"] + [f"  {k}: {val}" for k, val in raw.items() if k not in ("id", "_source") and val]
        entries.append("\n".join(lines))
        appended.append(next_id); amap.append((nid, next_id)); next_id += 1
    write_merged(os.path.join(cur, "merged.md"), header, entries)
    with open(mpath, "w") as fh:
        for r in mrows: fh.write("\t".join(r) + "\n")
    with open(st_path, "w") as fh:
        fh.write(st_lines[0] + "\n")
        for k in sorted(status): fh.write(status[k] + "\n")
    ap_path = os.path.join(rd, "appended.tsv")
    earlier = [l.strip() for l in open(ap_path).read().splitlines()[1:] if l.strip()] if os.path.exists(ap_path) else []
    with open(ap_path, "w") as fh:
        fh.write("merged_id\n" + "".join(f"{i}\n" for i in dict.fromkeys(earlier + [str(i) for i in appended])))
    with open(os.path.join(rd, "appended-map.tsv"), "w") as fh:
        fh.write("new_id\tmerged_id\n" + "".join(f"{a}\t{b}\n" for a, b in amap))
    with open(os.path.join(rd, "dropped.tsv"), "a") as fh:
        for nid, cid in dropped: fh.write(f"{nid}\t{cid}\tstale\n")
    print(f"incremental: {len(new)} new findings: {counts['duplicate']} duplicates, {counts['regressed']} regressions, "
          f"{counts['stale']} already covered by a fix, {len(appended)} appended", file=sys.stderr)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prev", nargs="?", help="previous run (omit with --append)")
    ap.add_argument("cur", help="current run")
    ap.add_argument("--append", metavar="NEW_MERGED", help="fold findings from NEW_MERGED into CUR_RUN")
    ap.add_argument("--judged"); ap.add_argument("--seed", action="store_true")
    a = ap.parse_args()
    if a.append:
        if a.prev: ap.error("--append takes NEW_MERGED and CUR_RUN only")
        return append_mode(a.append, a.cur, a.judged)
    if not a.prev: ap.error("PREV_RUN and CUR_RUN are required without --append")
    rd = os.path.join(a.cur, "reconcile"); os.makedirs(rd, exist_ok=True)
    prev, cur = load(a.prev), load(a.cur)
    pstatus = {int(r[0]): r for r in tsv(os.path.join(a.prev, "status.tsv")) if r and r[0].isdigit()}
    pnum = {int(r[1]): r[0] for r in tsv(os.path.join(a.prev, "numbers.tsv")) if len(r) > 1 and r[1].isdigit()}
    def pinfo(pid):
        s = pstatus.get(pid)
        return (pnum.get(pid, ""), s[1] if s else "open", s[2] if s and len(s) > 2 else "")
    label = os.path.basename(os.path.normpath(os.path.realpath(a.prev)))
    open(os.path.join(rd, "previous.txt"), "w").write(label + "\n")

    if a.seed:
        matches = tsv(os.path.join(rd, "matches.tsv"))
        st_path = os.path.join(a.cur, "status.tsv")
        existing = {int(r[0]) for r in tsv(st_path) if r and r[0].isdigit()}
        rows = [l for l in open(st_path)] if os.path.exists(st_path) else ["merged_id\tstatus\tref\tdate\n"]
        os.makedirs(os.path.join(a.cur, "resolution"), exist_ok=True)
        carried = 0
        for r in matches:
            cid, pid, status, ref = int(r[0]), int(r[1]), r[4], r[5] if len(r) > 5 else ""
            if status in ("in-progress", "wont-fix", "deferred") and cid not in existing:
                rows.append(f"{cid}\t{status}\t{ref}\t\n"); carried += 1
            src = os.path.join(a.prev, "resolution", f"{pid}.md")
            dst = os.path.join(a.cur, "resolution", f"{cid}.md")
            if os.path.exists(src) and not os.path.exists(dst):
                open(dst, "w").write(f"From the review in {label}:\n\n" + open(src).read())
        open(st_path, "w").writelines(rows)
        print(f"seeded {carried} statuses from {label}", file=sys.stderr)
        return

    if a.judged:
        matches = tsv(os.path.join(rd, "matches.tsv"))
        for line in open(a.judged):
            f = line.rstrip("\n").split("\t")
            if len(f) >= 3 and f[2].strip() == "same":
                cid, pid = int(f[0]), int(f[1])
                if not any(int(m[0]) == cid for m in matches) and not any(int(m[1]) == pid for m in matches):
                    n, s, ref = pinfo(pid); matches.append([str(cid), str(pid), "judge", n, s, ref])
        cands = []
    else:
        matches, cands, used_p, used_c = [], [], set(), set()
        pairs = []
        for cid, c in cur.items():
            cw = words(c)
            for pid, p in prev.items():
                sim = jac(cw, words(p))
                same_file = c["file"] == p["file"]
                near = same_file and c["line"] and p["line"] and abs(c["line"] - p["line"]) <= 15
                if same_file and (near and sim >= 0.2 or sim >= 0.5):
                    pairs.append((2 + sim, cid, pid, "line" if near else "text"))
                elif (same_file and sim >= 0.25) or (not same_file and sim >= 0.6):
                    cands.append((sim, cid, pid))
        for score, cid, pid, how in sorted(pairs, reverse=True):
            if cid in used_c or pid in used_p: continue
            used_c.add(cid); used_p.add(pid)
            n, s, ref = pinfo(pid); matches.append([str(cid), str(pid), how, n, s, ref])
        cands = [(s, c, p) for s, c, p in sorted(cands, reverse=True) if c not in used_c and p not in used_p]
    with open(os.path.join(rd, "matches.tsv"), "w") as fh:
        fh.write("cur_id\tprev_id\thow\tprev_number\tprev_status\tprev_ref\n")
        for m in matches: fh.write("\t".join(m) + "\n")
    with open(os.path.join(rd, "candidates.tsv"), "w") as fh:
        fh.write("cur_id\tprev_id\tscore\n")
        for s, c, p in cands: fh.write(f"{c}\t{p}\t{s:.2f}\n")
    matched_prev = {int(m[1]) for m in matches}
    with open(os.path.join(rd, "unmatched.tsv"), "w") as fh:
        fh.write("prev_id\tprev_number\tprev_status\tprev_ref\tlocation\ttitle\n")
        for pid, p in sorted(prev.items()):
            if pid in matched_prev or pid not in pnum: continue
            n, s, ref = pinfo(pid)
            fh.write(f"{pid}\t{n}\t{s}\t{ref}\t{p['file']}:{p['line']}\t{p.get('title') or p.get('claim','')[:80]}\n")
    print(f"previous {label}: {len(matches)} matched, {len(cands)} candidates for judging, "
          f"{sum(1 for pid in prev if pid not in matched_prev and pid in pnum)} reported earlier and not matched", file=sys.stderr)

if __name__ == "__main__": main()

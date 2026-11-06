#!/usr/bin/env python3
"""Match a review run's merged findings against a previous run's.

Usage:
  reconcile.py PREV_RUN CUR_RUN                 # propose matches
  reconcile.py PREV_RUN CUR_RUN --judged FILE   # apply judge decisions, finalize
  reconcile.py PREV_RUN CUR_RUN --seed          # carry statuses, resolutions, and posted findings
  reconcile.py --append NEW_MERGED CUR_RUN [--judged FILE]  # fold in delta findings
  reconcile.py PREV_RUN CUR_RUN --append NEW_MERGED [--judged FILE]  # fold in rechecked findings

Reviewers never see this; it runs after merge. Matching is mechanical first:
same file and either lines within 15 of each other or claim text overlap of
at least 0.5 is a match; weaker overlaps (0.25 to 0.5 in the same file, or at
least 0.6 across files) become candidates for a judge to decide.

Writes CUR_RUN/reconcile/:
  matches.tsv     cur_id, prev_id, how, prev_number, prev_status, prev_ref, cause
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
With PREV_RUN, --append takes NEW_MERGED as earlier findings a recheck
reopened, each under its id in PREV_RUN: every one it appends gets a
matches.tsv row (how = recheck) and its posted files, as --seed copies them.
Use --append for every finding added to a run after the merge step (a
recheck's new findings too), never a hand edit: it keeps every entry inside
the findings block, picks ids after the highest one in the file, and repairs
entries an earlier edit left outside the block.
--seed writes CUR_RUN/status.tsv rows for matches whose previous status was
in-progress, wont-fix, or deferred (open needs no row) (a previous "fixed" that is found
again is reopened, so it is not carried), and copies previous resolution
text into CUR_RUN/resolution/ prefixed with the previous run's label. It also
copies each matched finding's posted.tsv row, posted/keep.tsv row, posted
text (posted/<id>.md), and closing reply (posted/close-<id>.md) under its new
id, unless the current run already has a posted.tsv row for it, and only across
a judged match, a recheck, or a line match whose wording overlaps by at least
0.5; it names the posted findings a looser match left behind. When a previous
finding posted as a thread on GitHub matched nothing, it prints "N posted
findings not found again (...)": those threads come in as pull request
comments on the next pr-comments.py fetch.
"""
import argparse, functools, os, re, shutil, sys
from collections import namedtuple
from records import load_script
import run_files as rf

mf = load_script("merge-findings.py")

STOP = set("the a an and or of to in on for is are be by with that this it as at from not no when so then than its into".split())

def load(run):
    titles, overrides = rf.read_titles(run), rf.read_overrides(run)
    out = {e["id"]: e for e in rf.read_merged(rf.merged_path(run))}
    for mid, e in out.items():
        title = overrides.get(mid, {}).get("title") or e.get("title") or titles.get(mid)
        if title: e["title"] = title
    return out

def words(e):
    t = (e.get("title", "") + " " + e.get("claim", "")).lower()
    return {w for w in re.findall(r"[a-z_][a-z0-9_]{2,}", t) if w not in STOP}

def comparable(a, b):
    return mf.is_credit(a) == mf.is_credit(b)

def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0

TEXT_MATCH = 0.5

VERDICTS = ("duplicate", "regressed", "stale", "different")
APPEND_CANDIDATE_HEADER = ("new_id", "carried_id", "carried_status", "recheck")
CANDIDATE_HEADER = ("cur_id", "prev_id", "score")

def _cause(n):
    claim = re.split(r"(?<=[.!?])\s", str(n["_raw"].get("claim", "")).strip())[0]
    return f"{n['_raw'].get('lens','')}|{n['file']}:{n['line'] or ''}|{claim}"

def judged_rows(path, key=rf.merged_key):
    if not os.path.exists(path): sys.exit(f"no judged file at {path}")
    return rf.read_rows(path, key)

def judged_verdicts(path, new, cands):
    verdict = {}
    for f in judged_rows(path):
        if len(f) < 3 or f[2] not in VERDICTS: continue
        nid, cid, v = int(f[0]), f[1], f[2]
        if not cid.isdigit() or int(cid) not in cands.get(nid, []):
            print(f"new finding {nid}: judged against {cid or 'nothing'}, which was not among its candidates; ignoring that verdict", file=sys.stderr)
            continue
        if v in ("regressed", "stale") and mf.is_credit(new[nid]):
            print(f"new finding {nid}: a credit judged {v}; treating it as a duplicate of {cid}", file=sys.stderr)
            v = "duplicate"
        verdict[nid] = (int(cid), v)
    return verdict

def read_new_findings(path):
    new = {}
    for raw in rf.raw_entries(path, "n"):
        e = mf.norm(dict(raw)); e["id"] = rf.entry_id(e) or 0; e["_raw"] = raw
        new[e["id"]] = e
    return new

def append_candidates(new, carried):
    cands = {}
    for nid, n in new.items():
        nw = words(n); scored = []
        for cid, c in carried.items():
            if not comparable(n, c): continue
            sim = jac(nw, words(c))
            same = n["file"] == c["file"]
            near = same and n["line"] and c["line"] and abs(n["line"] - c["line"]) <= 15
            if (same and (near or sim >= 0.25)) or sim >= 0.5:
                scored.append((sim + (0.5 if near else 0) + (0.2 if same else 0), cid))
        if scored: cands[nid] = [cid for _, cid in sorted(scored, reverse=True)[:3]]
    return cands

def write_append_candidates(run, cands, status, since):
    rf.write_rows(rf.reconcile_path(run, "append-candidates.tsv"), APPEND_CANDIDATE_HEADER,
                  ([str(nid), str(cid), rf.status_of(status, cid), since.get(cid, {}).get("outcome", "")] for nid in sorted(cands) for cid in cands[nid]))

def fold_into(entries, status, matches, cid, n, v):
    ev = str(n["_raw"].get("evidence", "")).strip()
    if cid in entries and ev:
        entries[cid] = re.sub(r"(\n  evidence: )([^\n]*)", lambda m: m.group(1) + m.group(2) + " | " + ev, entries[cid], count=1)
    if v == "regressed" and rf.status_of(status, cid) == "fixed":
        status[cid] = {"status": "open", "ref": "", "date": ""}
        if cid in matches: matches[cid].update(how="reopened", cause=_cause(n))

def append_entry(entries, n, related):
    mid = mf.next_entry_id(entries)
    raw = {**n["_raw"], "id": str(mid)}
    if related is not None: raw["related_to"] = str(related)
    entries[mid] = mf.format_entry([("id", mid)] + [(k, val) for k, val in raw.items() if k not in ("id", "_source") and val])
    return mid

AppendResult = namedtuple("AppendResult", "appended amap dropped counts")

def apply_verdicts(new, cands, verdict, entries, status, matches, since):
    folded = AppendResult([], {}, [], {v: 0 for v in VERDICTS})
    for nid, n in sorted(new.items()):
        cid, v = verdict.get(nid, (None, "different"))
        if v == "regressed" and since.get(cid, {}).get("outcome") == "resolved":
            print(f"new finding {nid}: judged a regression of {cid}, but its recheck found it resolved; adding it as a separate finding", file=sys.stderr)
            v = "different"
        folded.counts[v] += 1
        if v in ("duplicate", "regressed"): fold_into(entries, status, matches, cid, n, v)
        elif v == "stale": folded.dropped.append((nid, cid))
        else:
            related = (cid if cid is not None else cands[nid][0]) if nid in cands else None
            mid = append_entry(entries, n, related)
            folded.appended.append(mid); folded.amap[nid] = mid
    return folded

def write_append_results(run, folded):
    rf.write_appended(run, rf.read_appended(run) | set(folded.appended))
    rf.write_appended_map(run, folded.amap)
    with open(rf.reconcile_path(run, "dropped.tsv"), "a") as fh:
        for nid, cid in folded.dropped: fh.write(f"{nid}\t{cid}\tstale\n")

Recheck = namedtuple("Recheck", "prev pinfo")

def record_rechecks(recheck, cur, amap, matches):
    for pid, cid in amap.items(): matches[cid] = {"prev_id": str(pid), "how": "recheck", **recheck.pinfo(pid)}
    seed_postings(recheck.prev, cur, amap.items())

def append_mode(new_path, cur, judged=None, recheck=None):
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
    header, entries = mf.read_entries(rf.merged_path(cur))
    carried, new = load(cur), read_new_findings(new_path)
    status, since = rf.read_status(cur), rf.read_since(cur)
    cands = append_candidates(new, carried)
    if judged is None and cands:
        write_append_candidates(cur, cands, status, since)
        print(f"{len(cands)} of {len(new)} new findings have candidate carried matches; judge reconcile/append-candidates.tsv, then rerun with --judged", file=sys.stderr)
        return
    matches = rf.read_matches(cur)
    folded = apply_verdicts(new, cands, judged_verdicts(judged, new, cands) if judged else {}, entries, status, matches, since)
    if recheck: record_rechecks(recheck, cur, folded.amap, matches)
    mf.write_entries(rf.merged_path(cur), header, entries)
    rf.write_matches(cur, matches)
    rf.write_status(cur, status)
    write_append_results(cur, folded)
    counts = folded.counts
    print(f"incremental: {len(new)} new findings: {counts['duplicate']} duplicates, {counts['regressed']} regressions, "
          f"{counts['stale']} already covered by a fix, {len(folded.appended)} appended", file=sys.stderr)

Posting = namedtuple("Posting", "posted kept")

def read_posting(run):
    return Posting(rf.read_posted(run), rf.read_kept_open(run))

def write_posting(run, posting):
    rf.write_posted(run, posting.posted)
    if posting.kept: rf.write_kept_open(run, posting.kept)

def copy_new(src, dst):
    if os.path.exists(src) and not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy2(src, dst)

def seed_posted(prev, cur, pid, cid, prev_posting, cur_posting):
    if pid not in prev_posting.posted or cid in cur_posting.posted: return False
    cur_posting.posted[cid] = prev_posting.posted[pid]
    if pid in prev_posting.kept: cur_posting.kept[cid] = prev_posting.kept[pid]
    for path in (rf.posted_path, rf.close_text_path): copy_new(path(prev, pid), path(cur, cid))
    return True

def seed_reviews(prev, cur, rows):
    review_ids = rf.review_ids(rows)
    for rid in review_ids: copy_new(rf.kept_body_path(prev, rid), rf.kept_body_path(cur, rid))
    if review_ids: copy_new(rf.review_text_path(prev), rf.review_text_path(cur))

def seed_postings(prev, cur, pairs):
    prev_posting, cur_posting = read_posting(prev), read_posting(cur)
    seeded = [cid for pid, cid in pairs if seed_posted(prev, cur, pid, cid, prev_posting, cur_posting)]
    if seeded:
        write_posting(cur, cur_posting)
        seed_reviews(prev, cur, {cid: cur_posting.posted[cid] for cid in seeded})
    return len(seeded)

def prev_name(pid, pnum):
    return f"finding {pnum[pid]}" if pid in pnum else f"#{pid}"

def lost_line(lost, pnum):
    names = ", ".join(prev_name(pid, pnum) for pid in lost)
    return f"{len(lost)} posted findings not found again ({names}); their threads come in as pull request comments"

def loose_line(loose, pnum):
    names = ", ".join(f"{prev_name(pid, pnum)} with #{cid}" for pid, cid in loose)
    return (f"{len(loose)} posted findings matched only loosely, so their postings were not carried ({names}); "
            "their threads come in as pull request comments")

CARRIES_POSTINGS = ("judge", "recheck")

def carries_postings(how, prev_finding, cur_finding):
    if how in CARRIES_POSTINGS: return True
    return how == "line" and bool(prev_finding and cur_finding) and jac(words(cur_finding), words(prev_finding)) >= TEXT_MATCH

def confident_pairs(prev, cur, pairs, matches):
    prev_found, cur_found = load(prev), load(cur)
    return [(pid, cid) for pid, cid in pairs if carries_postings(matches[cid]["how"], prev_found.get(pid), cur_found.get(cid))]

def seed_resolution(prev, cur, pid, cid, label):
    src = os.path.join(prev, "resolution", f"{pid}.md")
    dst = os.path.join(cur, "resolution", f"{cid}.md")
    if os.path.exists(src) and not os.path.exists(dst):
        open(dst, "w").write(f"From the review in {label}:\n\n" + open(src).read())

def seed(prev, cur, label, pnum):
    matches, st = rf.read_matches(cur), rf.read_status(cur)
    os.makedirs(os.path.join(cur, "resolution"), exist_ok=True)
    carried = 0
    pairs = [(int(m["prev_id"]), cid) for cid, m in matches.items()]
    for pid, cid in pairs:
        m = matches[cid]
        if m["prev_status"] in ("in-progress", "wont-fix", "deferred") and cid not in st:
            st[cid] = {"status": m["prev_status"], "ref": m["prev_ref"], "date": ""}; carried += 1
        seed_resolution(prev, cur, pid, cid, label)
    confident = confident_pairs(prev, cur, pairs, matches)
    seeded_posted = seed_postings(prev, cur, confident)
    rf.write_status(cur, st)
    matched, prev_posted = {pid for pid, _ in pairs}, rf.read_posted(prev)
    lost = [pid for pid, row in sorted(prev_posted.items()) if rf.has_thread(row) and pid not in matched]
    loose = [(pid, cid) for pid, cid in pairs if pid in prev_posted and (pid, cid) not in confident]
    print(f"seeded {carried} statuses" + (f" and {seeded_posted} posted findings" if seeded_posted else "") + f" from {label}"
          + (f"; {lost_line(lost, pnum)}" if lost else "") + (f"; {loose_line(loose, pnum)}" if loose else ""), file=sys.stderr)

def judged_same(path):
    pairs = []
    for f in judged_rows(path, key=str):
        if len(f) < 3 or f[2] != "same": continue
        if f[0].isdigit() and f[1].isdigit(): pairs.append((int(f[0]), int(f[1])))
        else: print(f"judged row {f[0]!r}, {f[1]!r}: an id is not a number; skipped", file=sys.stderr)
    return pairs

def judged_matches(run, judged, pinfo):
    matches = rf.read_matches(run)
    for cid, pid in judged_same(judged):
        if cid not in matches and pid not in {int(m["prev_id"]) for m in matches.values()}:
            matches[cid] = {"prev_id": str(pid), "how": "judge", **pinfo(pid)}
    return matches

def proposed_matches(prev, cur, pinfo):
    pairs, cands = [], []
    for cid, c in cur.items():
        cw = words(c)
        for pid, p in prev.items():
            if not comparable(c, p): continue
            sim = jac(cw, words(p))
            same_file = c["file"] == p["file"]
            near = same_file and c["line"] and p["line"] and abs(c["line"] - p["line"]) <= 15
            if same_file and (near and sim >= 0.2 or sim >= TEXT_MATCH):
                pairs.append((2 + sim, cid, pid, "line" if near else "text"))
            elif (same_file and sim >= 0.25) or (not same_file and sim >= 0.6):
                cands.append((sim, cid, pid))
    matches, used_p = {}, set()
    for score, cid, pid, how in sorted(pairs, reverse=True):
        if cid in matches or pid in used_p: continue
        used_p.add(pid)
        matches[cid] = {"prev_id": str(pid), "how": how, **pinfo(pid)}
    return matches, [(s, c, p) for s, c, p in sorted(cands, reverse=True) if c not in matches and p not in used_p]

def unmatched(prev, matches, pnum):
    matched = {int(m["prev_id"]) for m in matches.values()}
    return {pid: p for pid, p in sorted(prev.items()) if pid not in matched and pid in pnum and not mf.is_credit(p)}

def write_unmatched(run, left, pinfo):
    rf.write_unmatched(run, {pid: {**pinfo(pid), "location": f"{p['file']}:{p['line']}", "title": p.get("title") or p.get("claim", "")[:80]}
                             for pid, p in left.items()})

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prev", nargs="?", help="previous run (with --append, the run the rechecked findings come from)")
    ap.add_argument("cur", help="current run")
    ap.add_argument("--append", metavar="NEW_MERGED", help="fold findings from NEW_MERGED into CUR_RUN")
    ap.add_argument("--judged"); ap.add_argument("--seed", action="store_true")
    a = ap.parse_args()
    pnum = rf.read_numbers(a.prev) if a.prev else {}
    pinfo = functools.partial(rf.previous_state, rf.read_status(a.prev), pnum) if a.prev else None
    if a.append: return append_mode(a.append, a.cur, a.judged, Recheck(a.prev, pinfo) if a.prev else None)
    if not a.prev: ap.error("PREV_RUN and CUR_RUN are required without --append")
    label = rf.run_label(a.prev)
    rf.write_previous(a.cur, label)
    if a.seed: return seed(a.prev, a.cur, label, pnum)
    prev, cur = load(a.prev), load(a.cur)
    matches, cands = (judged_matches(a.cur, a.judged, pinfo), []) if a.judged else proposed_matches(prev, cur, pinfo)
    rf.write_matches(a.cur, matches)
    rf.write_rows(rf.reconcile_path(a.cur, "candidates.tsv"), CANDIDATE_HEADER, [[str(c), str(p), f"{s:.2f}"] for s, c, p in cands])
    left = unmatched(prev, matches, pnum)
    write_unmatched(a.cur, left, pinfo)
    print(f"previous {label}: {len(matches)} matched, {len(cands)} candidates for judging, {len(left)} reported earlier and not matched", file=sys.stderr)

if __name__ == "__main__": main()

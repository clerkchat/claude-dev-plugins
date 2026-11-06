import json, os, re, subprocess, sys
from collections import namedtuple
from records import load_script

mf = load_script("merge-findings.py")

def read_text(path, missing=""):
    return open(path, encoding="utf-8").read().strip() if path and os.path.exists(path) else missing

def merged_key(text):
    return int(text) if text.isdigit() else None

def read_rows(path, key=merged_key):
    if not os.path.exists(path): return []
    with open(path, encoding="utf-8") as fh:
        rows = [[cell.strip() for cell in line.rstrip("\n").split("\t")] for line in fh]
    return [f for f in rows if key(f[0]) is not None]

LINE_BREAKS = re.compile(r"[\t\r\n]")

def tsv_cell(value):
    return LINE_BREAKS.sub(" ", value)

def write_rows(path, header, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in [*([header] if header else []), *rows]: fh.write("\t".join(map(tsv_cell, row)) + "\n")

def read_keyed(path, fields, key=merged_key, defaults=None):
    return {key(f[0]): {name: value or (defaults or {}).get(name, "") for name, value in zip(fields, f[1:] + [""] * len(fields))}
            for f in read_rows(path, key) if len(f) > 1}

def write_keyed(path, fields, rows, header="merged_id", order=sorted):
    write_rows(path, (header, *fields) if header else None, ([str(k)] + [rows[k].get(f, "") for f in fields] for k in order(rows)))

FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
PROSE, FENCE_LINE, FENCE_BODY = "", "fence", "body"

def closes_fence(line, fence):
    s = line.rstrip()
    return len(s) >= len(fence) and s == fence[0] * len(s)

def fenced_lines(lines):
    fence = ""
    for line in lines:
        if fence:
            if closes_fence(line, fence): fence = ""; yield line, FENCE_LINE
            else: yield line, FENCE_BODY
            continue
        m = FENCE_RE.match(line)
        if m: fence = m.group(1)
        yield line, FENCE_LINE if m else PROSE

def line_span(lo, hi):
    return f"{lo}" + (f"-{hi}" if hi and hi != lo else "")

def merged_path(run):
    return os.path.join(run, "merged.md")

def entry_id(e):
    digits = re.sub(r"\D", "", str(e.get("id", "")))
    return int(digits) if digits else None

def raw_entries(path, source="merged"):
    with open(path, encoding="utf-8") as fh: text = fh.read()
    return [e for block in mf.parse_blocks(text) for e in mf.parse_entries(block, source)]

def read_merged(path):
    out = []
    for e in raw_entries(path):
        srcs = [x.strip() for x in str(e.get("sources", "")).split(",") if x.strip()]
        e = mf.norm(e)
        e["id"] = entry_id(e) or 0
        if srcs: e["sources"] = srcs
        out.append(e)
    return out

def read_overrides(run):
    o = {}
    d = os.path.join(run, "overrides")
    if not os.path.isdir(d): return o
    for n in sorted(os.listdir(d)):
        m = re.match(r"^(\d+)\.md$", n)
        if not m: continue
        text = open(os.path.join(d, n), encoding="utf-8").read()
        entries = mf.parse_entries(["- lens: override"] + ["  " + l if not l.startswith("  ") and l.strip() else l for l in text.splitlines()], n)
        if entries:
            e = entries[0]; e.pop("lens", None); e.pop("_source", None)
            o[int(m.group(1))] = {k: v for k, v in e.items() if v}
    return o

def read_findings(run):
    overrides = read_overrides(run)
    merged = read_merged(merged_path(run))
    for e in merged:
        over = overrides.get(e["id"], {})
        for k, val in over.items():
            e[k] = int(re.sub(r"\D", "", val) or 0) if k in ("line", "end_line") else val
        if "line" in over and "end_line" not in over: e["end_line"] = e["line"]
    return merged

def credit_ids(entries):
    return {e["id"] for e in entries if mf.is_credit(e)}

def read_titles(run):
    t = {}
    p = os.path.join(run, "titles.tsv")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t", 1)
            if len(parts) == 2 and parts[0].isdigit(): t[int(parts[0])] = parts[1].strip()
    return t

def report_titles(run):
    titles = read_titles(run)
    titles.update({mid: over["title"] for mid, over in read_overrides(run).items() if "title" in over})
    return titles

def title_of(e, titles):
    t = titles.get(e["id"]) or e.get("title") or ""
    if not t:
        t = e.get("claim", "").split(". ")[0].split(", so ")[0].split(", but ")[0].rstrip(".")
    return t.rstrip(". ")

STATUS_FIELDS = ("status", "ref", "date")
STATUS_DEFAULTS = {"status": "open"}
CLOSED_STATUSES = ("fixed", "wont-fix", "deferred")

def status_path(run):
    return os.path.join(run, "status.tsv")

def read_status(run):
    """status.tsv: merged id, status, ref (commit, ticket, or reason), date."""
    return read_keyed(status_path(run), STATUS_FIELDS, defaults=STATUS_DEFAULTS)

def write_status(run, st):
    write_keyed(status_path(run), STATUS_FIELDS, st)

def status_row(status, mid):
    return status.get(mid, {name: STATUS_DEFAULTS.get(name, "") for name in STATUS_FIELDS})

def status_of(status, mid):
    return status_row(status, mid)["status"]

COMMIT_TOKEN = re.compile(r"\b[0-9a-f]{7,40}\b")

def commits_named(repo, text):
    toks = COMMIT_TOKEN.findall(text)
    if not toks: return []
    r = subprocess.run(["git", "-C", repo, "cat-file", "--batch-check=%(objectname) %(objecttype)"],
                       input="".join(t + "^{commit}\n" for t in toks), capture_output=True, text=True)
    return [p[0] for p in (l.split() for l in r.stdout.splitlines()) if len(p) == 2 and p[1] == "commit"]

def commits_path(run):
    return os.path.join(run, "commits.tsv")

def log_commits(run, repo, mid, stt):
    shas = commits_named(repo, stt.get("ref", ""))
    if not shas: return
    path = commits_path(run)
    have = {tuple(r[:2]) for r in read_rows(path)}
    new = [s for s in shas if (str(mid), s) not in have]
    if not new: return
    with open(path, "a", encoding="utf-8") as fh:
        if not os.path.exists(path) or os.path.getsize(path) == 0: fh.write("merged_id\tcommit\tstatus\tdate\n")
        for s in new: fh.write(f"{mid}\t{s}\t{stt['status']}\t{stt.get('date', '')}\n")

INSTRUCTION_FIELDS = ("choice", "note", "date", "also", "option")

def instructions_path(run):
    return os.path.join(run, "instructions.tsv")

def read_instructions(run):
    """instructions.tsv: merged id, choice (fix|discuss|defer|ignore or empty),
    note, date, also (other ticked choices, comma separated), option (the
    labeled alternatives of the recommendation to follow, comma separated,
    only with fix). Free-text notes live in notes/<merged id>.md."""
    ins = read_keyed(instructions_path(run), INSTRUCTION_FIELDS)
    nd = os.path.join(run, "notes")
    if os.path.isdir(nd):
        for n in os.listdir(nd):
            m = re.match(r"^(\d+)\.md$", n)
            if m:
                txt = read_text(os.path.join(nd, n))
                if txt: ins.setdefault(int(m.group(1)), {"choice": "", "note": "", "date": "", "also": ""})["text"] = txt
    return ins

def write_instructions(run, ins):
    write_keyed(instructions_path(run), INSTRUCTION_FIELDS, {k: i for k, i in ins.items() if i.get("choice") or i.get("note") or i.get("also")})
    nd = os.path.join(run, "notes")
    for k, i in ins.items():
        f = os.path.join(nd, f"{k}.md")
        if i.get("text"):
            os.makedirs(nd, exist_ok=True); open(f, "w", encoding="utf-8").write(i["text"].strip() + "\n")
        elif os.path.exists(f):
            os.remove(f)

POSTED_FIELDS = ("state", "note", "date", "thread_id", "comment_id", "url", "path", "line", "end_line", "side", "kind", "review_id")

def read_posted(run):
    return read_keyed(os.path.join(run, "posted.tsv"), POSTED_FIELDS)

def write_posted(run, rows):
    write_keyed(os.path.join(run, "posted.tsv"), POSTED_FIELDS, rows)

def has_comment(row):
    return bool(row.get("kind"))

def is_posted(row):
    return has_comment(row) and row.get("state") == "posted"

def has_thread(row):
    return has_comment(row) and row["kind"] != "body" and bool(row.get("comment_id"))

def stale_text(row, note):
    return bool(row) and row["note"] != note and row["state"] != "edited"

def review_ids(rows):
    return {row["review_id"] for row in rows.values() if row.get("review_id")}

def posted_path(run, mid):
    return os.path.join(run, "posted", f"{mid}.md")

def posted_text(run, mid):
    return read_text(posted_path(run, mid))

def close_text_path(run, mid):
    return os.path.join(run, "posted", f"close-{mid}.md")

THREAD_FIELDS = ("comment_id", "thread_id", "state", "outdated", "can_resolve", "line", "replies", "date", "by_viewer")

def threads_path(run):
    return os.path.join(run, "pr", "threads.tsv")

def reply_line(author, text):
    return f"@{author}: {' '.join(text.split())}"

def joined_replies(replies):
    return "; ".join(reply_line(author, text) for author, text in replies)

def replies_cell(replies):
    return json.dumps([list(r) for r in replies], ensure_ascii=False) if replies else ""

def is_reply(r):
    return isinstance(r, list) and len(r) == 2 and all(isinstance(part, str) for part in r)

def cell_replies(cell):
    replies = json.loads(cell) if cell else []
    if not (isinstance(replies, list) and all(map(is_reply, replies))): raise ValueError("replies are not a list of author and text pairs")
    return [tuple(r) for r in replies]

def read_threads(run):
    rows = {}
    for mid, row in read_keyed(threads_path(run), THREAD_FIELDS).items():
        try: rows[mid] = {**row, "replies": cell_replies(row["replies"])}
        except ValueError: print(f"warning: skipped the row of merged id {mid} in {threads_path(run)}: its replies are unreadable", file=sys.stderr)
    return rows

def write_threads(run, rows):
    write_keyed(threads_path(run), THREAD_FIELDS, {mid: {**row, "replies": replies_cell(row.get("replies", []))} for mid, row in rows.items()})

def posted_threads(run, posted):
    return {mid: row for mid, row in read_threads(run).items() if row["comment_id"] == posted.get(mid, {}).get("comment_id")}

KEPT_OPEN_FIELDS = ("reason", "date")

def kept_open_path(run):
    return os.path.join(run, "posted", "keep.tsv")

def read_kept_open(run):
    return read_keyed(kept_open_path(run), KEPT_OPEN_FIELDS)

def write_kept_open(run, rows):
    write_keyed(kept_open_path(run), KEPT_OPEN_FIELDS, rows)

Closable = namedtuple("Closable", "posted status thread")

def is_open_and_ours(thread):
    return thread.get("state") == "open" and thread.get("by_viewer") == "1"

def closable(run):
    posted, status, kept = read_posted(run), read_status(run), read_kept_open(run)
    threads = posted_threads(run, posted)
    credits = credit_ids(read_findings(run))
    return {mid: Closable(row, status[mid], threads[mid]) for mid, row in sorted(posted.items())
            if has_thread(row) and mid not in credits and mid not in kept
            and status_of(status, mid) == "fixed" and is_open_and_ours(threads.get(mid, {}))}

NUMBER_FIELDS = ("merged_id", "section")

def numbers_path(run):
    return os.path.join(run, "numbers.tsv")

def number_rows(run):
    return [(n, int(r["merged_id"]), r["section"]) for n, r in read_keyed(numbers_path(run), NUMBER_FIELDS).items() if r["merged_id"].isdigit()]

def read_numbers(run):
    return {mid: n for n, mid, _ in number_rows(run)}

def read_sections(run):
    return {mid: section for _, mid, section in number_rows(run)}

def write_number_rows(run, rows):
    write_keyed(numbers_path(run), NUMBER_FIELDS, rows, header="number", order=list)

def finding_id(spec, nums):
    if spec.startswith("#"): return int(spec[1:])
    by_number = {n: mid for mid, n in nums.items()}
    if not spec.isdigit() or int(spec) not in by_number: sys.exit(f"finding {spec} not in numbers.tsv")
    return by_number[int(spec)]

def reconcile_path(run, name):
    return os.path.join(run, "reconcile", name)

def run_label(run):
    return os.path.basename(os.path.normpath(os.path.realpath(run)))

def write_previous(run, label):
    os.makedirs(reconcile_path(run, ""), exist_ok=True)
    with open(reconcile_path(run, "previous.txt"), "w", encoding="utf-8") as fh: fh.write(label + "\n")

def previous_state(status, numbers, mid):
    row = status_row(status, mid)
    return {"prev_number": str(numbers.get(mid, "")), "prev_status": row["status"], "prev_ref": row["ref"]}

MATCH_FIELDS = ("prev_id", "how", "prev_number", "prev_status", "prev_ref", "cause")

def read_matches(run):
    return read_keyed(reconcile_path(run, "matches.tsv"), MATCH_FIELDS)

def write_matches(run, rows):
    write_keyed(reconcile_path(run, "matches.tsv"), MATCH_FIELDS, rows, header="cur_id", order=list)

UNMATCHED_FIELDS = ("prev_number", "prev_status", "prev_ref", "location", "title")

def read_unmatched(run):
    return read_keyed(reconcile_path(run, "unmatched.tsv"), UNMATCHED_FIELDS)

def write_unmatched(run, rows):
    write_keyed(reconcile_path(run, "unmatched.tsv"), UNMATCHED_FIELDS, rows, header="prev_id")

OUTCOME_FIELDS = ("outcome", "note")

def read_since(run):
    return read_keyed(reconcile_path(run, "since.tsv"), OUTCOME_FIELDS)

def read_prior(run):
    return read_keyed(reconcile_path(run, "prior.tsv"), OUTCOME_FIELDS)

def appended_path(run):
    return reconcile_path(run, "appended.tsv")

def read_appended(run):
    return {int(r[0]) for r in read_rows(appended_path(run))}

def write_appended(run, ids):
    write_rows(appended_path(run), ["merged_id"], ([str(i)] for i in sorted(set(ids))))

APPENDED_MAP_FIELDS = ("merged_id",)

def appended_map_path(run):
    return reconcile_path(run, "appended-map.tsv")

def read_appended_map(run):
    return {new: int(r["merged_id"]) for new, r in read_keyed(appended_map_path(run), APPENDED_MAP_FIELDS).items() if r["merged_id"].isdigit()}

def write_appended_map(run, amap):
    write_keyed(appended_map_path(run), APPENDED_MAP_FIELDS, {new: {"merged_id": str(mid)} for new, mid in amap.items()}, header="new_id", order=list)

def read_reconcile(run):
    return {"label": read_text(reconcile_path(run, "previous.txt")), "matches": read_matches(run), "prior": read_prior(run),
            "since": read_since(run), "unmatched": [{"prev_id": pid, **row} for pid, row in read_unmatched(run).items()]}

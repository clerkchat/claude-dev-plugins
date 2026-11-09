#!/usr/bin/env python3
import argparse, datetime, json, os, re, shlex, subprocess, sys
import gh_api, ids
import run_files as rf
from records import ROUTING, load_script, phrase_of, phrases, read_plain_names

pc = load_script("pr-comments.py")

VERDICTS = {"comment": "COMMENT", "request-changes": "REQUEST_CHANGES", "approve": "APPROVE"}
CONFIRMED_VERDICTS = {"request-changes": "request changes", "approve": "approve"}
DEFAULT_BODY = "Comments from my review of this pull request."
HOW_REVIEWED = ("<!-- how reviewed: start -->", "<!-- how reviewed: end -->")
RANGE_LINE = re.compile(r"^Reviewed (?:`[^`\n]+`|the \d+ commits? since the last review)")
WHOLE_CHANGE = "**Whole change**: how the parts fit together, and what's left unfinished"
NOT_RUN_CAUSES = {"quick": "quick review", "removed": "left out for this review"}
NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
BLOCK_START = re.compile(r"^\s{0,3}(#|>|\||[-*+]\s|\d+[.)]\s)")
SUGGESTION = re.compile(r"^(\s*(?:`{3,}|~{3,}))suggestion\b", re.M)
LINE_KINDS = ("line", "range")
PULL_URL = re.compile(r"/([^/\s]+)/([^/\s]+)/pull/(\d+)/?$")
TARGET_PR = re.compile(r"^(?:pr\s*)?#?(\d+)$", re.I)
RECORD_ID = re.compile(r"(?<![\w-])(?:" + "|".join(sorted((re.escape(lead) for lead in (*ids.RECORD_LEADS.values(), *ids.ITEM_LEADS.values(), ids.SURVEY_LEAD)
                                                           if lead.endswith("-")), key=len, reverse=True)) + r")\d+\b")
INTERNAL = [("a .clerk-dev path", re.compile(r"\.clerk-dev\b")),
            ("a home-directory path", re.compile(r"(?<![\w.])(?:~|/Users/[^/\s`]+|/home/[^/\s`]+)/")),
            ("a record id", RECORD_ID),
            ("a confidence", re.compile(r"\bconfidence\b", re.I)),
            ("a lens", re.compile(r"\blens(?:es)?\b", re.I)),
            ("a finding number", re.compile(r"\bfindings?\s+#?\d+|\bmerged id\b", re.I)),
            ("a run label", re.compile(r"\b\d{8}-\d{4}\b"))]
SECRETS = [("a private key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
           ("a GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,})")),
           ("an API key", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|xox[abposr]-[A-Za-z0-9-]{10,})")),
           ("an AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"))]
SUSPECT_RUNS = [("a long hex run", re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{41,}(?![0-9A-Fa-f])")),
                ("a long base64 run", re.compile(r"(?<![\w+/=-])(?=[\w+/-]*[A-Z])(?=[\w+/-]*[a-z])(?=[\w+/-]*\d)[\w+/-]{40,}={0,2}"))]
MENTION = re.compile(r"(?<![\w/@])@([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:/[\w-]+)?)")
ISSUE_REFERENCE = re.compile(r"(?<![\w&/])#(\d+)\b")
LINKED = [(MENTION, "@", "mentions {}; GitHub notifies them"),
          (ISSUE_REFERENCE, "#", "names {}; GitHub links each to that issue or pull request of the repository")]
CROSS_REFERENCE = re.compile(r"\{#\d+\}")
CODE_SPAN = re.compile(r"(?<![`\\])(`+)(?!`)((?:(?!\n[ \t]*\n).)+?)(?<!`)\1(?!`)", re.S)

class UnexpectedReply(SystemExit):
    pass

FAILURES = (gh_api.GhError, Exception)

class Ref(str):
    def __new__(cls, name, key):
        ref = super().__new__(cls, f"{{{name}.{key}}}")
        ref.name, ref.key = name, key
        return ref

ADD_THREAD = """mutation($pullRequestReviewId:ID!,$path:String!,$body:String!,$subjectType:PullRequestReviewThreadSubjectType,
$line:Int,$side:DiffSide,$startLine:Int,$startSide:DiffSide){addPullRequestReviewThread(input:{
pullRequestReviewId:$pullRequestReviewId,path:$path,body:$body,subjectType:$subjectType,
line:$line,side:$side,startLine:$startLine,startSide:$startSide}){thread{id comments(first:1){nodes{id databaseId url}}}}}"""
UPDATE_COMMENT = """mutation($pullRequestReviewCommentId:ID!,$body:String!){updatePullRequestReviewComment(input:{
pullRequestReviewCommentId:$pullRequestReviewCommentId,body:$body}){pullRequestReviewComment{id url}}}"""
DELETE_COMMENT = """mutation($id:ID!){deletePullRequestReviewComment(input:{id:$id}){clientMutationId}}"""
ADD_REPLY = """mutation($pullRequestReviewThreadId:ID!,$body:String!){addPullRequestReviewThreadReply(input:{
pullRequestReviewThreadId:$pullRequestReviewThreadId,body:$body}){comment{databaseId url author{login}}}}"""
RESOLVE_THREAD = """mutation($threadId:ID!){resolveReviewThread(input:{threadId:$threadId}){thread{isResolved}}}"""

def answer_of(data, mutation):
    return (data or {}).get(mutation) or {}

def thread_result(data):
    t = answer_of(data, "addPullRequestReviewThread").get("thread") or {}
    nodes = (t.get("comments") or {}).get("nodes") or []
    if not nodes: raise UnexpectedReply("GitHub's answer named no new comment")
    c = nodes[0]
    return {"thread_id": t["id"], "comment_id": c["databaseId"], "comment_node": c["id"], "url": c["url"]}

def reply_result(data):
    c = answer_of(data, "addPullRequestReviewThreadReply").get("comment")
    if not c: raise UnexpectedReply("GitHub's answer named no reply")
    return {"comment_id": c["databaseId"], "url": c["url"], "login": pc.login(c)}

def resolve_result(data):
    return {"resolved": bool((answer_of(data, "resolveReviewThread").get("thread") or {}).get("isResolved"))}

MUTATIONS = {"addPullRequestReviewThread": (ADD_THREAD, thread_result),
             "updatePullRequestReviewComment": (UPDATE_COMMENT, lambda d: d),
             "deletePullRequestReviewComment": (DELETE_COMMENT, lambda d: d),
             "addPullRequestReviewThreadReply": (ADD_REPLY, reply_result),
             "resolveReviewThread": (RESOLVE_THREAD, resolve_result)}

def unwrap(text):
    out, joinable = [], False
    for line, code in rf.fenced_lines(text.strip("\n").split("\n")):
        if code:
            joinable = False
            out.append(line); continue
        if not line.strip():
            joinable = False; out.append(""); continue
        if joinable and not BLOCK_START.match(line): out[-1] = out[-1].rstrip() + " " + line.strip()
        else: out.append(line)
        joinable = not line.lstrip().startswith(("#", "|"))
    return "\n".join(out)

def prose(text):
    return CODE_SPAN.sub(" ", "\n".join("" if code else line for line, code in rf.fenced_lines(text.split("\n"))))

def local_paths(*dirs):
    found = {os.path.expanduser("~")} | {norm(d) for d in dirs for norm in (os.path.abspath, os.path.realpath)}
    return sorted((p for p in found if len(p.rstrip("/")) > 1), key=len, reverse=True)

def matches_in(patterns, text):
    return [(what, m.group(0)) for what, rx in patterns for m in [rx.search(text)] if m]

def looks_like(what, found):
    return f"what looks like {what}: {found[:12]}..."

def screen(text, local):
    path, token = next((p for p in local if p in text), None), CROSS_REFERENCE.search(text)
    secret = next(iter(matches_in(SECRETS, text)), None)
    problem = (f"its text holds {looks_like(*secret)}" if secret else
               f"its text names a local path of this machine ({path})" if path else
               f"its text holds a cross-reference token of the review ({token.group(0)})" if token else None)
    warnings = [f"the text names {what}: {found}" for what, found in matches_in(INTERNAL, text)]
    warnings += [f"the text holds {looks_like(what, found)}" for what, found in matches_in(SUSPECT_RUNS, text)]
    plain = prose(text)
    for rx, lead, says in LINKED:
        found = sorted(set(rx.findall(plain)))
        if found: warnings.append("the text " + says.format(", ".join(lead + f for f in found)))
    return problem, warnings

def outgoing(text, plain):
    sent = unwrap(text)
    return (SUGGESTION.sub(r"\1", sent), True) if plain and SUGGESTION.search(sent) else (sent, False)

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

def hunk_counts(m):
    return int(m.group(1)), int(m.group(2) or 1), int(m.group(3)), int(m.group(4) or 1)

def git_diff(repo, *args):
    r = subprocess.run(["git", "-C", repo, "diff", "--no-color", "--no-ext-diff", *args], capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace").strip()

def pr_patch(repo, base, reviewed):
    code, patch, err = git_diff(repo, "--src-prefix=a/", "--dst-prefix=b/", base, reviewed)
    if code: sys.exit(f"nothing sent; git could not diff the pull request at {reviewed[:9]} in {repo}: {err}")
    return patch

def read_hunks(patch):
    hunks, path, old_left, new_left, line = {}, None, 0, 0, 0
    for raw in patch.split("\n"):
        if old_left > 0 or new_left > 0:
            if raw.startswith("\\"): continue
            if not raw.startswith("+"): old_left -= 1
            if not raw.startswith("-"): new_left -= 1
            continue
        if raw.startswith("+++ "):
            path = None if raw[4:].strip() == "/dev/null" else re.sub(r"^b/", "", raw[4:].strip())
            continue
        m = HUNK.match(raw)
        if m and path:
            _, old_left, start, new_left = hunk_counts(m)
            if new_left: hunks.setdefault(path, []).append((start, start + new_left - 1))
    return hunks

def edits_since(repo, found, reviewed, path):
    code, patch, _ = git_diff(repo, "-U0", "--no-renames", found, reviewed, "--", path)
    lines = patch.split("\n")
    if code or "--- /dev/null" in lines: return None
    return [hunk_counts(m) for m in map(HUNK.match, lines) if m]

def shifted(edits, line, end):
    shift = 0
    for old_start, old_count, _, new_count in edits:
        last = old_start + old_count - 1 if old_count else old_start
        if old_count and old_start <= end and line <= last: return None
        if not old_count and line <= old_start < end: return None
        if last < line: shift += new_count - old_count
    return line + shift, end + shift

def found_lines(repo, found, reviewed, path, line, end):
    if rf.same_commit(found, reviewed): return (line, end), None
    where = f"{path}:{rf.line_span(line, end)}"
    edits = edits_since(repo, found, reviewed, path) if found else None
    if edits is None: return None, f"{where} was found on a commit this clone cannot compare with the reviewed {reviewed[:9]}"
    now = shifted(edits, line, end)
    return now, None if now else f"the code at the found lines ({where} on {found[:9]}) changed since"

def nearest_lines(hunks, line, end):
    for s, e in hunks:
        if s <= line and end <= e: return (line, end), False
    s, e = min(hunks, key=lambda h: max(0, h[0] - end, line - h[1]))
    lo, hi = max(line, s), min(end, e)
    if lo > hi: lo = hi = s if s > end else e
    return (lo, hi), True

def anchor(kind, path="", line=None, end_line=None):
    return {"kind": kind, "path": path, "line": line, "end_line": end_line}

def resolve(e, note, files, hunks, lines_now):
    where = rf.located(e, note)
    if where is None: return anchor("body", e.get("file", "")), None, None
    path, line, end = where
    if not path: return anchor("body"), "fallback: no file; sent in the review body", None
    if path not in files: return None, None, f"its file {path} is not in the pull request"
    if line is None: return anchor("file", path), None, None
    now, changed = lines_now(path, *sorted((line, end or line)))
    if changed: return anchor("file", path), f"fallback: {changed}; sent on the file", None
    line, end = now
    if not hunks.get(path): return anchor("file", path), f"fallback: {path} has no lines in the reviewed diff; sent on the file", None
    (lo, hi), moved = nearest_lines(hunks[path], line, end)
    moved_to = f"fallback: {path}:{rf.line_span(line, end)} is outside the diff; moved to {rf.line_span(lo, hi)}" if moved else None
    return anchor("line" if lo == hi else "range", path, lo, hi), moved_to, None

def on_github(row, ctx):
    return row["review_id"] in ctx["review_ids"] if row["kind"] == "body" else row["comment_id"] in ctx["comment_ids"]

def row_anchor(row):
    num = lambda v: int(v) if v else None
    return anchor(row["kind"], row.get("path", ""), num(row.get("line")), num(row.get("end_line")))

def findings(run):
    return {e["id"]: e for e in rf.read_findings(run)}

def number_of(mid, nums):
    return nums.get(mid, f"#{mid}")

def item_head(mid, nums, found, titles):
    return {"id": mid, "number": number_of(mid, nums), "title": rf.title_of(found[mid], titles) if mid in found else "(not in merged.md)"}

def in_number_order(mids, nums):
    return sorted(mids, key=lambda m: nums.get(m, 10 ** 6))

def finding_word(number):
    return f"finding {number}"

def named(it):
    return finding_word(it["number"])

def numbered(mid, nums):
    return finding_word(number_of(mid, nums))

def refuse_blocked(items):
    blocked = [f"{named(it)}: {it['problem']}" for it in items if it["problem"]]
    if blocked: sys.exit("nothing sent; " + "; ".join(blocked))

def print_warnings(label, warnings):
    if warnings: print("\n".join([label, *warning_lines(warnings)]), file=sys.stderr)

def drafted_elsewhere(it, e, reviewed):
    return it["action"] == "new" and e is not None and rf.code_moved(it["row"], rf.drafted_for(e, it["note"], reviewed))

SENDS = ("new", "update")

def pending_id(ctx):
    return str(ctx["pending"]["id"]) if ctx["pending"] else ""

def pending_comments(ctx):
    return (ctx["pending"] or {}).get("comments") or {}

def published(it, ctx):
    row = it["row"]
    if it["action"] != "update": return False
    return row["review_id"] != pending_id(ctx) if row["kind"] == "body" else int(row["comment_id"]) not in pending_comments(ctx)

def submitted_review(it):
    return it["row"]["review_id"] if it["published"] and it["row"]["kind"] == "body" else None

def recorded_comments(rows):
    return {row["comment_id"] for row in rows.values() if row.get("comment_id")}

def in_pending_review(ctx):
    return [c for c in ctx["comments"] if c["id"] in pending_comments(ctx)]

def own_drafts(ctx, rows):
    ours = recorded_comments(rows)
    return [c for c in in_pending_review(ctx) if str(c["id"]) not in ours]

def draft_place(comment):
    line = comment.get("line") or comment.get("original_line")
    return comment.get("path", "") + (f":{line}" if line else "")

def draft_line(comment):
    first = (comment.get("body") or "").strip().partition("\n")[0]
    return f"  {draft_place(comment)}: {first}"

def own_draft_lines(drafts):
    return ["your own drafts in this pending review; submitting publishes them too:", *map(draft_line, drafts)] if drafts else []

def holds(comment, a, text):
    at = comment.get("subject_type") == "file" if a["kind"] == "file" else a["end_line"] in (comment.get("line"), comment.get("original_line"))
    return comment.get("path") == a["path"] and at and comment.get("body") == text

def written_by(comment, login):
    return (comment.get("user") or {}).get("login") == login

def already_on_github(it, ctx, taken):
    a = it["anchor"]
    if it["action"] != "new" or not a or a["kind"] == "body": return None
    return next((c for c in ctx["comments"] if str(c["id"]) not in taken and written_by(c, ctx["viewer"]) and holds(c, a, it["text"])), None)

def lines_now_for(run, mid, note, repo, reviewed):
    found = reviewed if rf.placement(note) else rf.found_on(run, mid)
    return lambda path, line, end: found_lines(repo, found, reviewed, path, line, end)

def plan_items(run, ctx, hunks, reviewed, repo):
    ins, rows, nums, found = rf.read_instructions(run), rf.read_posted(run), rf.read_numbers(run), findings(run)
    sections = rf.read_sections(run)
    titles = rf.report_titles(run)
    items, taken = [], recorded_comments(rows)
    for mid in in_number_order((m for m, i in ins.items() if i.get("choice") == "post"), nums):
        e, row, note = found.get(mid), rows.get(mid, {}), ins[mid].get("note", "")
        it = {**item_head(mid, nums, found, titles), "note": note, "row": row, "fallback": None, "problem": None, "gone": None}
        if row.get("kind") and not on_github(row, ctx):
            it["gone"] = f"its earlier comment is no longer on GitHub (review {row['review_id']}); --post posts it again"
        if row.get("kind") and not it["gone"]:
            it["anchor"], it["action"] = row_anchor(row), "skip" if row["state"] == "posted" else "update"
        elif e is None:
            it["anchor"], it["action"], it["problem"] = None, "new", "it is not in merged.md"
        elif rf.mf.is_credit(e) and sections.get(mid) != "credit":
            it["anchor"], it["action"], it["problem"] = None, "new", f"it is a credit the report no longer shows; clear its Post with --instruct #{mid}=none"
        else:
            it["anchor"], it["fallback"], it["problem"] = resolve(e, note, ctx["files"], hunks, lines_now_for(run, mid, note, repo, reviewed))
            it["action"] = "new"
        raw = rf.posted_text(run, mid)
        if not raw: it["problem"] = it["problem"] or "it has no posted text"
        if it["action"] != "skip" and rf.stale_text(row, note):
            it["problem"] = it["problem"] or "its posted text is to be redrafted; the note changed"
        it["moved"] = drafted_elsewhere(it, e, reviewed)
        plain = bool(it["fallback"]) or it["moved"] or (it["anchor"] or {}).get("kind") not in LINE_KINDS
        it["text"], it["downgraded"] = outgoing(raw, plain)
        problem, it["warnings"] = screen(it["text"], ctx["local"])
        it["problem"] = it["problem"] or problem
        it["published"] = published(it, ctx)
        it["submitted"], it["existing"] = submitted_review(it), already_on_github(it, ctx, taken)
        if it["existing"]: it["action"] = "adopt"; taken.add(str(it["existing"]["id"]))
        items.append(it)
    return items

def review_head(run):
    head = rf.read_text(rf.review_text_path(run))
    return unwrap(head) if head else ""

def our_texts(run):
    posting = [mid for mid, i in rf.read_instructions(run).items() if i.get("choice") == "post"]
    return [DEFAULT_BODY, outside_block(review_head(run))[0], *(outgoing(rf.posted_text(run, mid), True)[0] for mid in posting)]

def before_ours(body, ours):
    return body[:min((at for at in (body.find(t) for t in ours if t) if at >= 0), default=len(body))].strip()

def kept_body(run, ctx):
    p = ctx["pending"]
    if not p: return ""
    if str(p["id"]) in rf.own_reviews(run, rf.read_posted(run)): return saved_body(run, p["id"])
    return before_ours(outside_block(p.get("body") or "")[0], our_texts(run))

def holds_our_body(run, ctx, rows):
    ours = rf.own_reviews(run, rows)
    return str(ctx["pending"]["id"]) in ours if ctx["pending"] else bool(ours & ctx["review_ids"])

def saved_body(run, review_id):
    return rf.read_text(rf.kept_body_path(run, review_id))

def review_body(run, rows, review_id, kept):
    parts = [part for part in (kept, review_head(run)) if part] or [DEFAULT_BODY]
    for mid in sorted(rows):
        row = rows[mid]
        if row.get("kind") == "body" and str(row.get("review_id")) == str(review_id):
            text = outgoing(rf.posted_text(run, mid), True)[0]
            parts.append((f"**`{row['path']}`**\n\n" if row.get("path") else "") + text)
    return "\n\n".join(parts)

def plural(n, word, say=str):
    return f"{say(n)} {word}" + ("" if n == 1 else "s")

def spelled(n):
    return NUMBER_WORDS[n] if n < len(NUMBER_WORDS) else str(n)

def commits_between(repo, base, head):
    r = subprocess.run(["git", "-C", repo, "rev-list", "--count", f"{base}..{head}"], capture_output=True, text=True)
    return int(r.stdout) if r.returncode == 0 and r.stdout.strip().isdigit() else None

def is_ancestor(repo, base, head):
    return subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", base, head], capture_output=True).returncode == 0

def commits_since_last_review(run, repo, target):
    prev = rf.previous_run(run)
    if not (prev and os.path.isdir(prev) and rf.same_commit(target.base, rf.reviewed_head(prev)) and is_ancestor(repo, target.base, target.head)): return None
    return commits_between(repo, target.base, target.head)

def range_line(run, repo, parts):
    target = rf.read_target(run)
    if not (target.base and target.head): sys.exit("nothing rendered; target.txt has no BASE and HEAD lines")
    span, files = f"`{target.base[:7]}..{target.head[:7]}`", plural(len(rf.included_files(run)), "file")
    since = commits_since_last_review(run, repo, target)
    reviewed = f"Reviewed the {plural(since, 'commit')} since the last review ({span}, {files})" if since else f"Reviewed {span} ({files})"
    return f"{reviewed}, " + (f"in {plural(len(parts), 'part', spelled)} plus a pass over the whole change." if parts else "as one piece.")

def in_name_order(names, lenses):
    rank = {lens: at for at, lens in enumerate(names)}
    return sorted(dict.fromkeys(lens for lens in lenses if lens != "credit"), key=lambda lens: rank.get(lens, len(rank)))

def entry(head, lines):
    return "\n".join([head, *(f"- {line}" for line in lines if line)])

def one_line(text):
    return " ".join(text.split()).replace("<!--", "&lt;!--")

def in_sentence(label):
    return label if label[:2].isupper() else label[:1].lower() + label[1:]

def part_label(slices, name):
    return one_line(rf.label_of(slices, name))

def seams_line(slices):
    crossings = [f"{in_sentence(part_label(slices, s.source))} to {in_sentence(part_label(slices, s.target))} ({one_line(s.crosses)})" for s in slices.seams]
    return "Checked between parts: " + ", ".join(crossings) if crossings else ""

def part_entry(names, slices, instances, name):
    summary = one_line(slices.by_name[name].summary)
    head = f"**{part_label(slices, name)}**" + (f": {summary}" if summary else "")
    return entry(head, [phrases(names, in_name_order(names, (i.lens for i in instances if i.scope == name)))])

def whole_change_entry(names, slices, instances):
    whole = in_name_order(names, (i.lens for i in instances if i.scope == "all" or not slices.order))
    return entry(WHOLE_CHANGE, [phrases(names, whole), seams_line(slices)])

def described(names, lens):
    return ": ".join(filter(None, (phrase_of(names, lens), names[lens].description if lens in names else "")))

def legend(names, instances):
    ran = in_name_order(names, (i.lens for i in instances))
    return entry("**Focuses**", [described(names, lens) for lens in ran]) if ran else ""

def not_run_line(run, names):
    cut = {n.lens: NOT_RUN_CAUSES[n.cause] for n in rf.read_not_run(run) if n.cause in NOT_RUN_CAUSES}
    return "Not run: " + ", ".join(f"{phrase_of(names, lens)} ({cut[lens]})" for lens in in_name_order(names, cut)) + "." if cut else ""

def how_reviewed(run, names, slices):
    instances = rf.read_instances(run)
    if instances is None: sys.exit(f"nothing rendered; {run} has no plan.md")
    entries = [*(part_entry(names, slices, instances, name) for name in slices.order), whole_change_entry(names, slices, instances)]
    return "\n\n".join([HOW_REVIEWED[0], "<details><summary>How the change was reviewed</summary>", *entries,
                        *filter(None, [legend(names, instances), not_run_line(run, names)]), "</details>", HOW_REVIEWED[1]])

def outside_block(text):
    start = text.find(HOW_REVIEWED[0])
    if start < 0: return text, ""
    above, _, last = text[:start].rstrip().rpartition("\n\n")
    above = (above if RANGE_LINE.match(last) else text[:start]).strip()
    after = text[start + len(HOW_REVIEWED[0]):]
    end = after.find(HOW_REVIEWED[1])
    if end < 0: return "\n\n".join(filter(None, [above, after.strip()])), ""
    return above, after[end + len(HOW_REVIEWED[1]):].strip()

def render_body(run, repo):
    path, slices = rf.review_text_path(run), rf.read_slices(run)
    above, below = outside_block(rf.read_text(path))
    rendered = [range_line(run, repo, slices.order), how_reviewed(run, read_plain_names(ROUTING), slices)]
    rf.write_text(path, "\n\n".join(filter(None, [above, *rendered, below])) + "\n")
    print(f"wrote {path}", file=sys.stderr)

def result_key(mid):
    return f"finding{mid}"

def pulls_path(ctx):
    return f"repos/{ctx['owner']}/{ctx['name']}/pulls/{ctx['pr']}"

def thread_call(it, review_node):
    a = it["anchor"]
    v = {"pullRequestReviewId": review_node, "path": a["path"], "body": it["text"]}
    if a["kind"] == "file": v["subjectType"] = "FILE"
    else: v.update(subjectType="LINE", line=a["end_line"], side="RIGHT")
    if a["kind"] == "range": v.update(startLine=a["line"], startSide="RIGHT")
    return {"graphql": "addPullRequestReviewThread", "variables": v, "finding": it["id"], "as": result_key(it["id"])}

def update_call(ctx, it):
    comment = int(it["row"]["comment_id"])
    node = pending_comments(ctx).get(comment)
    if node:
        return {"graphql": "updatePullRequestReviewComment", "finding": it["id"],
                "variables": {"pullRequestReviewCommentId": node, "body": it["text"]}}
    return {"method": "PATCH", "path": f"repos/{ctx['owner']}/{ctx['name']}/pulls/comments/{comment}",
            "fields": {"body": it["text"]}, "finding": it["id"]}

def placed(a, review_id):
    return {"kind": a["kind"], "path": a["path"], "line": str(a["line"] or ""), "end_line": str(a["end_line"] or ""),
            "side": "RIGHT" if a["kind"] in LINE_KINDS else "", "review_id": review_id}

def existing_ids(comment):
    return {"thread_id": "", "comment_id": str(comment["id"]), "url": comment.get("html_url", "")}

def sent_ids(it):
    if it["anchor"]["kind"] == "body": return {"thread_id": "", "comment_id": "", "url": Ref("review", "html_url")}
    return {k: Ref(result_key(it["id"]), k) for k in ("thread_id", "comment_id", "url")}

def planned_rows(rows, sending, review_id, today):
    out = dict(rows)
    for it in sending:
        a, row = it["anchor"], it["row"]
        new = {"state": "posted", "date": today, "note": row.get("note", it["note"])}
        if it["action"] == "adopt":
            new.update(placed(a, str(it["existing"].get("pull_request_review_id") or "")), **existing_ids(it["existing"]))
        elif it["action"] == "new" or (a["kind"] == "body" and not it["submitted"]):
            new.update(placed(a, review_id), **sent_ids(it))
        out[it["id"]] = {**row, **new}
    return out

def submitted_ids(sending):
    return sorted({it["submitted"] for it in sending if it["submitted"]})

def submitted_label(review_id):
    return f"body of submitted review {review_id}"

def submitted_body(run, rows, review_id):
    return review_body(run, rows, review_id, saved_body(run, review_id))

def comment_updates(ctx, sending):
    return [update_call(ctx, it) for it in sending if it["action"] == "update" and it["anchor"]["kind"] != "body"]

def post_calls(ctx, sending, body, reviewed):
    base, pending = pulls_path(ctx), ctx["pending"]
    calls = [] if pending else [{"method": "POST", "path": f"{base}/reviews", "fields": {"commit_id": reviewed, "body": body}, "as": "review"}]
    review_node = pending["node_id"] if pending else Ref("review", "node_id")
    calls += [thread_call(it, review_node) for it in sending if it["action"] == "new" and it["anchor"]["kind"] != "body"]
    calls += comment_updates(ctx, sending)
    if pending: calls.append({"method": "PUT", "path": f"{base}/reviews/{pending['id']}", "fields": {"body": body}})
    return calls

def published_calls(run, ctx, picked, rows):
    bodies = [{"method": "PUT", "path": f"{pulls_path(ctx)}/reviews/{rid}", "body_of": rid,
               "fields": {"body": checked(submitted_label(rid), submitted_body(run, rows, rid), ctx)}} for rid in submitted_ids(picked)]
    return comment_updates(ctx, picked) + bodies

def resolve_refs(value, results):
    if isinstance(value, dict): return {k: resolve_refs(v, results) for k, v in value.items()}
    return results[value.name][value.key] if isinstance(value, Ref) else value

def send(call, results, repo):
    if "graphql" in call:
        query, shape = MUTATIONS[call["graphql"]]
        return shape((gh_api.graphql(query, resolve_refs(call["variables"], results), repo) or {}).get("data"))
    return gh_api.rest(call["method"], call["path"], resolve_refs(call.get("fields", {}), results), repo)

def finding_name(call, items):
    return f"finding {items.get(call.get('finding'), {}).get('number', call.get('finding'))}"

def row_url(call, items):
    return items.get(call.get("finding"), {}).get("row", {}).get("url", "")

def is_thread(call):
    return call.get("graphql") == "addPullRequestReviewThread"

def undo_of(call, results, items):
    name = finding_name(call, items)
    if is_thread(call):
        added = results[call["as"]]
        return {"graphql": "deletePullRequestReviewComment", "variables": {"id": added["comment_node"]}}, f"{name}'s comment {added['url']}"
    if call.get("as") == "review":
        return {"method": "DELETE", "path": f"{call['path']}/{results['review']['id']}"}, f"pending review {results['review']['id']}"
    if "body_of" in call: return None, f"the {submitted_label(call['body_of'])}, which keeps its new text"
    return None, f"{name}'s comment {row_url(call, items)}, which keeps its new text"

def pending_now(call, repo):
    try: return next((r for r in gh_api.rest_list(call["path"], repo) if r["state"] == "PENDING"), None)
    except FAILURES: return None

def began_review(call, repo):
    found = pending_now(call, repo)
    left = (f" (pending review {found['id']} is on the pull request now and was left as it is, since it may be one started elsewhere)"
            if found else "")
    return "a pending review this batch began" + left

def unknown_of(call, results, items, ctx, repo):
    name = finding_name(call, items)
    if call.get("as") == "review": return began_review(call, repo)
    if is_thread(call): return f"{name}'s comment on pending review {(ctx['pending'] or results.get('review') or {}).get('id', '')}"
    if "finding" in call: return f"{name}'s new text on its comment {row_url(call, items)}"
    return f"{call.get('method', '')} {call.get('path', '')}"

def recover(call, results, repo, ctx):
    if not (is_thread(call) and ctx["pending"]): return None
    v, known = call["variables"], set(ctx["pending"]["comments"]) | {r.get("comment_id") for r in results.values()}
    found = next((c for c in gh_api.rest_list(f"{pulls_path(ctx)}/reviews/{ctx['pending']['id']}/comments", repo)
                  if c["id"] not in known and c["path"] == v["path"] and c["body"] == v["body"]), None)
    return found and {"comment_id": found["id"], "comment_node": found["node_id"], "url": found["html_url"]}

def found_by(call, results, repo, ctx):
    try: return recover(call, results, repo, ctx)
    except FAILURES: return None

def without_threads(entries):
    return [(c, w) for c, w in entries if not is_thread(c)]

def rollback(done, results, repo, items, ctx, inflight):
    maybe = []
    found = found_by(inflight, results, repo, ctx)
    if found: results[inflight["as"]] = found; done = [*done, inflight]
    else: maybe.append((inflight, unknown_of(inflight, results, items, ctx, repo)))
    left = []
    for call in reversed(done):
        undo, what = undo_of(call, results, items)
        if undo is None: left.append((call, what)); continue
        try: send(undo, results, repo)
        except FAILURES as err: left.append((call, f"{what} (could not delete it: {err})")); continue
        if call.get("as") == "review": left, maybe = without_threads(left), without_threads(maybe)
    kept, unsure = "; ".join(w for _, w in reversed(left)), "; ".join(w for _, w in maybe)
    parts = (["rolled back"] if done else []) + ([f"still on GitHub: {kept}"] if kept else [])
    parts += [f"possibly on GitHub: {unsure}"] if unsure else []
    if done and not (kept or unsure): parts.append("nothing from this batch is left on GitHub")
    return "; ".join(parts + ["posted.tsv is unchanged"])

def execute(calls, repo, ctx, items=()):
    results, done = {}, []
    stop = lambda: rollback(done, results, repo, {it["id"]: it for it in items}, ctx, calls[len(done)])
    try:
        for call in calls:
            r = send(call, results, repo)
            if "as" in call: results[call["as"]] = r
            done.append(call)
    except gh_api.GhError as err:
        sys.exit(f"{err}\nGitHub answered with an error; {stop()}")
    except UnexpectedReply as err:
        sys.exit(f"{err}\nthe batch stopped; {stop()}")
    except BaseException:
        print(f"the batch stopped; {stop()}", file=sys.stderr)
        raise
    return results

def write_payload(run, calls):
    os.makedirs(os.path.join(run, "posted"), exist_ok=True)
    p = os.path.join(run, "posted", "payload.json")
    with open(p, "w", encoding="utf-8") as fh: json.dump({"calls": calls}, fh, indent=1)
    print(f"dry run: wrote {len(calls)} calls to {p}", file=sys.stderr)

def reviewed_commit(run, repo):
    head = rf.reviewed_head(run) or sys.exit("target.txt has no HEAD line")
    return head if len(head) == 40 else full_sha(head, repo)

def full_sha(commit, repo):
    r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"], cwd=repo, capture_output=True, text=True)
    return r.stdout.strip() or sys.exit(f"target.txt names commit {commit}, which git does not find in {repo}")

def recorded_pr(run):
    number, url = (rf.read_text(os.path.join(run, "pr", "pr.txt")).split("\t") + [""])[:2]
    target = rf.read_target(run).target
    m = PULL_URL.search(url.strip()) or PULL_URL.search(target)
    if m: return int(m.group(3)), f"{m.group(1)}/{m.group(2)}"
    m = TARGET_PR.match(number.strip()) or TARGET_PR.match(target)
    return (int(m.group(1)) if m else None), None

def branch_pr(repo):
    try: return gh_api.pr_number(repo)
    except gh_api.GhError: return None

def reviewed_pr(repo, run, asked):
    number, reviewed_repo = recorded_pr(run)
    known = number or branch_pr(repo)
    if asked and known and asked != known: sys.exit(f"nothing sent; --pr {asked} is not the reviewed pull request #{known}")
    if not (asked or known): sys.exit("no pull request found for the run or the branch; pass --pr N")
    owner, name = reviewed_repo.split("/") if reviewed_repo else gh_api.repo_owner_name(repo)
    return owner, name, asked or known

def compared(ctx, base, head, field, repo):
    return gh_api.gh(["api", f"repos/{ctx['owner']}/{ctx['name']}/compare/{base}...{head}", "--jq", f".{field}"], repo).strip()

def merge_base(ctx, reviewed, repo):
    return compared(ctx, ctx["base"], reviewed, "merge_base_commit.sha", repo)

def fetch_pr(repo, run, pr, reviewed):
    owner, name, pr = reviewed_pr(repo, run, pr)
    ctx = {"owner": owner, "name": name, "pr": pr, "pending": None, "viewer": gh_api.viewer_login(repo)}
    base = pulls_path(ctx)
    view = json.loads(gh_api.gh(["pr", "view", str(pr), "--repo", f"{owner}/{name}", "--json", "headRefOid,baseRefOid"], repo))
    ctx["head"], ctx["base"] = view["headRefOid"], view["baseRefOid"]
    ctx["merge_base"] = merge_base(ctx, reviewed, repo)
    ctx["files"] = [f["filename"] for f in gh_api.rest_list(f"{base}/files", repo)]
    reviews = gh_api.rest_list(f"{base}/reviews", repo)
    ctx["review_ids"] = {str(r["id"]) for r in reviews}
    ctx["comments"] = gh_api.rest_list(f"{base}/comments", repo)
    pending = next((r for r in reviews if r["state"] == "PENDING"), None)
    if pending:
        comments = gh_api.rest_list(f"{base}/reviews/{pending['id']}/comments", repo)
        ctx["pending"] = {"id": pending["id"], "node_id": pending["node_id"], "commit_id": pending["commit_id"],
                          "html_url": pending.get("html_url", ""), "body": pending.get("body") or "", "comments": {c["id"]: c["node_id"] for c in comments}}
        ctx["comments"] = [*ctx["comments"], *comments]
    ctx["comment_ids"] = {str(c["id"]) for c in ctx["comments"]}
    return ctx

def current_review(ctx):
    return str(ctx["pending"]["id"]) if ctx["pending"] else Ref("review", "id")

def pending_line(ctx, reviewed, verb):
    p = ctx["pending"]
    if not p: return f"pending review: none; {verb} creates one on {reviewed[:9]}"
    if rf.same_commit(p["commit_id"], reviewed): return f"pending review: {p['id']} on {reviewed[:9]} exists; {verb} adds to it"
    return (f"pending review: {p['id']} exists on {p['commit_id'][:9]}, another commit than the reviewed {reviewed[:9]}; "
            f"{verb} adds to it anyway")

def indent(text):
    return "\n".join("    " + l if l else "" for l in text.split("\n"))

def warning_lines(warnings):
    return [f"  warning: {w}" for w in warnings]

def screened(label, text, ctx):
    problem, warnings = screen(text, ctx["local"])
    if problem: sys.exit(f"nothing sent; the {label}: {problem}")
    print_warnings(f"{label}:", warnings)
    return warnings

def checked(label, body, ctx):
    screened(label, body, ctx)
    return body

def checked_body(run, ctx, rows, review_id):
    return checked("review body", review_body(run, rows, review_id, ctx["kept"]), ctx)

def pending_comment_label(comment, rows, nums):
    mid = next((m for m, row in rows.items() if row.get("comment_id") == str(comment["id"])), None)
    return f"comment of {numbered(mid, nums)}" if mid else f"draft of yours on {draft_place(comment)}"

def pending_warnings(run, ctx, rows, body):
    nums = rf.read_numbers(run)
    found = screened("review body", body, ctx)
    return found + [w for c in in_pending_review(ctx) for w in screened(pending_comment_label(c, rows, nums), c.get("body") or "", ctx)]

def body_lines(label, body, ctx):
    problem, warnings = screen(body, ctx["local"])
    return [f"{label}:", indent(body)] + ([f"  cannot post: {problem}"] if problem else []) + warning_lines(warnings)

def updates_what(it):
    if it["submitted"]: return f"the {submitted_label(it['submitted'])}"
    return f"its published comment {it['row'].get('url', '')}" if it["published"] else "the comment"

def update_line(it):
    if it["published"]: return f"  changed since posting: --update-published {it['number']} updates {updates_what(it)}"
    return f"  changed since posting: --post updates {updates_what(it)}"

def item_lines(it):
    out = [f"{named(it)}: {it['title']}"]
    a = it["anchor"]
    if a: out.append(f"  anchor: " + ("review body" if a["kind"] == "body" else f"{a['path']}" + (f":{rf.line_span(a['line'], a['end_line'])}" if a["line"] else "")) + f" ({a['kind']})")
    if it["gone"]: out.append(f"  {it['gone']}")
    if it["fallback"]: out.append(f"  {it['fallback']}")
    if it["moved"]: out.append("  the code moved since its text was drafted")
    if it["downgraded"]: out.append("  suggestion sent as a plain code block")
    if it["action"] == "skip": return out + [f"  already posted: {it['row'].get('url', '')}"]
    if it["action"] == "adopt":
        return out + [f"  already on GitHub, though this run has no record of it: {it['existing'].get('html_url', '')}; --post records it"]
    if it["action"] == "update": out.append(update_line(it))
    if it["problem"]: return out + [f"  cannot post: {it['problem']}"]
    return out + ["  text:", indent(it["text"])] + warning_lines(it["warnings"])

def published_items(items):
    return [it for it in items if it["published"]]

def numbers_of(items):
    return ",".join(str(it["number"]) for it in items)

def published_lines(run, ctx, held):
    if not held: return []
    out = ["published; changes on GitHub at once:", *(line for it in held for line in item_lines(it))]
    rows = rf.read_posted(run)
    for rid in submitted_ids(held): out += body_lines(submitted_label(rid), submitted_body(run, rows, rid), ctx)
    return out + [f"  --post leaves these as they are; --update-published {numbers_of(held)} sends them, "
                  "once you type the pull request number at a terminal"]

def preview(run, ctx, items, reviewed):
    staged, held = [it for it in items if not it["published"]], published_items(items)
    out = [f"pull request: {ctx['owner']}/{ctx['name']}#{ctx['pr']}", *(line for it in staged for line in item_lines(it))]
    review_id = current_review(ctx)
    sending = [it for it in staged if it["action"] != "skip" and not it["problem"]]
    rows = planned_rows(rf.read_posted(run), sending, review_id, "")
    out += body_lines("review body", review_body(run, rows, review_id, ctx["kept"]), ctx)
    if ctx["kept"]: out.append(f"  keeps the text already in pending review {ctx['pending']['id']} on GitHub, with this run's text below it")
    out += published_lines(run, ctx, held)
    if not rf.same_commit(ctx["head"], reviewed):
        out.append(f"head moved: the pull request head is {ctx['head'][:9]}, the review judged {reviewed[:9]}; comments anchor on the reviewed commit")
    out.append(pending_line(ctx, reviewed, "--post"))
    out += own_draft_lines(own_drafts(ctx, rows))
    print("\n".join(out))

def posted_where(it, c):
    if it["submitted"]: return f"in the {submitted_label(it['submitted'])}"
    return "in the review body" if it["anchor"]["kind"] == "body" else f"comment {c.get('comment_id', '')} {c.get('url', '')}"

def posted_lines(sending, results):
    review = results.get("review")
    out = [f"  review {review['id']} {review.get('html_url', '')}"] if review else []
    return out + [f"  {named(it)}: {posted_where(it, results.get(result_key(it['id'])) or it['row'])}" for it in sending]

def posted_summary(items, sending, adopted, held, results, sent_body):
    new, review = sum(it["action"] == "new" for it in sending), results["review"]["id"] if sent_body else ""
    parts = ([f"posted {new} comments and updated {len(sending) - new} on review {review}"] if sending else
             [f"sent the review body to review {review}"] if sent_body else [])
    parts += [f"recorded {len(adopted)} already on GitHub"] if adopted else []
    return "; ".join(parts + [f"skipped {len(items) - len(sending) - len(adopted) - len(held)} already posted"])

def held_line(held):
    return (f"not sent: {', '.join(map(named, held))} changed since posting, and GitHub already shows the comment; "
            f"--update-published {numbers_of(held)} sends the change once you type the pull request number at a terminal")

def record_sent(run, rows, results, sending, kept=None):
    try:
        if kept: rf.write_text(*kept)
        rf.write_posted(run, {mid: {k: str(resolve_refs(v, results)) for k, v in row.items()} for mid, row in rows.items()})
    except BaseException:
        print("\n".join(["posted.tsv was not updated; this batch is on GitHub:", *posted_lines(sending, results)]), file=sys.stderr)
        raise

def today():
    return datetime.date.today().isoformat()

def post(a, ctx, items, reviewed):
    held = published_items(items)
    sending = [it for it in items if it["action"] in SENDS and not it["published"]]
    adopted = [it for it in items if it["action"] == "adopt"]
    refuse_blocked(sending)
    if held: print(held_line(held), file=sys.stderr)
    review_id = current_review(ctx)
    rows = planned_rows(rf.read_posted(a.run), sending + adopted, review_id, today())
    sends_body = bool(sending) or not holds_our_body(a.run, ctx, rows)
    if not (sends_body or adopted):
        print("nothing to post: the review body and every Post-marked finding are already posted", file=sys.stderr); return
    calls = post_calls(ctx, sending, checked_body(a.run, ctx, rows, review_id), reviewed) if sends_body else []
    if sends_body: print(pending_line(ctx, reviewed, "this batch"), file=sys.stderr)
    if a.dry_run: write_payload(a.run, calls); return
    results = execute(calls, a.repo, ctx, items)
    if ctx["pending"]: results["review"] = ctx["pending"]
    kept = sends_body and (rf.kept_body_path(a.run, results["review"]["id"]), ctx["kept"] + "\n")
    record_sent(a.run, rows, results, sending, kept)
    print(posted_summary(items, sending, adopted, held, results, sends_body), file=sys.stderr)

def unpicked_siblings(held, picked):
    return {rid: [it for it in held if it["submitted"] == rid and it not in picked] for rid in submitted_ids(picked)}

def refuse_split_bodies(held, picked):
    split = [f"the {submitted_label(rid)} also holds the changed text of {', '.join(map(named, rest))}; name it too"
             for rid, rest in unpicked_siblings(held, picked).items() if rest]
    if split: sys.exit("nothing sent; " + "; ".join(split))

def picked_published(run, spec, held):
    nums, by_id = rf.read_numbers(run), {it["id"]: it for it in held}
    picked = picked_ids(spec, nums, "--update-published")
    refused = [numbered(mid, nums) for mid in sorted(picked) if mid not in by_id]
    if refused: sys.exit("nothing sent; not a published comment changed since posting: " + ", ".join(refused))
    return [it for it in held if it["id"] in picked]

def update_published(a, ctx, items):
    held = published_items(items)
    picked = picked_published(a.run, a.update_published, held)
    refuse_blocked(picked)
    refuse_split_bodies(held, picked)
    rows = planned_rows(rf.read_posted(a.run), picked, "", today())
    calls = published_calls(a.run, ctx, picked, rows)
    if a.dry_run: write_payload(a.run, calls); return
    confirm(a, ctx, f"change {len(picked)} published comment" + ("" if len(picked) == 1 else "s") + " on GitHub now",
            ["--update-published", a.update_published])
    results = execute(calls, a.repo, ctx, items)
    record_sent(a.run, rows, results, picked)
    print("\n".join(["updated on GitHub:", *posted_lines(picked, results)]), file=sys.stderr)

def ask_terminal(prompt):
    with open("/dev/tty", "rb+", buffering=0) as tty:
        tty.write(prompt.encode())
        return tty.readline().decode()

def own_command(a, action):
    pr = ["--pr", str(a.pr)] if a.pr else []
    return shlex.join(["python3", os.path.abspath(__file__), os.path.abspath(a.run), "--repo", os.path.abspath(a.repo), *pr, *action])

def confirm(a, ctx, what, action):
    if a.confirm is not None: return confirmed_by_flag(a, ctx)
    try: typed = ask_terminal(f"Type the pull request number ({ctx['pr']}) to {what}: ").strip()
    except OSError:
        sys.exit(f"nothing sent; to {what}, confirm with --confirm {ctx['pr']} once the user has said yes to it, "
                 f"or run this at a terminal:\n! {own_command(a, action)}")
    if typed != str(ctx["pr"]): sys.exit(f"nothing sent; you typed {typed!r}, not the pull request number {ctx['pr']}")

def confirmed_by_flag(a, ctx):
    if a.confirm != ctx["pr"]: sys.exit(f"nothing sent; --confirm {a.confirm} is not the pull request number {ctx['pr']}")

def submit_confirmation(verdict, drafts, warned):
    if not (drafts or warned or verdict in CONFIRMED_VERDICTS): return None
    also = f", publishing {len(drafts)} draft" + ("" if len(drafts) == 1 else "s") + " of your own with it" if drafts else ""
    return CONFIRMED_VERDICTS.get(verdict, "submit as comment") + also + (", despite the warnings above" if warned else "")

def submit(a, ctx, verdict):
    p = ctx["pending"]
    if not p: sys.exit("no pending review on the pull request; run --post first")
    rows = rf.read_posted(a.run)
    if str(p["id"]) not in rf.own_reviews(a.run, rows):
        sys.exit(f"nothing sent; pending review {p['id']} holds nothing this run posted; run --post first, or submit it on GitHub")
    body = review_body(a.run, rows, p["id"], ctx["kept"])
    warned = pending_warnings(a.run, ctx, rows, body)
    drafts = own_drafts(ctx, rows)
    if drafts: print("\n".join(own_draft_lines(drafts)), file=sys.stderr)
    calls = [{"method": "POST", "path": f"{pulls_path(ctx)}/reviews/{p['id']}/events", "fields": {"event": VERDICTS[verdict], "body": body}}]
    if a.dry_run: write_payload(a.run, calls); return
    what = submit_confirmation(verdict, drafts, warned)
    if what: confirm(a, ctx, what, ["--submit", verdict])
    execute(calls, a.repo, ctx)
    print(f"submitted review {p['id']} as {verdict}", file=sys.stderr)

def close_text(run, mid, shas):
    own = rf.read_text(rf.close_text_path(run, mid))
    if own: return own
    return f"Looks fixed in {shas[0][:7]}." if shas else "Looks fixed."

NO_FIX_COMMIT = "no fix commit to check against the pull request"
ON_HEAD = ("ahead", "identical")

def off_head(ctx, sha, repo):
    where = f"the pull request's head {ctx['head'][:7]}"
    try: on_head = compared(ctx, sha, ctx["head"], "status", repo) in ON_HEAD
    except gh_api.GhError as err: return f"GitHub cannot compare its fix {sha[:7]} with {where}, so the fix may not be pushed ({err})"
    return None if on_head else f"its fix {sha[:7]} is not on {where}; close it once the fix is on the pull request"

UNFETCHED_NEXT = "fetch {it} if {one}, or reword the status or keep the thread open with --keep-open"

def unfetched(tokens):
    if not tokens: return None
    if len(tokens) == 1: return f"its status names {tokens[0]}, which is not a commit in this clone; {UNFETCHED_NEXT.format(it='it', one='it is one')}"
    names = ", ".join(tokens[:-1]) + f" and {tokens[-1]}"
    return f"its status names {names}, which are not commits in this clone; {UNFETCHED_NEXT.format(it='them', one='they are')}"

def fix_check(ctx, shas, unknown, repo):
    if unknown: return unfetched(unknown), []
    if not shas: return None, [NO_FIX_COMMIT]
    return next(filter(None, (off_head(ctx, sha, repo) for sha in shas)), None), []

def since_others(replies, viewer):
    start = max((i + 1 for i, (author, _) in enumerate(replies) if author != viewer), default=0)
    return replies[start:]

def already_replied(thread, text, viewer):
    return pc.short_reply(viewer, text) in since_others(thread["replies"], viewer)

def close_items(run, ctx, repo, viewer):
    nums, found, titles, closable, items = rf.read_numbers(run), findings(run), rf.report_titles(run), rf.closable(run), []
    for mid in in_number_order(closable, nums):
        c = closable[mid]
        shas = rf.commits_named(repo, c.status["ref"])
        text = unwrap(close_text(run, mid, shas))
        replied = already_replied(c.thread, text, viewer)
        off, fix_warnings = fix_check(ctx, shas, rf.commits_unknown(repo, c.status["ref"]), repo)
        problem, warnings = (None, []) if replied else screen(text, ctx["local"])
        items.append({**item_head(mid, nums, found, titles), "ref": c.status["ref"], "url": c.posted["url"], "thread": c.thread,
                      "text": text, "replied": replied, "problem": off or problem, "warnings": fix_warnings + warnings})
    return items

def can_resolve(it):
    return it["thread"]["can_resolve"] == "1"

def last_reply(replies, viewer):
    return next((rf.reply_line(author, text) for author, text in reversed(replies) if author != viewer), "none")

def pending_refusal(ctx):
    p = ctx["pending"]
    return p and (f"you have pending review {p['id']} on the pull request; submit or delete your pending review first, "
                  "since a reply held in it would be invisible to the author")

def replied_then(it):
    return "--close only resolves the thread" if can_resolve(it) else "you cannot resolve the thread, so --close keeps it open and no longer offers it"

def list_closable(ctx, items, viewer):
    out = [f"pull request: {ctx['owner']}/{ctx['name']}#{ctx['pr']}"]
    for it in items:
        out += [f"{named(it)}: {it['title']}", f"  fixed in: {it['ref'] or '(no ref)'}", f"  thread: {it['url']}",
                f"  last reply: {last_reply(it['thread']['replies'], viewer)}",
                "  can resolve: " + ("yes" if can_resolve(it) else "no; the reply is sent and the thread left open")]
        reply = [f"  reply: already sent; {replied_then(it)}"] if it["replied"] else ["  reply:", indent(it["text"])]
        out += ([f"  cannot send: {it['problem']}"] if it["problem"] else []) + reply + warning_lines(it["warnings"])
    if not items: out.append("nothing to close: no posted finding is marked fixed with its thread still open")
    refused = pending_refusal(ctx)
    if refused and items: out.append(f"cannot close: {refused}")
    print("\n".join(out))

SETTLED = {"resolved": "its thread is already resolved on GitHub", "missing": "its comment is no longer on the pull request"}

def settled_threads(run, mids):
    threads = rf.posted_threads(run, rf.read_posted(run))
    return {mid: SETTLED[threads[mid]["state"]] for mid in mids if threads.get(mid, {}).get("state") in SETTLED}

def picked_ids(spec, nums, flag):
    picked = {rf.finding_id(n.strip(), nums) for n in spec.split(",") if n.strip()}
    if not picked: sys.exit(f"bad {flag} {spec!r}; use {flag} N[,M]")
    return picked

def chosen(run, spec, items):
    nums, by_id = rf.read_numbers(run), {it["id"]: it for it in items}
    picked = picked_ids(spec, nums, "--close")
    settled = settled_threads(run, picked - by_id.keys())
    refused = [numbered(mid, nums) for mid in sorted(picked) if mid not in by_id and mid not in settled]
    if refused: sys.exit("nothing sent; not closable (a thread you posted, still open, marked fixed, not kept open): " + ", ".join(refused))
    refuse_blocked([by_id[mid] for mid in sorted(picked) if mid in by_id])
    for mid in sorted(settled): print(f"{numbered(mid, nums)}: {settled[mid]}; skipped", file=sys.stderr)
    return [it for it in items if it["id"] in picked]

def close_calls(it):
    tid = it["thread"]["thread_id"]
    calls = [] if it["replied"] else [{"graphql": "addPullRequestReviewThreadReply", "finding": it["id"], "as": "reply",
                                       "variables": {"pullRequestReviewThreadId": tid, "body": it["text"]}}]
    if can_resolve(it): calls.append({"graphql": "resolveReviewThread", "variables": {"threadId": tid}, "finding": it["id"], "as": "resolve"})
    return calls

def resolved(results):
    return results.get("resolve", {}).get("resolved")

def closed_row(it, row, results, today):
    if not results: return row
    reply = results.get("reply")
    return {**row, "state": "resolved" if resolved(results) else row["state"], "date": today,
            "replies": pc.add_reply(row["replies"], reply["login"], it["text"]) if reply else row["replies"]}

def reply_word(it, results):
    return "replied" if results.get("reply") else "already replied" if it["replied"] else None

def close_outcome(it, results):
    said_so = reply_word(it, results)
    if not said_so: return f"{named(it)}: nothing sent"
    if resolved(results): return f"{named(it)}: {said_so} and resolved"
    return f"{named(it)}: {said_so}; " + ("not resolved" if can_resolve(it) else "left open, you cannot resolve it; no longer offered for closing")

def in_flight(it, results, err):
    rejected, said_so = isinstance(err, gh_api.GhError), reply_word(it, results)
    if not said_so: return f"{named(it)}: " + ("nothing sent" if rejected else "its reply may be on GitHub")
    return f"{named(it)}: {said_so}; " + ("not resolved" if rejected else "it may be resolved")

def stopped_at(it, results, err, done):
    return (f"the close stopped at {in_flight(it, results, err)}; done before it: " + ("; ".join(done) or "none")
            + "; pr/threads.tsv holds what was done")

def close_threads(run, items, repo):
    rows, done, today = rf.read_threads(run), [], datetime.date.today().isoformat()
    for it in items:
        results = {}
        try:
            for call in close_calls(it): results[call["as"]] = send(call, results, repo)
        except BaseException as err:
            message = stopped_at(it, results, err, done)
            if isinstance(err, (gh_api.GhError, UnexpectedReply)): sys.exit(f"{err}\n{message}")
            print(message, file=sys.stderr)
            raise
        finally:
            rows[it["id"]] = closed_row(it, rows[it["id"]], results, today)
            rf.write_threads(run, rows)
        if not can_resolve(it): record_kept(run, it["id"], CANNOT_RESOLVE)
        done.append(close_outcome(it, results))
    print("\n".join(["closed:", *(f"  {d}" for d in done)]), file=sys.stderr)

def refresh_threads(run, ctx, repo):
    pull = pc.fetch(ctx["owner"], ctx["name"], ctx["pr"], repo)
    threads = pc.link_threads(run, rf.read_posted(run), pull, datetime.date.today().isoformat())
    if threads.unread:
        sys.exit(f"nothing sent; --close reads only the first {pc.THREAD_LIMIT} review threads of a pull request, and this one has "
                 f"{threads.unread} more; resolve the posted findings' threads on GitHub by hand")

def close(a, ctx):
    viewer = ctx["viewer"]
    refresh_threads(a.run, ctx, a.repo)
    items = close_items(a.run, ctx, a.repo, viewer)
    if not a.close: return list_closable(ctx, items, viewer)
    sending = chosen(a.run, a.close, items)
    if not sending: print("nothing sent", file=sys.stderr); return
    refused = pending_refusal(ctx)
    if refused: sys.exit(f"nothing sent; {refused}")
    for it in sending: print_warnings(f"{named(it)}:", it["warnings"])
    calls = [call for it in sending for call in close_calls(it)]
    if a.dry_run: write_payload(a.run, calls); return
    confirm(a, ctx, f"reply and resolve {len(sending)} thread" + ("" if len(sending) == 1 else "s"), ["--close", a.close])
    close_threads(a.run, sending, a.repo)

CANNOT_RESOLVE = "replied that it looks fixed; you cannot resolve the thread"

def record_kept(run, mid, reason):
    kept = rf.read_kept_open(run)
    kept[mid] = {"reason": reason, "date": datetime.date.today().isoformat()}
    rf.write_kept_open(run, kept)

KEEP_SPEC = re.compile(r"^(#?\d+)(?::(.*))?$", re.S)

def keep_open(run, spec):
    m = KEEP_SPEC.match(spec.strip())
    if not m: sys.exit(f"bad --keep-open {spec!r}; use N[:reason]")
    nums = rf.read_numbers(run)
    mid = rf.finding_id(m.group(1), nums)
    if not rf.has_thread(rf.read_posted(run).get(mid, {})): sys.exit(f"{numbered(mid, nums)} has no posted thread to keep open")
    record_kept(run, mid, m.group(2) or "")
    print(f"{numbered(mid, nums)}: its thread is kept open; it is no longer offered for closing", file=sys.stderr)

DRAFT_HEAD = re.compile(r"^## (#?\d+): (.+?)\s*$")
DRAFT_FORM = re.compile(r"^(?:comment|question|suggestion)(?:, one general comment|, one per place)?$")
NOT_DRAFTED = re.compile(r"^not drafted: (.+)$")
DRAFT_FENCE = re.compile(r"^(`{4,}|~{4,})\s*$")

def refuse_answer(at, expected):
    sys.exit(f"nothing saved; line {at + 1} of the answer: {expected}")

def skip_blank(lines, at):
    while at < len(lines) and not lines[at].strip(): at += 1
    return at

def fenced_draft(lines, at):
    fence = DRAFT_FENCE.match(lines[at]) if at < len(lines) else None
    if not fence: refuse_answer(at, "a fence of four or more backticks or tildes was expected")
    end = next((i for i in range(at + 1, len(lines)) if rf.closes_fence(lines[i], fence.group(1))), None)
    if end is None: refuse_answer(at, "its fence is never closed")
    return end + 1, "\n".join(lines[at + 1:end])

def answer_parts(text):
    lines, parts, at = text.split("\n"), [], 0
    while (at := skip_blank(lines, at)) < len(lines):
        head = DRAFT_HEAD.match(lines[at])
        if not head: refuse_answer(at, "a heading `## <number>: <form>` was expected")
        number, said = head.groups()
        missing = NOT_DRAFTED.match(said)
        if missing: parts.append((number, None, missing.group(1))); at += 1; continue
        if not DRAFT_FORM.match(said): refuse_answer(at, f"{said!r} is not comment, question, or suggestion")
        start = at
        at, draft = fenced_draft(lines, skip_blank(lines, at + 1))
        if not draft.strip(): refuse_answer(start, f"the draft of finding {number} is empty")
        parts.append((number, said, draft))
    return parts

def checked_drafts(run, parts):
    nums, ins, seen = rf.read_numbers(run), rf.read_instructions(run), set()
    out = []
    for number, form, text in parts:
        mid = rf.finding_id(number, nums)
        if ins.get(mid, {}).get("choice") != "post": sys.exit(f"nothing saved; finding {number} is not marked Post")
        if mid in seen: sys.exit(f"nothing saved; finding {number} is answered twice")
        seen.add(mid)
        out.append((number, mid, form, text))
    return out

def save_drafts(run, answer):
    text = rf.read_text(answer)
    if not text: sys.exit(f"nothing saved; no answer in {answer}")
    drafts = checked_drafts(run, answer_parts(text))
    for number, mid, form, said in drafts:
        if form is None: print(f"finding {number}: not drafted: {said}", file=sys.stderr); continue
        rf.write_text(rf.draft_path(run, mid), said.strip("\n") + "\n")
        print(f"{number}={rf.draft_path(run, mid)}")
        print(f"finding {number}: {form}", file=sys.stderr)

def main(argv=None):
    ap = argparse.ArgumentParser(description="Preview, post, and submit a run's Post-marked findings as a pending GitHub review.")
    ap.add_argument("run"); ap.add_argument("--repo", default="."); ap.add_argument("--pr", type=int)
    action = ap.add_mutually_exclusive_group()
    action.add_argument("--post", action="store_true", help="send the previewed comments and the review body to the pending review")
    action.add_argument("--submit", choices=list(VERDICTS),
                        help="submit the pending review with this verdict; approve, request-changes, and comment on a pending review "
                             "that holds drafts of your own or text that drew a warning ask you to type the pull request number at a terminal, "
                             "or take it as --confirm PR")
    action.add_argument("--close", nargs="?", const="", metavar="N[,M]",
                        help="list the posted findings marked fixed whose threads are still open; "
                             "with numbers, reply and resolve those threads once you type the pull request number at a terminal")
    action.add_argument("--update-published", metavar="N[,M]",
                        help="send the changed text of these findings' comments that GitHub already shows (in a submitted review) "
                             "once you type the pull request number at a terminal; --post never changes them")
    action.add_argument("--keep-open", metavar="N[:REASON]", help="stop offering finding N's thread for closing")
    action.add_argument("--render-body", action="store_true",
                        help="write how the change was reviewed into posted/review.md below the text already there, replacing what an earlier run wrote")
    action.add_argument("--save-drafts", metavar="FILE",
                        help="save the post-drafter's answer in FILE as posted/draft-<merged id>.md, one per Post-marked finding; print N=<path> for each")
    ap.add_argument("--confirm", type=int, metavar="PR",
                    help="the pull request number, given in place of typing it at a terminal, once the user has said yes to this step")
    ap.add_argument("--dry-run", action="store_true", help="write the calls to <run>/posted/payload.json instead of making them")
    a = ap.parse_args(argv)
    if a.dry_run and not (a.post or a.submit or a.close or a.update_published):
        ap.error("--dry-run goes with --post, --submit, --close N, or --update-published N")
    if a.keep_open is not None: return keep_open(a.run, a.keep_open)
    if a.save_drafts: return save_drafts(a.run, a.save_drafts)
    if a.render_body: return render_body(a.run, a.repo)
    reviewed = reviewed_commit(a.run, a.repo)
    ctx = {**fetch_pr(a.repo, a.run, a.pr, reviewed), "local": local_paths(a.run, a.repo)}
    ctx["kept"] = kept_body(a.run, ctx)
    if a.submit: return submit(a, ctx, a.submit)
    if a.close is not None: return close(a, ctx)
    items = plan_items(a.run, ctx, read_hunks(pr_patch(a.repo, ctx["merge_base"], reviewed)), reviewed, a.repo)
    if a.update_published: return update_published(a, ctx, items)
    return post(a, ctx, items, reviewed) if a.post else preview(a.run, ctx, items, reviewed)

if __name__ == "__main__": main()

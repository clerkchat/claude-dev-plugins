#!/usr/bin/env python3
import argparse, datetime, json, os, re, sys
import gh_api, ids
from records import load_script

rr = load_script("render-report.py")

VERDICTS = {"comment": "COMMENT", "request-changes": "REQUEST_CHANGES", "approve": "APPROVE"}
DEFAULT_BODY = "Comments from my review of this pull request."
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
MENTION = re.compile(r"(?<![\w`/@])@([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:/[\w-]+)?)")

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

def thread_result(data):
    t = ((data or {}).get("addPullRequestReviewThread") or {}).get("thread") or {}
    nodes = (t.get("comments") or {}).get("nodes") or []
    if not nodes: raise UnexpectedReply("GitHub's answer named no new comment")
    c = nodes[0]
    return {"thread_id": t["id"], "comment_id": c["databaseId"], "comment_node": c["id"], "url": c["url"]}

MUTATIONS = {"addPullRequestReviewThread": (ADD_THREAD, thread_result),
             "updatePullRequestReviewComment": (UPDATE_COMMENT, lambda d: d),
             "deletePullRequestReviewComment": (DELETE_COMMENT, lambda d: d)}

def code_lines(text):
    fence = ""
    for line in text.split("\n"):
        if fence:
            if rr.closes_fence(line, fence): fence = ""
            yield line, True; continue
        m = rr.FENCE_RE.match(line)
        if m: fence = m.group(1)
        yield line, bool(m)

def unwrap(text):
    out, joinable = [], False
    for line, code in code_lines(text.strip("\n")):
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
    return "\n".join(re.sub(r"`[^`\n]*`", "", line) for line, code in code_lines(text) if not code)

def local_paths(*dirs):
    found = {os.path.expanduser("~")} | {norm(d) for d in dirs for norm in (os.path.abspath, os.path.realpath)}
    return sorted((p for p in found if len(p.rstrip("/")) > 1), key=len, reverse=True)

def screen(text, local):
    path = next((p for p in local if p in text), None)
    problem = f"its text names a local path of this machine ({path})" if path else None
    warnings = [f"the text names {what}: {m.group(0)}" for what, rx in INTERNAL for m in [rx.search(text)] if m]
    mentions = sorted(set(MENTION.findall(prose(text))))
    if mentions: warnings.append(f"the text mentions {', '.join('@' + m for m in mentions)}; GitHub notifies them")
    return problem, warnings

def outgoing(text, plain):
    sent = unwrap(text)
    return (SUGGESTION.sub(r"\1", sent), True) if plain and SUGGESTION.search(sent) else (sent, False)

def patch_lines(run):
    p = os.path.join(run, "patch", "all.patch")
    if not os.path.exists(p): return []
    with open(p, encoding="utf-8", newline="") as fh: return fh.read().split("\n")

def read_hunks(run):
    hunks, path, old_left, new_left, line = {}, None, 0, 0, 0
    for raw in patch_lines(run):
        if old_left > 0 or new_left > 0:
            if raw.startswith("\\"): continue
            if not raw.startswith("+"): old_left -= 1
            if not raw.startswith("-"): new_left -= 1
            continue
        if raw.startswith("+++ "):
            path = None if raw[4:].strip() == "/dev/null" else re.sub(r"^b/", "", raw[4:].strip())
            continue
        m = re.match(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", raw)
        if m and path:
            old_left, start, new_left = int(m.group(1) or 1), int(m.group(2)), int(m.group(3) or 1)
            if new_left: hunks.setdefault(path, []).append((start, start + new_left - 1))
    return hunks

def span(lo, hi):
    return f"{lo}" + (f"-{hi}" if hi != lo else "")

def nearest_lines(hunks, line, end):
    for s, e in hunks:
        if s <= line and end <= e: return (line, end), False
    s, e = min(hunks, key=lambda h: max(0, h[0] - end, line - h[1]))
    lo, hi = max(line, s), min(end, e)
    if lo > hi: lo = hi = s if s > end else e
    return (lo, hi), True

def placement(note):
    if re.search(r"\bin the review body\b", note, re.I): return {"kind": "body"}
    for token in re.findall(r"\bon\s+`?([^\s`,;]+)", note):
        m = re.match(r"^([^:]*[/.][^:]*?)(?::(\d+)(?:-(\d+))?)?$", token.rstrip(".:;)"))
        if m:
            line = int(m.group(2)) if m.group(2) else None
            return {"path": m.group(1), "line": line, "end_line": int(m.group(3) or line or 0) or None}
    return None

def anchor(kind, path="", line=None, end_line=None):
    return {"kind": kind, "path": path, "line": line, "end_line": end_line}

def resolve(e, note, files, hunks):
    p = placement(note)
    if p and p.get("kind") == "body": return anchor("body", e.get("file", "")), None, None
    path, line, end = (p["path"], p["line"], p["end_line"]) if p else (e.get("file"), e.get("line"), e.get("end_line"))
    if not path: return anchor("body"), "fallback: no file; sent in the review body", None
    if path not in files: return None, None, f"its file {path} is not in the pull request"
    if line is None: return anchor("file", path), None, None
    line, end = sorted((line, end or line))
    if not hunks.get(path): return anchor("file", path), f"fallback: {path} has no lines in the reviewed diff; sent on the file", None
    (lo, hi), moved = nearest_lines(hunks[path], line, end)
    moved_to = f"fallback: {path}:{span(line, end)} is outside the diff; moved to {span(lo, hi)}" if moved else None
    return anchor("line" if lo == hi else "range", path, lo, hi), moved_to, None

def on_github(row, ctx):
    return row["review_id"] in ctx["review_ids"] if row["kind"] == "body" else row["comment_id"] in ctx["comment_ids"]

def row_anchor(row):
    num = lambda v: int(v) if v else None
    return anchor(row["kind"], row.get("path", ""), num(row.get("line")), num(row.get("end_line")))

def findings(run):
    return {e["id"]: e for e in rr.read_findings(run, rr.load_merge_module())}

def plan_items(run, ctx):
    ins, rows, nums, found = rr.read_instructions(run), rr.read_posted(run), rr.read_numbers(run), findings(run)
    titles, hunks = rr.read_titles(run), read_hunks(run)
    marked = sorted((m for m, i in ins.items() if i.get("choice") == "post"), key=lambda m: nums.get(m, 10 ** 6))
    items = []
    for mid in marked:
        e, row, note = found.get(mid), rows.get(mid, {}), ins[mid].get("note", "")
        it = {"id": mid, "number": nums.get(mid, f"#{mid}"), "title": rr.title_of(e, titles) if e else "(not in merged.md)",
              "note": note, "row": row, "fallback": None, "problem": None, "gone": None}
        if row.get("kind") and not on_github(row, ctx):
            it["gone"] = f"its earlier comment is no longer on GitHub (review {row['review_id']}); --post posts it again"
        if row.get("kind") and not it["gone"]:
            it["anchor"], it["action"] = row_anchor(row), "skip" if row["state"] == "posted" else "update"
        elif e is None:
            it["anchor"], it["action"], it["problem"] = None, "new", "it is not in merged.md"
        else:
            it["anchor"], it["fallback"], it["problem"] = resolve(e, note, ctx["files"], hunks)
            it["action"] = "new"
        raw = rr.posted_text(run, mid)
        if not raw: it["problem"] = it["problem"] or "it has no posted text"
        if it["action"] != "skip" and rr.stale_text(row, note):
            it["problem"] = it["problem"] or "its posted text is to be redrafted; the note changed"
        plain = bool(it["fallback"]) or (it["anchor"] or {}).get("kind") not in LINE_KINDS
        it["text"], it["downgraded"] = outgoing(raw, plain)
        problem, it["warnings"] = screen(it["text"], ctx["local"])
        it["problem"] = it["problem"] or problem
        items.append(it)
    return items

def review_body(run, rows, review_id):
    head = rr.read_text(os.path.join(run, "posted", "review.md"))
    parts = [unwrap(head) if head else DEFAULT_BODY]
    for mid in sorted(rows):
        row = rows[mid]
        if row.get("kind") == "body" and str(row.get("review_id")) == str(review_id):
            text = outgoing(rr.posted_text(run, mid), True)[0]
            parts.append((f"**`{row['path']}`**\n\n" if row.get("path") else "") + text)
    return "\n\n".join(parts)

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
    node = ((ctx["pending"] or {}).get("comments") or {}).get(comment)
    if node:
        return {"graphql": "updatePullRequestReviewComment", "finding": it["id"],
                "variables": {"pullRequestReviewCommentId": node, "body": it["text"]}}
    return {"method": "PATCH", "path": f"repos/{ctx['owner']}/{ctx['name']}/pulls/comments/{comment}",
            "fields": {"body": it["text"]}, "finding": it["id"]}

def planned_rows(rows, sending, review_id, today):
    out = dict(rows)
    for it in sending:
        a, row = it["anchor"], it["row"]
        new = {"state": "posted", "date": today, "note": row.get("note", it["note"])}
        if a["kind"] == "body":
            new.update(thread_id="", comment_id="", url=Ref("review", "html_url"))
        elif it["action"] == "new":
            new.update({k: Ref(result_key(it["id"]), k) for k in ("thread_id", "comment_id", "url")})
        if it["action"] == "new" or a["kind"] == "body":
            new.update(kind=a["kind"], path=a["path"], line=str(a["line"] or ""), end_line=str(a["end_line"] or ""),
                       side="RIGHT" if a["kind"] in LINE_KINDS else "", review_id=review_id)
        out[it["id"]] = {**row, **new}
    return out

def post_calls(ctx, sending, body, reviewed):
    base, pending = pulls_path(ctx), ctx["pending"]
    calls = [] if pending else [{"method": "POST", "path": f"{base}/reviews", "fields": {"commit_id": reviewed, "body": body}, "as": "review"}]
    review_node = pending["node_id"] if pending else Ref("review", "node_id")
    calls += [thread_call(it, review_node) for it in sending if it["action"] == "new" and it["anchor"]["kind"] != "body"]
    calls += [update_call(ctx, it) for it in sending if it["action"] == "update" and it["anchor"]["kind"] != "body"]
    if pending: calls.append({"method": "PUT", "path": f"{base}/reviews/{pending['id']}", "fields": {"body": body}})
    return calls

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
    return None, f"{name}'s comment {row_url(call, items)}, which keeps its new text"

def unknown_of(call, results, items, ctx):
    name = finding_name(call, items)
    if call.get("as") == "review": return "a pending review this batch began"
    if is_thread(call): return f"{name}'s comment on pending review {(ctx['pending'] or results.get('review') or {}).get('id', '')}"
    if "finding" in call: return f"{name}'s new text on its comment {row_url(call, items)}"
    return f"{call.get('method', '')} {call.get('path', '')}"

def recover(call, results, repo, ctx):
    if call.get("as") == "review":
        return next((r for r in gh_api.rest_list(call["path"], repo) if r["state"] == "PENDING"), None)
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

def rollback(done, results, repo, items, ctx, inflight=None):
    maybe = []
    if inflight is not None:
        found = found_by(inflight, results, repo, ctx)
        if found: results[inflight["as"]] = found; done = [*done, inflight]
        else: maybe.append((inflight, unknown_of(inflight, results, items, ctx)))
    if not (done or maybe): return "nothing changed on GitHub"
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
    stop = lambda inflight=None: rollback(done, results, repo, {it["id"]: it for it in items}, ctx, inflight)
    try:
        for call in calls:
            r = send(call, results, repo)
            if "as" in call: results[call["as"]] = r
            done.append(call)
    except gh_api.GhError as err:
        sys.exit(f"{err}\nGitHub rejected the request; {stop()}")
    except UnexpectedReply as err:
        sys.exit(f"{err}\nthe batch stopped; {stop(calls[len(done)])}")
    except BaseException:
        print(f"the batch stopped; {stop(calls[len(done)])}", file=sys.stderr)
        raise
    return results

def write_payload(run, calls):
    os.makedirs(os.path.join(run, "posted"), exist_ok=True)
    p = os.path.join(run, "posted", "payload.json")
    with open(p, "w", encoding="utf-8") as fh: json.dump({"calls": calls}, fh, indent=1)
    print(f"dry run: wrote {len(calls)} calls to {p}", file=sys.stderr)

def same_commit(a, b):
    return bool(a and b) and (a.startswith(b) or b.startswith(a))

def reviewed_commit(run):
    target = rr.read_text(os.path.join(run, "target.txt")).splitlines()
    if len(target) < 3: sys.exit("target.txt has no HEAD line")
    return target[2].strip()

def recorded_pr(run):
    number, url = (rr.read_text(os.path.join(run, "pr", "pr.txt")).split("\t") + [""])[:2]
    target = (rr.read_text(os.path.join(run, "target.txt")).splitlines() or [""])[0].strip()
    m = PULL_URL.search(url.strip()) or PULL_URL.search(target)
    if m: return int(m.group(3)), f"{m.group(1)}/{m.group(2)}"
    m = TARGET_PR.match(number.strip()) or TARGET_PR.match(target)
    return (int(m.group(1)) if m else None), None

def branch_pr(repo):
    try: return gh_api.pr_number(repo)
    except gh_api.GhError: return None

def reviewed_pr(repo, run, asked, repo_name):
    number, reviewed_repo = recorded_pr(run)
    if reviewed_repo and reviewed_repo.lower() != repo_name.lower():
        sys.exit(f"nothing sent; the run reviewed a pull request of {reviewed_repo}, but --repo is {repo_name}")
    known = number or branch_pr(repo)
    if asked and known and asked != known: sys.exit(f"nothing sent; --pr {asked} is not the reviewed pull request #{known}")
    if not (asked or known): sys.exit("no pull request found for the run or the branch; pass --pr N")
    return asked or known

def fetch_pr(repo, run, pr):
    owner, name = gh_api.repo_owner_name(repo)
    pr = reviewed_pr(repo, run, pr, f"{owner}/{name}")
    ctx = {"owner": owner, "name": name, "pr": pr, "pending": None}
    base = pulls_path(ctx)
    ctx["head"] = json.loads(gh_api.gh(["pr", "view", str(pr), "--json", "headRefOid"], repo))["headRefOid"]
    ctx["files"] = [f["filename"] for f in gh_api.rest_list(f"{base}/files", repo)]
    reviews = gh_api.rest_list(f"{base}/reviews", repo)
    ctx["review_ids"] = {str(r["id"]) for r in reviews}
    ctx["comment_ids"] = {str(c["id"]) for c in gh_api.rest_list(f"{base}/comments", repo)}
    pending = next((r for r in reviews if r["state"] == "PENDING"), None)
    if pending:
        comments = gh_api.rest_list(f"{base}/reviews/{pending['id']}/comments", repo)
        ctx["pending"] = {"id": pending["id"], "node_id": pending["node_id"], "commit_id": pending["commit_id"],
                          "html_url": pending.get("html_url", ""), "comments": {c["id"]: c["node_id"] for c in comments}}
        ctx["comment_ids"] |= {str(c) for c in ctx["pending"]["comments"]}
    return ctx

def current_review(ctx):
    return str(ctx["pending"]["id"]) if ctx["pending"] else Ref("review", "id")

def pending_line(ctx, reviewed, verb):
    p = ctx["pending"]
    if not p: return f"pending review: none; {verb} creates one on {reviewed[:9]}"
    if same_commit(p["commit_id"], reviewed): return f"pending review: {p['id']} on {reviewed[:9]} exists; {verb} adds to it"
    return (f"pending review: {p['id']} exists on {p['commit_id'][:9]}, another commit than the reviewed {reviewed[:9]}; "
            f"{verb} adds to it anyway")

def indent(text):
    return "\n".join("    " + l if l else "" for l in text.split("\n"))

def warning_lines(warnings):
    return [f"  warning: {w}" for w in warnings]

def checked_body(run, ctx, rows, review_id):
    body = review_body(run, rows, review_id)
    problem = screen(body, ctx["local"])[0]
    if problem: sys.exit(f"nothing sent; the review body: {problem}")
    return body

def preview(run, ctx, items, reviewed):
    out = [f"pull request: {ctx['owner']}/{ctx['name']}#{ctx['pr']}"]
    for it in items:
        out.append(f"finding {it['number']}: {it['title']}")
        a = it["anchor"]
        if a: out.append(f"  anchor: " + ("review body" if a["kind"] == "body" else f"{a['path']}" + (f":{span(a['line'], a['end_line'])}" if a["line"] else "")) + f" ({a['kind']})")
        if it["gone"]: out.append(f"  {it['gone']}")
        if it["fallback"]: out.append(f"  {it['fallback']}")
        if it["downgraded"]: out.append("  suggestion sent as a plain code block")
        if it["action"] == "skip": out.append(f"  already posted: {it['row'].get('url', '')}"); continue
        if it["action"] == "update": out.append("  changed since posting: --post updates the comment")
        if it["problem"]: out.append(f"  cannot post: {it['problem']}"); continue
        out += ["  text:", indent(it["text"])] + warning_lines(it["warnings"])
    review_id = current_review(ctx)
    rows = planned_rows(rr.read_posted(run), [it for it in items if it["action"] != "skip" and not it["problem"]], review_id, "")
    body = review_body(run, rows, review_id)
    problem, warnings = screen(body, ctx["local"])
    out += ["review body:", indent(body)] + ([f"  cannot post: {problem}"] if problem else []) + warning_lines(warnings)
    if not same_commit(ctx["head"], reviewed):
        out.append(f"head moved: the pull request head is {ctx['head'][:9]}, the review judged {reviewed[:9]}; comments anchor on the reviewed commit")
    out.append(pending_line(ctx, reviewed, "--post"))
    print("\n".join(out))

def posted_lines(sending, results):
    review = results["review"]
    out = [f"  review {review['id']} {review.get('html_url', '')}"]
    for it in sending:
        c = results.get(result_key(it["id"])) or it["row"]
        where = "in the review body" if it["anchor"]["kind"] == "body" else f"comment {c.get('comment_id', '')} {c.get('url', '')}"
        out.append(f"  finding {it['number']}: {where}")
    return out

def post(a, ctx, items, reviewed):
    blocked = [f"finding {it['number']}: {it['problem']}" for it in items if it["action"] != "skip" and it["problem"]]
    if blocked: sys.exit("nothing sent; " + "; ".join(blocked))
    sending = [it for it in items if it["action"] != "skip"]
    if not sending: print("nothing to post: every Post-marked finding is already posted", file=sys.stderr); return
    review_id = current_review(ctx)
    rows = planned_rows(rr.read_posted(a.run), sending, review_id, datetime.date.today().isoformat())
    calls = post_calls(ctx, sending, checked_body(a.run, ctx, rows, review_id), reviewed)
    print(pending_line(ctx, reviewed, "this batch"), file=sys.stderr)
    if a.dry_run: write_payload(a.run, calls); return
    results = execute(calls, a.repo, ctx, items)
    if ctx["pending"]: results["review"] = ctx["pending"]
    try: rr.write_posted(a.run, {mid: {k: str(resolve_refs(v, results)) for k, v in row.items()} for mid, row in rows.items()})
    except BaseException:
        print("\n".join(["posted.tsv was not updated; this batch is on GitHub:", *posted_lines(sending, results)]), file=sys.stderr)
        raise
    new = sum(it["action"] == "new" for it in sending)
    print(f"posted {new} comments and updated {len(sending) - new} on review {results['review']['id']}; "
          f"skipped {len(items) - len(sending)} already posted", file=sys.stderr)

def submit(a, ctx, verdict):
    p = ctx["pending"]
    if not p: sys.exit("no pending review on the pull request; run --post first")
    rows = rr.read_posted(a.run)
    if not any(row.get("review_id") == str(p["id"]) for row in rows.values()):
        sys.exit(f"nothing sent; pending review {p['id']} holds nothing this run posted; run --post first, or submit it on GitHub")
    body = checked_body(a.run, ctx, rows, p["id"])
    calls = [{"method": "POST", "path": f"{pulls_path(ctx)}/reviews/{p['id']}/events", "fields": {"event": VERDICTS[verdict], "body": body}}]
    if a.dry_run: write_payload(a.run, calls); return
    execute(calls, a.repo, ctx)
    print(f"submitted review {p['id']} as {verdict}", file=sys.stderr)

def main(argv=None):
    ap = argparse.ArgumentParser(description="Preview, post, and submit a run's Post-marked findings as a pending GitHub review.")
    ap.add_argument("run"); ap.add_argument("--repo", default="."); ap.add_argument("--pr", type=int)
    action = ap.add_mutually_exclusive_group()
    action.add_argument("--post", action="store_true", help="send the previewed comments to the pending review")
    action.add_argument("--submit", choices=list(VERDICTS), help="submit the pending review with this verdict")
    ap.add_argument("--dry-run", action="store_true", help="write the calls to <run>/posted/payload.json instead of making them")
    a = ap.parse_args(argv)
    if a.dry_run and not (a.post or a.submit): ap.error("--dry-run goes with --post or --submit")
    reviewed = reviewed_commit(a.run)
    ctx = {**fetch_pr(a.repo, a.run, a.pr), "local": local_paths(a.run, a.repo)}
    if a.submit: return submit(a, ctx, a.submit)
    items = plan_items(a.run, ctx)
    return post(a, ctx, items, reviewed) if a.post else preview(a.run, ctx, items, reviewed)

if __name__ == "__main__": main()

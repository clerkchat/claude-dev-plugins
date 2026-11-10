#!/usr/bin/env python3
"""Bring a pull request's human review comments into a review run.

Usage:
  pr-comments.py RUN_DIR [--pr N] [--repo PATH]   # fetch, add new comments, propose links
  pr-comments.py RUN_DIR --judged FILE            # apply judge decisions on candidates

Fetches review threads (inline comments with replies, resolved and outdated
state), review summaries with a body, and conversation comments through `gh`.
Comments already brought in (by GitHub id, recorded in
pr/seen.tsv) are updated in place, never duplicated.

Each new comment gets up to five candidate agent findings in
pr/candidates.tsv, ranked by wording overlap, same file, and same directory.
Nothing is linked automatically: human comments are phrased too differently
for word overlap, and nearby lines often hold a different defect. A judge
reads each comment with its candidates and decides; --judged applies its
lines "pr_id<TAB>finding_id<TAB>same|different" (at most one `same` per
comment). A linked comment
renders inside the finding's card; an unlinked one renders as its own card in
the "Pull request comments" section.

Two skip rules keep noise out. A conversation comment by a noise bot (Linear,
Vercel, Netlify, Codecov) is skipped; review threads and review summaries are
never skipped by author. A comment, thread, or review whose whole text is a
short courtesy phrase (LGTM, thanks, a thumbs up) is skipped; a thread only
when every comment in it is. Skipped comments are recorded in pr/seen.tsv with
their reason, never come back, and are counted by reason in the summary.
Every APPROVED review not posted by this run is recorded with its author in
pr/approvals.tsv, rewritten on each import, for the report's "Approved by" line.
"""
import argparse, datetime, json, os, re, sys
from collections import Counter, namedtuple
from records import load_script
from gh_api import graphql, pr_number, repo_owner_name
import run_files as rf

rc = load_script("reconcile.py"); mf = rc.mf

THREAD_LIMIT = 100
Q = """query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){
number url headRefName
reviewThreads(first:""" + str(THREAD_LIMIT) + """){totalCount nodes{id isResolved isOutdated viewerCanResolve path line startLine originalLine
  comments(first:50){nodes{databaseId author{login} viewerDidAuthor body url createdAt pullRequestReview{state}}}}}
reviews(first:100){nodes{databaseId author{login} body state url}}
comments(first:100){nodes{databaseId author{login} body url}}}}}"""

def words(e):
    """Words of the title and claim, with identifiers split into their parts
    (TestScenario, test_scenario, and testScenario all give test, scenario)."""
    t = e.get("title", "") + " " + e.get("claim", "")
    t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", t).replace("_", " ")
    return {w for w in re.findall(r"[a-z][a-z0-9]{2,}", t.lower()) if w not in rc.STOP}

def one_line(text, n=300):
    t = re.sub(r"<img[^>]*>", "[image]", text)
    t = re.sub(r"```.*?```", "[code]", t, flags=re.S)
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + " ..."

def title_from(text):
    t = one_line(text, 400)
    first = re.split(r"(?<=[.?!])\s", t)[0]
    return first if len(first) <= 90 else first[:87].rsplit(" ", 1)[0]

def short_reply(author, body):
    return author, one_line(body, 200)

def join_replies(replies):
    return rf.joined_replies(short_reply(a, b) for a, b in replies)

def add_reply(replies, author, body):
    return [*replies, short_reply(author, body)]

class GithubComment(namedtuple("GithubComment", "kind gid author body url path line oline replies resolved outdated state",
                                defaults=("", None, None, (), False, False, ""))):
    __slots__ = ()

    @property
    def key(self):
        return f"{self.kind}:{self.gid}"

def github_state(c):
    return ", ".join(x for x in ("resolved" if c.resolved else "", "outdated" if c.outdated else "",
                                 c.state.lower() if c.state and c.state != "COMMENTED" else "") if x)

def entry(mid, c):
    f = {
        "lens": "pr-review", "source": "github", "slice": "pull-request", "severity": "major", "confidence": "100",
        "file": c.path or "(pull request)", "line": str(c.line or c.oline or ""),
        "title": title_from(c.body), "claim": one_line(c.body, 1200), "author": c.author, "url": c.url,
        "github_id": c.key, "replies": join_replies(c.replies), "github_state": github_state(c),
        "evidence": f"Comment by @{c.author} on the pull request" + (f", originally at line {c.oline}" if c.oline and c.oline != c.line else ""),
    }
    return mf.format_entry([("id", mid)] + [(k, v) for k, v in f.items() if v not in ("", None)])

def login(c):
    return (c.get("author") or {}).get("login", "ghost")

def comment_item(kind, c, **fields):
    return GithubComment(kind, c["databaseId"], login(c), c["body"], c["url"], **fields)

def root_of(t):
    return t["comments"]["nodes"][0]

def is_pending(c):
    return (c.get("pullRequestReview") or {}).get("state") == "PENDING"

def replies_of(t):
    return [(login(c), c["body"]) for c in t["comments"]["nodes"][1:] if not is_pending(c)]

def thread_item(t):
    return comment_item("thread", root_of(t), path=t["path"], line=t["line"], oline=t["originalLine"], replies=replies_of(t),
                        resolved=t["isResolved"], outdated=t["isOutdated"])

def submitted_reviews(p):
    return [r for r in p["reviews"]["nodes"] if r["state"] != "PENDING"]

NOISE_BOTS = frozenset({"linear[bot]", "vercel[bot]", "netlify[bot]", "codecov[bot]", "codecov-commenter"})
COURTESY_WORDS = frozenset({"lgtm", "thanks", "thank", "you", "ty", "thx", "approved", "nice", "done", "great", "good", "looks", "to",
                            "me", "ship", "it", "work", "awesome", "perfect", "+1"})
COURTESY_MAX_WORDS = 5
NOT_WORD_CHARS = re.compile(r"[^\w\s+\u0080-\U0010ffff]|\ufe0f")

def is_courtesy_word(w):
    return w in COURTESY_WORDS or not w.isascii() and not any(ch.isalnum() for ch in w)

def is_courtesy(body):
    ws = NOT_WORD_CHARS.sub("", body.lower()).split()
    return 0 < len(ws) <= COURTESY_MAX_WORDS and all(map(is_courtesy_word, ws))

def skip_reason(c):
    if c.kind == "comment" and c.author.lower() in NOISE_BOTS: return "bot"
    return "courtesy" if all(is_courtesy(body) for body in (c.body, *(b for _, b in c.replies))) else ""

def github_items(p, threads, own_review_ids=()):
    return ([thread_item(t) for t in threads]
            + [comment_item("review", r, state=r["state"]) for r in submitted_reviews(p)
               if r["body"].strip() and str(r["databaseId"]) not in own_review_ids]
            + [comment_item("comment", c) for c in p["comments"]["nodes"] if c["body"].strip()])

Threads = namedtuple("Threads", "linked imported left_out unread")

def sort_threads(p, linking):
    linked, imported, left_out = {}, [], 0
    for t in p["reviewThreads"]["nodes"]:
        if not t["comments"]["nodes"]: continue
        root = root_of(t)
        if root["databaseId"] in linking: linked[linking[root["databaseId"]]] = t
        elif is_pending(root): left_out += 1
        else: imported.append(t)
    unread = p["reviewThreads"].get("totalCount", 0) - len(p["reviewThreads"]["nodes"])
    return Threads(linked, imported, left_out, max(unread, 0))

def flag(on):
    return "1" if on else "0"

def thread_span(t):
    return rf.line_span(t.get("startLine") or t["line"], t["line"]) if t["line"] else ""

def thread_row(t, today):
    root = root_of(t)
    state = "pending" if is_pending(root) else "resolved" if t["isResolved"] else "open"
    return {"comment_id": str(root["databaseId"]), "thread_id": t["id"], "state": state, "outdated": flag(t["isOutdated"]),
            "can_resolve": flag(t.get("viewerCanResolve")), "by_viewer": flag(root.get("viewerDidAuthor")), "line": thread_span(t),
            "replies": [short_reply(a, b) for a, b in replies_of(t)], "date": today}

def missing_row(posted, today):
    return {"comment_id": posted["comment_id"], "thread_id": posted["thread_id"], "state": "missing",
            "outdated": "0", "can_resolve": "0", "by_viewer": "0", "line": "", "replies": [], "date": today}

def unlinked_row(known, mid, posted, unread, today):
    return known.get(mid) if unread else missing_row(posted, today)

def link_threads(run, posted, p, today):
    posted = {mid: row for mid, row in posted.items() if rf.has_thread(row)}
    threads = sort_threads(p, {int(row["comment_id"]): mid for mid, row in posted.items()})
    if posted:
        known = rf.read_threads(run)
        rows = {mid: thread_row(threads.linked[mid], today) if mid in threads.linked else unlinked_row(known, mid, row, threads.unread, today)
                for mid, row in posted.items()}
        rf.write_threads(run, {mid: row for mid, row in rows.items() if row})
    return threads

Folded = namedtuple("Folded", "new_ids updated linked left_out unread_threads skipped approvals", defaults=(Counter(), 0))

def fetch(owner, name, pr, cwd):
    return graphql(Q, {"o": owner, "r": name, "n": pr}, cwd)["data"]["repository"]["pullRequest"]

def pr_dir(run):
    pd = os.path.join(run, "pr"); os.makedirs(pd, exist_ok=True)
    return pd

SEEN_FIELDS = ("merged_id", "skipped")

def seen_path(run):
    return os.path.join(run, "pr", "seen.tsv")

def read_seen(run):
    return rf.read_keyed(seen_path(run), SEEN_FIELDS, key=str)

def seen_order(item):
    key, row = item
    return (0, int(row["merged_id"]), key) if row["merged_id"].isdigit() else (1, 0, key)

def write_seen(run, seen):
    rf.write_keyed(seen_path(run), SEEN_FIELDS, dict(sorted(seen.items(), key=seen_order)), header=None, order=list)

DUPLICATE_OF = re.compile(r"\n  duplicate_of: (\d+)")

def duplicate_of(text):
    m = DUPLICATE_OF.search(text)
    return m.group(1) if m else None

def linked_to(text, fid):
    return f"{text}\n  duplicate_of: {fid}"

def refreshed(mid, c, old):
    dup = duplicate_of(old)
    return linked_to(entry(mid, c), dup) if dup else entry(mid, c)

def import_items(run, items):
    header, entries = mf.read_entries(rf.merged_path(run))
    seen = read_seen(run)
    new_ids, updated, skipped = [], 0, Counter()
    for c in items:
        row = seen.get(c.key, {})
        if row.get("skipped"): continue
        if row.get("merged_id", "").isdigit():
            mid = int(row["merged_id"])
            if mid in entries: entries[mid] = refreshed(mid, c, entries[mid]); updated += 1
        elif reason := skip_reason(c):
            seen[c.key] = {"merged_id": "", "skipped": reason}; skipped[reason] += 1
        else:
            mid = mf.next_entry_id(entries); new_ids.append(mid)
            seen[c.key] = {"merged_id": str(mid), "skipped": ""}
            entries[mid] = entry(mid, c)
    mf.write_entries(rf.merged_path(run), header, entries)
    write_seen(run, seen)
    return new_ids, updated, skipped

def approvals_of(p, own_review_ids, today):
    return {r["databaseId"]: {"author": login(r), "date": today} for r in submitted_reviews(p)
            if r["state"] == "APPROVED" and str(r["databaseId"]) not in own_review_ids}

def fold_in(run, p, today):
    pd = pr_dir(run)
    open(os.path.join(pd, "comments.json"), "w").write(json.dumps(p, indent=1))
    open(os.path.join(pd, "pr.txt"), "w").write(f"{p['number']}\t{p['url']}\n")
    posted = rf.read_posted(run)
    threads = link_threads(run, posted, p, today)
    own = rf.own_reviews(run, posted)
    own_reviews = [r for r in submitted_reviews(p) if r["body"].strip() and str(r["databaseId"]) in own]
    new_ids, updated, skipped = import_items(run, github_items(p, threads.imported, own))
    approvals = approvals_of(p, own, today)
    rf.write_approvals(run, approvals)
    return Folded(new_ids, updated, len(threads.linked) + len(own_reviews), threads.left_out, threads.unread, skipped, len(approvals))

CANDIDATE_HEADER = ("pr_id", "finding_id", "score")

def shortlist(run, new_ids):
    allm = rc.load(run)
    agents = {i: e for i, e in allm.items() if e.get("lens") != "pr-review" and not mf.is_credit(e)}
    reported = set(rf.read_numbers(run))
    rows = []
    for mid in new_ids:
        c = allm[mid]; cw = words(c); scored = []
        cdir = os.path.dirname(c["file"])
        for fid, f in agents.items():
            sim = rc.jac(cw, words(f))
            score = sim + (0.3 if f["file"] == c["file"] else 0) + (0.1 if cdir and os.path.dirname(f["file"]) == cdir else 0) + (0.05 if fid in reported else 0)
            scored.append((score, fid))
        ranked = sorted(scored, reverse=True)
        keep = [x for x in ranked if x[0] >= 0.12][:5] or ranked[:3]
        if len(keep) < 3: keep = ranked[:3]
        for score, fid in keep:
            rows.append((mid, fid, score))
    rf.write_rows(os.path.join(pr_dir(run), "candidates.tsv"), CANDIDATE_HEADER, ([str(mid), str(fid), f"{sc:.2f}"] for mid, fid, sc in rows))
    return rows

def apply_judged(run, judged):
    header, entries = mf.read_entries(rf.merged_path(run))
    links = 0
    for f in rc.judged_rows(judged):
        if len(f) >= 3 and f[2] == "same":
            pid, fid = int(f[0]), f[1]
            if pid in entries and duplicate_of(entries[pid]) is None:
                entries[pid] = linked_to(entries[pid], fid); links += 1
    mf.write_entries(rf.merged_path(run), header, entries)
    return links

SKIPPED_REASONS = {"bot": "from noise bots", "courtesy": "courtesy-only"}

def skipped_part(skipped):
    return f"{sum(skipped.values())} skipped (" + ", ".join(f"{skipped[k]} {text}" for k, text in SKIPPED_REASONS.items() if skipped[k]) + ")"

def summary(pr, folded, rows):
    parts = [f"{len(folded.new_ids)} new comments", f"{folded.updated} updated"]
    if folded.skipped: parts.append(skipped_part(folded.skipped))
    if folded.approvals: parts.append(f"{folded.approvals} approval" + "s" * (folded.approvals > 1))
    if folded.linked: parts.append(f"{folded.linked} posted findings linked")
    if folded.left_out: parts.append(f"{folded.left_out} threads of your own pending review left out")
    parts.append(f"{len(rows)} candidate links for {len({r[0] for r in rows})} comments to judge")
    if folded.unread_threads: parts.append(f"{folded.unread_threads} review threads past the first {THREAD_LIMIT} not read; "
                                           "a posted finding among them keeps the thread state last read")
    return f"PR #{pr}: " + ", ".join(parts)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run"); ap.add_argument("--pr", type=int); ap.add_argument("--repo", default=".")
    ap.add_argument("--judged")
    a = ap.parse_args()
    if a.judged:
        links = apply_judged(a.run, a.judged)
        print(f"linked {links} pull request comments after judging", file=sys.stderr); return
    pr = a.pr or pr_number(a.repo)
    folded = fold_in(a.run, fetch(*repo_owner_name(a.repo), pr, a.repo), datetime.date.today().isoformat())
    print(summary(pr, folded, shortlist(a.run, folded.new_ids)), file=sys.stderr)

if __name__ == "__main__": main()

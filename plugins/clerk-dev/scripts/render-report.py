#!/usr/bin/env python3
"""Render report.md for a review run from merged.md, the verify files, and the slice map.

Usage: render-report.py RUN_DIR --target T --branch B --base SHA --head SHA
         [--repo PATH] [--routing routing.md] [--threshold 80]
         [--summary summary.md] [--not-reviewed not-reviewed.md] [--out report.md]

Selection: a finding is dropped when its verdict is rejected. Confidence after
verification decides the section: blocker or major at or above the threshold
go to "Fix before merging"; minor at or above the threshold, and anything from
60 up to the threshold, go to "Worth a look" with a caveat; a blocker below 60
that was not rejected goes to "Needs confirmation". A finding whose origin
(the verifier's, else the reviewers') is `existing`, a defect already on the
remote main that the branch did not introduce or worsen, goes to "Already on
main" instead of any of those three, with a separate pull request as the
action. A tech-debt finding (one with a `debt` label: cleanup, simplify, or
refactor) goes to "Cleanup and refactoring" instead, whatever its origin, with
its label as the action. Each card carries a scope line (fix size, origin, follow-up in another
repository) and the glance table a Size column. Findings with no verdict
are not reported and are counted in "About this review". Numbers are assigned
in document order (section, then area ranked by its top finding, then severity
and confidence) and written to numbers.tsv so later references are stable.
RUN_DIR/overrides/<merged id>.md may hold replacement fields (title,
what_changed, steps, impact, snippet, fix) in `key: value` form; they overlay
the merged entry so a re-render keeps hand-written text.
Snippets come from `git show HEAD:path` in --repo when a finding names
`snippet: path:start-end` (at most 12 lines). Prose wraps at --wrap columns (default 80; 0 disables); headings, tables,
code, locations, and anchors are never wrapped. Each card carries an HTML
comment anchor with its number, merged id, verify file, and raw files.
A finding appended after a fix may carry `surfaced_by: <merged id>`; its card
then says which fix surfaced it. Any appended finding (reconcile/appended.tsv)
that has no instruction or status yet gets `[new]` after its heading.
RUN_DIR/reconcile/ (from reconcile.py, plus prior.tsv and since.tsv written by
the orchestrator) adds a "Since the previous review" block, a "Reopened"
section for findings marked fixed before and found again, a "Previously
declined" section for declined findings whose reason still holds, and a
history line on every card that matches an earlier finding.
RUN_DIR/resolution/<merged id>.md, when present, renders as a "Resolution"
subsection at the end of the card: what was done and how it differed from
the recommendation.
--set N=STATUS[:REF] changes a status by finding number (#<id> for a merged
id) and wins over everything else in that render. A checkbox in report.md
counts as a hand edit only when it differs from the line last rendered for
that finding (rendered-status.tsv), so a report that predates a status change
never reverts it. --routing defaults to the plugin's own routing.md.
RUN_DIR/status.tsv (merged id, status, ref, date) records what was done
about each finding: open, in-progress, fixed, wont-fix, deferred. Each card
shows it as a checkbox line and the glance table as a column; a checkbox
ticked by hand in the existing report.md is imported into status.tsv before
rendering, so hand edits survive. Every commit a --set ref names is also
appended to RUN_DIR/commits.tsv (merged id, commit, status, date), which is
never rewritten, so a fix of two commits keeps both.
Safeguards: each render stamps the report with a generation number and keeps
that render's snapshots under RUN_DIR/.render/<generation>/, so a report
saved from an editor buffer opened before a later render only contributes the
lines actually changed in it. The previous report is kept as report.prev.md. Two ticked instructions use the first and say so on
the card. A "Notes:" line under each checklist holds free text
(RUN_DIR/notes/<merged id>.md) that survives renders; --note N=FILE appends a
paragraph to it without touching the report. "Fix as noted" means: fix it,
following the Notes, which replace the card's recommendation. "Fix as
recommended (a)" (or "(a, c)") picks labeled alternatives of a recommendation;
the pick is stored in the option column of instructions.tsv.
Any `{#<merged id>}` token in the summary, overrides, or finding text is
replaced by that finding's current number. Titles come from the finding's
`title` field, overridden by RUN_DIR/titles.tsv (merged id, tab, title) when
present, else shortened from the claim.
"""
import argparse, os, re, shutil, subprocess, sys, textwrap
from collections import namedtuple
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from records import ROUTING, load_script, read_plain_names
mf = load_script("merge-findings.py")

SEV = {"blocker": 3, "major": 2, "minor": 1}
TITLES = {}
NAMES = {}
STATUS = {}
INSTR = {}
POSTED = {}
PR_LINKS = {}
RECON = {"label": "", "matches": {}, "prior": {}, "since": {}, "unmatched": []}
RUN = "."
IDNUM = {}
TITLE_BY_ID = {}
CREDITS = set()

def load_merge_module(): return mf

def read_merged(path, mf):
    text = open(path, encoding="utf-8").read()
    out = []
    for block in mf.parse_blocks(text):
        for e in mf.parse_entries(block, "merged"):
            srcs = [x.strip() for x in str(e.get("sources", "")).split(",") if x.strip()]
            e = mf.norm(e)
            e["id"] = int(re.sub(r"\D", "", str(e.get("id", "0")) or "0"))
            if srcs: e["sources"] = srcs
            out.append(e)
    return out

def read_verdicts(run):
    v = {}
    vdir = os.path.join(run, "verify")
    if os.path.isdir(vdir):
        for n in os.listdir(vdir):
            m = re.match(r"^(\d+)\.md$", n)
            if not m: continue
            t = open(os.path.join(vdir, n), encoding="utf-8").read()
            v[int(m.group(1))] = parse_verdict(t)
    flat = os.path.join(run, "verdicts.txt")
    if os.path.exists(flat):
        for line in open(flat, encoding="utf-8"):
            m = re.match(r"^\s*id:\s*(\d+)\s*\|(.*)$", line)
            if m: v.setdefault(int(m.group(1)), parse_verdict(m.group(2)))
    return v

def parse_verdict(t):
    def g(k, d=""):
        m = re.search(rf"{k}:\s*([^|\n]+)", t); return m.group(1).strip() if m else d
    conf = re.sub(r"\D", "", g("confidence", "0")) or "0"
    return {"verdict": g("verdict", "confirmed").lower(), "confidence": int(conf), "severity": g("severity", "").lower(), "note": g("note", ""),
            "origin": g("origin", "").lower(), "fix_size": g("fix_size", "").lower()}

ORIGIN_WORDS = {"new": "New on this branch", "worsened": "Made worse by this branch", "existing": "Already on main: fix in a separate pull request"}
SIZES = ("trivial", "small", "medium", "large")
DEBT_ORIGIN_WORDS = {"new": "In code new on this branch", "worsened": "In code on main this branch extended", "existing": "In code already on main"}
DEBT_WORDS = {"cleanup": "Cleanup", "simplify": "Simplify", "refactor": "Refactor"}

def debt_intro(entries):
    saved = sum(e.get("_saves", 0) for e in entries)
    return ("Ways to make the code this change touches smaller and easier to change: cleanups within a function, simplifications that keep the behavior in fewer lines, and refactors that change the structure. None of them holds the merge. Each recommendation says whether it fits in this pull request or belongs in its own."
            + (f" Together they would remove about {saved} lines." if saved else ""))

def existing_intro(entries):
    return "Defects that are already on the remote main branch: this branch did not introduce them or make them worse, so they do not hold the merge. Each recommendation is a fix in its own pull request. Fix as recommended records the finding as deferred to that pull request; to fix one on this branch anyway, choose Fix as noted."

def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")

def credit_intro(entries):
    marked = sum(1 for e in entries if choice_of(e["id"]) == "post")
    return (f"Things this change does well, worth telling its author: {plural(len(entries), 'credit')}, {marked} marked Post."
            " Post adds one to the review posted on the pull request and Ignore leaves it out; neither changes a status.")

def below_intro(entries):
    return "Major findings the bar left out: the reviewers or the verifier were not sure enough that they exist as described, or no verifier checked them. Each may still be real. Nothing here is acted on unless you tick an instruction."

Section = namedtuple("Section", "key heading action count_label intro counted_when_empty", defaults=(True,))
SECTIONS = [
    Section("reopen", "Reopened", "reopened", "reopened", None),
    Section("pr", "Pull request comments", "pull request comment", None, None),
    Section("fix", "Fix before merging", "fix before merging", "fix", None),
    Section("look", "Worth a look", "worth a look", "look", None),
    Section("confirm", "Needs confirmation", "needs confirmation", "confirm", None),
    Section("existing", "Already on main", "separate pull request", "existing", existing_intro),
    Section("debt", "Cleanup and refactoring", "cleanup", "cleanup", debt_intro),
    Section("declined", "Previously declined", "previously declined", "declined", None),
    Section("credit", "Credits", "credit", "credits", credit_intro, False),
    Section("below", "Below the bar", "below the bar", "below", below_intro),
]
ACTIONS = {s.key: s.action for s in SECTIONS}
DEFECT_SECTIONS = ("reopen", "fix", "look", "confirm", "existing")

def section_counts(routed, separator):
    return ", ".join(f"{s.count_label}{separator}{len(routed[s.key])}" for s in SECTIONS if s.count_label and (s.counted_when_empty or routed[s.key]))

def action_of(e, section):
    """The action for a finding in a section, as the glance table words it; a
    tech-debt finding's is its label."""
    return e["_debt"] if section == "debt" and e.get("_debt") else ACTIONS[section]

def scope_of(e, v):
    """Origin and fix size, the verifier's when it gave them, else the
    reviewers'; follow-up as the reviewers wrote it."""
    o = (v.get("origin") or "").strip()
    o = o if o in ORIGIN_WORDS else str(e.get("origin", "")).lower().strip()
    z = (v.get("fix_size") or "").strip()
    z = z if z in SIZES else str(e.get("fix_size", "")).lower().strip()
    f = str(e.get("follow_up", "")).strip()
    e["_origin"] = o if o in ORIGIN_WORDS else ""
    e["_size"] = z if z in SIZES else ""
    e["_follow"] = "" if f.lower() in ("", "none", "n/a") else f
    d = str(e.get("debt", "")).lower().strip()
    e["_debt"] = d if d in DEBT_WORDS else ""
    sv = re.search(r"\d+", str(e.get("saves", "")))
    e["_saves"] = int(sv.group()) if sv and e["_debt"] else 0

def scope_line(e):
    parts = []
    if e.get("_saves"): parts.append(f"Saves ~{e['_saves']} lines")
    if e.get("_size"): parts.append(f"Fix size: {e['_size']}")
    if e.get("_origin"): parts.append((DEBT_ORIGIN_WORDS if e.get("_debt") else ORIGIN_WORDS)[e["_origin"]])
    if e.get("_follow"): parts.append(f"Follow-up in {e['_follow']}")
    return code_spans(" · ".join(parts)) if parts else ""

def size_cell(e):
    return ", ".join(x for x in (e.get("_size", ""), "cross-repo" if e.get("_follow") else "") if x)

def read_labels(run):
    labels, cur = {}, None
    p = os.path.join(run, "slices.md")
    if not os.path.exists(p): return labels
    for line in open(p, encoding="utf-8"):
        m = re.match(r"^- name:\s*(.+)$", line)
        if m: cur = m.group(1).strip(); labels[cur] = cur.replace("-", " ").capitalize(); continue
        m = re.match(r"^\s+label:\s*(.+)$", line)
        if m and cur: labels[cur] = m.group(1).strip()
    return labels

def read_titles(run):
    t = {}
    p = os.path.join(run, "titles.tsv")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t", 1)
            if len(parts) == 2 and parts[0].isdigit(): t[int(parts[0])] = parts[1].strip()
    return t

def unquote(t):
    t = (t or "").strip()
    while len(t) > 1 and t[0] in "\"'“" and t[-1] in "\"'”.":
        t = t.rstrip(".").strip()
        if t[0] in "\"'“" and t[-1] in "\"'”": t = t[1:-1].strip()
        else: break
    return t

def report_titles(run, mf):
    titles = read_titles(run)
    titles.update({mid: over["title"] for mid, over in read_overrides(run, mf).items() if "title" in over})
    return titles

def title_of(e, titles):
    t = titles.get(e["id"]) or e.get("title") or ""
    if not t:
        t = e.get("claim", "").split(". ")[0].split(", so ")[0].split(", but ")[0].rstrip(".")
    return t.rstrip(". ")

def snippet(repo, head, spec):
    m = re.match(r"^\s*([^:\s]+):(\d+)(?:-(\d+))?\s*$", spec or "")
    if not m: return ""
    path, a = m.group(1), int(m.group(2)); b = int(m.group(3) or a)
    b = min(b, a + 11)
    try:
        src = subprocess.run(["git", "-C", repo, "show", f"{head}:{path}"], capture_output=True, text=True, check=True).stdout.splitlines()
    except Exception:
        return ""
    lines = src[a-1:b]
    if not lines: return ""
    lines = textwrap.dedent("\n".join(lines)).splitlines()
    ext = os.path.splitext(path)[1].lstrip(".") or "text"
    return f"```{ext}\n// {path}:{a}\n" + "\n".join(lines) + "\n```"

def area_of(e, labels):
    sl = sorted(s for s in e["slices"] if s not in ("whole", "all"))
    return labels.get(sl[0], sl[0].replace("-", " ").capitalize()) if sl else "Whole change"

def steps_md(text):
    items = [l.strip() for l in text.split("\n") if l.strip()]
    if len(items) <= 1: return text.strip()
    out = []
    for i, it in enumerate(items, 1):
        it = re.sub(r"^(\d+[.)]|-)\s+", "", it)
        out.append(f"{i}. {it}")
    return "\n".join(out)

_LEN = {}
def file_len(repo, head, path):
    if path not in _LEN:
        try:
            out = subprocess.run(["git", "-C", repo, "show", f"{head}:{path}"], capture_output=True, text=True, check=True).stdout
            _LEN[path] = out.count("\n") + (0 if out.endswith("\n") or not out else 1)
        except Exception:
            _LEN[path] = None
    return _LEN[path]

def read_overrides(run, mf):
    """overrides/<merged id>.md holds hand-written or orchestrator-written
    fields (what_changed, steps, impact, snippet, fix, title) in the same
    key: value form as a finding. They overlay the merged entry at render
    time, so a re-render keeps them."""
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

def code_spans(text):
    """Protect identifiers that Markdown would read as emphasis. Wraps bare
    __dunder__ and snake_case tokens that are not already in code spans."""
    parts = re.split(r"(`[^`]*`)", text)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"(?<![`\w])(__[A-Za-z]\w*__)(?![`\w])", r"`\1`", parts[i])
        parts[i] = re.sub(r"(?<![`\w])('_'|\"_\"|_)(?![`\w])", r"`\1`", parts[i])
    return "".join(parts)

def paragraphs(text):
    return [code_spans(t.strip()) for t in re.split(r"\n\s*\n", text) if t.strip()]

def prose(text):
    return sum(([p, ""] for p in paragraphs(text)), [])

def prose_block(heading, text):
    return [f"##### {heading}", ""] + prose(text)

def note_block(heading, note):
    return [f"##### {heading}", "", code_spans(note), ""]

def recommendation(e):
    return prose_block("Recommendation", e["fix"]) if e.get("fix") and e["fix"].lower() != "none obvious" else []

def instruction_tail(e):
    out = ["##### Instruction", ""] + instruction_block(INSTR.get(e["id"]), choices_for(e["id"], CREDITS))
    return out + (posted_block(e["id"]) if choice_of(e["id"]) == "post" else [])

def _card_tail(e):
    body = read_text(os.path.join(RUN, "resolution", f"{e['id']}.md"))
    return (prose_block("Resolution", body) if body else []) + instruction_tail(e)

def claim_lines(e):
    if e.get("claim") and title_of(e, TITLES) != unquote(e["claim"]).rstrip("."):
        return [code_spans(unquote(e["claim"]).rstrip(".") + "."), ""]
    return []

def credit_body(e, v, repo, head):
    out = [f"Overlaps finding {IDNUM[e['_overlaps']]}.", ""] if e.get("_overlaps") in IDNUM else []
    out += claim_lines(e) + context_lines(e) + snippet_lines(e, repo, head)
    if v.get("note"): out += note_block("Second opinion", v["note"])
    return out + instruction_tail(e)

_APPENDED = None
def is_new(mid):
    """Added to the run after its first report (a fix's recheck, an
    incremental review, a final pass; listed in reconcile/appended.tsv) and
    not yet acted on. Its heading carries [new] until it gets an
    instruction or a status, so `grep -n '\\[new\\]' report.md` lists what is
    left to look at."""
    global _APPENDED
    if _APPENDED is None:
        p = os.path.join(RUN, "reconcile", "appended.tsv")
        rows = read_text(p).split()[1:]
        _APPENDED = {int(r) for r in rows if r.isdigit()}
    return mid in _APPENDED and not decided(mid)

def card(n, e, v, labels, names, repo, head, section):
    action = action_of(e, section)
    action = action[:1].upper() + action[1:]
    raw = "pull request" if is_pr(e) else ", ".join(sorted(set(e.get("sources", []))))
    if is_pr(e):
        head_lines = [f"**{action}** · by @{e.get('author', 'someone')}", ""]
    else:
        focus = ", ".join(names.get(l, l) for l in sorted(e["lenses"]))
        head_lines = [f"**{action}** · {area_of(e, labels)}", "", f"Focus: {focus}", ""]
    status = [] if is_credit(e) else [status_line(STATUS.get(e["id"], {"status": "open"})), ""]
    out = [f"#### {n}. {title_of(e, TITLES)}" + (" [new]" if is_new(e["id"]) else ""), "", f"<!-- finding {n}, merged {e['id']}, verify/{e['id']}.md, raw: {raw} -->", ""] + head_lines + status
    sl = "" if is_pr(e) or is_credit(e) else scope_line(e)
    if sl: out += [sl, ""]
    loc = f"{e['file']}:{e['line']}" if e["line"] else e["file"]
    fl = file_len(repo, head, e["file"]) if e["line"] else None
    out += [loc, ""]
    hl = history_line(e)
    if hl: out += [code_spans(hl), ""]
    rel = re.sub(r"\D", "", str(e.get("related_to", "")))
    if rel and int(rel) in IDNUM:
        st = STATUS.get(int(rel), {"status": "open"})
        how = f", marked fixed in {st['ref']}" if st["status"] == "fixed" and st.get("ref") else ""
        out += [f"Related to finding {IDNUM[int(rel)]}{how}; this is a separate issue.", ""]
    if section == "below":
        if v.get("verdict") == "unverified":
            why = "Below the bar: no verifier checked it."
        else:
            doubt = (e.get("uncertainty") or v.get("note") or "").split(". ")[0].rstrip(".")
            why = "Below the bar: the verifier had doubts" + (f": {doubt}." if doubt else ".")
        out += [code_spans(why), ""]
    if not is_pr(e) and PR_LINKS.get(e["id"]):
        out += [f"Also raised on the pull request by " + ", ".join(sorted({"@" + c.get("author", "someone") for c in PR_LINKS[e["id"]]})) + ".", ""]
    sb = re.sub(r"\D", "", str(e.get("surfaced_by", "")))
    if sb:
        pn = IDNUM.get(int(sb))
        out += [f"Surfaced by the fix for finding {pn}." if pn else "Surfaced by a fix.", ""]
    if fl and e["line"] > fl:
        out += [f"Line number uncertain: the file has {fl} lines. The reviewer's evidence in merged.md names the real locations.", ""]
    if is_credit(e):
        return "\n".join(out + credit_body(e, v, repo, head))
    if is_pr(e):
        out += pr_block(e, "Comment", with_location=False)
        out += _sections(e, repo, head) + recommendation(e)
        if v.get("note"): out += note_block("Second opinion", v["note"])
        return "\n".join(out + _card_tail(e))
    out += claim_lines(e)
    for c in PR_LINKS.get(e["id"], []):
        out += pr_block(c, "Raised on the pull request")
    out += _sections(e, repo, head)
    if section == "confirm":
        out += note_block("What would confirm it", v.get("note") or "Trace the deploy mechanics the reviewer could not see.")
    else:
        out += recommendation(e)
        if v["verdict"] in ("adjusted", "rejected") and v.get("note"): out += note_block("Second opinion", v["note"])
    return "\n".join(out + _card_tail(e))

def _sections(e, repo, head):
    """Why it matters, Context, How it goes wrong, and the snippet. A pull
    request comment has them only when its verifier filled them in through
    overrides/<merged id>.md; the comment's own words are never rewritten."""
    out = []
    if e.get("impact"):
        out += prose_block("Why it matters", e["impact"])
        if e.get("uncertainty"):
            out += [code_spans("Uncertain: " + e["uncertainty"].strip()), ""]
    out += context_lines(e)
    how = e.get("steps") or e.get("scenario", "")
    if how:
        out += ["##### How it goes wrong", ""]
        if e.get("steps") and "\n" in e["steps"]:
            out += [code_spans(steps_md(how)), ""]
        else:
            out += prose(how)
    return out + snippet_lines(e, repo, head)

def context_lines(e):
    ctx = e.get("context") or e.get("what_changed")
    return prose_block("Context", ctx) if ctx else []

def snippet_lines(e, repo, head):
    sn = snippet(repo, head, e.get("snippet", ""))
    return [sn, ""] if sn else []

STATUS_WORDS = {"open": "Open", "in-progress": "In progress", "fixed": "Fixed", "wont-fix": "Won't fix", "deferred": "Deferred"}
DONE = ("fixed", "wont-fix", "deferred")

def read_status(run):
    """status.tsv: merged id, status, ref (commit, ticket, or reason), date."""
    st = {}
    p = os.path.join(run, "status.tsv")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[0].isdigit():
                st[int(parts[0])] = {"status": parts[1].strip() or "open", "ref": (parts[2] if len(parts) > 2 else "").strip(), "date": (parts[3] if len(parts) > 3 else "").strip()}
    return st

def write_status(run, st):
    with open(os.path.join(run, "status.tsv"), "w", encoding="utf-8") as fh:
        fh.write("merged_id\tstatus\tref\tdate\n")
        for k in sorted(st): fh.write(f"{k}\t{st[k]['status']}\t{st[k].get('ref','')}\t{st[k].get('date','')}\n")

GEN_RE = re.compile(r"^<!-- review generation (\d+)")
FINDING_MARKER = re.compile(r"^<!-- finding \d+, merged (\d+),")
CHECKBOX_RE = re.compile(r"^- \[( |x|X)\] (.*)$")

def card_blocks(lines):
    cards, mid, block, fence = {}, None, None, ""
    for line in lines:
        m = FINDING_MARKER.match(line)
        if m:
            mid, fence = int(m.group(1)), ""
            block = cards.setdefault(mid, {}).setdefault("", [])
            continue
        if fence:
            if closes_fence(line, fence): fence = ""
        elif line.startswith("#") or line == "---":
            if line.startswith(("#### ", "### ", "## ", "# ")): mid = None
            heading = line.strip()[len("##### "):] if line.startswith("##### ") else None
            block = cards[mid].setdefault(heading, []) if mid is not None and heading is not None else None
            continue
        else:
            m = FENCE_RE.match(line)
            if m: fence = m.group(1)
        if block is not None: block.append(line)
    return cards

def read_card_blocks(run):
    p = os.path.join(run, "report.md")
    if not os.path.exists(p): return {}
    with open(p, encoding="utf-8") as fh: return card_blocks(fh.read().split("\n"))

def status_box(head):
    return next((line for line in head if CHECKBOX_RE.match(line)), None)

def log_commits(run, repo, mid, stt):
    """Append every commit a status names to commits.tsv (merged id, commit,
    status, date). status.tsv keeps one ref per finding, so without this the
    first commit of a fix that took two is forgotten, and later tools count
    it as unreviewed work."""
    toks = re.findall(r"\b[0-9a-f]{7,40}\b", stt.get("ref", ""))
    if not toks: return
    r = subprocess.run(["git", "-C", repo, "cat-file", "--batch-check=%(objectname) %(objecttype)"],
                       input="".join(t + "^{commit}\n" for t in toks), capture_output=True, text=True)
    shas = [p[0] for p in (l.split() for l in r.stdout.splitlines()) if len(p) == 2 and p[1] == "commit"]
    path = os.path.join(run, "commits.tsv")
    have = set()
    if os.path.exists(path):
        have = {tuple(l.split("\t")[:2]) for l in open(path, encoding="utf-8").read().splitlines()[1:]}
    new = [s for s in shas if (str(mid), s) not in have]
    if not new: return
    with open(path, "a", encoding="utf-8") as fh:
        if not os.path.exists(path) or os.path.getsize(path) == 0: fh.write("merged_id\tcommit\tstatus\tdate\n")
        for s in new: fh.write(f"{mid}\t{s}\t{stt['status']}\t{stt.get('date', '')}\n")

def report_generation(run):
    """The generation stamp in the existing report.md: which render produced it."""
    p = os.path.join(run, "report.md")
    if not os.path.exists(p): return None
    for i, line in enumerate(open(p, encoding="utf-8")):
        m = GEN_RE.match(line)
        if m: return int(m.group(1))
        if i > 40: break
    return None

def snapshot_path(run, name):
    """The snapshot written by the render that produced the report as it is on
    disk. A report saved from an editor buffer opened before a later render is
    compared against what that earlier render wrote, so only the lines the
    user changed count as edits."""
    g = report_generation(run)
    if g is not None:
        p = os.path.join(run, ".render", str(g), name)
        if os.path.exists(p): return p
    return os.path.join(run, name)

def read_snapshot(run, name):
    snap = {}
    p = snapshot_path(run, name)
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t", 1)
            if len(parts) == 2 and parts[0].isdigit(): snap[int(parts[0])] = parts[1]
    return snap

def import_hand_edits(run, st, today):
    """Read checkbox lines from the existing report.md. A ticked box the
    status file does not know about becomes fixed, won't fix, or deferred by
    its wording, with a commit hash if the line has one; an unticked box over
    a done status reopens it."""
    snap, credits = read_snapshot(run, "rendered-status.tsv"), credit_ids(run)
    for mid, blocks in read_card_blocks(run).items():
        line = status_box(blocks[""])
        if line is None or snap.get(mid) == line or mid in credits: continue
        m = CHECKBOX_RE.match(line)
        ticked = m.group(1).lower() == "x"; text = m.group(2); low = text.lower()
        cur = st.get(mid, {"status": "open", "ref": "", "date": ""})
        sha = re.search(r"\b[0-9a-f]{7,40}\b", text)
        if ticked and cur["status"] not in DONE:
            kind = "wont-fix" if "won't fix" in low or "wont fix" in low else "deferred" if "deferred" in low else "fixed"
            ref = sha.group(0) if sha else re.sub(r"^(fixed|won't fix|wont fix|deferred)\s*(in|:)?\s*", "", text, flags=re.I).strip()
            st[mid] = {"status": kind, "ref": ref, "date": today}
        elif ticked and sha and sha.group(0) != cur.get("ref"):
            st[mid] = {**cur, "ref": sha.group(0), "date": today}
        elif not ticked and cur["status"] in DONE:
            st[mid] = {"status": "open", "ref": "", "date": today}
    return st

def status_line(stt):
    s = stt["status"]; ref = stt.get("ref", ""); date = stt.get("date", "")
    tail = (f" ({date})" if date else "")
    if s == "fixed": return "- [x] Fixed" + (f" in {ref}" if ref else "") + tail
    if s == "wont-fix": return "- [x] Won't fix" + (f": {ref}" if ref else "") + tail
    if s == "deferred": return "- [x] Deferred" + (f": {ref}" if ref else "") + tail
    if s == "in-progress": return "- [ ] In progress" + (f": {ref}" if ref else "") + tail
    return "- [ ] Open"

def status_cell(stt):
    s = stt["status"]; ref = stt.get("ref", "")
    if s == "fixed": return "fixed " + ref[:7] if ref else "fixed"
    if s == "open": return ""
    return STATUS_WORDS.get(s, s).lower()

def read_reconcile(run):
    """Reconciliation against a previous run, if any (see reconcile.py)."""
    rd = os.path.join(run, "reconcile")
    rec = {"label": "", "matches": {}, "prior": {}, "since": {}, "unmatched": []}
    if not os.path.isdir(rd): return rec
    pt = os.path.join(rd, "previous.txt")
    rec["label"] = read_text(pt)
    def rows(name):
        p = os.path.join(rd, name)
        if not os.path.exists(p): return []
        return [l.rstrip("\n").split("\t") for l in open(p, encoding="utf-8").readlines()[1:] if l.strip()]
    for r in rows("matches.tsv"):
        rec["matches"][int(r[0])] = {"prev_id": int(r[1]), "how": r[2], "prev_number": r[3], "prev_status": r[4], "prev_ref": r[5] if len(r) > 5 else "", "cause": r[6] if len(r) > 6 else ""}
    for r in rows("prior.tsv"):
        rec["prior"][int(r[0])] = {"outcome": r[1], "note": r[2] if len(r) > 2 else ""}
    for r in rows("since.tsv"):
        rec["since"][int(r[0])] = {"outcome": r[1], "note": r[2] if len(r) > 2 else ""}
    for r in rows("unmatched.tsv"):
        rec["unmatched"].append({"prev_id": int(r[0]), "prev_number": r[1], "prev_status": r[2], "prev_ref": r[3], "location": r[4], "title": r[5] if len(r) > 5 else ""})
    return rec

def is_pr(e):
    return str(e.get("lens", "")).startswith("pr-review") or e.get("source") == "github"

is_credit = mf.is_credit

def credit_ids(run):
    path = os.path.join(run, "merged.md")
    return {e["id"] for e in read_merged(path, mf) if is_credit(e)} if os.path.exists(path) else set()

def pr_block(c, heading, with_location=True):
    """The human comment's own words, author, link, replies, and GitHub state."""
    who = f"@{c.get('author', 'someone')}"
    loc = f"{c['file']}:{c['line']}" if c.get("line") and c.get("file") not in ("", "(pull request)") else ""
    out = [f"##### {heading}", ""]
    meta = who + (f" on {loc}" if loc and with_location else "") + (f" ([comment]({c['url']}))" if c.get("url") else "")
    out += [meta + ":", ""]
    out += ["> " + code_spans(c.get("claim", "").strip()), ""]
    if c.get("replies"):
        out += [code_spans("Replies: " + c["replies"]), ""]
    st = c.get("github_state", "")
    if st:
        words = {"resolved": "marked resolved on GitHub", "outdated": "outdated on GitHub: the code it was attached to has changed"}
        out += [ "State: " + "; ".join(words.get(x.strip(), x.strip()) for x in st.split(",")) + ".", ""]
    return out

def history_line(e):
    m = RECON["matches"].get(e["id"])
    if not m or m.get("how") == "carried": return ""
    where = f"finding {m['prev_number']} in the previous review" if m["prev_number"] else "the previous review"
    if m["prev_status"] == "fixed":
        line = f"Reopened: {where} was marked fixed" + (f" in {m['prev_ref']}" if m["prev_ref"] else "")
        if m.get("cause"):
            lens, loc, claim = (m["cause"].split("|", 2) + ["", "", ""])[:3]
            who = NAMES.get(lens.split(",")[0].strip(), lens) if lens else "a"
            return line + f", but this review's {who} reviewer reported: {claim.rstrip('.')} ({loc})."
        return line + ", and this review found it again."
    if m["prev_status"] in ("wont-fix", "deferred"):
        pr = RECON["prior"].get(e["id"], {})
        word = "declined" if m["prev_status"] == "wont-fix" else "deferred"
        why = f" ({m['prev_ref']})" if m["prev_ref"] else ""
        if pr.get("outcome") == "answered":
            return f"Raised again: {where} was {word}{why}. " + (pr.get("note") or "The new evidence may answer that reason.")
        return f"Previously {word}{why}: {where}."
    return f"Also reported as {where}."

Choice = namedtuple("Choice", "key label word note options", defaults=("note", False))
CHOICES = [Choice("fix", "Fix as recommended", "fix", options=True), Choice("noted", "Fix as noted", "fix as noted"), Choice("discuss", "Discuss", "discuss"),
           Choice("defer", "Defer", "defer", note="ref"), Choice("ignore", "Ignore", "ignore", note="reason"), Choice("post", "Post", "post")]
CREDIT_CHOICES = [c._replace(note="note") for key in ("post", "ignore") for c in CHOICES if c.key == key]
CHOICE_WORD = {c.key: c.word for c in CHOICES}
LABEL_TO_CHOICE = {c.label.lower(): c.key for c in CHOICES}

def choices_for(mid, credits):
    return CREDIT_CHOICES if mid in credits else CHOICES

def choice_of(mid):
    return INSTR.get(mid, {}).get("choice", "")

def takes_option(key, choices=CHOICES):
    return any(c.key == key and c.options for c in choices)

def instruct_re(choices):
    return re.compile(r"^(#?\d+)=(" + "|".join(c.key for c in choices) + r"|none)(\([a-z ,+]+\))?(?::(.*))?$")

INSTRUCT_RE = instruct_re(CHOICES)

def instruct_usage(choices=CHOICES):
    forms = []
    for c in choices:
        forms.append(f"N={c.key}[:{c.note}]")
        if c.options: forms.append(f"N={c.key}(a)[:{c.note}]")
    return ", ".join(forms + ["N=none"])

def instruct_help(choices=CHOICES):
    keys = [c.key + (f", {c.key}(a) for one labeled alternative" if c.options else "") for c in choices]
    return "set a triage instruction: " + ", ".join(keys) + ", or none"

# "Fix as recommended (a)" picks one labeled alternative of a recommendation
# that offers several; "(a, c)" picks more than one.
OPTION_RE = re.compile(r"\s*\(\s*([a-z](?:\s*(?:,|\+|and)\s*[a-z])*)\s*\)\s*$")

def split_option(label):
    """'Fix as recommended (a)' -> ('Fix as recommended', 'a')."""
    m = OPTION_RE.search(label)
    if not m: return label.strip(), ""
    return label[:m.start()].strip(), ",".join(re.findall(r"[a-z]", re.sub(r"\band\b", ",", m.group(1))))

def recommendation_options(fix):
    """The labels a recommendation offers, in order: '(a) ... or (b) ...'."""
    return re.findall(r"(?:^|[\s(])\(([a-z])\)\s", fix or "")

def read_instructions(run):
    """instructions.tsv: merged id, choice (fix|discuss|defer|ignore or empty),
    note, date, also (other ticked choices, comma separated), option (the
    labeled alternatives of the recommendation to follow, comma separated,
    only with fix). Free-text notes live in notes/<merged id>.md."""
    ins = {}
    p = os.path.join(run, "instructions.tsv")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            f = line.rstrip("\n").split("\t")
            if f and f[0].isdigit():
                ins[int(f[0])] = {"choice": f[1] if len(f) > 1 else "", "note": f[2] if len(f) > 2 else "",
                                  "date": f[3] if len(f) > 3 else "", "also": f[4] if len(f) > 4 else "",
                                  "option": f[5] if len(f) > 5 else ""}
    nd = os.path.join(run, "notes")
    if os.path.isdir(nd):
        for n in os.listdir(nd):
            m = re.match(r"^(\d+)\.md$", n)
            if m:
                txt = read_text(os.path.join(nd, n))
                if txt: ins.setdefault(int(m.group(1)), {"choice": "", "note": "", "date": "", "also": ""})["text"] = txt
    return ins

def write_instructions(run, ins):
    with open(os.path.join(run, "instructions.tsv"), "w", encoding="utf-8") as fh:
        fh.write("merged_id\tchoice\tnote\tdate\talso\toption\n")
        for k in sorted(ins):
            i = ins[k]
            if i.get("choice") or i.get("note") or i.get("also"):
                fh.write(f"{k}\t{i.get('choice','')}\t{i.get('note','')}\t{i.get('date','')}\t{i.get('also','')}\t{i.get('option','')}\n")
    nd = os.path.join(run, "notes")
    for k, i in ins.items():
        f = os.path.join(nd, f"{k}.md")
        if i.get("text"):
            os.makedirs(nd, exist_ok=True); open(f, "w", encoding="utf-8").write(i["text"].strip() + "\n")
        elif os.path.exists(f):
            os.remove(f)

POSTED_FIELDS = ("state", "note", "date", "thread_id", "comment_id", "url", "path", "line", "end_line", "side", "kind", "review_id")

def read_posted(run):
    rows = {}
    p = os.path.join(run, "posted.tsv")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh: lines = fh.read().splitlines()[1:]
        for line in lines:
            f = line.split("\t")
            if f[0].isdigit(): rows[int(f[0])] = dict(zip(POSTED_FIELDS, f[1:] + [""] * len(POSTED_FIELDS)))
    return rows

def write_posted(run, rows):
    with open(os.path.join(run, "posted.tsv"), "w", encoding="utf-8") as fh:
        fh.write("\t".join(("merged_id",) + POSTED_FIELDS) + "\n")
        for k in sorted(rows): fh.write("\t".join([str(k)] + [rows[k].get(f, "") for f in POSTED_FIELDS]) + "\n")

def read_findings(run, mf):
    overrides = read_overrides(run, mf)
    merged = read_merged(os.path.join(run, "merged.md"), mf)
    for e in merged:
        over = overrides.get(e["id"], {})
        for k, val in over.items():
            e[k] = int(re.sub(r"\D", "", val) or 0) if k in ("line", "end_line") else val
        if "line" in over and "end_line" not in over: e["end_line"] = e["line"]
    return merged

def posted_path(run, mid):
    return os.path.join(run, "posted", f"{mid}.md")

def read_text(path, missing=""):
    return open(path, encoding="utf-8").read().strip() if path and os.path.exists(path) else missing

def posted_text(run, mid):
    return read_text(posted_path(run, mid))

def record_posted(run, mid, text, state, today):
    os.makedirs(os.path.dirname(posted_path(run, mid)), exist_ok=True)
    open(posted_path(run, mid), "w", encoding="utf-8").write(text.strip() + "\n")
    POSTED[mid] = {**POSTED.get(mid, {}), "state": state, "note": INSTR.get(mid, {}).get("note", ""), "date": today}

def note_changed(mid):
    return mid in POSTED and POSTED[mid]["note"] != INSTR.get(mid, {}).get("note", "")

def stale_text(row, note):
    return bool(row) and row["note"] != note and row["state"] != "edited"

def is_stale(mid):
    return stale_text(POSTED.get(mid), INSTR.get(mid, {}).get("note", ""))

def check_posted_notes():
    for mid in sorted(POSTED):
        if choice_of(mid) != "post" or not note_changed(mid): continue
        n = IDNUM.get(mid, f"#{mid}")
        if POSTED[mid]["state"] == "edited":
            print(f"warning: finding {n}: note changed after its posted text was edited; the edit stands", file=sys.stderr)
            POSTED[mid]["note"] = INSTR[mid]["note"]
        else:
            print(f"finding {n}: note changed; redraft the posted text", file=sys.stderr)

def posted_fence(text):
    return "`" * max([4] + [len(r) + 1 for r in re.findall(r"^(`{3,})", text, re.M)])

def posted_link(row):
    if not row.get("kind"): return []
    span = row["line"] + (f"-{row['end_line']}" if row.get("end_line") and row["end_line"] != row["line"] else "")
    where = "in the review body" if row["kind"] == "body" else f"on `{row['path']}" + (f":{span}" if span else "") + "`"
    link = f", [comment]({row['url']})" if row.get("url") else ""
    return [f"Posted {where}{link}" + ("." if row["state"] == "posted" else "; changed since posting."), ""]

def posted_block(mid):
    text = posted_text(RUN, mid)
    if not text: body = ["Posted text: not drafted yet."]
    elif is_stale(mid): body = ["Posted text: to be redrafted; the note changed."]
    else: body = [posted_fence(text), text, posted_fence(text)]
    return ["##### Posted", ""] + body + [""] + posted_link(POSTED.get(mid, {}))

def fenced_text(block):
    fence, body = "", []
    for line in block:
        if fence:
            if closes_fence(line, fence): return "\n".join(body)
            body.append(line)
        else:
            m = FENCE_RE.match(line)
            if m: fence = m.group(1)
    return None

def posted_blocks(cards):
    texts = {mid: fenced_text(blocks.get("Posted", [])) for mid, blocks in cards.items()}
    return {mid: text for mid, text in texts.items() if text is not None}

def flat(text):
    return " ".join(text.split())

def import_posted_edits(run, today):
    snap = read_snapshot(run, "rendered-posted.tsv")
    for mid, text in posted_blocks(read_card_blocks(run)).items():
        if flat(text) not in (snap.get(mid), flat(posted_text(run, mid))): record_posted(run, mid, text, "edited", today)

def instruction_lines(i, choices=CHOICES):
    """The checklist lines, as compared in the snapshot (notes excluded)."""
    i = i or {}
    choice, note = i.get("choice", ""), i.get("note", "")
    also = [x for x in i.get("also", "").split(",") if x]
    opt = i.get("option", "") if takes_option(choice, choices) else ""
    out = []
    for c in choices:
        box = "[x]" if c.key == choice or c.key in also else "[ ]"
        lab = c.label + (" (" + ", ".join(opt.split(",")) + ")" if c.key == choice and opt else "")
        out.append(f"- {box} {lab}" + (f": {note}" if c.key == choice and note else ""))
    if note and not choice: out[0] += f": {note}"
    return out

def instruction_block(i, choices=CHOICES):
    """Checklist, a conflict line when two boxes are ticked, and the free-text
    notes. Everything in this block survives re-rendering."""
    i = i or {}
    out = instruction_lines(i, choices) + [""]
    if i.get("also"):
        used = next((c.label for c in choices if c.key == i.get("choice", "")), "")
        out += [f"More than one instruction is ticked; using {used} until the others are cleared.", ""]
    text = i.get("text", "").strip()
    out += ["Notes:" + ((" " + text.split("\n", 1)[0]) if text else "")]
    if text and "\n" in text: out += [text.split("\n", 1)[1]]
    out += [""]
    return out

def snapshot_key(lines, text):
    return " | ".join(lines) + " || " + flat(text)

def instruction_key(i, choices=CHOICES):
    return snapshot_key(instruction_lines(i, choices), (i or {}).get("text", ""))

def choice_counts(entries, choices=CHOICES):
    return {c.key: sum(1 for e in entries if choice_of(e["id"]) == c.key) for c in choices}

def triage_line(numbered, choices=CHOICES):
    numbered = [e for e in numbered if e["_sec"] != "credit"]
    counts = choice_counts(numbered, choices)
    undecided = sum(1 for e in numbered if e["_sec"] != "below" and not choice_of(e["id"]))
    below_open = sum(1 for e in numbered if e["_sec"] == "below" and not choice_of(e["id"]))
    return ("Triage: " + ", ".join(f"{counts[c.key]} {c.word}" for c in choices) + f", {undecided} not decided"
            + (f", {below_open} below the bar left as is." if below_open else "."))

def instruction_fields(block):
    lines, notes, in_notes = [], [], False
    for line in block:
        if CHECKBOX_RE.match(line) and not in_notes: lines.append(line.strip())
        elif line.startswith("  ") and lines and not in_notes: lines[-1] += " " + line.strip()
        elif line.startswith("Notes:"):
            in_notes = True; first = line[len("Notes:"):].strip()
            if first: notes.append(first)
        elif in_notes and not line.startswith("More than one instruction is ticked"):
            notes.append(line)
    return lines, "\n".join(notes).strip()

def ticked_instruction(lines, choices=CHOICES):
    allowed = {c.key for c in choices}
    ticked, refused, note, any_note, option = [], [], "", "", ""
    for l in lines:
        m = re.match(r"^- \[( |x|X)\] ([^:]+?)(?::\s*(.*))?$", l)
        if not m: continue
        label, opt = split_option(m.group(2))
        key = LABEL_TO_CHOICE.get(label.lower())
        if m.group(3) and not any_note: any_note = m.group(3).strip()
        if m.group(1).lower() == "x" and key and key not in allowed: refused.append(label)
        elif m.group(1).lower() == "x" and key:
            if not ticked: note, option = (m.group(3) or "").strip(), opt if takes_option(key) else ""
            ticked.append(key)
    return ticked, note if ticked else any_note, option, refused

def choice_labels(choices):
    return " and ".join(c.label for c in choices)

def import_instruction_edits(run, ins, today):
    """Read Instruction blocks from the existing report.md. A block counts as a
    hand edit only when it differs from what the renderer last wrote
    (rendered-instructions.tsv), so a stale report never undoes a change made
    through --instruct. Returns the changed ids."""
    snap, credits = read_snapshot(run, "rendered-instructions.tsv"), credit_ids(run)
    changed = set()
    for mid, blocks in read_card_blocks(run).items():
        lines, text = instruction_fields(blocks.get("Instruction", []))
        if not lines or snap.get(mid) == snapshot_key(lines, text): continue
        ticked, note, option, refused = ticked_instruction(lines, choices_for(mid, credits))
        if refused:
            print(f"warning: finding with merged id {mid} is a credit; dropped the tick on {', '.join(refused)}: only {choice_labels(CREDIT_CHOICES)} apply", file=sys.stderr)
        choice, also = (ticked or [""])[0], ",".join(ticked[1:])
        if also:
            print(f"warning: finding with merged id {mid} has {len(ticked)} instructions ticked; using {choice}", file=sys.stderr)
        cur = ins.get(mid, {})
        if cur.get("choice", "") != choice or cur.get("note", "") != note or cur.get("also", "") != also or cur.get("option", "") != option or flat(cur.get("text", "")) != flat(text):
            ins[mid] = {"choice": choice, "note": note, "date": today, "also": also, "option": option, "text": text}; changed.add(mid)
    return changed

def decided(mid):
    """The user or the fix flow has acted on this finding: it carries an
    instruction or a status other than open. Such a finding is always shown,
    whatever its severity and confidence, so it keeps a number and a card."""
    return bool(choice_of(mid)) or STATUS.get(mid, {}).get("status", "open") != "open"

def md_table(rows):
    """Pipe table with padded columns, the way common formatters align it, so a
    resave with a formatter changes nothing."""
    widths = [max(3, max(len(r[i]) for r in rows)) for i in range(len(rows[0]))]
    def line(r): return "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(r)) + " |"
    sep = "| " + " | ".join("-" * max(3, w) for w in widths) + " |"
    return [line(rows[0]), sep] + [line(r) for r in rows[1:]]

FENCE_RE = re.compile(r"^(`{3,}|~{3,})")

def closes_fence(line, fence):
    s = line.rstrip()
    return len(s) >= len(fence) and s == fence[0] * len(s)

def wrap_markdown(text, width):
    """Wrap prose paragraphs and list items; leave headings, tables, code,
    front matter, HTML comments, and bare location lines untouched."""
    if not width: return text
    out, fence, in_fm = [], "", False
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if i == 0 and line == "---": in_fm = True; out.append(line); continue
        if in_fm:
            out.append(line)
            if line == "---": in_fm = False
            continue
        if fence:
            out.append(line)
            if closes_fence(line, fence): fence = ""
            continue
        m = FENCE_RE.match(line)
        if m: fence = m.group(1); out.append(line); continue
        if not line.strip() or line.startswith("#") or line.startswith("|") or line.startswith("<!--") or line == "---" or len(line) <= width:
            out.append(line); continue
        if re.match(r"^\S+:\d+(\s|$)", line) and " " not in line.split("  ")[0]:
            out.append(line); continue
        # Code spans never break across lines: hide their spaces while wrapping.
        NB = "\u0001"
        protected = re.sub(r"`[^`]*`|<!--.*?-->", lambda c: c.group(0).replace(" ", NB), line)
        m = re.match(r"^(\s*(?:\d+\.|-)\s+|>\s)(.*)$", protected)
        if m and m.group(1).startswith(">"):
            # The marker goes in as an indent, not as a word, so a first word
            # longer than the width does not leave a bare ">" line.
            wrapped = textwrap.wrap(m.group(2), width=width, initial_indent="> ", subsequent_indent="> ", break_long_words=False, break_on_hyphens=False)
        elif m:
            indent = " " * len(m.group(1))
            wrapped = textwrap.wrap(protected, width=width, subsequent_indent=indent, break_long_words=False, break_on_hyphens=False)
        else:
            wrapped = textwrap.wrap(protected, width=width, break_long_words=False, break_on_hyphens=False)
        out.extend(w.replace(NB, " ") for w in wrapped)
    return "\n".join(out)

def read_numbers(run):
    nums = {}
    p = os.path.join(run, "numbers.tsv")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8").read().splitlines()[1:]:
            f = line.split("\t")
            if len(f) >= 2 and f[0].isdigit() and f[1].isdigit(): nums[int(f[1])] = int(f[0])
    return nums

def finding_id(spec, nums):
    if spec.startswith("#"): return int(spec[1:])
    by_number = {n: mid for mid, n in nums.items()}
    if not spec.isdigit() or int(spec) not in by_number: sys.exit(f"finding {spec} not in numbers.tsv")
    return by_number[int(spec)]

def file_spec(flag, spec, nums):
    m = re.match(r"^(#?\d+)=(.+)$", spec.strip())
    if not m or not os.path.exists(m.group(2)): sys.exit(f"bad {flag} {spec!r}; use N=<path of a text file>")
    return finding_id(m.group(1), nums), open(m.group(2), encoding="utf-8").read()

def posted_draft(spec, nums):
    mid, text = file_spec("--posted", spec, nums)
    if not text.strip(): sys.exit(f"bad --posted {spec!r}; the file is empty")
    return mid, text

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("run"); ap.add_argument("--target", required=True); ap.add_argument("--branch", default=""); ap.add_argument("--base", default=""); ap.add_argument("--head", default="HEAD")
    ap.add_argument("--repo", default="."); ap.add_argument("--routing", default=ROUTING); ap.add_argument("--threshold", type=int, default=80, help="confidence a blocker or major needs for Fix before merging")
    ap.add_argument("--quick", action="store_true", help="quick mode: minors need 80 to be shown")
    ap.add_argument("--summary"); ap.add_argument("--not-reviewed"); ap.add_argument("--out"); ap.add_argument("--date", default="")
    ap.add_argument("--files", default=""); ap.add_argument("--parts", default=""); ap.add_argument("--focuses", default="")
    ap.add_argument("--wrap", type=int, default=80, help="wrap prose at this width; 0 disables")
    ap.add_argument("--renumber", action="store_true", help="assign numbers afresh in document order, ignoring numbers.tsv")
    ap.add_argument("--instruct", action="append", default=[], metavar="N=CHOICE[:NOTE]", help=instruct_help())
    ap.add_argument("--note", action="append", default=[], metavar="N=FILE",
                    help="append the text of FILE as a new paragraph to finding N's Notes (#<id> for a merged id)")
    ap.add_argument("--posted", action="append", default=[], metavar="N=FILE",
                    help="use the text of FILE as finding N's posted text (#<id> for a merged id)")
    ap.add_argument("--set", action="append", default=[], metavar="N=STATUS[:REF]",
                    help="set a status by finding number (or #<merged id>): fixed, in-progress, wont-fix, deferred, open")
    return ap.parse_args()

def apply_statuses(run, repo, nums, specs, today):
    global STATUS
    STATUS = {mid: st for mid, st in import_hand_edits(run, read_status(run), today).items() if mid not in CREDITS}
    for spec in specs:
        m = re.match(r"^(#?\d+)=([a-z-]+)(?::(.*))?$", spec.strip())
        if not m or m.group(2) not in STATUS_WORDS:
            sys.exit(f"bad --set {spec!r}; use N=fixed:<sha>, N=wont-fix:<reason>, N=deferred:<ref>, N=in-progress:<files>, N=open")
        mid = finding_id(m.group(1), nums)
        if mid in CREDITS: sys.exit(f"bad --set {spec!r}; finding {m.group(1)} is a credit, which has no status")
        STATUS[mid] = {"status": m.group(2), "ref": (m.group(3) or "").strip(), "date": today}
        log_commits(run, repo, mid, STATUS[mid])

def set_instruction(spec, nums, today):
    m = INSTRUCT_RE.match(spec.strip())
    if not m or (m.group(3) and not takes_option(m.group(2))): sys.exit(f"bad --instruct {spec!r}; use {instruct_usage()}")
    mid = finding_id(m.group(1), nums)
    if m.group(2) != "none" and not any(c.key == m.group(2) for c in choices_for(mid, CREDITS)):
        sys.exit(f"bad --instruct {spec!r}; finding {m.group(1)} is a credit: use {instruct_usage(CREDIT_CHOICES)}")
    INSTR[mid] = {**INSTR.get(mid, {}), "choice": "" if m.group(2) == "none" else m.group(2), "note": (m.group(4) or "").strip(), "date": today, "also": "",
                  "option": split_option("x" + (m.group(3) or ""))[1]}
    return mid

def mirror_decision(mid, today):
    ch, note = INSTR[mid]["choice"], INSTR[mid]["note"]
    cur = STATUS.get(mid, {"status": "open"})["status"]
    if ch == "ignore" and cur in ("open", "in-progress"): STATUS[mid] = {"status": "wont-fix", "ref": note, "date": today}
    elif ch == "defer" and cur in ("open", "in-progress"): STATUS[mid] = {"status": "deferred", "ref": note, "date": today}
    elif ch in ("fix", "noted", "discuss", "") and cur in ("wont-fix", "deferred"): STATUS[mid] = {"status": "open", "ref": "", "date": today}

def add_note(spec, nums):
    mid, add = file_spec("--note", spec, nums)
    cur = INSTR.setdefault(mid, {"choice": "", "note": "", "date": "", "also": ""})
    cur["text"] = (cur.get("text", "").rstrip() + "\n\n" + add.strip()).strip()

def apply_instructions(run, nums, instruct_specs, note_specs, today):
    global INSTR
    INSTR = read_instructions(run)
    changed = import_instruction_edits(run, INSTR, today)
    for spec in instruct_specs: changed.add(set_instruction(spec, nums, today))
    # Ignore and Defer are decisions about the outcome: mirror them into status
    # when the finding is still open; undoing them reopens it.
    for mid in changed - CREDITS: mirror_decision(mid, today)
    for spec in note_specs: add_note(spec, nums)

def apply_posted(run, drafts, today):
    global POSTED
    POSTED = read_posted(run)
    import_posted_edits(run, today)
    for mid, text in drafts: record_posted(run, mid, text, "drafted", today)

def warn_unlabeled_options(merged):
    for e in merged:
        opt = INSTR.get(e["id"], {}).get("option", "") if takes_option(choice_of(e["id"])) else ""
        missing = [o for o in opt.split(",") if o and o not in recommendation_options(e.get("fix", ""))]
        if missing:
            print(f"warning: finding with merged id {e['id']} picks ({', '.join(missing)}), which its recommendation does not label", file=sys.stderr)

def pr_links(merged):
    ids, links = {e["id"] for e in merged}, {}
    for e in merged:
        d = re.sub(r"\D", "", str(e.get("duplicate_of", "")))
        if is_pr(e) and d and int(d) in ids: links.setdefault(int(d), []).append(e)
    return links

UNVERIFIED = {"verdict": "unverified", "confidence": 0, "severity": "", "note": ""}

def credit_section(e, v):
    if not v: return "unshown"
    if v["verdict"] == "rejected" and not decided(e["id"]): return "rejected"
    e["_conf"], e["_sev"], e["_v"] = v["confidence"] or e["confidence"], e["severity"], v
    return "credit"

def unverified_section(e):
    if e["id"] in PR_LINKS: dest = "look"
    elif (e["severity"] in ("blocker", "major") and e["confidence"] >= 40) or decided(e["id"]): dest = "below"
    else: return "unshown"
    e["_conf"], e["_sev"], e["_v"] = e["confidence"], e["severity"], dict(UNVERIFIED)
    return dest

def bar_section(e, sev, conf, a):
    minor_bar = 80 if a.quick else 60
    if sev in ("blocker", "major") and conf >= a.threshold: return "fix"
    if sev == "major" and conf >= 60: return "look"
    if sev == "minor" and conf >= minor_bar: return "look"
    if sev == "blocker": return "confirm"
    if e["id"] in PR_LINKS: return "look"
    if sev == "major" and conf >= 40: return "below"
    if decided(e["id"]): return "below"
    return "hidden"

def verified_section(e, v, a):
    if v["verdict"] == "rejected" and not decided(e["id"]): return "rejected"
    if v["verdict"] == "rejected":
        # A finding the user or the fix flow acted on stays visible when a
        # later verifier rejects it (usually because the fix holds); it
        # keeps the reviewers' own scores, and the note shows as a second opinion.
        v = dict(v, confidence=e["confidence"], severity=e["severity"])
    conf = v["confidence"] or e["confidence"]
    sev = v["severity"] if v["severity"] in SEV else e["severity"]
    e["_conf"], e["_sev"], e["_v"] = conf, sev, v
    scope_of(e, v)
    m = RECON["matches"].get(e["id"])
    if m and m.get("how") == "reopened" or (m and m["prev_status"] == "fixed" and m.get("how") != "carried" and conf >= 60): return "reopen"
    if m and m.get("how") != "carried" and m["prev_status"] in ("wont-fix", "deferred") and RECON["prior"].get(e["id"], {}).get("outcome") != "answered": return "declined"
    dest = bar_section(e, sev, conf, a)
    if dest not in ("fix", "look", "confirm"): return dest
    if e["_debt"]: return "debt"
    if e["_origin"] == "existing": return "existing"
    return dest

def section_of(e, v, a):
    if is_pr(e):
        e["_conf"], e["_sev"], e["_v"] = 100, "major", v or {"verdict": "", "confidence": 0, "severity": "", "note": ""}
        return "pr"
    if is_credit(e): return credit_section(e, v)
    scope_of(e, {})
    return verified_section(e, v, a) if v else unverified_section(e)

OFF_REPORT = ("rejected", "hidden", "unshown")

def route_findings(merged, verdicts, a):
    outcomes = {key: [] for key in [s.key for s in SECTIONS] + list(OFF_REPORT)}
    linked = {c["id"] for cs in PR_LINKS.values() for c in cs}
    for e in merged:
        if e["id"] not in linked: outcomes[section_of(e, verdicts.get(e["id"]), a)].append(e)
    unverified = [e for e in merged if not is_pr(e) and e["id"] not in verdicts]
    return {s.key: outcomes[s.key] for s in SECTIONS}, unverified, outcomes["rejected"], outcomes["hidden"]

def is_posted(row):
    return bool(row.get("kind")) and row.get("state") == "posted"

def drop_overlapping_credits(routed):
    defects = [d for key in DEFECT_SECTIONS for d in routed[key]]
    kept, dropped = [], []
    for c in routed["credit"]:
        hit = next((d for d in defects if mf.same_lines(c, d)), None)
        if hit and not is_posted(POSTED.get(c["id"], {})): dropped.append(c); continue
        if hit: c["_overlaps"] = hit["id"]
        kept.append(c)
    routed["credit"] = kept
    return dropped

def priority(e):
    return (-SEV[e["_sev"]], -e["_conf"], e["file"], e["line"] or 0)

def number_sections(routed, prior_nums, labels):
    # Document order: sections by action; within a section, areas ranked by
    # their most important finding; within an area, by severity then
    # confidence. Numbers follow this order so they ascend through the body
    # and the glance table reads the same way.
    # Numbers are stable across re-renders and incremental runs: an id that
    # already has a number keeps it; new ids get numbers after the highest
    # existing one, in document order.
    numbered, ordered_areas = [], {}
    next_n = max(prior_nums.values(), default=0)
    routed["pr"].sort(key=lambda e: (e["file"], e["line"] or 0))
    for s in SECTIONS:
        if s.key != "pr": routed[s.key].sort(key=priority)
        by_area = {}
        for e in routed[s.key]: by_area.setdefault(area_of(e, labels), []).append(e)
        ordered_areas[s.key] = sorted(by_area.items(), key=lambda kv: priority(kv[1][0]))
        for area, es in ordered_areas[s.key]:
            for e in es:
                if e["id"] in prior_nums: e["_n"] = prior_nums[e["id"]]
                else: next_n += 1; e["_n"] = next_n
                e["_sec"] = s.key; numbered.append(e)
    return numbered, ordered_areas

def front_matter(a, title, routed):
    fm = ["---", f"title: {title}", f"branch: {a.branch}", f"base: {a.base}", f"head: {a.head}", f"date: {a.date}", f"run: {os.path.relpath(a.run, a.repo)}", f"files: {a.files}", f"parts: {a.parts}", f"focuses: {a.focuses}", "findings: { " + section_counts(routed, ": ") + " }", "---", ""]
    return [l.rstrip() for l in fm]

def glance_rows(numbered, labels):
    def glance_title(e):
        t = title_of(e, TITLES)
        return t + " (also on the PR)" if e["id"] in PR_LINKS else t
    return [["#", "Finding", "Area", "Focus", "Size", "Action", "Triage", "Status"]] + [[str(e["_n"]), glance_title(e), "Pull request" if is_pr(e) else area_of(e, labels), ", ".join(NAMES.get(l, l) for l in sorted(e["lenses"])), size_cell(e), action_of(e, e["_sec"]), CHOICE_WORD.get(choice_of(e["id"]), ""), status_cell(STATUS.get(e["id"], {"status": "open"}))] for e in numbered]

def progress_line(numbered):
    done = {k: sum(1 for e in numbered if e["_sec"] == k and STATUS.get(e["id"], {}).get("status") in DONE) for k in ("reopen", "pr", "fix", "look", "confirm")}
    tot = {k: sum(1 for e in numbered if e["_sec"] == k) for k in ("reopen", "pr", "fix", "look", "confirm")}
    prog = f"Progress: {done['fix']} of {tot['fix']} to fix before merging resolved, {done['look']} of {tot['look']} worth a look resolved."
    if tot["reopen"]: prog = f"Progress: {done['reopen']} of {tot['reopen']} reopened resolved. " + prog[len("Progress: "):]
    linked_pr = sum(len(v) for v in PR_LINKS.values())
    if tot["pr"] or linked_pr:
        prog += f" Pull request: {done['pr']} of {tot['pr']} standalone comments resolved, {linked_pr} more linked to findings."
    if tot["confirm"]: prog += f" {done['confirm']} of {tot['confirm']} needing confirmation settled."
    return prog

def since_lines(numbered, routed):
    new = sum(1 for e in numbered if e["id"] not in RECON["matches"])
    still = sum(1 for e in numbered if e["id"] in RECON["matches"] and STATUS.get(e["id"], {}).get("status", "open") in ("open", "in-progress") and RECON["matches"][e["id"]].get("how") != "reopened")
    resolved = [u for u in RECON["unmatched"] if RECON["since"].get(u["prev_id"], {}).get("outcome") == "resolved"]
    resolved += [{"title": TITLE_BY_ID.get(pid, ""), "prev_number": RECON["matches"].get(pid, {}).get("prev_number", ""), "prev_ref": RECON["matches"].get(pid, {}).get("prev_ref", "")}
                 for pid, v in RECON["since"].items() if v.get("outcome") == "resolved" and RECON["matches"].get(pid, {}).get("how") == "carried"]
    unchecked = [u for u in RECON["unmatched"] if u["prev_status"] == "fixed" and u["prev_id"] not in RECON["since"]]
    notfound = [u for u in RECON["unmatched"] if u["prev_status"] in ("open", "in-progress") and RECON["since"].get(u["prev_id"], {}).get("outcome", "not-found") == "not-found"]
    answered = sum(1 for e in numbered if RECON["prior"].get(e["id"], {}).get("outcome") == "answered")
    lines = [f"Compared with the previous review, {RECON['label']}:", "",
             f"- New: {new}",
             f"- Reopened (marked fixed, found again or failed recheck): {len(routed['reopen'])}",
             f"- Still open: {still}",
             f"- Resolved, confirmed by recheck: {len(resolved)}",
             f"- Not found again, never marked fixed: {len(notfound)}",
             f"- Previously declined and raised again: {len(routed['declined']) + answered}" + (f", of which {answered} with evidence that may answer the reason" if answered else ""),
             ""]
    if resolved:
        lines += ["Resolved since the previous review:", ""] + [code_spans(f"- {u['title']} (finding {u['prev_number']} there, {u['prev_ref'] or 'no commit recorded'})") for u in resolved] + [""]
    if unchecked:
        lines += ["Marked fixed and not found again, but not yet rechecked:", ""] + [code_spans(f"- {u['title']} (finding {u['prev_number']} there, {u['prev_ref'] or 'no commit recorded'})") for u in unchecked] + [""]
    if notfound:
        lines += ["Open in the previous review and not found this time; confirm before closing:", ""] + [code_spans(f"- {u['title']} (finding {u['prev_number']} there, {u['location']})") for u in notfound] + [""]
    return ["## Since the previous review", ""] + lines

def section_lines(a, routed, ordered_areas, labels):
    out = []
    for s in SECTIONS:
        sec, areas = s.key, ordered_areas[s.key]
        if not areas: continue
        out += ["---", "", f"## {s.heading}", ""] + ([s.intro(routed[sec]), ""] if s.intro else [])
        for area, es in areas:
            if sec != "pr": out += [f"### {area}", ""]
            for i, e in enumerate(es):
                out += [card(e["_n"], e, e["_v"], labels, NAMES, a.repo, a.head, sec), ""]
                if sec in ("reopen", "pr", "fix") and i < len(es) - 1: out += ["---", ""]
    return out

def about_lines(merged, verdicts, unverified, rejected, hidden_minor, numbered, overlapping):
    low = len(hidden_minor) + sum(1 for e in unverified if e['severity'] == 'minor' or e['confidence'] < 40)
    dropped = f" {plural(len(overlapping), 'credit')} dropped for overlapping a confirmed defect." if overlapping else ""
    return ["## About this review", "", f"{len(merged)} findings were raised by the reviewers and merged; {len(verdicts)} were checked by a verifier and {len(rejected)} rejected. {low} minor or low-confidence findings are below the bar and listed only in merged.md.{dropped} Refer to a finding by its number (\"finding {numbered[0]['_n'] if numbered else 1}\"); numbers are fixed for this run. Scores, lens attribution, and evidence: merged.md. Reviewer output: raw/. Verifier notes: verify/.", ""]

def sort_number_list(m):
    nums = sorted({int(x) for x in re.findall(r"\d+", m.group(2))})
    if len(nums) == 1: return m.group(1) + str(nums[0])
    return m.group(1) + ", ".join(str(x) for x in nums[:-1]) + (", and " if len(nums) > 2 else " and ") + str(nums[-1])

def finish_text(text, wrap):
    # {#<merged id>} in any text resolves to that finding's current number, so
    # cross-references survive renumbering. Unreported ids render as "a finding
    # not in this report".
    text = re.sub(r"\{#(\d+)\}", lambda m: str(IDNUM.get(int(m.group(1)), "a finding not in this report")), text)
    # Sort the numbers inside "findings 9, 7, and 14" style lists.
    text = re.sub(r"(?i)(findings )((?:\d+)(?:(?:, | and |, and )\d+)+)", sort_number_list, text)
    text = wrap_markdown(text, wrap)
    return re.sub(r"\n{3,}", "\n\n", text)

def render_report(a, merged, verdicts, routed, ordered_areas, numbered, labels, unverified, rejected, hidden_minor, overlapping):
    title = f"Review of {a.target}"
    out = front_matter(a, title, routed) + [f"# {title}", "", "## Summary", "", read_text(a.summary, "(summary pending)"), ""]
    if RECON["label"]: out += since_lines(numbered, routed)
    out += ["## Findings at a glance", "", progress_line(numbered), "", triage_line(numbered), ""] + md_table(glance_rows(numbered, labels)) + [""]
    out += section_lines(a, routed, ordered_areas, labels)
    out += ["---", "", "## Not reviewed this run", "", read_text(a.not_reviewed, "(not provided)"), ""]
    out += about_lines(merged, verdicts, unverified, rejected, hidden_minor, numbered, overlapping)
    return finish_text("\n".join(out), a.wrap)

def write_snapshots(run, gen_dir, text, numbered):
    snaps = {"rendered-status.tsv": "".join(f"{e['id']}\t{status_line(STATUS.get(e['id'], {'status': 'open'}))}\n" for e in numbered if e["id"] not in CREDITS),
             "rendered-instructions.tsv": "".join(f"{e['id']}\t{instruction_key(INSTR.get(e['id']), choices_for(e['id'], CREDITS))}\n" for e in numbered),
             "rendered-posted.tsv": "".join(f"{mid}\t{flat(t)}\n" for mid, t in sorted(posted_blocks(card_blocks(text.split("\n"))).items()))}
    os.makedirs(gen_dir, exist_ok=True)
    for name, body in snaps.items():
        open(os.path.join(run, name), "w", encoding="utf-8").write(body)
        open(os.path.join(gen_dir, name), "w", encoding="utf-8").write(body)

def write_report(a, text, numbered):
    outp = a.out or os.path.join(a.run, "report.md")
    # This render's generation: stamped into the report, with its snapshots
    # kept under .render/<generation>/ (the last twenty).
    rdir = os.path.join(a.run, ".render"); os.makedirs(rdir, exist_ok=True)
    gens = sorted(int(x) for x in os.listdir(rdir) if x.isdigit())
    gen = (gens[-1] + 1) if gens else 1
    stamp = f"<!-- review generation {gen}. Edit the checkboxes, the Notes lines, and the Posted text; everything else is regenerated. -->"
    text = text.replace("\n# ", "\n" + stamp + "\n\n# ", 1) if text.startswith("---") else stamp + "\n\n" + text
    if os.path.exists(outp):
        shutil.copy2(outp, os.path.join(os.path.dirname(outp), "report.prev.md"))
    open(outp, "w", encoding="utf-8").write(text)
    write_snapshots(a.run, os.path.join(rdir, str(gen)), text, numbered)
    for g in gens[:-19]: shutil.rmtree(os.path.join(rdir, str(g)), ignore_errors=True)
    return outp

def write_numbers(run, numbered, prior_nums):
    # Numbers are never released: ids numbered before but not shown in this
    # render keep their rows (section "hidden"), so they get the same number
    # back if they reappear and no other finding takes it.
    shown = {e["id"] for e in numbered}
    kept = [(n, mid) for mid, n in prior_nums.items() if mid not in shown]
    open(os.path.join(run, "numbers.tsv"), "w").write("number\tmerged_id\tsection\n" + "".join(f"{e['_n']}\t{e['id']}\t{e['_sec']}\n" for e in numbered) + "".join(f"{n}\t{mid}\thidden\n" for n, mid in sorted(kept)))

def main():
    a = parse_args()
    today = a.date or ""
    mf = load_merge_module()
    merged = read_findings(a.run, mf)
    verdicts, labels = read_verdicts(a.run), read_labels(a.run)
    global NAMES, TITLES, RUN, RECON, PR_LINKS, IDNUM, TITLE_BY_ID, CREDITS
    NAMES, TITLES, RUN, CREDITS = read_plain_names(a.routing), report_titles(a.run, mf), a.run, credit_ids(a.run)
    nums = read_numbers(a.run)
    drafts = [posted_draft(spec, nums) for spec in a.posted]
    apply_statuses(a.run, a.repo, nums, a.set, today)
    apply_instructions(a.run, nums, a.instruct, a.note, today)
    write_instructions(a.run, INSTR)
    write_status(a.run, STATUS)
    apply_posted(a.run, drafts, today)
    warn_unlabeled_options(merged)
    RECON, PR_LINKS = read_reconcile(a.run), pr_links(merged)
    routed, unverified, rejected, hidden_minor = route_findings(merged, verdicts, a)
    overlapping = drop_overlapping_credits(routed)
    prior_nums = {} if a.renumber else dict(nums)
    numbered, ordered_areas = number_sections(routed, prior_nums, labels)
    IDNUM = {e["id"]: e["_n"] for e in numbered}
    TITLE_BY_ID = {e["id"]: title_of(e, TITLES) for e in merged}
    check_posted_notes()
    if POSTED: write_posted(a.run, POSTED)
    text = render_report(a, merged, verdicts, routed, ordered_areas, numbered, labels, unverified, rejected, hidden_minor, overlapping)
    outp = write_report(a, text, numbered)
    write_numbers(a.run, numbered, prior_nums)
    print(f"report: {outp}; {section_counts(routed, ' ')}, unverified {len(unverified)}, rejected {len(rejected)}", file=sys.stderr)

if __name__ == "__main__": main()

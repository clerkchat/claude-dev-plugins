#!/usr/bin/env python3
"""Bring a pull request's human review comments into a review run.

Usage:
  pr-comments.py RUN_DIR [--pr N] [--repo PATH]   # fetch, add new comments, propose links
  pr-comments.py RUN_DIR --judged FILE            # apply judge decisions on candidates

Fetches review threads (inline comments with replies, resolved and outdated
state), review summaries with a body, and conversation comments through `gh`.
Each thread or comment becomes a finding entry in RUN_DIR/merged.md with
`lens: pr-review`, `source: github`, the author, the link, the replies, and
the GitHub state. Comments already brought in (by GitHub id, recorded in
pr/seen.tsv) are updated in place, never duplicated.

Each new comment gets up to five candidate agent findings in
pr/candidates.tsv, ranked by wording overlap, same file, and same directory.
Nothing is linked automatically: human comments are phrased too differently
for word overlap, and nearby lines often hold a different defect. A judge
reads each comment with its candidates and decides; --judged applies its
lines "pr_id<TAB>finding_id<TAB>same|different" (at most one `same` per
comment). A linked comment
renders inside the finding's card; an unlinked one renders as its own card in
the "Pull request comments" section. Human comments are never filtered by any
confidence bar.
"""
import argparse, importlib.util, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
def mod(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
rc = mod("rc", "reconcile.py"); mf = rc.mf

Q = """query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){
number url headRefName
reviewThreads(first:100){nodes{id isResolved isOutdated path line originalLine
  comments(first:50){nodes{databaseId author{login} body url createdAt}}}}
reviews(first:100){nodes{databaseId author{login} body state url}}
comments(first:100){nodes{databaseId author{login} body url}}}}}"""

def words(e):
    """Words of the title and claim, with identifiers split into their parts
    (TestScenario, test_scenario, and testScenario all give test, scenario)."""
    t = e.get("title", "") + " " + e.get("claim", "")
    t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", t).replace("_", " ")
    return {w for w in re.findall(r"[a-z][a-z0-9]{2,}", t.lower()) if w not in rc.STOP}

def gh(args, cwd):
    r = subprocess.run(["gh"] + args, capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0: sys.exit(f"gh {' '.join(args[:3])} failed: {r.stderr.strip()}")
    return r.stdout

def one_line(text, n=300):
    t = re.sub(r"<img[^>]*>", "[image]", text)
    t = re.sub(r"```.*?```", "[code]", t, flags=re.S)
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + " ..."

def title_from(text):
    t = one_line(text, 400)
    first = re.split(r"(?<=[.?!])\s", t)[0]
    return first if len(first) <= 90 else first[:87].rsplit(" ", 1)[0]

def entry(mid, kind, gid, author, body, url, path="", line=None, oline=None, replies=(), resolved=False, outdated=False, state=""):
    rep = "; ".join(f"@{a}: {one_line(b, 200)}" for a, b in replies)
    gh_state = ", ".join(x for x in ("resolved" if resolved else "", "outdated" if outdated else "", state.lower() if state and state != "COMMENTED" else "") if x)
    f = {
        "lens": "pr-review", "source": "github", "slice": "pull-request", "severity": "major", "confidence": "100",
        "file": path or "(pull request)", "line": str(line or oline or ""),
        "title": title_from(body), "claim": one_line(body, 1200), "author": author, "url": url,
        "github_id": f"{kind}:{gid}", "replies": rep, "github_state": gh_state,
        "evidence": f"Comment by @{author} on the pull request" + (f", originally at line {oline}" if oline and oline != line else ""),
    }
    return "\n".join([f"- id: {mid}"] + [f"  {k}: {v}" for k, v in f.items() if v not in ("", None)])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run"); ap.add_argument("--pr", type=int); ap.add_argument("--repo", default=".")
    ap.add_argument("--judged")
    a = ap.parse_args()
    pd = os.path.join(a.run, "pr"); os.makedirs(pd, exist_ok=True)
    mpath = os.path.join(a.run, "merged.md")
    header, entries = rc.normalize_merged(open(mpath, encoding="utf-8").read())

    if a.judged:
        links = 0
        for line in open(a.judged):
            f = line.rstrip("\n").split("\t")
            if len(f) >= 3 and f[2].strip() == "same":
                pid, fid = f[0], f[1]
                for k, c in enumerate(entries):
                    if c.startswith(f"- id: {pid}\n") and "duplicate_of:" not in c:
                        entries[k] = c + f"\n  duplicate_of: {fid}"; links += 1
        rc.write_merged(mpath, header, entries)
        print(f"linked {links} pull request comments after judging", file=sys.stderr); return

    repo_full = json.loads(gh(["repo", "view", "--json", "nameWithOwner"], a.repo))["nameWithOwner"]
    owner, name = repo_full.split("/")
    pr = a.pr or json.loads(gh(["pr", "view", "--json", "number"], a.repo))["number"]
    data = json.loads(gh(["api", "graphql", "-f", f"query={Q}", "-F", f"o={owner}", "-F", f"r={name}", "-F", f"n={pr}"], a.repo))
    p = data["data"]["repository"]["pullRequest"]
    open(os.path.join(pd, "comments.json"), "w").write(json.dumps(p, indent=1))
    open(os.path.join(pd, "pr.txt"), "w").write(f"{pr}\t{p['url']}\n")

    seen = {}
    sp = os.path.join(pd, "seen.tsv")
    if os.path.exists(sp):
        for l in open(sp):
            f = l.rstrip("\n").split("\t")
            if len(f) == 2 and f[1].isdigit(): seen[f[0]] = int(f[1])
    next_id = max([int(re.match(r"^- id: (\d+)", c).group(1)) for c in entries] or [0]) + 1
    new_ids, updated = [], 0
    items = []
    for t in p["reviewThreads"]["nodes"]:
        cs = t["comments"]["nodes"]
        if not cs: continue
        root = cs[0]
        items.append(("thread", root["databaseId"], (root["author"] or {}).get("login", "ghost"), root["body"], root["url"],
                      dict(path=t["path"], line=t["line"], oline=t["originalLine"],
                           replies=[((c["author"] or {}).get("login", "ghost"), c["body"]) for c in cs[1:]],
                           resolved=t["isResolved"], outdated=t["isOutdated"])))
    for r in p["reviews"]["nodes"]:
        if r["body"].strip():
            items.append(("review", r["databaseId"], (r["author"] or {}).get("login", "ghost"), r["body"], r["url"], dict(state=r["state"])))
    for c in p["comments"]["nodes"]:
        if c["body"].strip():
            items.append(("comment", c["databaseId"], (c["author"] or {}).get("login", "ghost"), c["body"], c["url"], {}))
    for kind, gid, author, body, url, extra in items:
        key = f"{kind}:{gid}"
        if key in seen:
            mid = seen[key]
            for k, c in enumerate(entries):
                if c.startswith(f"- id: {mid}\n"):
                    dup = re.search(r"\n  duplicate_of: (\d+)", c)
                    entries[k] = entry(mid, kind, gid, author, body, url, **extra) + (f"\n  duplicate_of: {dup.group(1)}" if dup else "")
                    updated += 1
            continue
        mid = next_id; next_id += 1; seen[key] = mid; new_ids.append(mid)
        entries.append(entry(mid, kind, gid, author, body, url, **extra))
    rc.write_merged(mpath, header, entries)
    with open(sp, "w") as fh:
        for k, v in sorted(seen.items(), key=lambda kv: kv[1]): fh.write(f"{k}\t{v}\n")

    # shortlist candidate findings for each new comment; a judge decides
    allm = rc.load(a.run)
    agents = {i: e for i, e in allm.items() if e.get("lens") != "pr-review"}
    reported = set()
    np_ = os.path.join(a.run, "numbers.tsv")
    if os.path.exists(np_):
        reported = {int(l.split("\t")[1]) for l in open(np_).read().splitlines()[1:] if l.split("\t")[1].isdigit()}
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
    with open(os.path.join(pd, "candidates.tsv"), "w") as fh:
        fh.write("pr_id\tfinding_id\tscore\n")
        for mid, fid, sc in rows: fh.write(f"{mid}\t{fid}\t{sc:.2f}\n")
    print(f"PR #{pr}: {len(new_ids)} new comments, {updated} updated, "
          f"{len(rows)} candidate links for {len({r[0] for r in rows})} comments to judge", file=sys.stderr)

if __name__ == "__main__": main()

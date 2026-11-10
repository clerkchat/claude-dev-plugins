import glob
import os
import json
import re
import subprocess
import tempfile
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugins", "clerk-dev")
SCRIPTS = os.path.join(PLUGIN, "scripts")

sys.path.insert(0, SCRIPTS)
import config
import gh_api
import paths
import records
import run_files


GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def referring_files():
    return [
        *glob.glob(os.path.join(PLUGIN, "skills", "**", "*.md"), recursive=True),
        *glob.glob(os.path.join(PLUGIN, "agents", "*.md")),
        os.path.join(ROOT, "README.md"),
    ]


def plugin_text_files():
    return [*referring_files(), *glob.glob(os.path.join(SCRIPTS, "*.py"))]


FEATURE_MD = "# Feature: test\n\n## Summary\n\nA test feature.\n"


def run_script(name, *args, env=None):
    done = subprocess.run(
        ["python3", os.path.join(SCRIPTS, name + ".py"), *map(str, args)],
        capture_output=True,
        text=True,
        env=env,
    )
    return done.returncode, (done.stdout + done.stderr).rstrip("\n")


def run_ok(name, *args, env=None):
    code, out = run_script(name, *args, env=env)
    if code != 0:
        raise AssertionError(f"{name} {args} failed: {out}")
    return out


def add_backlog_item(wt, kind, title, *extra, env=None):
    return run_ok("backlog", "add", wt, title, "--kind", kind, *extra, env=env)


def add_idea(wt, title, *extra, env=None):
    return add_backlog_item(wt, "idea", title, *extra, env=env)


def add_cleanup(wt, title, *extra, env=None):
    return add_backlog_item(wt, "cleanup", title, "--removes", "EXPORT_V2_FLAG", *extra, env=env)


def add_followup(wt, title, *extra, env=None):
    return add_backlog_item(wt, "followup", title, "--origin", "web 7c1e2ab", *extra, env=env)


def drop_backlog_title(wt, iid, env=None):
    path = run_ok("backlog", "path", wt, iid, env=env)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    write_file(path, re.sub(r"^title: .*\n", "", text, count=1, flags=re.M))


def write_config(path, repos=(), pattern="", after_create=""):
    cfg = config.Config([], [config.Repo(*repo) for repo in repos], pattern, after_create)
    write_file(path, config.render(cfg, ""))


def git(path, *args):
    done = subprocess.run(
        ["git", "-C", str(path), *map(str, args)],
        capture_output=True,
        text=True,
        env=GIT_ENV,
    )
    if done.returncode != 0:
        raise AssertionError(f"git {args} failed: {done.stderr}")
    return done.stdout.strip()


def clone(source, dest, *args):
    subprocess.run(["git", "clone", "-q", *args, str(source), str(dest)], check=True, env=GIT_ENV)
    return Repo(dest)


def write_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def write_record(root, record_id, record_type, title, status="active", extra="", body=""):
    records = paths.records_dir(root)
    os.makedirs(records, exist_ok=True)
    text = (
        f"---\nid: {record_id}\ntype: {record_type}\ntitle: {title}\n"
        f"status: {status}\n{extra}---\n\n# {record_id}. {title}\n\n{body}\n"
    )
    with open(os.path.join(records, record_id + ".md"), "w") as f:
        f.write(text)


def write_feature_md(root):
    write_file(paths.feature_meta(root), FEATURE_MD)


def read_feature_md(root):
    with open(paths.feature_md(root)) as f:
        return f.read()


def feature_md_link(root, path):
    return os.path.relpath(path, os.path.dirname(paths.feature_md(root)))


def read_log(root):
    with open(paths.build_log(root)) as f:
        return f.read()


def write_log(root, text):
    with open(paths.build_log(root), "w") as f:
        f.write(text)


def log_field(root, entry_id, key):
    on = False
    for line in read_log(root).split("\n"):
        if re.match(rf"^- \[.\] {entry_id}\. ", line):
            on = True
        elif line.startswith("- ["):
            on = False
        elif on and line.startswith(f"  - {key}: "):
            return line[len(f"  - {key}: "):]
    return ""


PROBE = """
import json, sys
sys.path.insert(0, sys.argv[1])
import build
try:
    found = build.log(sys.argv[2])
except SystemExit as e:
    print(json.dumps({"error": str(e)}))
else:
    print(json.dumps({
        "relinked": found.relinked,
        "unlinked": [{"id": e["id"], "commit": e["f"]["Commit"]} for e in found.unlinked],
    }))
"""


def probe_log(root):
    done = subprocess.run(
        ["python3", "-c", PROBE, SCRIPTS, str(root)], capture_output=True, text=True
    )
    if done.returncode != 0:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout)


def log_state(root):
    found = probe_log(root)
    return found["relinked"], [e["id"] for e in found["unlinked"]]


def log_unlinked_commit(root, entry_id):
    return next(e["commit"] for e in probe_log(root)["unlinked"] if e["id"] == entry_id)


def log_error(root):
    return probe_log(root).get("error", "no error")


def init_repo(path, with_origin=True):
    os.makedirs(path, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "commit.gpgsign", "false")
    repo = Repo(path)
    repo.base = repo.commit("base")
    if with_origin:
        repo.add_origin()
    return repo


class Repo:
    def __init__(self, path):
        self.path = str(path)
        self.counter = 0

    def git(self, *args):
        return git(self.path, *args)

    def commit(self, subject, filename="file.txt"):
        self.counter += 1
        with open(os.path.join(self.path, filename), "a") as f:
            f.write(f"{subject} {self.counter}\n")
        self.git("add", filename)
        self.git("commit", "-qm", subject)
        return self.git("rev-parse", "--short", "HEAD")

    def add_origin(self):
        bare = os.path.join(self.path + ".remote", "origin.git")
        os.makedirs(os.path.dirname(bare))
        self.origin = bare
        subprocess.run(
            ["git", "clone", "-q", "--bare", self.path, bare], check=True, env=GIT_ENV
        )
        self.git("remote", "add", "origin", bare)
        self.git("fetch", "-q", "origin")
        self.git("remote", "set-head", "origin", "main")

    def head(self):
        return self.git("rev-parse", "--short", "HEAD")

    def find(self, subject):
        return self.git("log", "--format=%h", f"--grep=^{subject}$", "-1")

    def main_moves(self, subject="main moves on", back_to="feat", rebase=True):
        self.git("checkout", "-q", "main")
        self.commit(subject, "main.txt")
        self.git("push", "-q", "origin", "main")
        self.git("checkout", "-q", back_to)
        if rebase:
            self.git("rebase", "-q", "origin/main")

    def squash_merge(self, branch="feat"):
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--squash", branch)
        self.git("commit", "-qm", "squashed " + branch)
        self.git("push", "-q", "origin", "main")
        self.git("checkout", "-q", branch)

    def reset_to_origin(self):
        self.git("reset", "-q", "--hard", "origin/main")

    def build(self, *args):
        return run_script("build", *args[:1], self.path, *args[1:])

    def build_ok(self, *args):
        return run_ok("build", args[0], self.path, *args[1:])

    def status(self, *args):
        return run_script("status", self.path, *args, "--no-mark")

    def digest(self):
        return run_ok("records", "digest", self.path)

    def field(self, entry_id, key):
        return log_field(self.path, entry_id, key)

    def log_text(self):
        return read_log(self.path)

    def state(self):
        return log_state(self.path)

    def error(self):
        return log_error(self.path)


class TempCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = os.path.realpath(tmp.name)

    def path(self, name):
        return os.path.join(self.tmp, name)


class FeatureRepoCase(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("work"))
        self.base = self.repo.base
        self.repo.git("checkout", "-q", "-b", "feat")
        self.c1 = self.repo.commit("feat: decision one")
        self.c2 = self.repo.commit("feat: plan step two")
        self.c3 = self.repo.commit("feat: spec six")
        self.c4 = self.repo.commit("feat: spec five piece")
        self.write_records(self.repo.path)

    def write_records(self, root):
        write_feature_md(root)
        write_record(root, "R1", "decision", "Decision one", body="## Decision\n\nOne.")
        write_record(root, "R2", "decision", "Old decision", "superseded", "superseded_by: R3\n", "## Decision\n\nOld.")
        write_record(root, "R3", "decision", "New decision", "active", "supersedes: R2\n", "## Decision\n\nNew.")
        write_record(root, "R4", "plan", "Active plan", body="1. Piece one, spec R5. Done: when five is built.\n2. Piece two, the second thing. Done: when it is.")
        write_record(root, "R5", "spec", "Spec five", body="## Requirements\n\n1. Five one.\n2. Five two.")
        write_record(root, "R6", "spec", "Spec six", body="## Requirements\n\n1. Six one.\n2. Six two.")
        write_record(root, "R7", "brainstorm", "A brainstorm", body="Ideas.")
        write_record(root, "R8", "plan", "Old plan", "superseded", "superseded_by: R4\n", "1. Old step. Done when old.")


PLAN = """# Plan

## Instances
| # | lens | scope | patch | model | raw file |
| --- | --- | --- | --- | --- | --- |
| 1 | security | entities | patch/entities.patch | opus | raw/security-entities.md |
| 2 | rollout | all | patch/whole.patch | opus | raw/rollout.md |
"""


def plan_md(instances, not_run=None):
    rows = "".join(f"| {n} | {lens} | {scope} | patch/{scope}.patch | opus | raw/{lens}-{scope}.md |\n" for n, (lens, scope) in enumerate(instances, 1))
    cut = "" if not_run is None else "\n## Not run\n| lens | cause |\n| --- | --- |\n" + "".join(f"| {lens} | {cause} |\n" for lens, cause in not_run)
    return "# Plan\n\n## Instances\n| # | lens | scope | patch | model | raw file |\n| --- | --- | --- | --- | --- | --- |\n" + rows + cut


SLICES = """## Slices
- name: webhook-schema
  label: Webhook schema
  summary: new delivery-attempts table
    and its migration
  layer: schema
  files:
    - db/migrations/1.sql
- name: delivery
  summary: webhook intake retried through the queue
## Seams
- webhook-schema -> delivery: the delivery-attempts row
## Order
delivery, webhook-schema
"""


def merged_md(*entries):
    return "```findings\n" + "".join(entries) + "```\n"


class RunCase(TempCase):
    def setUp(self):
        super().setUp()
        self.run_dir = self.path("run")

    def write(self, name, text):
        write_file(os.path.join(self.run_dir, name), text)

    def read(self, name):
        with open(os.path.join(self.run_dir, name), encoding="utf-8") as f:
            return f.read()

    def write_merged(self, *entries):
        self.write("merged.md", merged_md(*entries))

    def write_numbers(self, sections):
        self.write("numbers.tsv", "number\tmerged_id\tsection\n" + "".join(f"{m}\t{m}\t{s}\n" for m, s in sections.items()))

    def write_instructions(self, rows):
        self.write("instructions.tsv", "merged_id\tchoice\tnote\tdate\talso\toption\n"
                   + "".join(f"{m}\t{choice}\t{note}\t\t\t\n" for m, (choice, note) in sorted(rows.items())))

    def write_status(self, rows):
        self.write("status.tsv", "merged_id\tstatus\tref\tdate\n"
                   + "".join(f"{m}\t{status}\t{ref}\t\n" for m, (status, ref) in sorted(rows.items())))

    def write_plan(self, text=PLAN):
        self.write("plan.md", text)

    def write_target(self, *lines):
        self.write("target.txt", "".join(l + "\n" for l in lines))

    def write_files(self, included, excluded=()):
        self.write("files.tsv", "file\tbytes\tadded\tremoved\ttokens\texcluded\n"
                   + "".join(f"{name}\t10\t1\t0\t5\t{reason}\n" for name, reason in [*((f, "") for f in included), *((f, "generated") for f in excluded)]))


def defect(mid, path, line=3, lens="correctness", extra=""):
    return (
        f"- id: {mid}\n  lens: {lens}\n  severity: major\n  confidence: 90\n"
        f"  file: {path}\n  line: {line}\n  claim: Finding {mid} breaks.\n  impact: It matters.\n  fix: Repair finding {mid}.\n{extra}"
    )


class GhRunCase(RunCase):
    def setUp(self):
        super().setUp()
        self.unstubbed_gh_calls = []
        self.stub("gh", side_effect=self.refuse_gh)
        self.addCleanup(self.assertNoUnstubbedGh)

    def refuse_gh(self, args, cwd, stdin=None):
        self.unstubbed_gh_calls.append(list(args))
        raise AssertionError(f"unstubbed gh call: gh {' '.join(map(str, args))}")

    def assertNoUnstubbedGh(self):
        self.assertEqual(self.unstubbed_gh_calls, [])

    def stub(self, name, **kw):
        patcher = mock.patch.object(gh_api, name, **kw)
        self.addCleanup(patcher.stop)
        return patcher.start()


class RenderRunCase(RunCase):
    DATE = "2026-11-05"

    def args(self, *extra):
        return (self.run_dir, "--target", "t", "--repo", self.tmp, "--date", self.DATE, "--wrap", "0", *extra)

    def render(self, *extra):
        return run_ok("render-report", *self.args(*extra))

    def render_fails(self, *extra):
        code, out = run_script("render-report", *self.args(*extra))
        self.assertEqual(code, 1)
        return out

    def report(self):
        return self.read("report.md")

    def edit_report(self, old, new):
        text = self.report()
        self.assertIn(old, text)
        self.write("report.md", text.replace(old, new, 1))

    def card(self, number):
        return self.report().split(f"#### {number}. ", 1)[1].split("\n#### ", 1)[0].split("\n## ", 1)[0]

    def instruction(self, mid):
        return run_files.read_instructions(self.run_dir).get(mid, {})

    def status(self, mid):
        return run_files.read_status(self.run_dir).get(mid)

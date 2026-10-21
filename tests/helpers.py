import os
import json
import re
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "plugins", "clerk-dev", "scripts")

GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}

FEATURE_MD = "# Feature: test\n\n## Summary\n\nA test feature.\n"


def run_script(name, *args):
    done = subprocess.run(
        ["python3", os.path.join(SCRIPTS, name + ".py"), *map(str, args)],
        capture_output=True,
        text=True,
    )
    return done.returncode, (done.stdout + done.stderr).rstrip("\n")


def run_ok(name, *args):
    code, out = run_script(name, *args)
    if code != 0:
        raise AssertionError(f"{name} {args} failed: {out}")
    return out


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


def write_record(root, record_id, record_type, title, status="active", extra="", body=""):
    records = os.path.join(root, ".clerk-dev", "feature", "records")
    os.makedirs(records, exist_ok=True)
    text = (
        f"---\nid: {record_id}\ntype: {record_type}\ntitle: {title}\n"
        f"status: {status}\n{extra}---\n\n# {record_id}. {title}\n\n{body}\n"
    )
    with open(os.path.join(records, record_id + ".md"), "w") as f:
        f.write(text)


def write_feature_md(root):
    feature = os.path.join(root, ".clerk-dev", "feature")
    os.makedirs(feature, exist_ok=True)
    with open(os.path.join(feature, "feature.md"), "w") as f:
        f.write(FEATURE_MD)


def read_log(root):
    with open(os.path.join(root, ".clerk-dev", "build.md")) as f:
        return f.read()


def write_log(root, text):
    with open(os.path.join(root, ".clerk-dev", "build.md"), "w") as f:
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

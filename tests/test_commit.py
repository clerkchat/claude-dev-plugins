import os
import shutil
import subprocess

from helpers import GIT_ENV, SCRIPTS, TempCase, git, init_repo, write_file
import commit


def run_commit(wt, message, *files):
    done = subprocess.run(
        ["python3", os.path.join(SCRIPTS, "commit.py"), wt, *files],
        input=message, capture_output=True, text=True, env=GIT_ENV,
    )
    return done.returncode, (done.stdout + done.stderr).strip()


class CommitScriptCase(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("wt"), with_origin=False)
        self.wt = self.repo.path
        self.head_before = self.repo.head()
        write_file(os.path.join(self.wt, "a.txt"), "a\n")

    def message(self):
        return git(self.wt, "log", "-1", "--format=%B")

    def assertRefused(self, message, *files, shows=()):
        code, out = run_commit(self.wt, message, *(files or ("a.txt",)))
        self.assertNotEqual(code, 0)
        self.assertEqual(self.repo.head(), self.head_before)
        for text in shows:
            self.assertIn(text, out)


class CommitSubjectTest(CommitScriptCase):
    def test_commits_a_good_subject_and_prints_the_sha(self):
        code, out = run_commit(self.wt, "feat(api): add a\n\nBody.\n", "a.txt")
        self.assertEqual((code, out), (0, self.repo.head()))

    def test_accepts_the_breaking_marker(self):
        code, _ = run_commit(self.wt, "change(api)!: drop the route\n", "a.txt")
        self.assertEqual(code, 0)

    def test_refuses_a_space_before_the_area(self):
        self.assertRefused("click-house (refactor): x\n", shows=["<type>(<area>)", "click-house (refactor): x"])

    def test_refuses_an_unknown_type(self):
        self.assertRefused("wip(api): x\n", shows=["feat", "wip(api): x"])

    def test_refuses_a_missing_area(self):
        self.assertRefused("feat: x\n", shows=["<type>(<area>)", "feat: x"])


class CommitTrailerTest(CommitScriptCase):
    def trailer_lines(self):
        return [l for l in self.message().split("\n") if l.startswith("Assisted-by:")]

    def test_adds_the_trailer_once_before_co_authored_by(self):
        run_commit(self.wt, "feat(api): add a\n\nBody.\n\nCo-Authored-By: Claude <c@c>\n", "a.txt")
        lines = self.message().strip().split("\n")
        self.assertEqual(lines[-2].split(" ")[0], "Assisted-by:")
        self.assertEqual(lines[-1], "Co-Authored-By: Claude <c@c>")
        self.assertEqual(len(self.trailer_lines()), 1)

    def test_replaces_an_existing_assisted_by(self):
        run_commit(self.wt, "feat(api): add a\n\nAssisted-by: clerk-dev 0.0.1\n", "a.txt")
        self.assertEqual(len(self.trailer_lines()), 1)
        self.assertNotIn("0.0.1", self.message())

    def test_adds_the_trailer_to_a_subject_only_message(self):
        run_commit(self.wt, "feat(api): add a\n", "a.txt")
        self.assertEqual(len(self.trailer_lines()), 1)
        self.assertEqual(self.message().split("\n")[0], "feat(api): add a")


class CommitFilesTest(CommitScriptCase):
    def test_refuses_a_clerk_dev_file(self):
        write_file(os.path.join(self.wt, ".clerk-dev", "build.md"), "x\n")
        self.assertRefused("feat(api): add a\n", "a.txt", ".clerk-dev/build.md", shows=[".clerk-dev/build.md"])

    def test_refuses_when_a_clerk_dev_path_is_already_staged(self):
        write_file(os.path.join(self.wt, ".clerk-dev", "build.md"), "x\n")
        git(self.wt, "add", "-f", ".clerk-dev/build.md")
        self.assertRefused("feat(api): add a\n", shows=[".clerk-dev/build.md"])

    def test_commits_only_the_named_files(self):
        write_file(os.path.join(self.wt, "b.txt"), "b\n")
        git(self.wt, "add", "b.txt")
        run_commit(self.wt, "feat(api): add a\n", "a.txt")
        self.assertEqual(git(self.wt, "show", "--name-only", "--format=", "HEAD"), "a.txt")
        self.assertEqual(git(self.wt, "diff", "--cached", "--name-only"), "b.txt")

    def test_commits_a_deletion(self):
        git(self.wt, "rm", "-q", "file.txt")
        code, _ = run_commit(self.wt, "refactor(api): drop file\n", "file.txt")
        self.assertEqual(code, 0)
        self.assertEqual(git(self.wt, "show", "--name-status", "--format=", "HEAD"), "D\tfile.txt")


class CommitTypesTest(TempCase):
    def test_reads_the_types_from_the_commits_table(self):
        self.assertEqual(commit.allowed_types()[:3], ["refactor", "feat", "fix"])

    def test_a_new_row_admits_a_new_type(self):
        copy = self.path("commits.md")
        shutil.copy(commit.COMMITS_MD, copy)
        with open(copy, "a") as f:
            f.write("\n| `perf` | live | Speed |\n")
        types = commit.allowed_types(copy)
        self.assertIsNone(commit.subject_error("perf(api): faster", types))
        self.assertIsNotNone(commit.subject_error("perf(api): faster", commit.allowed_types()))

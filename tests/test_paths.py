import os
import unittest

from helpers import TempCase, init_repo, run_script
import paths

WORKTREE_PATHS = {
    "clerk-dev": ".clerk-dev",
    "ledger": ".clerk-dev/.ledger",
    "runs-dir": ".clerk-dev/.ledger/runs",
    "latest": ".clerk-dev/.ledger/latest",
    "review-link": ".clerk-dev/review.md",
    "notes": ".clerk-dev/branch-notes.md",
    "pr-description": ".clerk-dev/pr-description.md",
    "pr-generated": ".clerk-dev/.ledger/pr-description.generated.md",
    "pr-body": ".clerk-dev/.ledger/pr-body.md",
    "pr-notes": ".clerk-dev/.ledger/pr-draft-notes.md",
    "build-log": ".clerk-dev/.ledger/build.md",
    "passes": ".clerk-dev/.ledger/passes.md",
    "deferred": ".clerk-dev/.ledger/deferred.md",
    "workspace": ".clerk-dev/.ledger/workspace.md",
    "seen-backlog": ".clerk-dev/.ledger/status-seen-backlog",
}

FEATURE_PATHS = {
    "feature-dir": ".clerk-dev/.ledger/feature",
    "feature-meta": ".clerk-dev/.ledger/feature/feature.md",
    "records-dir": ".clerk-dev/.ledger/feature/records",
    "checks-dir": ".clerk-dev/.ledger/feature/checks",
    "feature-md": ".clerk-dev/feature.md",
    "overview": ".clerk-dev/overview.md",
}

USER_FACING = {"clerk-dev", "review-link", "notes", "pr-description", "feature-md", "overview"}


class PathsCase(TempCase):
    def setUp(self):
        super().setUp()
        self.wt = self.path("wt")

    def at(self, rel):
        return os.path.join(self.wt, *rel.split("/"))


class NamedPathsTest(PathsCase):
    def test_each_worktree_path_is_where_the_scripts_keep_it(self):
        for name, rel in WORKTREE_PATHS.items():
            with self.subTest(name):
                self.assertEqual(paths.PRINTABLE[name](self.wt), self.at(rel))

    def test_each_feature_path_is_under_the_hub(self):
        for name, rel in FEATURE_PATHS.items():
            with self.subTest(name):
                self.assertEqual(paths.PRINTABLE[name](self.wt), self.at(rel))

    def test_only_the_files_the_user_opens_are_outside_the_ledger(self):
        ledger = paths.ledger(self.wt) + os.sep
        outside = {name for name, f in paths.PRINTABLE.items() if name != "run" and not f(self.wt).startswith(ledger)}
        self.assertEqual(outside, USER_FACING | {"ledger"})

    def test_every_printable_name_is_covered(self):
        self.assertEqual(set(paths.PRINTABLE) - {"run"}, set(WORKTREE_PATHS) | set(FEATURE_PATHS))

    def test_a_run_is_its_label_under_the_runs_directory(self):
        self.assertEqual(paths.run(self.wt, "20261110-0900-branch"), self.at(".clerk-dev/.ledger/runs/20261110-0900-branch"))

    def test_the_feature_runs_pointer_is_latest_feature(self):
        self.assertEqual(paths.latest(self.wt, feature=True), self.at(".clerk-dev/.ledger/latest-feature"))

    def test_the_feature_runs_review_link_is_review_feature(self):
        self.assertEqual(paths.review_link(self.wt, feature=True), self.at(".clerk-dev/review-feature.md"))


class RunNameCase(PathsCase):
    def setUp(self):
        super().setUp()
        self.run = paths.run(self.wt, "20261110-0900-branch")
        os.makedirs(self.run)

    def write_report(self, run):
        with open(os.path.join(run, "report.md"), "w") as f:
            f.write("# Review\n")

    def link_review(self):
        os.symlink(os.path.join(".ledger", "runs", "20261110-0900-branch", "report.md"), paths.review_link(self.wt))


class RunNameTest(RunNameCase):
    def test_a_run_without_a_report_is_named_by_its_directory(self):
        self.assertEqual(paths.run_name(self.wt, self.run), ".clerk-dev/.ledger/runs/20261110-0900-branch")

    def test_a_report_no_review_link_reaches_is_named_by_its_path(self):
        self.write_report(self.run)
        self.assertEqual(paths.run_name(self.wt, self.run), ".clerk-dev/.ledger/runs/20261110-0900-branch/report.md")


class WhenTheReviewLinkResolvesToTheReportTest(RunNameCase):
    def setUp(self):
        super().setUp()
        self.write_report(self.run)
        self.link_review()

    def test_names_the_review_link(self):
        self.assertEqual(paths.run_name(self.wt, self.run), ".clerk-dev/review.md")

    def test_names_another_run_by_its_report(self):
        other = paths.run(self.wt, "20261110-1000-branch")
        os.makedirs(other)
        self.write_report(other)
        self.assertEqual(paths.run_name(self.wt, other), ".clerk-dev/.ledger/runs/20261110-1000-branch/report.md")


class EnsureTest(PathsCase):
    def setUp(self):
        super().setUp()
        init_repo(self.wt, with_origin=False)
        self.exclude = self.at(".git/info/exclude")
        paths.ensure(self.wt)

    def exclude_lines(self):
        with open(self.exclude) as f:
            return [line for line in f.read().splitlines() if line == ".clerk-dev/"]

    def test_creates_the_clerk_dev_directory(self):
        self.assertTrue(os.path.isdir(self.at(".clerk-dev")))

    def test_creates_the_ledger_and_its_runs_directory(self):
        self.assertTrue(os.path.isdir(self.at(".clerk-dev/.ledger/runs")))

    def test_adds_the_exclude_line(self):
        self.assertEqual(self.exclude_lines(), [".clerk-dev/"])

    def test_adds_it_once_when_run_again(self):
        paths.ensure(self.wt)
        self.assertEqual(self.exclude_lines(), [".clerk-dev/"])


class MainTest(PathsCase):
    def test_prints_a_path_by_name(self):
        self.assertEqual(run_script("paths", self.wt, "build-log"), (0, self.at(".clerk-dev/.ledger/build.md")))

    def test_prints_a_run_by_its_label(self):
        self.assertEqual(run_script("paths", self.wt, "run", "20261110-0900-branch"), (0, self.at(".clerk-dev/.ledger/runs/20261110-0900-branch")))

    def test_prints_the_feature_runs_pointer(self):
        self.assertEqual(run_script("paths", self.wt, "latest", "--feature"), (0, self.at(".clerk-dev/.ledger/latest-feature")))

    def test_prints_the_feature_runs_review_link(self):
        self.assertEqual(run_script("paths", self.wt, "review-link", "--feature"), (0, self.at(".clerk-dev/review-feature.md")))

    def test_refuses_feature_with_another_name(self):
        self.assertNotEqual(run_script("paths", self.wt, "build-log", "--feature")[0], 0)

    def test_refuses_a_run_without_a_label(self):
        self.assertNotEqual(run_script("paths", self.wt, "run")[0], 0)

    def test_ensure_creates_the_directory(self):
        init_repo(self.wt, with_origin=False)
        run_script("paths", "ensure", self.wt)
        self.assertTrue(os.path.isdir(self.at(".clerk-dev/.ledger/runs")))


if __name__ == "__main__":
    unittest.main()

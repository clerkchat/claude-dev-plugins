import os
import unittest

from helpers import TempCase, init_repo, run_script
import paths

WORKTREE_PATHS = {
    "clerk-dev": ".clerk-dev",
    "ledger": ".clerk-dev",
    "runs-dir": ".clerk-dev",
    "latest": ".clerk-dev/latest",
    "review-link": ".clerk-dev/review.md",
    "notes": ".clerk-dev/branch-notes.md",
    "pr-description": ".clerk-dev/pr-description.md",
    "pr-generated": ".clerk-dev/pr-description.generated.md",
    "pr-body": ".clerk-dev/pr-body.md",
    "pr-notes": ".clerk-dev/pr-draft-notes.md",
    "build-log": ".clerk-dev/build.md",
    "passes": ".clerk-dev/passes.md",
    "deferred": ".clerk-dev/deferred.md",
    "workspace": ".clerk-dev/workspace.md",
    "seen-backlog": ".clerk-dev/status-seen-backlog",
}

FEATURE_PATHS = {
    "feature-dir": ".clerk-dev/feature",
    "feature-meta": ".clerk-dev/feature/feature.md",
    "records-dir": ".clerk-dev/feature/records",
    "checks-dir": ".clerk-dev/feature/checks",
    "feature-md": ".clerk-dev/feature/feature.md",
    "overview": ".clerk-dev/feature/overview.md",
}


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

    def test_every_printable_name_is_covered(self):
        self.assertEqual(set(paths.PRINTABLE) - {"run"}, set(WORKTREE_PATHS) | set(FEATURE_PATHS))

    def test_a_run_is_its_label_under_the_runs_directory(self):
        self.assertEqual(paths.run(self.wt, "20261110-0900-branch"), self.at(".clerk-dev/20261110-0900-branch"))

    def test_the_feature_runs_pointer_is_latest_feature(self):
        self.assertEqual(paths.latest(self.wt, feature=True), self.at(".clerk-dev/latest-feature"))


class HubOfTest(PathsCase):
    def test_inverts_feature_dir(self):
        self.assertEqual(paths.hub_of(paths.feature_dir(self.wt)), self.wt)

    def test_ignores_a_trailing_separator(self):
        self.assertEqual(paths.hub_of(paths.feature_dir(self.wt) + os.sep), self.wt)

    def test_refuses_a_directory_that_is_not_a_feature_directory(self):
        with self.assertRaises(ValueError):
            paths.hub_of(self.at(".clerk-dev/records"))


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

    def test_adds_the_exclude_line(self):
        self.assertEqual(self.exclude_lines(), [".clerk-dev/"])

    def test_adds_it_once_when_run_again(self):
        paths.ensure(self.wt)
        self.assertEqual(self.exclude_lines(), [".clerk-dev/"])


class MainTest(PathsCase):
    def test_prints_a_path_by_name(self):
        self.assertEqual(run_script("paths", self.wt, "build-log"), (0, self.at(".clerk-dev/build.md")))

    def test_prints_a_run_by_its_label(self):
        self.assertEqual(run_script("paths", self.wt, "run", "20261110-0900-branch"), (0, self.at(".clerk-dev/20261110-0900-branch")))

    def test_prints_the_feature_runs_pointer(self):
        self.assertEqual(run_script("paths", self.wt, "latest", "--feature"), (0, self.at(".clerk-dev/latest-feature")))

    def test_refuses_a_run_without_a_label(self):
        self.assertNotEqual(run_script("paths", self.wt, "run")[0], 0)

    def test_ensure_creates_the_directory(self):
        init_repo(self.wt, with_origin=False)
        run_script("paths", "ensure", self.wt)
        self.assertTrue(os.path.isdir(self.at(".clerk-dev")))


if __name__ == "__main__":
    unittest.main()

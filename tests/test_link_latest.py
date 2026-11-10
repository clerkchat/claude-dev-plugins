import os
import sys
import unittest

from helpers import SCRIPTS, TempCase
import paths

sys.path.insert(0, SCRIPTS)
import records

link = records.load_script("link-latest.py")

RUN = "20261106-1052-branch"
EARLIER = "20261106-0938-branch"
FEATURE_RUN = "20261106-1052-branch-feature"


class LinkLatestCase(TempCase):
    def setUp(self):
        super().setUp()
        self.worktree = self.path("wt")
        self.clerk_dev = paths.clerk_dev(self.worktree)

    def run_dir(self, label):
        path = paths.run(self.worktree, label)
        os.makedirs(path)
        return path

    def reported_run(self, label):
        path = self.run_dir(label)
        with open(os.path.join(path, "report.md"), "w") as f:
            f.write("# Review\n")
        return path

    def latest_target(self, feature=False):
        return os.readlink(paths.latest(self.worktree, feature))

    def review_target(self, feature=False):
        return os.readlink(paths.review_link(self.worktree, feature))

    def has_review_link(self, feature=False):
        return os.path.lexists(paths.review_link(self.worktree, feature))

    def refusal(self, run):
        with self.assertRaises(SystemExit) as raised:
            link.link_latest(self.worktree, run)
        return str(raised.exception)


class WhenTheRunHasNoReportYetTest(LinkLatestCase):
    def setUp(self):
        super().setUp()
        link.link_latest(self.worktree, self.run_dir(RUN))

    def test_points_latest_at_the_run(self):
        self.assertEqual(self.latest_target(), f"runs/{RUN}")

    def test_makes_no_review_link(self):
        self.assertFalse(self.has_review_link())

    def test_leaves_only_the_ledger_on_top(self):
        self.assertEqual(os.listdir(self.clerk_dev), [".ledger"])


class WhenTheRunHasItsReportTest(LinkLatestCase):
    def setUp(self):
        super().setUp()
        link.link_latest(self.worktree, self.reported_run(RUN))

    def test_points_review_md_at_the_runs_report(self):
        self.assertEqual(self.review_target(), f".ledger/runs/{RUN}/report.md")

    def test_review_md_reads_the_report(self):
        with open(paths.review_link(self.worktree)) as f:
            self.assertEqual(f.read(), "# Review\n")

    def test_leaves_only_review_md_and_the_ledger_on_top(self):
        self.assertEqual(sorted(os.listdir(self.clerk_dev)), [".ledger", "review.md"])

    def test_leaves_nothing_but_the_pointer_beside_the_runs(self):
        self.assertEqual(sorted(os.listdir(paths.ledger(self.worktree))), ["latest", "runs"])


class WhenLatestPointsAtAnEarlierRunTest(LinkLatestCase):
    def setUp(self):
        super().setUp()
        link.link_latest(self.worktree, self.reported_run(EARLIER))

    def test_moves_latest_to_the_new_run(self):
        link.link_latest(self.worktree, self.run_dir(RUN))
        self.assertEqual(self.latest_target(), f"runs/{RUN}")

    def test_moves_review_md_to_the_new_runs_report(self):
        link.link_latest(self.worktree, self.reported_run(RUN))
        self.assertEqual(self.review_target(), f".ledger/runs/{RUN}/report.md")

    def test_removes_review_md_until_the_new_run_has_its_report(self):
        link.link_latest(self.worktree, self.run_dir(RUN))
        self.assertFalse(self.has_review_link())


class WhenTheRunIsAFeatureRunTest(LinkLatestCase):
    def setUp(self):
        super().setUp()
        link.link_latest(self.worktree, self.reported_run(FEATURE_RUN))

    def test_points_latest_feature_at_it(self):
        self.assertEqual(self.latest_target(feature=True), f"runs/{FEATURE_RUN}")

    def test_points_review_feature_md_at_its_report(self):
        self.assertEqual(self.review_target(feature=True), f".ledger/runs/{FEATURE_RUN}/report.md")

    def test_leaves_latest_alone(self):
        self.assertFalse(os.path.lexists(paths.latest(self.worktree)))

    def test_leaves_review_md_alone(self):
        self.assertFalse(self.has_review_link())


class RefusalTest(LinkLatestCase):
    def test_refuses_a_directory_outside_the_runs_directory(self):
        outside = self.path("elsewhere")
        os.makedirs(outside)
        self.assertIn("not a run directory directly under", self.refusal(outside))

    def test_refuses_a_path_that_climbs_out_of_the_runs_directory(self):
        os.makedirs(self.path("scripts"))
        self.run_dir(RUN)
        self.assertIn("not a run directory", self.refusal(os.path.join(paths.runs_dir(self.worktree), "..", "..", "..", "..", "scripts")))

    def test_refuses_a_run_that_does_not_exist(self):
        os.makedirs(paths.runs_dir(self.worktree))
        self.assertIn("not a run directory", self.refusal(paths.run(self.worktree, RUN)))

    def test_refuses_a_directory_directly_under_clerk_dev(self):
        os.makedirs(os.path.join(self.clerk_dev, RUN))
        self.assertIn("not a run directory", self.refusal(os.path.join(self.clerk_dev, RUN)))

    def test_refuses_to_replace_a_latest_that_is_not_a_link(self):
        os.makedirs(paths.latest(self.worktree))
        self.assertIn("is not a link", self.refusal(self.run_dir(RUN)))


class WhenReviewMdIsNotALinkTest(LinkLatestCase):
    def setUp(self):
        super().setUp()
        os.makedirs(self.clerk_dev)
        with open(paths.review_link(self.worktree), "w") as f:
            f.write("my notes\n")
        self.refused = self.refusal(self.reported_run(RUN))

    def test_refuses_to_replace_it(self):
        self.assertIn("is not a link", self.refused)

    def test_leaves_latest_unmade(self):
        self.assertFalse(os.path.lexists(paths.latest(self.worktree)))

    def test_leaves_the_file_as_it_was(self):
        with open(paths.review_link(self.worktree)) as f:
            self.assertEqual(f.read(), "my notes\n")


if __name__ == "__main__":
    unittest.main()

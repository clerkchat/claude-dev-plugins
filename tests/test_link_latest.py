import os
import sys
import unittest

from helpers import SCRIPTS, TempCase

sys.path.insert(0, SCRIPTS)
import records

link = records.load_script("link-latest.py")


class LinkLatestCase(TempCase):
    def setUp(self):
        super().setUp()
        self.worktree = self.path("wt")
        self.clerk_dev = os.path.join(self.worktree, ".clerk-dev")

    def run_dir(self, label):
        path = os.path.join(self.clerk_dev, label)
        os.makedirs(path)
        return path

    def target_of(self, name):
        return os.readlink(os.path.join(self.clerk_dev, name))

    def refusal(self, run):
        with self.assertRaises(SystemExit) as raised:
            link.link_latest(self.worktree, run)
        return str(raised.exception)


class LinkLatestTest(LinkLatestCase):
    def test_points_latest_at_the_run(self):
        link.link_latest(self.worktree, self.run_dir("20261106-1052-branch"))
        self.assertEqual(self.target_of("latest"), "20261106-1052-branch")

    def test_leaves_nothing_but_the_link_beside_the_run(self):
        link.link_latest(self.worktree, self.run_dir("20261106-1052-branch"))
        self.assertEqual(sorted(os.listdir(self.clerk_dev)), ["20261106-1052-branch", "latest"])


class WhenLatestPointsAtAnEarlierRunTest(LinkLatestCase):
    def setUp(self):
        super().setUp()
        link.link_latest(self.worktree, self.run_dir("20261106-0938-branch"))

    def test_moves_it_to_the_new_run(self):
        link.link_latest(self.worktree, self.run_dir("20261106-1052-branch"))
        self.assertEqual(self.target_of("latest"), "20261106-1052-branch")


class WhenTheRunIsAFeatureRunTest(LinkLatestCase):
    def setUp(self):
        super().setUp()
        link.link_latest(self.worktree, self.run_dir("20261106-1052-branch-feature"))

    def test_points_latest_feature_at_it(self):
        self.assertEqual(self.target_of("latest-feature"), "20261106-1052-branch-feature")

    def test_leaves_latest_alone(self):
        self.assertFalse(os.path.lexists(os.path.join(self.clerk_dev, "latest")))


class RefusalTest(LinkLatestCase):
    def test_refuses_a_directory_outside_the_worktrees_clerk_dev(self):
        outside = self.path("elsewhere")
        os.makedirs(outside)
        self.assertIn("not a run directory directly under", self.refusal(outside))

    def test_refuses_a_path_that_climbs_out_of_clerk_dev(self):
        os.makedirs(self.path("scripts"))
        self.run_dir("20261106-1052-branch")
        self.assertIn("not a run directory", self.refusal(os.path.join(self.clerk_dev, "..", "..", "scripts")))

    def test_refuses_a_run_that_does_not_exist(self):
        os.makedirs(self.clerk_dev)
        self.assertIn("not a run directory", self.refusal(os.path.join(self.clerk_dev, "20261106-1052-branch")))

    def test_refuses_to_replace_a_latest_that_is_not_a_link(self):
        os.makedirs(os.path.join(self.clerk_dev, "latest"))
        self.assertIn("is not a link", self.refusal(self.run_dir("20261106-1052-branch")))


if __name__ == "__main__":
    unittest.main()

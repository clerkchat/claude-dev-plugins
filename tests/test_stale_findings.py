import os
import unittest

from helpers import RunCase, add_backlog_item, init_repo, records, run_ok, write_file
import paths

sf = records.load_script("stale-findings.py")


class FollowUpCommitCase(RunCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("work"))
        self.repo.git("checkout", "-q", "-b", "feat")
        self.reviewed = self.repo.git("rev-parse", "HEAD")
        self.fix = self.repo.commit("feat: send exportId back")
        self.later = self.repo.commit("feat: other work")
        self.write_merged()
        self.write_target("branch", self.repo.base, self.reviewed)
        add_backlog_item(self.repo.path, "followup", "Send exportId back", "--origin", "web abc1234")

    def close_with(self, ref):
        run_ok("backlog", "set", self.repo.path, "BL-1", "done", "--ref", ref)

    def full(self, short):
        return self.repo.git("rev-parse", short)

    def labels(self):
        return sf.followup_labels(self.repo.path)

    def delta_kinds(self):
        rows = run_ok("stale-findings", self.run_dir, "--delta", "--repo", self.repo.path).splitlines()[1:]
        return {row.split("\t")[0]: row.split("\t")[1] for row in rows if "\t" in row}


class FollowUpLabelTests(FollowUpCommitCase):
    def test_an_owed_follow_up_labels_no_commit(self):
        self.assertEqual(self.labels(), {})

    def test_the_commit_a_follow_up_was_done_in_is_labelled_with_its_id(self):
        self.close_with(self.fix)
        self.assertEqual(self.labels(), {self.full(self.fix): "BL-1"})

    def test_an_outcome_that_also_names_the_brief_still_labels_the_commit(self):
        self.close_with(f"{self.fix} (BRIEF-62)")
        self.assertEqual(self.labels(), {self.full(self.fix): "BL-1"})


class WhenTheWorkspaceNamesAMissingHubTests(FollowUpCommitCase):
    def setUp(self):
        super().setUp()
        self.close_with(self.fix)
        write_file(paths.workspace(self.repo.path), f"Hub: {self.path('gone')}\n")

    def test_the_commit_a_follow_up_was_done_in_is_still_labelled(self):
        self.assertEqual(self.labels(), {self.full(self.fix): "BL-1"})


class NarrowCoveredCase(FollowUpCommitCase):
    def write_narrow(self, directory, head):
        write_file(os.path.join(directory, "narrow.txt"), f"{head}\n{self.reviewed}\n{head}\n")

    def covered(self):
        return sf.narrow_covered(self.repo.path)


class NarrowCoveredTests(NarrowCoveredCase):
    def test_a_narrow_run_covers_the_commits_it_read(self):
        self.write_narrow(paths.run(self.repo.path, "20261110-0900-narrow"), self.fix)
        self.assertEqual(self.covered(), {self.full(self.fix)})


class WhenTheUserKeepsNotesAndLogsTests(NarrowCoveredCase):
    def setUp(self):
        super().setUp()
        for name in ("notes", "logs"):
            self.write_narrow(os.path.join(paths.clerk_dev(self.repo.path), name), self.later)

    def test_their_directories_are_not_read_as_runs(self):
        self.assertEqual(self.covered(), set())


class DeltaTests(FollowUpCommitCase):
    def setUp(self):
        super().setUp()
        self.close_with(self.fix)

    def test_marks_the_follow_ups_commit_follow_up(self):
        self.assertEqual(self.delta_kinds()[self.full(self.fix)], "follow-up")

    def test_leaves_other_commits_unreviewed(self):
        self.assertEqual(self.delta_kinds()[self.full(self.later)], "unreviewed")


if __name__ == "__main__":
    unittest.main()

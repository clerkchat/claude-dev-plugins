import os
import unittest

from helpers import TempCase, init_repo

DRAFT_STEP = '"draft the PR description"'


class DraftStepCase(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("work"))
        self.repo.git("checkout", "-q", "-b", "feat")
        self.repo.commit("feat: the change")
        self.run_dir = os.path.join(self.repo.path, ".clerk-dev", "latest")

    def write_run(self):
        os.makedirs(self.run_dir, exist_ok=True)
        self.write("merged.md", "")
        head = self.repo.git("rev-parse", "HEAD")
        self.write("target.txt", f"branch\n{self.repo.git('rev-parse', 'main')}\n{head}\n")

    def write_final(self, verdict):
        self.write("final-review-report.md", f"# Final review: {verdict}\n\nWhole branch.\n")

    def write(self, name, text):
        with open(os.path.join(self.run_dir, name), "w") as f:
            f.write(text)

    def next_steps(self):
        code, out = self.repo.status()
        self.assertEqual(code, 0, out)
        return out.split("**Next:**", 1)[1]


class DraftStepTests(DraftStepCase):
    def test_a_branch_never_reviewed_is_offered_the_draft(self):
        steps = self.next_steps()
        self.assertIn("Run a review", steps)
        self.assertIn(DRAFT_STEP, steps)

    def test_a_review_without_a_final_pass_is_not_offered_the_draft(self):
        self.write_run()
        self.assertNotIn(DRAFT_STEP, self.next_steps())

    def test_a_passed_final_pass_with_triage_done_is_offered_the_draft(self):
        self.write_run()
        self.write_final("PASSED")
        self.assertIn(DRAFT_STEP, self.next_steps())

    def test_a_final_pass_that_did_not_pass_is_not_offered_the_draft(self):
        self.write_run()
        self.write_final("NOT PASSED: 1 still open in Fix before merging")
        self.assertNotIn(DRAFT_STEP, self.next_steps())

    def test_a_review_after_the_passed_final_pass_withholds_the_draft(self):
        self.write_run()
        self.write_final("PASSED")
        later = os.path.getmtime(os.path.join(self.run_dir, "final-review-report.md")) + 60
        os.utime(os.path.join(self.run_dir, "target.txt"), (later, later))
        self.assertNotIn(DRAFT_STEP, self.next_steps())

    def test_commits_after_the_passed_final_pass_withhold_the_draft(self):
        self.write_run()
        self.write_final("PASSED")
        self.repo.commit("feat: more after the final pass")
        steps = self.next_steps()
        self.assertIn("unreviewed commit", steps)
        self.assertNotIn(DRAFT_STEP, steps)


if __name__ == "__main__":
    unittest.main()

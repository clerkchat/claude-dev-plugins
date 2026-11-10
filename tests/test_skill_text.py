import os
import unittest

from helpers import PLUGIN, ROOT


def text_of(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return " ".join(f.read().split())


class ReviewTriageStepFourTest(unittest.TestCase):
    def setUp(self):
        self.text = text_of(PLUGIN, "skills", "review-triage", "SKILL.md")

    def test_runs_render_body_after_writing_the_sentence(self):
        self.assertIn("post-review.py <run> --repo <worktree> --render-body", self.text)

    def test_tells_the_user_the_whole_file_is_theirs_to_edit(self):
        self.assertIn("the whole file is theirs to edit", self.text)


class ReviewSkillTest(unittest.TestCase):
    def setUp(self):
        self.text = text_of(PLUGIN, "skills", "review", "SKILL.md")

    def test_ends_the_plan_with_a_not_run_table(self):
        self.assertIn("## Not run | lens | cause |", self.text)

    def test_writes_the_table_with_no_rows_for_a_pass(self):
        self.assertIn("always empty with `--pass`", self.text)

    def test_lists_the_review_file_as_the_sentence_and_the_rendered_block(self):
        self.assertIn("`review.md` the review body (the drafted sentence, then the range line and the how-reviewed block `--render-body` writes)", self.text)


class CommitsGuideTest(unittest.TestCase):
    def setUp(self):
        self.text = text_of(PLUGIN, "skills", "review", "commits.md")

    def test_asks_for_the_assisted_by_trailer_with_the_plugin_version(self):
        self.assertIn("Every commit a skill writes ends with the trailer `Assisted-by: clerk-dev <version>`", self.text)

    def test_puts_it_before_the_attribution_lines_the_session_adds(self):
        self.assertIn("before any attribution lines the session adds", self.text)

    def test_leaves_the_users_own_commits_without_it(self):
        self.assertIn("The user's own commits get none.", self.text)


class ReadmeTest(unittest.TestCase):
    def setUp(self):
        self.text = text_of(ROOT, "README.md")

    def test_says_how_to_turn_the_hooks_on(self):
        self.assertIn("git config core.hooksPath .githooks", self.text)

    def test_says_to_merge_into_main_with_merge_commits(self):
        self.assertIn("git config branch.main.mergeoptions --no-ff", self.text)

    def test_says_how_to_bump(self):
        self.assertIn("scripts/bump-version.py <patch|minor|major>", self.text)

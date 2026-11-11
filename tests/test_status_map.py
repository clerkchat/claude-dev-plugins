import os
import unittest

from helpers import TempCase, add_followup, add_idea, init_repo, write_feature_md, write_file, write_record
import paths

PLAN_BODY = (
    "1. Step one, brief R5. Done: when it runs.\n"
    "2. Step two, brief R5. Done: when it reads.\n"
    "3. Step three. Done: when it shows.\n"
)
BRIEF_BODY = "## Requirements\n\n1. One.\n2. Two.\n"
PIECES_BODY = "1. **Export job**: create the export.\n2. **Status endpoint**: read it back.\n"


class MapCase(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("work"))
        self.repo.git("checkout", "-q", "-b", "feat")
        write_feature_md(self.repo.path)
        write_record(self.repo.path, "R5", "brief", "The brief", body=BRIEF_BODY)

    def plan(self, body=PLAN_BODY):
        write_record(self.repo.path, "R4", "plan", "The plan", body=body)

    def milestone(self, *where, passes="prep"):
        mid = self.repo.build_ok("milestone", *where, "--passes", passes).split()[0]
        self.repo.build_ok("skip", mid, "prep", "--why", "nothing to reshape")

    def map(self):
        code, out = self.repo.status("--map")
        self.assertEqual(code, 0, out)
        return out.splitlines()

    def everything(self):
        code, out = self.repo.status()
        self.assertEqual(code, 0, out)
        return out


class WhenThePlanHasStepsTests(MapCase):
    def setUp(self):
        super().setUp()
        self.plan()
        self.milestone("--step", "R4.1")
        self.milestone("--step", "R4.2", passes="prep,happy-path")

    def test_the_header_names_the_feature_repository_and_branch(self):
        self.assertEqual(self.map()[0], "test · origin (feat)")

    def test_lists_the_steps_in_order_marked_done_current_and_not_started(self):
        self.assertEqual(self.map()[1:], ["  [x] Step one", "  [>] Step two  <- the draft", "  [ ] Step three"])

    def test_an_open_handoff_on_the_current_steps_brief_says_what_is_happening(self):
        self.repo.build_ok("add", "Wire the reader", "--brief", "R5", "--reqs", "1")
        self.assertIn("  [>] Step two  <- the draft: Wire the reader", self.map())

    def test_a_step_built_by_a_record_entry_is_done(self):
        self.repo.build_ok("built", "R4.3", "--commit", self.repo.commit("feat: step three"))
        self.assertIn("  [x] Step three", self.map())

    def test_the_default_status_shows_the_same_map_right_after_its_heading(self):
        lines = self.map()
        self.assertEqual(self.everything().splitlines()[2 : 4 + len(lines)], ["```", *lines, "```"])


class WhenTheFeatureHasAnotherWorktreeTests(MapCase):
    def setUp(self):
        super().setUp()
        self.web = init_repo(self.path("web"), with_origin=False)
        self.web.git("checkout", "-q", "-b", "feat-web")
        table = "| Repo | Worktree |\n| --- | --- |\n" + f"| api | {self.repo.path} |\n| web | {self.web.path} |\n"
        write_file(paths.workspace(self.repo.path), table)

    def test_the_other_worktree_is_one_line_with_its_branch_and_step_progress(self):
        self.plan(PLAN_BODY + "4. web: Step four on the web. Done: when it renders.\n")
        self.assertEqual(self.map()[-1], "  web (feat-web): 0 of 1 step done")

    def test_steps_for_the_other_repository_are_left_out_here(self):
        self.plan(PLAN_BODY + "4. web: Step four on the web. Done: when it renders.\n")
        self.assertNotIn("Step four", "\n".join(self.map()[:-1]))

    def test_without_steps_of_its_own_the_other_worktree_shows_what_is_built(self):
        self.plan()
        self.assertEqual(self.map()[-1], "  web (feat-web): nothing built yet")

    def test_with_no_plan_the_map_still_shows_the_other_worktree(self):
        self.assertEqual(self.map(), ["test · api (feat)", "  web (feat-web): nothing built yet"])


class CountsLineTests(MapCase):
    def setUp(self):
        super().setUp()
        self.plan()

    def test_counts_the_follow_ups_owed_here_and_the_parked_ideas(self):
        add_followup(self.repo.path, "Send the export id")
        add_idea(self.repo.path, "Phone digits")
        add_idea(self.repo.path, "Retry on hangup")
        self.assertEqual(self.map()[-1], "  owed here: 1 follow-up · parked: 2 ideas")

    def test_leaves_out_a_part_that_is_zero(self):
        add_idea(self.repo.path, "Phone digits")
        self.assertEqual(self.map()[-1], "  parked: 1 idea")

    def test_is_left_out_when_both_are_zero(self):
        self.assertEqual(self.map()[-1], "  [ ] Step three")


class WhenThereIsNoPlanTests(MapCase):
    def setUp(self):
        super().setUp()
        write_record(self.repo.path, "R6", "pieces", "The pieces", body=PIECES_BODY)
        self.milestone("--brief", "R5", "--piece", "Export job")

    def test_lists_the_pieces_marked_by_their_milestones(self):
        self.assertEqual(self.map()[1:], ["  [x] Export job", "  [ ] Status endpoint"])


class WhenThereIsNothingToMapTests(MapCase):
    def test_the_map_prints_nothing(self):
        self.assertEqual(self.map(), [])

    def test_the_default_status_shows_no_map(self):
        self.assertNotIn("```", self.everything())


if __name__ == "__main__":
    unittest.main()

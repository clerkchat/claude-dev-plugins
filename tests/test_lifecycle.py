import os
import unittest

from helpers import RunCase, TempCase, init_repo, records, run_files, run_script, write_feature_md, write_file, write_record
import lifecycle
import paths

link = records.load_script("link-latest.py")
pr_posted = records.load_script("pr-posted.py")

BRIEF_BODY = "## Requirements\n\n1. One.\n2. Two.\n"
FINDING = "- id: {n}\n  lens: tests\n  severity: minor\n  file: a.py\n  line: 1\n  title: Finding {n}\n"
CHECK = """# Design check: R5 The brief

Checked 2026-11-17: R5.

- [ ] Q-1. Which store holds it?
  - Weight: settle-first
- [ ] Q-2. What is the name?
  - Weight: minor
"""
ONE_QUESTION_CHECK = "# Design check: R5 The brief\n\nChecked 2026-11-17: R5.\n\n- [ ] Q-1. Which store holds it?\n"
SETTLED_CHECK = "# Design check: R5 The brief\n\nChecked 2026-11-17: R5.\n\n- [x] Q-1. Which store holds it?\n"


def pass_entry(n, status, piece="R5", check=""):
    return f"- [ ] PASS-{n}. tests on {piece}\n  - Piece: {piece}\n  - Status: {status}\n" + (f"  - Check: {check}\n" if check else "")


class NoFeatureTests(TempCase):
    def test_prints_nothing_and_exits_zero(self):
        repo = init_repo(self.path("work"))
        self.assertEqual(run_script("lifecycle", repo.path), (0, ""))


class LifecycleCase(RunCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("work"))
        self.repo.git("checkout", "-q", "-b", "feat")
        write_feature_md(self.repo.path)
        write_record(self.repo.path, "R5", "brief", "The brief", body=BRIEF_BODY)

    def strip(self):
        return lifecycle.strip(self.repo.path)

    def handoff(self, reqs="1"):
        self.repo.build_ok("add", "Wire it", "--brief", "R5", "--reqs", reqs)

    def landed(self, reqs="1"):
        self.handoff(reqs)
        self.repo.build_ok("done", "BUILD-1", "--commit", self.repo.commit("feat: wire it"))

    def write_check(self, text=CHECK):
        write_file(os.path.join(paths.checks_dir(self.repo.path), "R5-1.md"), text)

    def write_passes(self, *entries):
        write_file(paths.passes(self.repo.path), "".join(entries))

    def write_run(self, label, queued=0, unmarked=0, previous=None):
        """A run with findings in Fix before merging: queued ones marked fix, then unmarked ones."""
        self.run_dir = paths.run(self.repo.path, label)
        found = range(1, queued + unmarked + 1)
        self.write_merged(*(FINDING.format(n=n) for n in found))
        self.write_numbers({n: "fix" for n in found})
        self.write_instructions({n: ("fix", "") for n in found if n <= queued})
        self.write_target("branch", self.repo.git("rev-parse", "main"), self.repo.git("rev-parse", "HEAD"))
        if previous:
            self.write("reconcile/previous.txt", previous + "\n")

    def review(self, label, queued=0, unmarked=0, previous=None):
        self.write_run(label, queued, unmarked, previous)
        link.link_latest(self.repo.path, self.run_dir)

    def milestone(self, *where):
        self.repo.build_ok("milestone", *where, "--passes", "prep")


class StageSignsTests(LifecycleCase):
    def test_records_alone_show_design_and_no_placeholder_for_later_stages(self):
        self.assertEqual(self.strip(), "test · design ✓")

    def test_a_feature_with_no_records_shows_only_its_name(self):
        os.remove(os.path.join(paths.records_dir(self.repo.path), "R5.md"))
        self.assertEqual(self.strip(), "test")

    def test_build_appears_once_a_handoff_is_logged(self):
        self.handoff()
        self.assertEqual(self.strip(), "test · design ✓ · build 0/2")

    def test_passes_appear_once_a_pass_is_logged(self):
        self.write_passes(pass_entry(1, "open"))
        self.assertEqual(self.strip(), "test · design ✓ · passes 0/1 checked")

    def test_an_abandoned_pass_is_no_sign(self):
        self.write_passes(pass_entry(1, "abandoned"))
        self.assertEqual(self.strip(), "test · design ✓")

    def test_review_appears_once_latest_names_a_merged_run(self):
        self.review("r1")
        self.assertEqual(self.strip(), "test · design ✓ · review ✓")

    def test_a_run_without_its_target_is_no_sign(self):
        self.review("r1")
        os.remove(os.path.join(self.run_dir, "target.txt"))
        self.assertEqual(self.strip(), "test · design ✓")

    def test_pr_appears_once_a_draft_exists(self):
        write_file(paths.pr_description(self.repo.path), "# The change\n")
        self.assertEqual(self.strip(), "test · design ✓ · PR drafted")


class DesignTests(LifecycleCase):
    def test_a_settled_check_shows_design_done(self):
        self.write_check(SETTLED_CHECK)
        self.assertEqual(self.strip(), "test · design ✓")

    def test_open_questions_name_the_settle_first_ones(self):
        self.write_check()
        self.assertEqual(self.strip(), "test · design · 2 questions open (1 settle-first)")

    def test_one_open_question_is_singular(self):
        self.write_check(ONE_QUESTION_CHECK)
        self.assertEqual(self.strip(), "test · design · 1 question open")

    def test_open_questions_ride_on_the_current_stage(self):
        self.write_check()
        self.handoff()
        self.assertEqual(self.strip(), "test · design · build 0/2 · 2 design questions open (1 settle-first)")


class BuildTests(LifecycleCase):
    def test_counts_requirements_done_over_counted(self):
        self.landed()
        self.assertEqual(self.strip(), "test · design ✓ · build 1/2")

    def test_every_requirement_done_shows_build_done(self):
        self.landed("1,2")
        self.assertEqual(self.strip(), "test · design ✓ · build ✓ 2/2")

    def test_a_stopped_handoff_rides_after_the_build_segment(self):
        self.handoff()
        self.repo.build_ok("stop", "BUILD-1", "--question", "Which store?")
        self.assertEqual(self.strip(), "test · design ✓ · build 0/2 · 1 handoff stopped")

    def test_handoffs_stopped_are_counted_in_the_plural(self):
        for title in ("Wire it", "Wire it too"):
            self.repo.build_ok("add", title, "--brief", "R5", "--reqs", "1")
        for build in ("BUILD-1", "BUILD-2"):
            self.repo.build_ok("stop", build, "--question", "Which store?")
        self.assertEqual(self.strip(), "test · design ✓ · build 0/2 · 2 handoffs stopped")

    def test_an_unreadable_log_shows_a_question_mark_and_exits_zero(self):
        write_file(paths.build_log(self.repo.path), "- junk\n")
        self.assertEqual(run_script("lifecycle", self.repo.path), (0, "test · design ✓ · build ?"))


class MilestoneTests(LifecycleCase):
    def test_a_milestone_under_way_names_its_plan_step(self):
        write_record(self.repo.path, "R4", "plan", "The plan", body="1. Step one, brief R5. Done: when it runs.\n2. Step two, brief R5. Done: when it reads.\n")
        self.milestone("--step", "R4.2")
        self.assertEqual(self.strip(), "test · design ✓ · build (milestone 2)")

    def test_a_milestone_without_a_plan_is_named_by_its_piece(self):
        self.milestone("--brief", "R5", "--piece", "Export job")
        self.assertEqual(self.strip(), "test · design ✓ · build (milestone Export job)")

    def test_a_milestone_whose_passes_are_through_is_not_named(self):
        self.milestone("--brief", "R5", "--piece", "Export job")
        self.repo.build_ok("skip", "MILE-1", "prep", "--why", "nothing to reshape")
        self.assertEqual(self.strip(), "test · design ✓ · build ✓")

    def test_its_passes_are_left_out_of_the_passes_segment(self):
        self.milestone("--brief", "R5", "--piece", "Export job")
        self.write_passes(pass_entry(1, "open"))
        self.assertEqual(self.strip(), "test · design ✓ · build (milestone Export job)")


class TwoWorktreesTests(LifecycleCase):
    def setUp(self):
        super().setUp()
        self.web = init_repo(self.path("web"), with_origin=False)
        self.web.git("checkout", "-q", "-b", "feat-web")
        write_record(self.repo.path, "R6", "brief", "The web brief", extra="repo: web\n", body=BRIEF_BODY)
        table = f"| Repo | Worktree |\n| --- | --- |\n| work | {self.repo.path} |\n| web | {self.web.path} |\n"
        write_file(paths.workspace(self.repo.path), table)
        write_file(paths.workspace(self.web.path), "Hub: work\n\n" + table)

    def test_the_build_count_sums_both_worktrees(self):
        self.landed()
        self.web.build_ok("add", "Render it", "--brief", "R6", "--reqs", "1")
        self.web.build_ok("done", "BUILD-1", "--commit", self.web.commit("feat: render it"))
        self.assertEqual(self.strip(), "test · design ✓ · build 2/4")


class PassesTests(LifecycleCase):
    def test_counts_checked_passes_over_those_not_abandoned(self):
        self.write_passes(pass_entry(1, "open"), pass_entry(2, "checked", check="pass-2; ran tests; tests 0"), pass_entry(3, "abandoned"))
        self.assertEqual(self.strip(), "test · design ✓ · passes 1/2 checked")

    def test_every_pass_checked_and_clean_shows_passes_done(self):
        self.write_passes(pass_entry(1, "checked", check="pass-1; ran tests; tests 0"))
        self.assertEqual(self.strip(), "test · design ✓ · passes ✓ 1/1 checked")

    def test_adds_the_open_findings_of_the_checked_runs(self):
        self.write_run("pass-1", unmarked=2)
        self.write_passes(pass_entry(1, "checked", check="pass-1; ran tests; tests 2"))
        self.assertEqual(self.strip(), "test · design ✓ · passes 1/1 checked · 2 open")

    def test_an_unreadable_log_shows_a_question_mark(self):
        self.write_passes("- junk\n")
        self.assertEqual(self.strip(), "test · design ✓ · passes ?")


class ReviewTests(LifecycleCase):
    def test_one_round_counts_open_findings_and_those_to_triage(self):
        self.review("r1", queued=3, unmarked=3)
        self.assertEqual(self.strip(), "test · design ✓ · review · 6 open (3 to triage)")

    def test_a_chained_run_is_the_next_round_with_an_arrow_from_the_last(self):
        self.write_run("r1", queued=6)
        self.review("r2", queued=2, previous="r1")
        self.assertEqual(self.strip(), "test · design ✓ · review round 2 · 6 → 2 open")

    def test_a_round_not_below_the_last_is_not_converging(self):
        self.write_run("r1", queued=4)
        self.review("r2", queued=4, previous="r1")
        self.assertEqual(self.strip(), "test · design ✓ · review round 2 · 4 → 4 open, not converging")

    def test_a_round_with_nothing_left_open_shows_review_done(self):
        self.write_run("r1", queued=4)
        self.review("r2", previous="r1")
        self.assertEqual(self.strip(), "test · design ✓ · review ✓ round 2 · 4 → 0 open")

    def test_a_run_named_by_label_is_read_in_place_of_latest(self):
        self.write_run("r1", queued=3)
        self.assertEqual(lifecycle.strip(self.repo.path, "r1"), "test · design ✓ · review · 3 open")

    def test_the_command_takes_the_run_label(self):
        self.write_run("r1", queued=3)
        self.assertEqual(run_script("lifecycle", self.repo.path, "--run", "r1"), (0, "test · design ✓ · review · 3 open"))

    def test_a_run_not_chained_is_a_round_of_its_own(self):
        self.write_run("r1", queued=6)
        self.review("r2", queued=2)
        self.assertEqual(self.strip(), "test · design ✓ · review · 2 open")

    def test_an_unreadable_merged_report_shows_a_question_mark(self):
        self.review("r1", queued=1)
        with open(os.path.join(self.run_dir, "merged.md"), "wb") as f:
            f.write(b"\xff\xfe")
        self.assertEqual(self.strip(), "test · design ✓ · review ?")

    def test_an_unreadable_report_in_the_chain_shows_a_question_mark(self):
        self.write_run("r1", queued=1)
        with open(os.path.join(self.run_dir, "merged.md"), "wb") as f:
            f.write(b"\xff\xfe")
        self.review("r2", queued=1, previous="r1")
        self.assertEqual(self.strip(), "test · design ✓ · review ?")

    def test_a_chain_that_loops_stops_at_the_first_repeat(self):
        self.write_run("r1", queued=2)
        self.review("r2", queued=1, previous="r2")
        self.assertEqual(self.strip(), "test · design ✓ · review · 1 open")

    def test_a_chain_whose_earlier_run_was_deleted_stops_there(self):
        self.review("r2", queued=1, previous="r1")
        self.assertEqual(self.strip(), "test · design ✓ · review · 1 open")


class PullRequestTests(LifecycleCase):
    def setUp(self):
        super().setUp()
        self.repo.commit("feat: the change")
        write_file(paths.pr_description(self.repo.path), "# The change\n")

    def test_a_posted_pull_request_says_posted(self):
        pr_posted.record(self.repo.path, 42, "https://github.com/clerk/api/pull/42")
        self.assertEqual(self.strip(), "test · design ✓ · PR posted")

    def test_imported_approvals_say_approved(self):
        self.review("r1")
        run_files.write_approvals(self.run_dir, {7: {"author": "bob", "date": "2026-11-17"}})
        self.assertEqual(self.strip(), "test · design ✓ · review ✓ · PR approved")

    def test_approvals_outrank_a_posted_pull_request(self):
        self.review("r1")
        pr_posted.record(self.repo.path, 42, "https://github.com/clerk/api/pull/42")
        run_files.write_approvals(self.run_dir, {7: {"author": "bob", "date": "2026-11-17"}})
        self.assertEqual(self.strip(), "test · design ✓ · review ✓ · PR approved")

    def test_unreadable_approvals_leave_the_strip_standing(self):
        self.review("r1")
        path = run_files.approvals_path(self.run_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"\xff\xfe")
        self.assertEqual(self.strip(), "test · design ✓ · review ✓ · PR drafted")

    def test_a_branch_merged_into_the_remote_main_says_merged(self):
        self.landed("1,2")
        self.repo.squash_merge()
        self.repo.reset_to_origin()
        self.assertEqual(self.strip(), "test · design ✓ · build ✓ 2/2 · PR merged")


class StatusFirstLineTests(LifecycleCase):
    def setUp(self):
        super().setUp()
        self.handoff()

    def test_every_view_starts_with_the_strip(self):
        for view in ((), ("--map",), ("--focus", "design"), ("--focus", "implementation"), ("--focus", "review"), ("--focus", "blockers"), ("--area", "R5")):
            with self.subTest(view=view):
                code, out = self.repo.status(*view)
                self.assertEqual((code, out.splitlines()[0]), (0, "test · design ✓ · build 0/2"))


if __name__ == "__main__":
    unittest.main()

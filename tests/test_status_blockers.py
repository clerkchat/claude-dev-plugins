import datetime
import os
import unittest

from helpers import RunCase, add_backlog_item, drop_backlog_title, init_repo, run_ok, run_script, write_feature_md, write_file, write_record

CHECK = """# Design check: R5 Spec five

Checked 2026-10-21: R5.

- [ ] Q-1. Which store holds it?
  - Weight: settle-first
- [ ] Q-2. What is the name?
  - Weight: minor
"""

FINDING = "- id: {n}\n  lens: tests\n  severity: minor\n  file: a.py\n  line: 1\n  title: Finding {n}\n"

SEEN = "status-seen-backlog"


class BlockersCase(RunCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("work"))
        self.repo.git("checkout", "-q", "-b", "feat")
        self.run_dir = os.path.join(self.repo.path, ".clerk-dev", "latest")
        write_feature_md(self.repo.path)
        write_record(self.repo.path, "R5", "spec", "Spec five", body="## Requirements\n\n1. One.\n\n## Baseline\n\nClean.")

    def blockers(self):
        code, out = self.repo.status("--focus", "blockers")
        self.assertEqual(code, 0, out)
        return out

    def write_check(self):
        checks = os.path.join(self.repo.path, ".clerk-dev", "feature", "checks")
        os.makedirs(checks, exist_ok=True)
        with open(os.path.join(checks, "R5-1.md"), "w") as f:
            f.write(CHECK)

    def write_run(self, sections, instructions=(), statuses=()):
        self.write_merged(*(FINDING.format(n=n) for n in sections))
        self.write_target("branch", self.repo.git("rev-parse", "main"), self.repo.git("rev-parse", "HEAD"))
        self.write_numbers(sections)
        self.write_instructions({n: (c, "") for n, c in instructions})
        self.write_status({n: (s, "abc") for n, s in statuses})


class BlockersTests(BlockersCase):
    def test_nothing_blocking(self):
        out = self.blockers()
        self.assertIn("## What blocks", out)
        self.assertIn("Nothing blocking.", out)
        self.assertNotIn("**Next:**", out)

    def test_a_stopped_handoff_appears_with_its_question(self):
        self.repo.build_ok("add", "Five piece", "--spec", "R5", "--reqs", "1")
        self.repo.build_ok("stop", "BUILD-1", "--question", "Which store holds it?")
        out = self.blockers()
        self.assertIn("**Handoffs stopped on a question:**", out)
        self.assertIn("BUILD-1", out)
        self.assertIn("Which store holds it?", out)
        self.assertNotIn("Nothing blocking.", out)
        self.assertIn("1. Answer the question of the stopped handoff", out)

    def test_a_settle_first_question_appears_and_another_does_not(self):
        self.write_check()
        out = self.blockers()
        self.assertIn("**Settle-first design questions:**", out)
        self.assertIn("- BRIEF-5-1 (design check of BRIEF-5): BRIEF-5-1.Q-1", out)
        self.assertNotIn("BRIEF-5 (brief", out)
        self.assertNotIn("Q-2", out)
        self.assertIn("walk the design questions", out)

    def test_an_open_follow_up_appears_and_status_seen_is_not_written(self):
        add_backlog_item(self.repo.path, "followup", "Send exportId back", "--origin", "api abc1234")
        out = self.blockers()
        self.assertIn("**Follow-ups owed here:**", out)
        self.assertIn("Send exportId back", out)
        self.assertIn("go through the follow-ups", out)
        self.assertFalse(os.path.exists(os.path.join(self.repo.path, ".clerk-dev", SEEN)))

    def test_a_fix_section_finding_appears_whatever_its_mark_and_a_closed_one_does_not(self):
        self.write_run(
            {1: "fix", 2: "fix", 3: "fix", 4: "look"},
            instructions=[(2, "fix"), (3, "ignore")],
        )
        out = self.blockers()
        self.assertIn("**Findings to fix before merging:** 2 (1, 2)", out)
        self.assertIn("work the queue", out)

    def test_a_fixed_finding_does_not_appear(self):
        self.write_run({1: "fix"}, statuses=[(1, "fixed")])
        self.assertIn("Nothing blocking.", self.blockers())

    def test_other_sections_do_not_block(self):
        self.write_run({1: "look", 2: "debt"})
        self.assertIn("Nothing blocking.", self.blockers())


def workspace_md(*rows):
    return "| Repo | Worktree |\n| --- | --- |\n" + "".join(f"| {name} | {path} |\n" for name, path in rows)


class BacklogStatusCase(BlockersCase):
    def setUp(self):
        super().setUp()
        self.write_workspace(("api", self.repo.path))
        self.today = datetime.date.today().isoformat()

    def write_workspace(self, *rows):
        write_file(os.path.join(self.repo.path, ".clerk-dev", "workspace.md"), workspace_md(*rows))

    def add(self, kind, title, *extra):
        return add_backlog_item(self.repo.path, kind, title, *extra)

    def followup(self, title="Send exportId back", *extra):
        return self.add("followup", title, "--origin", "web abc1234", *extra)

    def idea(self, title="Phone digits", *extra):
        return self.add("idea", title, *extra)

    def backlog(self, *args):
        return run_ok("backlog", args[0], self.repo.path, *args[1:])

    def full_status(self):
        code, out = self.repo.status()
        self.assertEqual(code, 0, out)
        return out

    def marking_status(self):
        return run_ok("status", self.repo.path)

    def seen_path(self, name=SEEN):
        return os.path.join(self.repo.path, ".clerk-dev", name)

    def seen(self, name=SEEN):
        with open(self.seen_path(name)) as f:
            return f.read()

    def write_seen(self, text, name=SEEN):
        write_file(self.seen_path(name), text)

    def detach(self, repo=None):
        (repo or self.repo).git("checkout", "-q", "--detach")


class FollowUpsOwedHereTests(BacklogStatusCase):
    def test_an_owed_follow_up_shows_its_id_title_and_origin(self):
        self.followup()
        self.assertIn("- BL-1: Send exportId back (web abc1234)", self.full_status())

    def test_a_done_follow_up_is_counted_not_listed(self):
        self.followup()
        self.backlog("set", "BL-1", "done", "--ref", "1a2b3c4")
        self.assertIn("**Follow-ups owed here:** none open (1 done).", self.full_status())

    def test_a_follow_up_for_new_work_is_not_owed_here(self):
        self.followup("Later", "--scope", "new")
        self.assertIn("**Follow-ups owed here:** none.", self.full_status())

    def test_an_idea_is_not_a_follow_up(self):
        self.idea()
        self.assertIn("**Follow-ups owed here:** none.", self.full_status())

    def test_a_follow_up_with_no_title_line_is_still_counted(self):
        self.followup()
        drop_backlog_title(self.repo.path, "BL-1")
        self.assertIn("**Follow-ups owed here:** 1 open.\n- BL-1 (follow-up (owed)):  (web abc1234)", self.full_status())


class StatusSeenTests(BacklogStatusCase):
    def setUp(self):
        super().setUp()
        self.followup()
        self.followup("Second")

    def test_a_status_writes_the_highest_id_of_each_backlog_it_read(self):
        self.marking_status()
        self.assertEqual(self.seen(), "api 2\n")

    def test_no_mark_leaves_it_untouched(self):
        self.full_status()
        self.assertFalse(os.path.exists(self.seen_path()))

    def test_the_old_status_seen_file_is_left_as_it_was(self):
        self.write_seen("5\n", "status-seen")
        self.marking_status()
        self.assertEqual(self.seen("status-seen"), "5\n")

    def test_the_old_status_seen_file_tags_nothing_new(self):
        self.write_seen("1\n", "status-seen")
        self.assertNotIn("(new)", self.full_status())

    def test_the_lines_of_other_backlogs_are_kept(self):
        self.write_seen("web 9\n")
        self.marking_status()
        self.assertEqual(self.seen(), "api 2\nweb 9\n")


class WhenTheLastStatusSawTheFirstFollowUpTests(BacklogStatusCase):
    def setUp(self):
        super().setUp()
        self.followup()
        self.write_seen("api 1\n")
        self.followup("Second")

    def test_the_later_one_is_tagged_new(self):
        self.assertIn("- BL-2: Second (web abc1234) (new)", self.full_status())

    def test_the_count_says_how_many_are_new(self):
        self.assertIn("**Follow-ups owed here:** 2 open, 1 new since the last status.", self.full_status())


class WhenTheNewestItemIsNotAFollowUpOwedHereTests(BacklogStatusCase):
    def setUp(self):
        super().setUp()
        self.followup()
        self.idea()

    def test_a_status_marks_only_the_follow_up_it_showed(self):
        self.marking_status()
        self.assertEqual(self.seen(), "api 1\n")


class WhenTheLastStatusShowedNoFollowUpTests(BacklogStatusCase):
    def setUp(self):
        super().setUp()
        self.idea()
        self.marking_status()
        self.followup()

    def test_the_first_follow_up_is_tagged_new(self):
        self.assertIn("- BL-2: Send exportId back (web abc1234) (new)", self.full_status())


class WhenHeadIsDetachedTests(BacklogStatusCase):
    def setUp(self):
        super().setUp()
        self.followup()
        self.write_seen("api 0\n")
        self.detach()

    def test_says_the_follow_ups_owed_here_are_not_shown(self):
        self.assertIn("\nHEAD is detached; follow-ups owed here not shown.\n", self.full_status())

    def test_does_not_say_none_are_owed(self):
        self.assertNotIn("**Follow-ups owed here:**", self.full_status())

    def test_a_status_leaves_the_seen_marks_as_they_were(self):
        self.marking_status()
        self.assertEqual(self.seen(), "api 0\n")

    def test_blockers_say_the_follow_ups_are_not_shown(self):
        self.assertIn("HEAD is detached; follow-ups owed here not shown.", self.blockers())

    def test_blockers_do_not_say_nothing_is_blocking(self):
        self.assertNotIn("Nothing blocking.", self.blockers())


class RelatedWorktreeCase(BacklogStatusCase):
    def setUp(self):
        super().setUp()
        self.web = init_repo(self.path("web"), with_origin=False)
        self.web.git("checkout", "-q", "-b", "feat/web")
        self.write_workspace(("api", self.repo.path), ("web", self.web.path))
        add_backlog_item(self.web.path, "followup", "Accept exportId", "--origin", "api abc1234")
        add_backlog_item(self.web.path, "followup", "Accept the new header", "--origin", "worker 7c1e2ab")


class RelatedWorktreeTests(RelatedWorktreeCase):
    def test_counts_their_open_follow_ups_and_those_this_repository_asked_for(self):
        self.assertIn("**Follow-ups owed by related worktrees:** web 2 open (1 from api).", self.full_status())


class WhenTheRelatedWorktreeIsDetachedTests(RelatedWorktreeCase):
    def setUp(self):
        super().setUp()
        self.detach(self.web)

    def test_says_its_follow_ups_are_not_shown(self):
        self.assertIn("**Follow-ups owed by related worktrees:** web not shown (HEAD is detached).", self.full_status())


class SetupTests(BlockersCase):
    def test_a_follow_ups_origin_asks_for_a_workspace_row(self):
        add_backlog_item(self.repo.path, "followup", "Send exportId back", "--origin", "web abc1234")
        code, out = self.repo.status("--setup")
        self.assertIn("name web but there is no review workspace", out)


class PreflightTests(BlockersCase):
    def test_counts_the_follow_ups_owed_on_this_branch(self):
        add_backlog_item(self.repo.path, "followup", "Send exportId back", "--origin", "web abc1234")
        add_backlog_item(self.repo.path, "followup", "Later", "--origin", "web abc1234", "--scope", "new")
        self.assertIn("- Open follow-ups: 1", run_ok("preflight", self.repo.path))


class ParkedIdeasTests(BacklogStatusCase):
    def setUp(self):
        super().setUp()
        write_record(self.repo.path, "R6", "decision", "Delivery", extra="area: delivery\n", body="## Decision\n\nPoll.")
        self.idea("Phone digits", "--area", "delivery", "--when", "after launch")
        self.idea("Fuzzy names")
        self.idea("New work", "--scope", "new")

    def view(self, *args):
        code, out = self.repo.status(*args)
        self.assertEqual(code, 0, out)
        return out

    def test_the_feature_view_counts_them_by_area(self):
        self.assertIn("**Parked ideas:** 2 (delivery: 1; feature-wide: 1)", self.view("--focus", "design"))

    def test_the_area_view_lists_the_areas_ideas_with_their_when(self):
        out = self.view("--area", "delivery")
        self.assertIn("**Parked ideas:** 1\n- BL-1: Phone digits When: after launch.", out)

    def test_the_area_view_lists_an_idea_with_no_title_line_by_its_id(self):
        drop_backlog_title(self.repo.path, "BL-1")
        self.assertIn("**Parked ideas:** 1\n- BL-1 (idea (open)):  When: after launch.", self.view("--area", "delivery"))

    def test_an_adopted_idea_is_no_longer_parked(self):
        self.backlog("set", "BL-1", "adopted", "--ref", "DEC-6")
        self.assertIn("**Parked ideas:** 1 (feature-wide: 1)", self.view("--focus", "design"))


class BacklogBlockTests(BacklogStatusCase):
    def test_absent_when_the_backlog_is_empty(self):
        self.assertNotIn("**Backlog:**", self.full_status())

    def test_counts_the_open_items_by_kind(self):
        self.idea()
        self.add("cleanup", "Drop v1", "--trigger", "all clients on v2")
        self.followup()
        self.assertIn("**Backlog:** 3 open (1 idea, 1 cleanup, 1 follow-up).", self.full_status())

    def test_lists_the_oldest_three_open_items(self):
        for title in ("First", "Second", "Third", "Fourth"):
            self.idea(title)
        out = self.full_status()
        self.assertIn(f"- oldest: BL-3: Third (idea, since {self.today})", out)
        self.assertNotIn("- oldest: BL-4", out)


class WithAnOrphanTests(BacklogStatusCase):
    def setUp(self):
        super().setUp()
        self.repo.git("branch", "-q", "spike/gone")
        self.idea("Will be orphaned", "--scope", "spike/gone")
        self.repo.git("branch", "-q", "-D", "spike/gone")

    def test_names_it_with_its_gone_branch(self):
        self.assertIn("- orphaned: BL-1: Will be orphaned (idea, from spike/gone, branch gone)", self.full_status())

    def test_offers_to_rescope_or_drop_it(self):
        self.assertIn("Rescope the orphaned item BL-1 to new work, or drop it with a reason.", self.full_status())


class WithACleanupWhoseCodeIsGoneTests(BacklogStatusCase):
    def setUp(self):
        super().setUp()
        self.add("cleanup", "Remove the flag", "--scope", "new", "--removes", "EXPORT_V2_FLAG")

    def test_names_it_as_gone_from_origin_main(self):
        self.assertIn("- gone: BL-1: Remove the flag (cleanup, EXPORT_V2_FLAG is gone from origin/main)", self.full_status())

    def test_shows_the_last_fetch(self):
        self.assertRegex(self.full_status(), r"\n- last fetch: \d{4}-\d{2}-\d{2} ")

    def test_offers_to_mark_it_done(self):
        self.assertIn("Mark the cleanup BL-1 done: its code is gone from origin/main.", self.full_status())

    def test_one_whose_code_is_still_on_origin_main_is_not_listed(self):
        self.repo.main_moves("EXPORT_V2_FLAG = true", rebase=False)
        self.assertNotIn("- gone:", self.full_status())


class WithAFollowUpForNewWorkTests(BacklogStatusCase):
    def setUp(self):
        super().setUp()
        self.followup("Send exportId back", "--scope", "new")

    def test_lists_it_as_one_this_branch_could_take_up(self):
        self.assertIn("- could take up here: BL-1: Send exportId back (follow-up, new work, web abc1234)", self.full_status())

    def test_offers_to_rescope_it_here(self):
        self.assertIn("Take up the follow-up BL-1 on this branch by rescoping it to feat, or leave it for later.", self.full_status())


class WithACleanupAndNoRemoteMainTests(BacklogStatusCase):
    def setUp(self):
        super().setUp()
        self.repo.git("remote", "remove", "origin")
        self.add("cleanup", "Remove the flag", "--scope", "new", "--removes", "EXPORT_V2_FLAG")

    def test_status_still_succeeds(self):
        self.assertEqual(self.repo.status()[0], 0)

    def test_says_once_that_cleanups_were_not_checked(self):
        unchecked = [l for l in self.full_status().splitlines() if l.startswith("- cleanups not checked: ")]
        self.assertEqual(len(unchecked), 1)


POSTED_HEADER = "merged_id\tstate\tnote\tdate\tthread_id\tcomment_id\turl\tpath\tline\tend_line\tside\tkind\treview_id\n"


class PostQueueCase(BlockersCase):
    def setUp(self):
        super().setUp()
        self.write_run({1: "look", 2: "look", 3: "look", 4: "look"}, instructions=[(n, "post") for n in (1, 2, 3, 4)])

    def write_posted(self, rows, notes=None):
        self.write("posted.tsv", POSTED_HEADER + "".join(f"{n}\t{state}\t{(notes or {}).get(n, '')}\t\t\t\t\ta.py\t1\t1\tRIGHT\t{kind}\t\n"
                                                         for n, state, kind in rows))

    def full_status(self):
        code, out = self.repo.status()
        self.assertEqual(code, 0, out)
        return out


class PostQueueTests(PostQueueCase):
    def test_without_posted_tsv_every_post_finding_is_queued(self):
        out = self.full_status()
        self.assertIn("marked to post, not yet posted or changed since posting: 4 (1, 2, 3, 4)", out)
        self.assertIn('"post the review"', out)

    def test_only_drafted_and_edited_findings_are_queued(self):
        self.write_posted([(1, "drafted", ""), (2, "posted", "inline"), (3, "edited", "inline")])
        out = self.full_status()
        self.assertIn("marked to post, not yet posted or changed since posting: 3 (1, 3, 4)", out)

    def test_a_posted_finding_whose_note_changed_is_queued(self):
        self.write_posted([(n, "posted", "inline") for n in (1, 2, 3, 4)], notes={2: "an earlier note"})
        out = self.full_status()
        self.assertIn("marked to post, not yet posted or changed since posting: 1 (2)", out)

    def test_all_posted_and_unchanged_lists_nothing(self):
        self.write_posted([(n, "posted", "inline") for n in (1, 2, 3, 4)])
        out = self.full_status()
        self.assertNotIn("marked to post", out)
        self.assertNotIn("post the review", out)

    def test_a_run_with_no_post_marks_is_unchanged(self):
        self.write_run({1: "look"}, instructions=[(1, "fix")])
        out = self.full_status()
        self.assertNotIn("marked to post", out)
        self.assertNotIn("post the review", out)


class WhenAFindingIgnoredEarlierIsMarkedPostTest(PostQueueCase):
    def setUp(self):
        super().setUp()
        self.write_status({4: ("wont-fix", "")})

    def test_it_is_still_queued(self):
        self.assertIn("marked to post, not yet posted or changed since posting: 4 (1, 2, 3, 4)", self.full_status())


class CloseStepTests(PostQueueCase):
    def setUp(self):
        super().setUp()
        self.write("posted.tsv", POSTED_HEADER + "".join(f"{n}\tposted\tinline\t\tT{n}\t{n}\t\ta.py\t1\t1\tRIGHT\tline\t\n" for n in (1, 2, 3, 4)))
        self.write_status({1: ("fixed", "abc"), 2: ("fixed", "abc")})
        self.write("pr/threads.tsv", "merged_id\tcomment_id\tthread_id\tstate\toutdated\tcan_resolve\tline\treplies\tdate\tby_viewer\n"
                   "1\t1\tT1\topen\t0\t1\t1\t\td\t1\n2\t2\tT2\tresolved\t0\t1\t1\t\td\t1\n")

    def test_names_the_fixed_findings_with_an_open_thread(self):
        self.assertIn("Close the posted thread of finding 1; see Closing posted threads in the `review` skill.", self.full_status())

    def test_names_nothing_when_no_thread_is_open(self):
        self.write("pr/threads.tsv", "merged_id\tcomment_id\tthread_id\tstate\toutdated\tcan_resolve\tline\treplies\tdate\n")
        self.assertNotIn("Close the posted thread", self.full_status())


class CreditsInStatusTests(PostQueueCase):
    CREDIT = "- id: 5\n  lens: credit\n  file: a.py\n  line: 1\n  title: Credit 5\n  claim: Guards it.\n"

    def setUp(self):
        super().setUp()
        self.write_merged(*(FINDING.format(n=n) for n in (1, 2, 3, 4)), self.CREDIT)
        self.write_numbers({1: "look", 2: "look", 3: "look", 4: "look", 5: "credit"})
        self.write_instructions({n: ("post", "") for n in (1, 2, 3, 4, 5)})

    def test_a_post_marked_credit_is_queued_to_post(self):
        self.assertIn("marked to post, not yet posted or changed since posting: 5 (1, 2, 3, 4, 5)", self.full_status())

    def test_a_credit_is_not_counted_as_a_finding(self):
        self.assertIn("**Findings:** 4 in the report", self.full_status())

    def test_a_credit_only_post_mark_prompts_to_post(self):
        self.write_instructions({5: ("post", "")})
        self.assertIn('"post the review"', self.full_status())

    def test_a_posted_credit_is_not_queued(self):
        self.write_posted([(n, "posted", "inline") for n in (1, 2, 3, 4, 5)])
        self.assertNotIn("marked to post", self.full_status())


if __name__ == "__main__":
    unittest.main()

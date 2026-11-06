import os
import unittest

from helpers import RunCase, init_repo, run_script, write_feature_md, write_record

CHECK = """# Design check: R5 Spec five

Checked 2026-10-21: R5.

- [ ] Q-1. Which store holds it?
  - Weight: settle-first
- [ ] Q-2. What is the name?
  - Weight: minor
"""

FINDING = "- id: {n}\n  lens: tests\n  severity: minor\n  file: a.py\n  line: 1\n  title: Finding {n}\n"


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
        code, out = run_script("followups", "add", self.repo.path, "Send exportId back", "--from", "api abc1234",
                               "--contract", "changed: POST /exports: now returns exportId")
        self.assertEqual(code, 0, out)
        out = self.blockers()
        self.assertIn("**Follow-ups owed here:**", out)
        self.assertIn("Send exportId back", out)
        self.assertIn("go through the follow-ups", out)
        self.assertFalse(os.path.exists(os.path.join(self.repo.path, ".clerk-dev", "status-seen")))

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


class CloseStepTests(PostQueueCase):
    def setUp(self):
        super().setUp()
        self.write("posted.tsv", POSTED_HEADER + "".join(f"{n}\tposted\tinline\t\tT{n}\t{n}\t\ta.py\t1\t1\tRIGHT\tline\t\n" for n in (1, 2, 3, 4)))
        self.write_status({1: ("fixed", "abc"), 2: ("fixed", "abc")})
        self.write("pr/threads.tsv", "merged_id\tcomment_id\tthread_id\tstate\toutdated\tcan_resolve\tline\treplies\tdate\n"
                   "1\t1\tT1\topen\t0\t1\t1\t\td\n2\t2\tT2\tresolved\t0\t1\t1\t\td\n")

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

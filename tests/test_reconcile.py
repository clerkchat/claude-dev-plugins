import os
import sys
import unittest

from helpers import SCRIPTS, RunCase, defect, merged_md, run_ok, write_file

sys.path.insert(0, SCRIPTS)
import run_files


def posted_row(comment_id, kind="line"):
    return {"state": "posted", "kind": kind, "comment_id": str(comment_id), "thread_id": f"T{comment_id}", "path": "a.py", "line": "3"}


class TwoRunsCase(RunCase):
    def setUp(self):
        super().setUp()
        self.prev, self.cur = self.run_dir, self.path("cur")
        self.write_merged(defect(7, "a.py"), defect(8, "b.py"))
        self.write_numbers({7: "fix", 8: "fix"})
        write_file(os.path.join(self.cur, "merged.md"), merged_md(defect(1, "a.py"), defect(2, "c.py")))
        write_file(os.path.join(self.cur, "reconcile", "matches.tsv"),
                   "cur_id\tprev_id\thow\tprev_number\tprev_status\tprev_ref\n1\t7\tline\t7\topen\t\n")


class SeedCase(TwoRunsCase):
    def post(self, rows):
        run_files.write_posted(self.prev, rows)
        for mid in rows: self.write(f"posted/{mid}.md", f"Posted text of {mid}.\n")

    def seed(self):
        return run_ok("reconcile", self.prev, self.cur, "--seed")

    def match_as(self, how):
        write_file(os.path.join(self.cur, "reconcile", "matches.tsv"),
                   f"cur_id\tprev_id\thow\tprev_number\tprev_status\tprev_ref\n1\t7\t{how}\t7\topen\t\n")

    def cur_text(self, name):
        with open(os.path.join(self.cur, name), encoding="utf-8") as f:
            return f.read()


class SeedStatusTest(SeedCase):
    def match(self, prev_status, prev_ref="reason"):
        write_file(os.path.join(self.cur, "reconcile", "matches.tsv"),
                   "cur_id\tprev_id\thow\tprev_number\tprev_status\tprev_ref\n"
                   f"1\t7\tline\t7\t{prev_status}\t{prev_ref}\n")

    def seeded_status(self):
        self.seed()
        return run_files.read_status(self.cur).get(1)

    def test_carries_a_wont_fix_status_and_its_reason(self):
        self.match("wont-fix")
        self.assertEqual(self.seeded_status(), {"status": "wont-fix", "ref": "reason", "date": ""})

    def test_does_not_carry_a_fixed_status(self):
        self.match("fixed", "abc1234")
        self.assertIsNone(self.seeded_status())

    def test_keeps_a_status_the_current_run_already_has(self):
        self.match("wont-fix")
        self.write_cur_status({1: ("in-progress", "")})
        self.assertEqual(self.seeded_status()["status"], "in-progress")

    def write_cur_status(self, rows):
        run_files.write_status(self.cur, {m: {"status": s, "ref": r, "date": ""} for m, (s, r) in rows.items()})


class SeedResolutionTest(SeedCase):
    def test_copies_the_resolution_text_under_the_current_id_naming_the_review_it_came_from(self):
        self.write("resolution/7.md", "Handled upstream.\n")
        self.seed()
        self.assertEqual(self.cur_text("resolution/1.md"), f"From the review in {os.path.basename(self.prev)}:\n\nHandled upstream.\n")


class SeedWithoutPostedTest(SeedCase):
    def test_writes_no_posted_file(self):
        self.seed()
        self.assertFalse(os.path.exists(os.path.join(self.cur, "posted.tsv")))


class SeedPostedTest(SeedCase):
    def setUp(self):
        super().setUp()
        self.post({7: posted_row(5), 8: posted_row(6)})
        self.out = self.seed()

    def test_re_keys_the_posted_row_to_the_current_id(self):
        self.assertEqual(run_files.read_posted(self.cur)[1]["comment_id"], "5")

    def test_copies_the_posted_text_under_the_current_id(self):
        self.assertEqual(self.cur_text("posted/1.md"), "Posted text of 7.\n")

    def test_leaves_an_unmatched_posted_finding_out(self):
        self.assertEqual(list(run_files.read_posted(self.cur)), [1])

    def test_counts_the_seeded_posted_findings(self):
        self.assertIn("seeded 0 statuses and 1 posted findings from", self.out)

    def test_names_the_posted_findings_not_found_again(self):
        self.assertIn("; 1 posted findings not found again (finding 8); their threads come in as pull request comments", self.out)


def other_defect(mid, path):
    return (f"- id: {mid}\n  lens: correctness\n  severity: major\n  confidence: 90\n  file: {path}\n  line: 5\n"
            f"  claim: Finding {mid} leaks a handle in the retry loop.\n  impact: It matters.\n  fix: Close it.\n")


class SeedOtherFindingCase(SeedCase):
    def setUp(self):
        super().setUp()
        write_file(os.path.join(self.cur, "merged.md"), merged_md(other_defect(1, "a.py"), defect(2, "c.py")))
        self.post({7: posted_row(5)})
        self.write("posted/close-7.md", "Thanks, that does it.\n")


class SeedLooseLineMatchTest(SeedOtherFindingCase):
    def setUp(self):
        super().setUp()
        self.out = self.seed()

    def test_carries_no_posted_row(self):
        self.assertFalse(os.path.exists(os.path.join(self.cur, "posted.tsv")))

    def test_copies_no_posted_text(self):
        self.assertFalse(os.path.exists(os.path.join(self.cur, "posted", "1.md")))

    def test_copies_no_closing_reply(self):
        self.assertFalse(os.path.exists(os.path.join(self.cur, "posted", "close-1.md")))

    def test_names_the_posted_finding_left_behind(self):
        self.assertIn("; 1 posted findings matched only loosely, so their postings were not carried (finding 7 with #1); "
                      "their threads come in as pull request comments", self.out)


class SeedJudgedMatchTest(SeedOtherFindingCase):
    def test_carries_the_posted_row(self):
        self.match_as("judge")
        self.seed()
        self.assertEqual(run_files.read_posted(self.cur)[1]["comment_id"], "5")


class SeedTextMatchTest(SeedCase):
    def test_carries_no_posted_row(self):
        self.post({7: posted_row(5)})
        self.match_as("text")
        self.seed()
        self.assertFalse(os.path.exists(os.path.join(self.cur, "posted.tsv")))


class SeedPendingReviewTest(SeedCase):
    def setUp(self):
        super().setUp()
        self.post({7: {**posted_row(5), "review_id": "55"}})
        self.write("posted/pending-55.md", "My summary.\n")
        self.write("posted/review.md", "Nice work.\n")

    def test_copies_the_text_kept_from_the_pending_review(self):
        self.seed()
        self.assertEqual(self.cur_text("posted/pending-55.md"), "My summary.\n")

    def test_copies_the_review_body(self):
        self.seed()
        self.assertEqual(self.cur_text("posted/review.md"), "Nice work.\n")

    def test_keeps_a_review_body_the_current_run_already_has(self):
        write_file(os.path.join(self.cur, "posted", "review.md"), "Current body.\n")
        self.seed()
        self.assertEqual(self.cur_text("posted/review.md"), "Current body.\n")


class SeedWithoutAReviewTest(SeedCase):
    def test_copies_no_review_body(self):
        self.post({7: posted_row(5)})
        self.write("posted/review.md", "Nice work.\n")
        self.seed()
        self.assertFalse(os.path.exists(os.path.join(self.cur, "posted", "review.md")))


class SeedUnnumberedPostingTest(SeedCase):
    def test_names_a_lost_posting_without_a_number_by_its_merged_id(self):
        self.post({9: posted_row(6)})
        self.assertIn("1 posted findings not found again (#9)", self.seed())


class SeedOverACurrentPostingTest(SeedCase):
    def setUp(self):
        super().setUp()
        self.post({7: posted_row(5)})
        run_files.write_posted(self.cur, {1: posted_row(9)})
        write_file(os.path.join(self.cur, "posted", "1.md"), "Current text.\n")
        self.seed()

    def test_keeps_the_current_row(self):
        self.assertEqual(run_files.read_posted(self.cur)[1]["comment_id"], "9")

    def test_keeps_the_current_text(self):
        self.assertEqual(self.cur_text("posted/1.md"), "Current text.\n")


class SeedUnmatchedBodyPostingTest(SeedCase):
    def test_does_not_name_a_body_posting_as_lost(self):
        self.post({8: posted_row("", kind="body")})
        self.assertNotIn("not found again", self.seed())


class KeptOpenPostingCase(SeedCase):
    KEPT = {"reason": "waiting on author", "date": "2026-11-05"}

    def post_kept_open(self, mid):
        self.post({mid: posted_row(5)})
        run_files.write_kept_open(self.prev, {mid: self.KEPT})
        self.write(f"posted/close-{mid}.md", "Thanks, that does it.\n")


class SeedKeptOpenPostingTest(KeptOpenPostingCase):
    def setUp(self):
        super().setUp()
        self.post_kept_open(7)
        self.seed()

    def test_re_keys_the_kept_open_row_to_the_current_id(self):
        self.assertEqual(run_files.read_kept_open(self.cur), {1: self.KEPT})

    def test_copies_the_closing_reply_under_the_current_id(self):
        self.assertEqual(self.cur_text("posted/close-1.md"), "Thanks, that does it.\n")


class AppendRecheckCase(KeptOpenPostingCase):
    def setUp(self):
        super().setUp()
        self.post_kept_open(8)
        self.new = self.path("rechecked.md")
        write_file(self.new, merged_md(defect(8, "b.py")))
        write_file(self.path("judged.tsv"), "new_id\tcarried_id\tverdict\n")

    def append(self, *prev):
        run_ok("reconcile", *prev, self.cur, "--append", self.new, "--judged", self.path("judged.tsv"))


class AppendRecheckTest(AppendRecheckCase):
    def setUp(self):
        super().setUp()
        self.append(self.prev)

    def test_records_the_appended_finding_as_a_recheck_match(self):
        self.assertEqual({k: run_files.read_matches(self.cur)[3][k] for k in ("prev_id", "how", "prev_number")},
                         {"prev_id": "8", "how": "recheck", "prev_number": "8"})

    def test_re_keys_the_posted_row_to_the_appended_id(self):
        self.assertEqual(run_files.read_posted(self.cur)[3]["comment_id"], "5")

    def test_copies_the_posted_text_under_the_appended_id(self):
        self.assertEqual(self.cur_text("posted/3.md"), "Posted text of 8.\n")

    def test_re_keys_the_kept_open_row_to_the_appended_id(self):
        self.assertEqual(run_files.read_kept_open(self.cur), {3: self.KEPT})

    def test_copies_the_closing_reply_under_the_appended_id(self):
        self.assertEqual(self.cur_text("posted/close-3.md"), "Thanks, that does it.\n")


class AppendWithoutAPreviousRunTest(AppendRecheckCase):
    def setUp(self):
        super().setUp()
        self.append()

    def test_adds_no_match(self):
        self.assertNotIn(3, run_files.read_matches(self.cur))

    def test_copies_no_posted_row(self):
        self.assertFalse(os.path.exists(os.path.join(self.cur, "posted.tsv")))


class JudgedTest(TwoRunsCase):
    def setUp(self):
        super().setUp()
        judged = self.path("judged.tsv")
        write_file(judged, "cur_id\tprev_id\tverdict\nfinding 2\t8\tsame\n2\t8\tsame\n")
        self.out = run_ok("reconcile", self.prev, self.cur, "--judged", judged)

    def test_skips_a_row_whose_id_is_not_a_number_with_a_warning(self):
        self.assertIn("judged row 'finding 2', '8': an id is not a number; skipped", self.out)

    def test_applies_the_rows_with_numbers(self):
        self.assertEqual(run_files.read_matches(self.cur)[2]["how"], "judge")


if __name__ == "__main__":
    unittest.main()

import os
import sys
import unittest

from helpers import SCRIPTS, RunCase, defect, merged_md, run_ok, write_file

sys.path.insert(0, SCRIPTS)
import records

render = records.load_script("render-report.py")


def posted_row(comment_id, kind="line"):
    return {"state": "posted", "kind": kind, "comment_id": str(comment_id), "thread_id": f"T{comment_id}", "path": "a.py", "line": "3"}


class SeedCase(RunCase):
    def setUp(self):
        super().setUp()
        self.prev, self.cur = self.run_dir, self.path("cur")
        self.write_merged(defect(7, "a.py"), defect(8, "b.py"))
        self.write_numbers({7: "fix", 8: "fix"})
        write_file(os.path.join(self.cur, "merged.md"), merged_md(defect(1, "a.py"), defect(2, "c.py")))
        write_file(os.path.join(self.cur, "reconcile", "matches.tsv"),
                   "cur_id\tprev_id\thow\tprev_number\tprev_status\tprev_ref\n1\t7\tline\t7\topen\t\n")

    def post(self, rows):
        render.write_posted(self.prev, rows)
        for mid in rows: self.write(f"posted/{mid}.md", f"Posted text of {mid}.\n")

    def seed(self):
        return run_ok("reconcile", self.prev, self.cur, "--seed")

    def cur_text(self, name):
        with open(os.path.join(self.cur, name), encoding="utf-8") as f:
            return f.read()


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
        self.assertEqual(render.read_posted(self.cur)[1]["comment_id"], "5")

    def test_copies_the_posted_text_under_the_current_id(self):
        self.assertEqual(self.cur_text("posted/1.md"), "Posted text of 7.\n")

    def test_leaves_an_unmatched_posted_finding_out(self):
        self.assertEqual(list(render.read_posted(self.cur)), [1])

    def test_counts_the_seeded_posted_findings(self):
        self.assertIn("seeded 0 statuses and 1 posted findings from", self.out)

    def test_names_the_posted_findings_not_found_again(self):
        self.assertIn("; 1 posted findings not found again (finding 8); their threads come in as pull request comments", self.out)


class SeedUnnumberedPostingTest(SeedCase):
    def test_names_a_lost_posting_without_a_number_by_its_merged_id(self):
        self.post({9: posted_row(6)})
        self.assertIn("1 posted findings not found again (#9)", self.seed())


class SeedOverACurrentPostingTest(SeedCase):
    def setUp(self):
        super().setUp()
        self.post({7: posted_row(5)})
        render.write_posted(self.cur, {1: posted_row(9)})
        write_file(os.path.join(self.cur, "posted", "1.md"), "Current text.\n")
        self.seed()

    def test_keeps_the_current_row(self):
        self.assertEqual(render.read_posted(self.cur)[1]["comment_id"], "9")

    def test_keeps_the_current_text(self):
        self.assertEqual(self.cur_text("posted/1.md"), "Current text.\n")


class SeedUnmatchedBodyPostingTest(SeedCase):
    def test_does_not_name_a_body_posting_as_lost(self):
        self.post({8: posted_row("", kind="body")})
        self.assertNotIn("not found again", self.seed())


if __name__ == "__main__":
    unittest.main()

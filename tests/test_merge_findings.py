import os
import sys
import unittest

from helpers import PLUGIN, SCRIPTS, TempCase, run_ok, write_file

sys.path.insert(0, SCRIPTS)
import records

mf = records.load_script("merge-findings.py")


def entry(line, end_line=None, file="a.py", debt="", lens="correctness"):
    return mf.norm({"_source": "t", "lens": lens, "file": file, "line": str(line), "end_line": str(end_line or line), "debt": debt})


def credit(line):
    return entry(line, lens="credit")


class SameLinesTest(unittest.TestCase):
    def test_matches_lines_within_the_slack(self):
        self.assertTrue(mf.same_lines(entry(10), entry(13)))

    def test_matches_a_line_inside_a_range(self):
        self.assertTrue(mf.same_lines(entry(10, 20), entry(15)))

    def test_refuses_lines_beyond_the_slack(self):
        self.assertFalse(mf.same_lines(entry(10), entry(14)))

    def test_widens_with_a_larger_slack(self):
        self.assertTrue(mf.same_lines(entry(10), entry(14), slack=4))

    def test_refuses_another_file(self):
        self.assertFalse(mf.same_lines(entry(10), entry(10, file="b.py")))

    def test_refuses_an_entry_without_a_line(self):
        self.assertFalse(mf.same_lines(entry(10), entry("")))

    def test_ignores_the_kind(self):
        self.assertTrue(mf.same_lines(entry(10), entry(10, debt="cleanup")))


class OverlapsTest(unittest.TestCase):
    def test_joins_two_defects_on_the_same_lines(self):
        self.assertTrue(mf.overlaps(entry(10), entry(12)))

    def test_joins_two_debt_findings_on_the_same_lines(self):
        self.assertTrue(mf.overlaps(entry(10, debt="cleanup"), entry(12, debt="refactor")))

    def test_keeps_a_debt_finding_apart_from_a_defect(self):
        self.assertFalse(mf.overlaps(entry(10), entry(10, debt="cleanup")))

    def test_keeps_defects_on_distant_lines_apart(self):
        self.assertFalse(mf.overlaps(entry(10), entry(30)))

    def test_keeps_a_credit_apart_from_a_defect(self):
        self.assertFalse(mf.overlaps(entry(10), credit(10)))

    def test_joins_two_credits_on_the_same_lines(self):
        self.assertTrue(mf.overlaps(credit(10), credit(12)))


class IsCreditTest(unittest.TestCase):
    def test_holds_for_a_raw_entry_of_the_credit_lens(self):
        self.assertTrue(mf.is_credit({"lens": "credit"}))

    def test_holds_for_a_normalized_entry(self):
        self.assertTrue(mf.is_credit(credit(10)))

    def test_refuses_a_lens_set_that_holds_another_lens(self):
        self.assertFalse(mf.is_credit({"lens": "credit, tests"}))


CREDIT_RAW = (
    "```findings\n- lens: credit\n  slice: api\n  confidence: 90\n  file: a.py\n  line: 10\n"
    "  title: Guards the retry\n  claim: It guards the retry.\n  evidence: read a.py\n```\n"
)


class MergedCreditTest(TempCase):
    def setUp(self):
        super().setUp()
        write_file(os.path.join(self.path("raw"), "credit.md"), CREDIT_RAW)
        run_ok("merge-findings", self.path("raw"), "-o", self.path("merged.md"), "--readable", self.path("so-far.md"))

    def read(self, name):
        with open(self.path(name), encoding="utf-8") as f:
            return f.read()

    def test_writes_only_the_credit_fields(self):
        self.assertNotIn("severity:", self.read("merged.md"))

    def test_keeps_the_credit_claim(self):
        self.assertIn("  claim: It guards the retry.\n", self.read("merged.md"))

    def test_leaves_credits_out_of_the_readable_findings(self):
        self.assertNotIn("It guards the retry", self.read("so-far.md"))


CREDIT_LENS_FIELDS = {"lens", "slice", "confidence", "file", "line", "end_line", "title", "claim", "context", "snippet", "evidence"}


class CreditLensTemplateTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(PLUGIN, "agents", "lens-credit.md"), encoding="utf-8") as f:
            [block] = mf.parse_blocks(f.read())
        [self.entry] = mf.parse_entries(block, "lens-credit.md")

    def test_parses_into_the_credit_fields(self):
        self.assertEqual(set(self.entry) - {"_source"}, CREDIT_LENS_FIELDS)

    def test_names_only_fields_the_merge_keeps_for_a_credit(self):
        self.assertLessEqual(CREDIT_LENS_FIELDS - {"end_line"}, set(mf.CREDIT_FIELDS))


if __name__ == "__main__":
    unittest.main()

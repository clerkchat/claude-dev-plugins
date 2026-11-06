import sys
import unittest

from helpers import SCRIPTS

sys.path.insert(0, SCRIPTS)
import records

mf = records.load_script("merge-findings.py")


def entry(line, end_line=None, file="a.py", debt=""):
    return mf.norm({"_source": "t", "file": file, "line": str(line), "end_line": str(end_line or line), "debt": debt})


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


if __name__ == "__main__":
    unittest.main()

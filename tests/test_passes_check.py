import os
import unittest

from helpers import TempCase, write_file
import paths
import records

passes = records.load_script("passes.py")

CHECK = "pass-p3-1016; ran edge-cases; edge-cases 2"


def checked(check=CHECK):
    return {"f": {"Status": "checked", "Check": check}}


class CheckRunTests(TempCase):
    def test_label_is_the_first_part_of_check(self):
        self.assertEqual(passes.check_label(checked()), "pass-p3-1016")

    def test_label_is_empty_without_a_check(self):
        self.assertEqual(passes.check_label({"f": {}}), "")

    def test_findings_are_none_without_merged_findings(self):
        self.assertIsNone(passes.check_findings(self.path("wt"), checked()))

    def test_findings_are_none_without_a_label(self):
        self.assertIsNone(passes.check_findings(self.path("wt"), checked("")))

    def test_findings_are_the_label_and_the_open_count_once_merged(self):
        wt = self.path("wt")
        run = paths.run(wt, "pass-p3-1016")
        write_file(os.path.join(run, "merged.md"), "")
        self.assertEqual(passes.check_findings(wt, checked()), ("pass-p3-1016", 0))


if __name__ == "__main__":
    unittest.main()

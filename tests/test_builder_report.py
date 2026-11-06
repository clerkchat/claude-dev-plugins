import os
import re
import unittest

from helpers import PLUGIN

REPORT_LINES = [
    "status", "size", "scope", "files", "tests", "summary", "requirements", "decisions", "choices",
    "questions", "deviations", "refactor", "rollout", "cleanups", "follow-ups", "contract", "findings",
]


def read(*parts):
    with open(os.path.join(PLUGIN, *parts), encoding="utf-8") as f:
        return f.read()


def report_block():
    return re.search(r"```\n(status: .*?)```", read("agents", "builder.md"), re.S).group(1)


class BuilderReportTest(unittest.TestCase):
    def setUp(self):
        self.lines = re.findall(r"^([a-z-]+): ", report_block(), re.M)

    def test_lists_its_lines_in_order(self):
        self.assertEqual(self.lines, REPORT_LINES)

    def test_puts_cleanups_between_rollout_and_follow_ups(self):
        at = self.lines.index("cleanups")
        self.assertEqual(self.lines[at - 1:at + 2], ["rollout", "cleanups", "follow-ups"])


class CleanupsReaderTest(unittest.TestCase):
    def test_building_reads_the_cleanups_line(self):
        self.assertIn("`cleanups:`", read("skills", "building", "SKILL.md"))

    def test_review_fix_names_the_cleanup_it_filed(self):
        self.assertIn("cleanup filed", read("skills", "review-fix", "SKILL.md"))

    def test_review_fix_ties_it_to_the_cleanups_line(self):
        self.assertIn("cleanups:", read("skills", "review-fix", "SKILL.md"))


if __name__ == "__main__":
    unittest.main()

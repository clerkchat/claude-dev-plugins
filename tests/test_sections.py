import sys
import unittest

from helpers import SCRIPTS

sys.path.insert(0, SCRIPTS)
import records

TEXT = "## Open items\n- [ ] one\n```\n# not a heading\n```\n- [x] two\n\n## Next\ntext\n"


class SectionTests(unittest.TestCase):
    def test_a_level_one_line_inside_a_section_does_not_end_it(self):
        self.assertIn("- [x] two", records.section(TEXT, "Open items"))

    def test_a_level_two_heading_ends_the_section(self):
        self.assertNotIn("text", records.section(TEXT, "Open items"))

    def test_a_missing_section_is_empty(self):
        self.assertEqual(records.section(TEXT, "Absent"), "")

    def test_body_section_strips(self):
        self.assertEqual(records.body_section(TEXT, "Next"), "text")

    def test_open_items_read_through_the_section(self):
        self.assertEqual(records.brief_open_items(TEXT), ["one"])


if __name__ == "__main__":
    unittest.main()

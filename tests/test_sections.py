import os
import sys
import unittest

from helpers import SCRIPTS, TempCase, write_record

sys.path.insert(0, SCRIPTS)
import build
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


class HasSectionTests(unittest.TestCase):
    def test_a_present_heading(self):
        self.assertTrue(records.has_section(TEXT, "Next"))

    def test_an_absent_heading(self):
        self.assertFalse(records.has_section(TEXT, "Absent"))

    def test_an_empty_section_is_still_present(self):
        self.assertTrue(records.has_section("## Empty\n\n## Next\ntext\n", "Empty"))

    def test_a_heading_with_trailing_spaces(self):
        text = "## Purpose  \nWhat it builds.\n"
        self.assertTrue(records.has_section(text, "Purpose"))
        self.assertEqual(records.body_section(text, "Purpose"), "What it builds.")


class GistTests(TempCase):
    def gist_of(self, body):
        write_record(self.tmp, "R1", "decision", "One", body=body)
        return records.gist(records.records(os.path.join(self.tmp, ".clerk-dev", "feature"))[0])

    def test_reads_the_decision_section(self):
        self.assertEqual(self.gist_of("Context.\n\n## Decision\n\nWe do this.\n"), "We do this.")

    def test_a_level_one_line_inside_the_section_does_not_end_it(self):
        self.assertEqual(self.gist_of("## Decision\n\n```\n# not a heading\n```\n\nWe do this.\n"), "We do this.")

    def test_an_empty_section_falls_back_to_the_body(self):
        self.assertEqual(self.gist_of("Context.\n\n## Decision\n"), "Context.")


class SpecRequirementsTests(TempCase):
    def requirements_of(self, body):
        write_record(self.tmp, "R1", "spec", "Spec", body=body)
        return build.spec_requirements(os.path.join(self.tmp, ".clerk-dev", "feature"), "R1")[1]

    def test_reads_the_numbered_items(self):
        self.assertEqual(self.requirements_of("## Requirements\n\n1. One.\n2. Two.\n"), {1: "One.", 2: "Two."})

    def test_a_level_one_line_inside_the_section_does_not_end_it(self):
        self.assertEqual(self.requirements_of("## Requirements\n\n1. One.\n```\n# not a heading\n```\n2. Two.\n"), {1: "One.", 2: "Two."})

    def test_a_missing_section_is_empty(self):
        self.assertEqual(self.requirements_of("## Shape\n\n1. One.\n"), {})


class LensSectionTests(TempCase):
    def setUp(self):
        super().setUp()
        self.lens = records.load_script("lens-section.py")
        self.lens.AGENTS = self.tmp
        with open(self.path("lens-x.md"), "w", encoding="utf-8") as f:
            f.write("## Empty\n\n## Pass mode\ntext\n")

    def test_prints_the_section(self):
        self.assertEqual(self.lens.section("x", "Pass mode"), "text")

    def test_an_empty_section_is_present(self):
        self.assertEqual(self.lens.section("x", "Empty"), "")

    def test_a_missing_section_is_none(self):
        self.assertIsNone(self.lens.section("x", "Absent"))

    def test_a_missing_lens_is_none(self):
        self.assertIsNone(self.lens.section("nope", "Pass mode"))


if __name__ == "__main__":
    unittest.main()

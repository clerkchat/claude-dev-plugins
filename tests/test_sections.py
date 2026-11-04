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


LENS = """## Intro

## Concerns

### Inputs

1. **One.**
   - Review: checks one,
     across two lines.
   - Pass: n/a: nothing to write.

### State

2. **Two.**
   - Review: checks two.
   - Pass: do two.

## Next
text
"""


class LensModeTests(TempCase):
    def setUp(self):
        super().setUp()
        self.lens = records.load_script("lens-mode.py")
        self.lens.AGENTS = self.tmp
        self.write("x", LENS)

    def write(self, lens, text):
        with open(self.path(f"lens-{lens}.md"), "w", encoding="utf-8") as f:
            f.write(text)

    def concern(self, number):
        return self.lens.concerns("x")[number - 1]

    def test_numbers_run_across_groups(self):
        self.assertEqual([c.number for c in self.lens.concerns("x")], [1, 2])

    def test_reads_the_title(self):
        self.assertEqual(self.concern(1).title, "One.")

    def test_joins_a_line_continued_under_its_label(self):
        self.assertEqual(self.lens.line(self.concern(1), "Review"), "checks one, across two lines.")

    def test_keeps_the_labels_in_file_order(self):
        self.assertEqual(self.concern(2).lines, [("Review", "checks two."), ("Pass", "do two.")])

    def test_reads_the_why_of_an_na_line(self):
        self.assertEqual(self.lens.na(self.lens.line(self.concern(1), "Pass")), "nothing to write.")

    def test_a_line_with_text_is_not_na(self):
        self.assertIsNone(self.lens.na("do two."))

    def test_mode_text_skips_na_lines(self):
        self.assertEqual(self.lens.mode_text("x", "Pass"), f"## x: Pass mode\n\n{self.lens.OPENERS['Pass']}\n\n- **Two.** do two.")

    def test_a_label_on_every_concern_is_carried(self):
        self.assertTrue(self.lens.carries(self.lens.concerns("x"), "Pass"))

    def test_a_label_on_some_concerns_is_not_carried(self):
        self.write("y", "## Concerns\n\n1. **A.**\n   - Review: a\n   - Pass: p\n2. **B.**\n   - Review: b\n")
        self.assertFalse(self.lens.carries(self.lens.concerns("y"), "Pass"))

    def test_mode_text_for_a_label_not_carried_names_the_lens(self):
        with self.assertRaisesRegex(self.lens.ConcernError, "lens-x.md .*'Design:'"):
            self.lens.mode_text("x", "Design")

    def test_mode_text_for_a_lens_without_concerns_says_so(self):
        self.write("y", "## Checklist\n\n1. Schema.\n")
        with self.assertRaisesRegex(self.lens.ConcernError, "lens-y.md has no concerns"):
            self.lens.mode_text("y", "Pass")

    def test_a_missing_lens_is_an_error(self):
        with self.assertRaisesRegex(self.lens.ConcernError, "no lens nope"):
            self.lens.concerns("nope")

    def test_a_stray_line_names_the_lens_and_concern(self):
        self.write("y", "## Concerns\n\n1. **A.**\n   - Review: a\nstray\n")
        with self.assertRaisesRegex(self.lens.ConcernError, "lens-y.md concern 1: cannot read 'stray'"):
            self.lens.concerns("y")

    def test_an_unknown_label_names_the_lens_and_concern(self):
        self.write("y", "## Concerns\n\n1. **A.**\n   - Fix: a\n")
        with self.assertRaisesRegex(self.lens.ConcernError, "lens-y.md concern 1: unknown label 'Fix'"):
            self.lens.concerns("y")


if __name__ == "__main__":
    unittest.main()

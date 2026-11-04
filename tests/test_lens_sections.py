import os
import re
import sys
import unittest

from helpers import PLUGIN, ROOT, SCRIPTS, plugin_text_files, run_ok, run_script

sys.path.insert(0, SCRIPTS)
import records

lens_mode = records.load_script("lens-mode.py")

SKILLS = os.path.join(PLUGIN, "skills")
PASSES = os.path.join(SKILLS, "pass", "passes.md")
PROTOCOL = os.path.join(SKILLS, "review-protocol", "SKILL.md")
ROUTING = os.path.join(SKILLS, "review", "routing.md")
SURVEY_LENSES = ["concurrency", "design", "edge-cases", "naming-concepts", "tech-debt", "tenancy"]
MODE_HEADINGS = ("Design mode", "Survey mode", "Pass mode")
OLD_NAMES = re.compile(r"`## (?:Design|Survey|Pass) mode`|lens-section")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def lens_text(lens):
    return read(os.path.join(lens_mode.AGENTS, f"lens-{lens}.md"))


def converted_lenses():
    return [lens for lens in lens_mode.lenses() if records.has_section(lens_text(lens), "Concerns")]


def expected_labels(lens):
    carried = {"Review", "Design", *(["Survey"] if lens in SURVEY_LENSES else []), *([] if lens == "cross-repo" else ["Pass"])}
    return [label for label in lens_mode.LABELS if label in carried]


def labels(concern):
    return [label for label, _ in concern.lines]


def heading_names(text):
    return [name for name, _ in records.headings(text, "##")]


def catalogue_lenses():
    lines = read(PASSES).split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith("| Pass "))
    table = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        table.append(line.split("|")[2])
    return {name.strip() for cell in table for name in cell.split(",")}


class EveryLensTest(unittest.TestCase):
    def test_has_concerns(self):
        missing = [lens for lens in lens_mode.lenses() if lens not in converted_lenses()]
        if missing:
            self.skipTest(f"not yet converted to ## Concerns: {', '.join(missing)}")
        self.assertEqual(converted_lenses(), lens_mode.lenses())


class ConvertedLensTest(unittest.TestCase):
    def each_concern(self):
        for lens in converted_lenses():
            for concern in lens_mode.concerns(lens):
                yield lens, concern

    def test_at_least_one_lens_is_converted(self):
        self.assertIn("rollout", converted_lenses())

    def test_has_no_mode_sections(self):
        for lens in converted_lenses():
            for heading in MODE_HEADINGS:
                with self.subTest(lens=lens, heading=heading):
                    self.assertFalse(records.has_section(lens_text(lens), heading))

    def test_has_concerns_that_parse(self):
        for lens in converted_lenses():
            with self.subTest(lens=lens):
                self.assertTrue(lens_mode.concerns(lens))

    def test_numbers_run_one_to_n(self):
        for lens in converted_lenses():
            with self.subTest(lens=lens):
                numbers = [c.number for c in lens_mode.concerns(lens)]
                self.assertEqual(numbers, list(range(1, len(numbers) + 1)))

    def test_labels_come_in_order_once_each(self):
        for lens, concern in self.each_concern():
            with self.subTest(lens=lens, concern=concern.number):
                found = labels(concern)
                self.assertEqual(found, [label for label in lens_mode.LABELS if label in found])

    def test_every_concern_carries_the_lens_label_set(self):
        for lens, concern in self.each_concern():
            with self.subTest(lens=lens, concern=concern.number):
                self.assertEqual(labels(concern), expected_labels(lens))

    def test_each_line_is_text_or_na_with_a_why(self):
        for lens, concern in self.each_concern():
            for label, text in concern.lines:
                with self.subTest(lens=lens, concern=concern.number, label=label):
                    self.assertTrue(text)
                    if text.lower().startswith("n/a"):
                        self.assertTrue(lens_mode.na(text))

    def test_review_is_never_na(self):
        for lens, concern in self.each_concern():
            with self.subTest(lens=lens, concern=concern.number):
                self.assertIsNone(lens_mode.na(lens_mode.line(concern, "Review")))


class PassModeTextTest(unittest.TestCase):
    def test_catalogue_names_no_lens_without_pass_lines(self):
        self.assertIn("tech-debt", catalogue_lenses())
        self.assertNotIn("cross-repo", catalogue_lenses())

    def test_catalogue_lenses_carry_pass_lines(self):
        for lens in sorted(catalogue_lenses() & set(converted_lenses())):
            with self.subTest(lens=lens):
                self.assertTrue(lens_mode.carries(lens_mode.concerns(lens), "Pass"))

    def test_prints_titles_with_only_the_lines_that_apply(self):
        for lens in converted_lenses():
            if lens == "cross-repo":
                continue
            out = run_ok("lens-mode", lens)
            for concern in lens_mode.concerns(lens):
                with self.subTest(lens=lens, concern=concern.number):
                    text = lens_mode.line(concern, "Pass")
                    if lens_mode.na(text) is None:
                        self.assertIn(f"- **{concern.title}** {text}", out)
                    else:
                        self.assertNotIn(f"**{concern.title}**", out)

    def test_heads_the_text_with_the_lens_and_the_opener(self):
        out = run_ok("lens-mode", "rollout")
        self.assertTrue(out.startswith(f"## rollout: Pass mode\n\n{lens_mode.OPENERS['Pass']}\n\n"))


class LensModeCommandTest(unittest.TestCase):
    def test_lists_the_converted_survey_lenses(self):
        out = run_ok("lens-mode", "--list", "survey")
        self.assertEqual(out.split(), [lens for lens in SURVEY_LENSES if lens in converted_lenses()])

    def test_lists_pass_lenses_by_default(self):
        out = run_ok("lens-mode", "--list")
        self.assertEqual(out.split(), [lens for lens in converted_lenses() if lens != "cross-repo"])

    def test_an_unknown_lens_exits_1(self):
        self.assertEqual(run_script("lens-mode", "nope"), (1, "no lens nope"))

    def test_a_label_the_lens_does_not_carry_exits_1(self):
        code, out = run_script("lens-mode", "rollout", "survey")
        self.assertEqual(code, 1)
        self.assertIn("'Survey:'", out)

    def test_an_unknown_mode_exits_1(self):
        self.assertEqual(run_script("lens-mode", "rollout", "fix")[0], 1)


class OldNamesTest(unittest.TestCase):
    def test_no_plugin_file_outside_agents_names_the_mode_sections_or_lens_section(self):
        agents = os.path.join(PLUGIN, "agents") + os.sep
        named = []
        for path in plugin_text_files():
            if path.startswith(agents):
                continue
            for number, line in enumerate(read(path).split("\n"), 1):
                if OLD_NAMES.search(line):
                    named.append(f"{os.path.relpath(path, ROOT)}:{number}")
        self.assertEqual(named, [])


class ProtocolSurveyModeTest(unittest.TestCase):
    def setUp(self):
        self.text = read(PROTOCOL)
        self.found = heading_names(self.text)

    def test_follows_design_mode(self):
        self.assertEqual(self.found[self.found.index("Survey mode") - 1], "Design mode")

    def test_intro_names_the_survey_task(self):
        self.assertIn("`TASK: survey`", self.text.split("\n## ", 1)[0])


class ProtocolConcernLinesTest(unittest.TestCase):
    def setUp(self):
        self.intro = read(PROTOCOL).split("\n## ", 1)[0]

    def test_intro_names_the_line_each_task_applies(self):
        for label in ("Review", "Design", "Survey"):
            with self.subTest(label=label):
                self.assertRegex(self.intro, rf"`{label}` lines?")

    def test_intro_leaves_the_pass_lines_to_the_author(self):
        self.assertIn("the `Pass` lines are for the `pass` skill and the author", re.sub(r"\s+", " ", self.intro))


class RoutingSurveysTest(unittest.TestCase):
    def setUp(self):
        self.text = read(ROUTING)
        self.found = heading_names(self.text)

    def test_follows_design_checks(self):
        self.assertEqual(self.found[self.found.index("Surveys") - 1], "Design checks")

    def test_names_the_six_lenses(self):
        body = records.section(self.text, "Surveys")
        for lens in SURVEY_LENSES:
            with self.subTest(lens=lens):
                self.assertIn(f"`{lens}`", body)


if __name__ == "__main__":
    unittest.main()

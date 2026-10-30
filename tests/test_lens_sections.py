import glob
import os
import re
import unittest

from helpers import ROOT, run_ok

AGENTS = os.path.join(ROOT, "plugins", "clerk-dev", "agents")
SKILLS = os.path.join(ROOT, "plugins", "clerk-dev", "skills")
PASSES = os.path.join(SKILLS, "pass", "passes.md")
PROTOCOL = os.path.join(SKILLS, "review-protocol", "SKILL.md")
ROUTING = os.path.join(SKILLS, "review", "routing.md")
SURVEY_LENSES = ["concurrency", "design", "edge-cases", "naming-concepts", "tech-debt", "tenancy"]


def lens_files():
    return sorted(glob.glob(os.path.join(AGENTS, "lens-*.md")))


def lens_name(path):
    return re.fullmatch(r"lens-(.+)\.md", os.path.basename(path)).group(1)


def split_at_headings(path):
    with open(path, encoding="utf-8") as f:
        return re.split(r"^## (.+)$", f.read(), flags=re.M)


def headings(path):
    return split_at_headings(path)[1::2]


def sections(path):
    parts = split_at_headings(path)
    return {None: parts[0], **dict(zip(parts[1::2], parts[2::2]))}


def catalogue_lenses():
    with open(PASSES, encoding="utf-8") as f:
        lines = f.read().split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith("| Pass "))
    table = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        table.append(line.split("|")[2])
    return {name.strip() for cell in table for name in cell.split(",")}


class EveryLensTest(unittest.TestCase):
    def test_has_design_mode(self):
        for path in lens_files():
            with self.subTest(lens=lens_name(path)):
                self.assertIn("Design mode", headings(path))

    def test_catalogue_lenses_have_pass_mode(self):
        lenses = catalogue_lenses()
        self.assertIn("tech-debt", lenses)
        for lens in sorted(lenses):
            with self.subTest(lens=lens):
                found = headings(os.path.join(AGENTS, f"lens-{lens}.md"))
                self.assertIn("Pass mode", found)


class SurveyModeTest(unittest.TestCase):
    def test_only_the_six_lenses_have_it(self):
        having = [lens_name(p) for p in lens_files() if "Survey mode" in headings(p)]
        self.assertEqual(having, SURVEY_LENSES)

    def test_sits_between_design_mode_and_pass_mode(self):
        for lens in SURVEY_LENSES:
            with self.subTest(lens=lens):
                found = headings(os.path.join(AGENTS, f"lens-{lens}.md"))
                at = found.index("Survey mode")
                self.assertEqual(found[at - 1], "Design mode")
                self.assertEqual(found[at + 1], "Pass mode")

    def test_lens_section_prints_it(self):
        for lens in SURVEY_LENSES:
            with self.subTest(lens=lens):
                out = run_ok("lens-section", lens, "Survey mode")
                self.assertTrue(out.startswith(f"## {lens}: Survey mode"))
                self.assertIn("Asked of existing code before a change is defined", out)

    def test_lens_section_lists_exactly_the_six(self):
        out = run_ok("lens-section", "--list", "Survey mode")
        self.assertEqual(out.split("\n"), SURVEY_LENSES)


class ProtocolSurveyModeTest(unittest.TestCase):
    def setUp(self):
        self.found = headings(PROTOCOL)

    def test_follows_design_mode(self):
        self.assertEqual(self.found[self.found.index("Survey mode") - 1], "Design mode")

    def test_intro_names_the_survey_task(self):
        self.assertIn("`TASK: survey`", sections(PROTOCOL)[None])


class RoutingSurveysTest(unittest.TestCase):
    def setUp(self):
        self.found = headings(ROUTING)

    def test_follows_design_checks(self):
        self.assertEqual(self.found[self.found.index("Surveys") - 1], "Design checks")

    def test_names_the_six_lenses(self):
        body = sections(ROUTING)["Surveys"]
        for lens in SURVEY_LENSES:
            with self.subTest(lens=lens):
                self.assertIn(f"`{lens}`", body)


if __name__ == "__main__":
    unittest.main()

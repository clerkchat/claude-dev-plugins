import os
import re
import sys
import unittest

from helpers import PLUGIN, ROOT, SCRIPTS, plugin_text_files, run_ok, run_script

sys.path.insert(0, SCRIPTS)
import records

lens_mode = records.load_script("lens-mode.py")
build = records.load_script("build.py")

SKILLS = os.path.join(PLUGIN, "skills")
PROTOCOL = os.path.join(SKILLS, "review-protocol", "SKILL.md")
ROUTING = os.path.join(SKILLS, "review", "routing.md")
SURVEY_LENSES = ["concurrency", "design", "edge-cases", "naming-concepts", "tech-debt", "tenancy"]
MODE_HEADINGS = ("Design mode", "Survey mode", "Pass mode")
OLD_NAMES = re.compile(r"## (?:Design|Survey|Pass) mode|(?:Design|Survey|Pass) mode section|lens-section")
PROTOCOL_HEADINGS = {"## Design mode", "## Survey mode"}


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def lens_text(lens):
    return read(os.path.join(lens_mode.AGENTS, f"lens-{lens}.md"))


def expected_labels(lens):
    carried = {"Review", "Design", *(["Survey"] if lens in SURVEY_LENSES else []), *([] if lens == "cross-repo" else ["Pass"])}
    return [label for label in lens_mode.LABELS if label in carried]


def labels(concern):
    return [label for label, _ in concern.lines]


def heading_names(text):
    return [name for name, _ in records.headings(text, "##")]


def catalogue_lenses():
    return {lens for lenses in build.catalogue().values() for lens in lenses}


class EveryLensTest(unittest.TestCase):
    def test_has_concerns(self):
        missing = [lens for lens in lens_mode.lenses() if not records.has_section(lens_text(lens), "Concerns")]
        self.assertEqual(missing, [])
        self.assertEqual(len(lens_mode.lenses()), 25)


class CreditLensTest(unittest.TestCase):
    def setUp(self):
        self.found = lens_mode.concerns("credit")

    def test_carries_review_design_and_pass_lines(self):
        self.assertEqual({tuple(labels(c)) for c in self.found}, {("Review", "Design", "Pass")})

    def test_design_lines_are_na(self):
        self.assertTrue(all(lens_mode.na(lens_mode.line(c, "Design")) for c in self.found))

    def test_pass_lines_are_na(self):
        self.assertTrue(all(lens_mode.na(lens_mode.line(c, "Pass")) for c in self.found))


class LensConcernsTest(unittest.TestCase):
    def each_concern(self):
        for lens in lens_mode.lenses():
            for concern in lens_mode.concerns(lens):
                yield lens, concern

    def test_has_no_mode_sections(self):
        for lens in lens_mode.lenses():
            for heading in MODE_HEADINGS:
                with self.subTest(lens=lens, heading=heading):
                    self.assertFalse(records.has_section(lens_text(lens), heading))

    def test_has_concerns_that_parse(self):
        for lens in lens_mode.lenses():
            with self.subTest(lens=lens):
                self.assertTrue(lens_mode.concerns(lens))

    def test_numbers_run_one_to_n(self):
        for lens in lens_mode.lenses():
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


class RolloutCleanupsOwedTest(unittest.TestCase):
    def setUp(self):
        self.text = lens_text("rollout")

    def test_is_a_section_of_the_lens(self):
        self.assertTrue(records.has_section(self.text, "Cleanups owed"))

    def test_follows_the_concerns(self):
        found = heading_names(self.text)
        self.assertLess(found.index("Concerns"), found.index("Cleanups owed"))

    def test_is_not_read_as_a_concern(self):
        self.assertEqual([c.number for c in lens_mode.concerns("rollout")], list(range(1, 9)))


class PassModeTextTest(unittest.TestCase):
    def test_catalogue_names_no_lens_without_pass_lines(self):
        self.assertIn("tech-debt", catalogue_lenses())
        self.assertNotIn("cross-repo", catalogue_lenses())

    def test_catalogue_lenses_carry_pass_lines(self):
        for lens in sorted(catalogue_lenses()):
            with self.subTest(lens=lens):
                self.assertTrue(lens_mode.carries(lens_mode.concerns(lens), "Pass"))

    def test_prints_titles_with_only_the_lines_that_apply(self):
        for lens in lens_mode.lenses():
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

    def test_pass_named_explicitly_prints_the_default(self):
        self.assertEqual(run_ok("lens-mode", "rollout", "pass"), run_ok("lens-mode", "rollout"))


class AppliesTest(unittest.TestCase):
    def found(self, *texts):
        return [lens_mode.Concern(n, "C", [("Pass", text)]) for n, text in enumerate(texts, 1)]

    def test_holds_when_a_concern_has_a_real_line(self):
        self.assertTrue(lens_mode.applies(self.found("n/a: not for authors", "Check it."), "Pass"))

    def test_fails_when_every_line_is_na(self):
        self.assertFalse(lens_mode.applies(self.found("n/a: one", "n/a: two"), "Pass"))

    def test_fails_when_a_concern_lacks_the_line(self):
        found = self.found("Check it.") + [lens_mode.Concern(2, "D", [("Review", "Look.")])]
        self.assertFalse(lens_mode.applies(found, "Pass"))

    def test_fails_without_concerns(self):
        self.assertFalse(lens_mode.applies([], "Pass"))


class LensModeCommandTest(unittest.TestCase):
    def test_lists_the_six_survey_lenses(self):
        out = run_ok("lens-mode", "--list", "survey")
        self.assertEqual(out.split(), SURVEY_LENSES)

    def test_lists_pass_lenses_by_default(self):
        out = run_ok("lens-mode", "--list")
        self.assertEqual(out.split(), [lens for lens in lens_mode.lenses() if lens not in ("cross-repo", "credit")])

    def test_lists_every_lens_for_review(self):
        self.assertEqual(run_ok("lens-mode", "--list", "review").split(), lens_mode.lenses())

    def test_leaves_the_credit_lens_out_of_survey(self):
        self.assertNotIn("credit", run_ok("lens-mode", "--list", "survey").split())

    def test_leaves_out_a_lens_whose_lines_for_the_mode_are_all_na(self):
        self.assertNotIn("credit", run_ok("lens-mode", "--list", "design").split())

    def test_lists_a_lens_with_a_line_for_the_mode(self):
        self.assertIn("credit", run_ok("lens-mode", "--list", "review").split())

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
                if OLD_NAMES.search(line) and not (path == PROTOCOL and line in PROTOCOL_HEADINGS):
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


class RoutingCreditTest(unittest.TestCase):
    def setUp(self):
        self.text = read(ROUTING)

    def test_plain_name_is_credits(self):
        self.assertEqual(records.read_plain_names(ROUTING)["credit"], "credits")

    def test_triggers_on_any_category_in_every_mode(self):
        self.assertRegex(records.section(self.text, "Lens triggers"), r"\| `credit` +\| any +\| yes in every mode +\|")

    def test_quick_mode_runs_it_outside_the_cap(self):
        self.assertIn("`credit` still runs, outside the cap", records.section(self.text, "Quick mode"))

    def test_triage_never_drops_it(self):
        self.assertIn("credit,", records.section(self.text, "Triage questions").split("Lenses never dropped by triage:")[1])


if __name__ == "__main__":
    unittest.main()

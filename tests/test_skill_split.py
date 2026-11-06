import os
import re
import unittest

from helpers import ROOT

SKILLS = os.path.join(ROOT, "plugins", "clerk-dev", "skills")


def skill(name):
    with open(os.path.join(SKILLS, name, "SKILL.md"), encoding="utf-8") as f:
        return f.read()


def headings(text):
    prose = re.sub(r"^\s*```.*?^\s*```", "", text, flags=re.S | re.M)
    return re.findall(r"^## (.+)$", prose, re.M)


class SkillSplitTests(unittest.TestCase):
    def test_writing_code_holds_only_how_to_shape_code(self):
        self.assertEqual(
            headings(skill("writing-code")),
            ["Refactor first", "Changing live code", "Reuse", "One source of truth", "Tests"],
        )

    def test_building_opens_with_the_setup_check_then_intake(self):
        self.assertEqual(headings(skill("building"))[:2], ["Before the first handoff", "Intake"])

    def test_design_check_shares_the_lens_run_between_a_check_and_a_survey(self):
        self.assertEqual(
            headings(skill("design-check")),
            ["Running the lenses", "Running a check", "Running a survey", "Check file", "Survey file", "Walking the questions"],
        )

    def test_neither_skill_names_the_old_agents_or_delegating(self):
        for name in ("writing-code", "building"):
            self.assertIsNone(re.search(r"implementer|fixer|delegat", skill(name), re.I), name)


if __name__ == "__main__":
    unittest.main()


def allowed_tools(name):
    return re.search(r"^allowed-tools: (.*)$", skill(name), re.M).group(1).split(", ")


READS_OF_THE_PULL_REQUEST = {"Bash(gh pr view *)", "Bash(gh pr diff *)", "Bash(gh pr list *)"}


class ReviewSkillToolsTests(unittest.TestCase):
    def test_pre_approve_no_github_call_but_reading_the_pull_request(self):
        for name in ("review", "review-fix", "review-triage"):
            with self.subTest(name):
                gh = {tool for tool in allowed_tools(name) if tool.startswith("Bash(gh")}
                self.assertLessEqual(gh, READS_OF_THE_PULL_REQUEST)

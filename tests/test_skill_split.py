import os
import re
import unittest

from helpers import ROOT

SKILLS = os.path.join(ROOT, "plugins", "clerk-dev", "skills")


def skill(name):
    with open(os.path.join(SKILLS, name, "SKILL.md"), encoding="utf-8") as f:
        return f.read()


def headings(text):
    return re.findall(r"^## (.+)$", text, re.M)


class SkillSplitTests(unittest.TestCase):
    def test_writing_code_holds_only_how_to_shape_code(self):
        self.assertEqual(
            headings(skill("writing-code")),
            ["Refactor first", "Changing live code", "Reuse", "One source of truth"],
        )

    def test_building_opens_with_the_setup_check_then_intake(self):
        self.assertEqual(headings(skill("building"))[:2], ["Before the first handoff", "Intake"])

    def test_neither_skill_names_the_old_agents_or_delegating(self):
        for name in ("writing-code", "building"):
            self.assertIsNone(re.search(r"implementer|fixer|delegat", skill(name), re.I), name)


if __name__ == "__main__":
    unittest.main()

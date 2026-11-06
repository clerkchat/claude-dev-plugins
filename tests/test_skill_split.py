import os
import re
import unittest

from helpers import ROOT, SCRIPTS

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


def frontmatter_and_body(name):
    return skill(name).split("---", 2)[1:]


def allowed_tools(name):
    front, _ = frontmatter_and_body(name)
    inline = re.search(r"^allowed-tools: (.+)$", front, re.M)
    if inline:
        return inline.group(1).split(", ")
    listed = re.search(r"^allowed-tools:\n((?:  - .+\n)+)", front, re.M).group(1)
    return re.findall(r"^  - (.+)$", listed, re.M)


def bash_rules(tools):
    return [tool for tool in tools if tool.startswith("Bash(")]


def headless_review_rules(name):
    launch = re.search(r"--allowedTools (.*?) Read Grep", skill(name), re.S).group(1)
    return re.findall(r'"(Bash\([^"]*\))"', launch)


READS_OF_THE_PULL_REQUEST = {"Bash(gh pr view *)", "Bash(gh pr diff *)", "Bash(gh pr list *)"}
SKILLS_READING_PULL_REQUEST_TEXT = ("review", "review-fix", "review-triage")
SCRIPT_RULE = re.compile(r"^Bash\(python3 \$\{CLAUDE_PLUGIN_ROOT\}/scripts/([a-z_-]+\.py) \*\)$")
GIT_SUBCOMMAND_RULE = re.compile(r"^Bash\(git ([a-z][a-z-]*)( [^*]*)?( \*)?\)$")
WIDE_RULES = {"Bash(python3 *)", "Bash(git *)", "Bash(ln *)"}


def scripts_named_in(name):
    _, body = frontmatter_and_body(name)
    named = set(re.findall(r"\b([a-z][a-z_-]*\.py)\b", body))
    return named & set(os.listdir(SCRIPTS))


class ReviewSkillToolsTests(unittest.TestCase):
    def test_pre_approve_no_github_call_but_reading_the_pull_request(self):
        for name in SKILLS_READING_PULL_REQUEST_TEXT:
            with self.subTest(name):
                gh = {rule for rule in bash_rules(allowed_tools(name)) if rule.startswith("Bash(gh")}
                self.assertLessEqual(gh, READS_OF_THE_PULL_REQUEST)

    def test_pre_approve_no_interpreter_git_ln_or_claude_at_large(self):
        for name in SKILLS_READING_PULL_REQUEST_TEXT:
            with self.subTest(name):
                rules = bash_rules(allowed_tools(name))
                self.assertEqual(WIDE_RULES & set(rules), set())
                self.assertEqual([rule for rule in rules if rule.startswith("Bash(claude")], [])

    def test_pre_approve_python3_only_for_the_plugin_scripts_by_path(self):
        for name in SKILLS_READING_PULL_REQUEST_TEXT:
            for rule in bash_rules(allowed_tools(name)):
                if rule.startswith("Bash(python3"):
                    with self.subTest(name, rule=rule):
                        self.assertRegex(rule, SCRIPT_RULE)
                        self.assertIn(SCRIPT_RULE.match(rule).group(1), os.listdir(SCRIPTS))

    def test_pre_approve_every_script_the_skill_names(self):
        for name in SKILLS_READING_PULL_REQUEST_TEXT:
            with self.subTest(name):
                rules = bash_rules(allowed_tools(name))
                allowed = {match.group(1) for match in map(SCRIPT_RULE.match, rules) if match}
                self.assertLessEqual(scripts_named_in(name), allowed)

    def test_pre_approve_git_only_by_subcommand_and_never_grep(self):
        for name in SKILLS_READING_PULL_REQUEST_TEXT:
            for rule in bash_rules(allowed_tools(name)):
                if rule.startswith("Bash(git"):
                    with self.subTest(name, rule=rule):
                        self.assertRegex(rule, GIT_SUBCOMMAND_RULE)
                        self.assertNotEqual(GIT_SUBCOMMAND_RULE.match(rule).group(1), "grep")


class HeadlessReviewLaunchTests(unittest.TestCase):
    def test_review_children_and_pass_reviews_get_the_review_rules_but_the_scripts(self):
        expected = [rule for rule in bash_rules(allowed_tools("review")) if not SCRIPT_RULE.match(rule)]
        for name in ("review", "pass"):
            with self.subTest(name):
                self.assertEqual(headless_review_rules(name), expected)


if __name__ == "__main__":
    unittest.main()

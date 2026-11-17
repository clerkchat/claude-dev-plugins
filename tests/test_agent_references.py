import os
import re
import unittest

from helpers import PLUGIN, ROOT, TempCase, plugin_text_files, referring_files, run_ok
import paths

REFERENCE = re.compile(r"clerk-dev:([a-z0-9][a-z0-9-]*[a-z0-9])(-?<)?")


def resolves(plugin, name):
    return os.path.isfile(os.path.join(plugin, "agents", name + ".md")) or os.path.isdir(
        os.path.join(plugin, "skills", name)
    )


def check_references(paths, plugin=PLUGIN, root=ROOT):
    broken, templates = [], set()
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for number, line in enumerate(f, 1):
                for m in REFERENCE.finditer(line):
                    if m.group(2):
                        templates.add(m.group(0))
                    elif not resolves(plugin, m.group(1)):
                        broken.append(f"{os.path.relpath(path, root)}:{number}: clerk-dev:{m.group(1)}")
    return broken, sorted(templates)


STORES_THE_BACKLOG_REPLACED = re.compile(
    r"followups\.py|\.clerk-dev/followups\.md|ideas\.md"
    r"|records\.py`? +(?:idea|ideas|adopt|drop|unpark)\b"
    r"|\bIDEA-\d+|\bF\d+\b"
)


def lines_matching(pattern):
    named = []
    for path in plugin_text_files():
        with open(path, encoding="utf-8") as f:
            for number, line in enumerate(f, 1):
                if pattern.search(line):
                    named.append(f"{os.path.relpath(path, ROOT)}:{number}")
    return named


class AgentReferenceTests(unittest.TestCase):
    def test_every_reference_names_an_agent_or_a_skill(self):
        broken, templates = check_references(referring_files())
        print(f"templates skipped: {templates or 'none'}")
        self.assertEqual(broken, [])

    def test_the_old_builder_agents_are_gone(self):
        for name in ("implementer", "review-fixer"):
            self.assertFalse(os.path.exists(os.path.join(PLUGIN, "agents", name + ".md")), name)
        self.assertFalse(os.path.exists(os.path.join(PLUGIN, "skills", "review-followups")))
        self.assertTrue(os.path.isfile(os.path.join(PLUGIN, "skills", "followups", "SKILL.md")))

    def test_no_file_names_the_old_agents_or_the_old_followups_skill(self):
        self.assertEqual(lines_matching(re.compile(r"implementer|fixer|review-followups", re.I)), [])

    def test_no_file_names_the_stores_the_backlog_replaced_or_their_ids(self):
        self.assertEqual(lines_matching(STORES_THE_BACKLOG_REPLACED), [])


def agent_frontmatter(name):
    with open(os.path.join(PLUGIN, "agents", name + ".md"), encoding="utf-8") as f:
        return f.read().split("---", 2)[1]


class PostDrafterToolsTests(unittest.TestCase):
    TOOLS = {"Bash", "Read", "Write", "Edit", "Glob", "Grep", "NotebookEdit", "WebFetch", "WebSearch", "Agent"}

    def setUp(self):
        self.front = agent_frontmatter("post-drafter")

    def test_has_no_tools(self):
        self.assertRegex(self.front, r"(?m)^tools: \[\]$")

    def test_also_disallows_every_tool_that_reads_writes_or_reaches_out(self):
        listed = re.search(r"(?m)^disallowedTools: (.+)$", self.front).group(1)
        self.assertLessEqual(self.TOOLS, set(listed.split(", ")))


class ReferenceCheckerTests(TempCase):
    def setUp(self):
        super().setUp()
        self.plugin = self.path("plugin")
        os.makedirs(os.path.join(self.plugin, "agents"))
        os.makedirs(os.path.join(self.plugin, "skills", "pass"))
        open(os.path.join(self.plugin, "agents", "builder.md"), "w").close()

    def check(self, text):
        doc = os.path.join(self.plugin, "doc.md")
        with open(doc, "w") as f:
            f.write(text)
        return check_references([doc], self.plugin, self.plugin)

    def test_an_agent_and_a_skill_resolve_through_trailing_punctuation(self):
        self.assertEqual(self.check("Send `clerk-dev:builder`, then clerk-dev:pass.\n"), ([], []))

    def test_a_name_with_no_agent_or_skill_is_reported(self):
        self.assertEqual(self.check("Send clerk-dev:implementer.\n")[0], ["doc.md:1: clerk-dev:implementer"])

    def test_a_template_is_skipped_and_listed(self):
        self.assertEqual(self.check("Run clerk-dev:review-<lens> here.\n"), ([], ["clerk-dev:review-<"]))


class GuidanceBranchScopeTests(TempCase):
    def rule(self):
        with open(os.path.join(PLUGIN, "skills", "review", "tracking.md"), encoding="utf-8") as f:
            return re.search(r"^## Branch scope\n(.*?)(?=^## )", f.read(), re.S | re.M).group(1).strip()

    def scope(self, root):
        return run_ok("records", "guidance", root).split("## Branch scope\n", 1)[1].split("\n## ", 1)[0]

    def test_the_guidance_file_carries_the_branch_scope_rule_ahead_of_purpose(self):
        root = self.path("wt")
        os.makedirs(paths.clerk_dev(root))
        with open(paths.notes(root), "w") as f:
            f.write("# Branch notes\n\n## Purpose\nBuild the widget.\n")
        scope = self.scope(root)
        self.assertLess(scope.index(self.rule()), scope.index("### Purpose"))
        self.assertLess(scope.index("### Purpose"), scope.index("Build the widget."))

    def test_the_rule_is_written_when_the_worktree_has_no_branch_notes(self):
        root = self.path("bare")
        os.makedirs(root)
        scope = self.scope(root)
        self.assertIn(self.rule(), scope)
        self.assertIn("No branch notes in this worktree.", scope)


if __name__ == "__main__":
    unittest.main()

import glob
import os
import re
import unittest

from helpers import ROOT, TempCase, run_ok

PLUGIN = os.path.join(ROOT, "plugins", "clerk-dev")
REFERENCE = re.compile(r"clerk-dev:([a-z0-9][a-z0-9-]*[a-z0-9])(<)?")


def referring_files():
    return [
        *glob.glob(os.path.join(PLUGIN, "skills", "**", "*.md"), recursive=True),
        *glob.glob(os.path.join(PLUGIN, "agents", "*.md")),
        os.path.join(ROOT, "README.md"),
    ]


def resolves(name):
    return os.path.isfile(os.path.join(PLUGIN, "agents", name + ".md")) or os.path.isdir(
        os.path.join(PLUGIN, "skills", name)
    )


class AgentReferenceTests(unittest.TestCase):
    def test_every_reference_names_an_agent_or_a_skill(self):
        broken, templates = [], set()
        for path in referring_files():
            with open(path, encoding="utf-8") as f:
                for number, line in enumerate(f, 1):
                    for m in REFERENCE.finditer(line):
                        if m.group(2):
                            templates.add(m.group(0))
                        elif not resolves(m.group(1)):
                            broken.append(f"{os.path.relpath(path, ROOT)}:{number}: clerk-dev:{m.group(1)}")
        print(f"templates skipped: {sorted(templates) or 'none'}")
        self.assertEqual(broken, [])

    def test_the_old_builder_agents_are_gone(self):
        for name in ("implementer", "review-fixer"):
            self.assertFalse(os.path.exists(os.path.join(PLUGIN, "agents", name + ".md")), name)


class GuidanceBranchScopeTests(TempCase):
    def test_the_guidance_file_carries_the_branch_scope_rule_ahead_of_purpose(self):
        root = self.path("wt")
        os.makedirs(os.path.join(root, ".clerk-dev"))
        with open(os.path.join(root, ".clerk-dev", "branch-notes.md"), "w") as f:
            f.write("# Branch notes\n\n## Purpose\nBuild the widget.\n")
        with open(os.path.join(PLUGIN, "skills", "review", "tracking.md"), encoding="utf-8") as f:
            rule = re.search(r"^## Branch scope\n(.*?)(?=^## )", f.read(), re.S | re.M).group(1).strip()
        text = run_ok("records", "guidance", root)
        scope = text.split("## Branch scope\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn(rule, scope)
        self.assertLess(scope.index(rule), scope.index("### Purpose"))
        self.assertLess(scope.index("### Purpose"), scope.index("Build the widget."))


if __name__ == "__main__":
    unittest.main()

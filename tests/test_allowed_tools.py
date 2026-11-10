import glob
import os
import re
import unittest

from helpers import ROOT

GIT_BROAD = re.compile(r"^Bash\(git(\s+\*)?\)$")
GIT_PUSH = re.compile(r"^Bash\(git\b[^)]*\bpush\b")
GH_PR_CHANGING = re.compile(
    r"^Bash\(gh(\s+\*|\s+(pr|api)(\s+\*)?|\s+pr\s+(create|edit|merge|comment|close|review|ready|reopen)\b[^)]*)\)$"
)


def frontmatter(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    end = lines.index("---", 1)
    return lines[1:end]


def allowed_tools(path):
    entries = []
    lines = frontmatter(path)
    for i, line in enumerate(lines):
        if not line.startswith("allowed-tools:"):
            continue
        inline = line[len("allowed-tools:"):].strip()
        if inline:
            return [e.strip() for e in re.split(r",\s*(?=[A-Z])", inline)]
        for item in lines[i + 1:]:
            if not item.startswith(" ") and not item.startswith("-"):
                break
            entries.append(item.strip().lstrip("- ").strip())
    return entries


def entries_by_file():
    pattern = os.path.join(ROOT, "plugins", "**", "SKILL.md")
    for path in sorted(glob.glob(pattern, recursive=True)):
        for entry in allowed_tools(path):
            yield os.path.relpath(path, ROOT), entry


class AllowedToolsTest(unittest.TestCase):
    def assert_no_entry_matches(self, pattern):
        bad = [f"{path}: {entry}" for path, entry in entries_by_file() if pattern.match(entry)]
        self.assertEqual(bad, [])

    def test_finds_entries(self):
        self.assertTrue(any(e == "Bash(git status *)" for _, e in entries_by_file()))

    def test_no_skill_pre_approves_every_git_subcommand(self):
        self.assert_no_entry_matches(GIT_BROAD)

    def test_no_skill_pre_approves_git_push(self):
        self.assert_no_entry_matches(GIT_PUSH)

    def test_no_skill_pre_approves_pr_changing_gh_calls(self):
        self.assert_no_entry_matches(GH_PR_CHANGING)


if __name__ == "__main__":
    unittest.main()

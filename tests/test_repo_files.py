import os
import unittest

from helpers import SCRIPTS, TempCase, git, init_repo, run_script


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def read(path):
    with open(path) as f:
        return f.read()


class RepoFilesCase(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("main"), with_origin=False)
        self.second = self.path("second")
        git(self.repo.path, "worktree", "add", "-q", "-b", "second", self.second)
        self.common = os.path.join(self.repo.path, ".git")

    def old_context(self, worktree, body):
        write(os.path.join(worktree, ".claude", "skills", "review-context", "SKILL.md"),
              "---\nname: review-context\n---\n\n" + body)

    def migrate(self, *args):
        return run_script("migrate-guidance", "repo-files", self.repo.path, *args)


class GuardTests(RepoFilesCase):
    def test_an_old_workspace_file_stops_status_with_the_migrate_hint(self):
        write(os.path.join(self.repo.path, ".clerk-dev", "review-workspace.md"), "| Repo | Worktree |\n")
        code, out = run_script("status", self.repo.path, "--no-mark")
        self.assertNotEqual(code, 0)
        self.assertIn("review-workspace.md", out)
        self.assertIn("/clerk-dev:migrate", out)

    def test_an_old_context_copy_stops_status(self):
        self.old_context(self.repo.path, "## Slices\n")
        code, out = run_script("status", self.repo.path, "--no-mark")
        self.assertNotEqual(code, 0)
        self.assertIn("/clerk-dev:migrate", out)


@unittest.skipUnless(os.path.exists(os.path.join(SCRIPTS, "migrate-guidance.py")), "migrate-guidance.py is local to the plugin's own worktrees")
class MigrateTests(RepoFilesCase):
    def test_identical_copies_become_one_repo_context_without_frontmatter(self):
        self.old_context(self.repo.path, "## Slices\n")
        self.old_context(self.second, "## Slices\n")
        code, out = self.migrate()
        self.assertEqual(code, 0, out)
        self.assertEqual(read(os.path.join(self.common, "clerk-dev", "repo-context.md")), "## Slices\n")
        self.assertFalse(os.path.exists(os.path.join(self.repo.path, ".claude")))
        self.assertFalse(os.path.exists(os.path.join(self.second, ".claude")))

    def test_differing_copies_stop_until_a_merged_file_is_given(self):
        self.old_context(self.repo.path, "## Slices\n")
        self.old_context(self.second, "## Known noise\n")
        code, out = self.migrate()
        self.assertNotEqual(code, 0)
        self.assertIn("--context", out)
        self.assertFalse(os.path.exists(os.path.join(self.common, "clerk-dev", "repo-context.md")))
        merged = self.path("merged.md")
        write(merged, "## Slices\n\n## Known noise\n")
        code, out = self.migrate("--context", merged)
        self.assertEqual(code, 0, out)
        self.assertEqual(read(os.path.join(self.common, "clerk-dev", "repo-context.md")), "## Slices\n\n## Known noise\n")

    def test_setup_and_workspace_files_move_to_their_new_names(self):
        write(os.path.join(self.common, "review-setup"), "context: never 2026-10-01\n")
        write(os.path.join(self.second, ".clerk-dev", "review-workspace.md"), "Hub: main\n")
        code, out = self.migrate()
        self.assertEqual(code, 0, out)
        self.assertEqual(read(os.path.join(self.common, "clerk-dev", "setup")), "context: never 2026-10-01\n")
        self.assertEqual(read(os.path.join(self.second, ".clerk-dev", "workspace.md")), "Hub: main\n")
        self.assertFalse(os.path.exists(os.path.join(self.common, "review-setup")))
        code, out = run_script("status", self.second, "--no-mark")
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()

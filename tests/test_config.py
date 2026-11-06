import os
import sys
import unittest

from helpers import SCRIPTS, TempCase, git, init_repo, run_ok, run_script, write_file

sys.path.insert(0, SCRIPTS)
import config

SAMPLE = """# clerk-dev

## Search roots

- ~/code/work
- {root}/elsewhere
a line that is not a root

## Repositories

| Name | Main checkout | Main branch |
| ---- | ------------- | ----------- |
| api  | {api}         | master      |
| web  | {web}         |             |
| | /nameless | main |

## Worktrees

Pattern: <repo parent>/<branch>
After create: make setup
"""


class ConfigFileCase(TempCase):
    def setUp(self):
        super().setUp()
        self.api = init_repo(self.path("api/api-main"), with_origin=False)
        self.web = self.path("web/web-main")
        self.file = self.path("local.md")
        write_file(self.file, SAMPLE.format(root=self.tmp, api=self.api.path, web="~/web/web-main"))
        self.cfg = config.load(self.file)

    def env(self, path):
        return {**os.environ, config.ENV: path}


class LoadTests(ConfigFileCase):
    def test_search_roots_are_expanded(self):
        self.assertEqual(self.cfg.search_roots, [os.path.expanduser("~/code/work"), self.path("elsewhere")])

    def test_repositories_are_read_from_the_table(self):
        self.assertEqual(self.cfg.repos[0], config.Repo("api", self.api.path, "master"))

    def test_a_checkout_is_expanded_and_a_missing_main_is_empty(self):
        self.assertEqual(self.cfg.repos[1], config.Repo("web", os.path.expanduser("~/web/web-main"), ""))

    def test_a_row_without_a_name_is_ignored(self):
        self.assertEqual([r.name for r in self.cfg.repos], ["api", "web"])

    def test_the_worktree_lines_are_raw(self):
        self.assertEqual(self.cfg.pattern, "<repo parent>/<branch>")
        self.assertEqual(self.cfg.after_create, "make setup")


class MissingPartsTests(ConfigFileCase):
    def test_a_missing_file_is_an_empty_config(self):
        self.assertEqual(config.load(self.path("absent.md")), config.Config([], [], "", ""))

    def test_a_missing_section_is_empty(self):
        write_file(self.file, "# clerk-dev\n\n## Repositories\n\n| Name | Main checkout | Main branch |\n| - | - | - |\n| api | /a | main |\n")
        cfg = config.load(self.file)
        self.assertEqual((cfg.search_roots, cfg.pattern, cfg.after_create), ([], "", ""))
        self.assertEqual([r.name for r in cfg.repos], ["api"])


class LookupTests(ConfigFileCase):
    def test_by_name(self):
        self.assertEqual(config.by_name(self.cfg, "web").checkout, os.path.expanduser("~/web/web-main"))

    def test_by_name_misses(self):
        self.assertIsNone(config.by_name(self.cfg, "worker"))

    def test_by_common_dir_finds_the_main_checkouts_row_from_a_worktree(self):
        wt = self.path("api/feat")
        git(self.api.path, "worktree", "add", "-q", wt, "-b", "feat")
        common = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir")
        self.assertEqual(config.by_common_dir(self.cfg, common).name, "api")

    def test_by_common_dir_misses_an_unregistered_repository(self):
        other = init_repo(self.path("other"), with_origin=False)
        self.assertIsNone(config.by_common_dir(self.cfg, os.path.join(other.path, ".git")))

    def test_a_checkout_that_does_not_exist_never_matches(self):
        cwd_common = os.path.realpath(os.getcwd())
        self.assertIsNone(config.by_common_dir(self.cfg, cwd_common))


class CommandTests(ConfigFileCase):
    def test_path_is_the_environment_variable(self):
        self.assertEqual(run_ok("config", "path", env=self.env(self.file)), self.file)

    def test_path_defaults_under_the_claude_directory(self):
        env = {k: v for k, v in os.environ.items() if k != config.ENV}
        self.assertEqual(run_ok("config", "path", env=env), os.path.expanduser("~/.claude/clerk-dev/local.md"))

    def test_show_prints_one_line_per_part(self):
        lines = run_ok("config", "show", env=self.env(self.file)).splitlines()
        self.assertEqual(lines, [
            f"search root: {os.path.expanduser('~/code/work')}",
            f"search root: {self.path('elsewhere')}",
            f"repository: api {self.api.path} (main branch master)",
            f"repository: web {os.path.expanduser('~/web/web-main')}",
            "pattern: <repo parent>/<branch>",
            "after create: make setup",
        ])

    def test_show_of_a_missing_file_prints_nothing_and_succeeds(self):
        code, out = run_script("config", "show", env=self.env(self.path("absent.md")))
        self.assertEqual((code, out), (0, ""))


if __name__ == "__main__":
    unittest.main()

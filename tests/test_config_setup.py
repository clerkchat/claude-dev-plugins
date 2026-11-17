import datetime
import os
import sys
import unittest

from helpers import SCRIPTS, TempCase, git, init_repo, run_ok, run_script, write_file
import paths

sys.path.insert(0, SCRIPTS)
import config


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class ScanCase(TempCase):
    def setUp(self):
        super().setUp()
        self.home = self.path("home")
        os.makedirs(self.home)
        self.env = {**{k: v for k, v in os.environ.items() if k != config.ENV}, "HOME": self.home}
        self.code = self.path("code")
        self.out = self.path("proposal.md")
        self.api = self.repo("api")
        self.web = self.repo("web")
        self.feat = self.worktree("api", "feat/x")
        self.worktree("web", "feat/y")

    def repo(self, name, parent=None):
        repo = init_repo(os.path.join(parent or self.code, name, f"{name}-main"))
        repo.git("remote", "set-url", "origin", f"git@example.com:org/{name}.git")
        return repo

    def worktree(self, name, branch, at=None):
        path = at or os.path.join(self.code, name, branch)
        git(os.path.join(self.code, name, f"{name}-main"), "worktree", "add", "-q", "-b", branch, path)
        return path

    def config_path(self):
        return os.path.join(self.home, ".claude", "clerk-dev", "local.md")

    def scan(self, *args):
        return run_ok("config-setup", "scan", self.feat, "--out", self.out, *args, env=self.env).splitlines()

    def notes(self, *args):
        return self.scan(*args)[1:]

    def proposal(self, *args):
        self.scan(*args)
        return config.load(self.out)

    def repos(self, *args):
        return {r.name: r for r in self.proposal(*args).repos}

    def write(self, path=None):
        return run_script("config-setup", "write", path or self.out, env=self.env)


class TwoRepositoriesTests(ScanCase):
    def test_the_first_line_is_the_proposals_path(self):
        self.assertEqual(self.scan()[0], self.out)

    def test_every_repository_gets_a_row(self):
        self.assertEqual(self.repos(), {
            "api": config.Repo("api", self.api.path, "main"),
            "web": config.Repo("web", self.web.path, "main"),
        })

    def test_the_pattern_is_the_repo_parent_and_branch(self):
        self.assertEqual(self.proposal().pattern, "<repo parent>/<branch>")

    def test_the_after_create_command_is_left_empty(self):
        self.assertEqual(self.proposal().after_create, "")

    def test_the_roots_are_the_main_checkouts_parent_and_its_parent(self):
        self.assertEqual(self.proposal().search_roots, [self.path("code/api"), self.code])

    def test_proposing_the_parent_is_noted(self):
        self.assertEqual(self.notes(), [f"proposed root {self.code}: {self.path('code/api')} holds only this repository's worktrees"])

    def test_the_header_says_when_and_from_where(self):
        self.scan()
        lines = read(self.out).splitlines()
        self.assertEqual(lines[:3], ["# clerk-dev config", "", f"Proposed {datetime.date.today().isoformat()} from {self.feat}. Edit freely."])

    def test_the_config_itself_is_not_written(self):
        self.scan()
        self.assertFalse(os.path.exists(self.config_path()))


class WorktreeElsewhereTests(ScanCase):
    def setUp(self):
        super().setUp()
        self.other = self.worktree("web", "feat/z", self.path("elsewhere/z"))

    def test_the_pattern_is_the_default(self):
        self.assertEqual(self.proposal().pattern, "<repo parent>/<branch>")

    def test_a_note_lists_only_the_worktrees_off_the_pattern(self):
        self.assertIn(
            f"worktree paths do not all follow <repo parent>/<branch>: {self.other} (feat/z)",
            self.notes(),
        )


class NoOriginHeadTests(ScanCase):
    def setUp(self):
        super().setUp()
        self.web.git("remote", "set-head", "origin", "-d")

    def test_the_main_branch_is_left_empty(self):
        self.assertEqual(self.repos()["web"].main, "")

    def test_a_note_says_how_to_fill_it(self):
        self.assertIn(f"no origin/HEAD in {self.web.path}: run git remote set-head origin --auto there or fill in its Main branch cell", self.notes())


class WorkspaceNameTests(ScanCase):
    def setUp(self):
        super().setUp()
        rows = f"| api | {self.feat} |\n| web-app | {self.path('code/web/feat/y')} |\n| gone | {self.path('nowhere')} |\n"
        write_file(paths.workspace(self.feat), f"# Review workspace: x\n\n| Repo | Worktree |\n| - | - |\n{rows}")

    def test_the_workspace_name_wins(self):
        self.assertEqual(sorted(self.repos()), ["api", "web-app"])

    def test_a_note_lists_the_other_name(self):
        self.assertIn(f"name web-app for {self.web.path} is from workspace.md; also called web", self.notes())

    def test_a_row_whose_path_is_gone_is_noted(self):
        self.assertIn(f"workspace.md in {self.feat}: row gone names {self.path('nowhere')}, which does not exist; skipped", self.notes())


class PathOutsideTheRootsTests(ScanCase):
    def setUp(self):
        super().setUp()
        self.lib = self.repo("lib", self.path("far/away"))

    def test_it_is_not_found_by_the_walk(self):
        self.assertNotIn("lib", self.repos())

    def test_a_path_inside_it_registers_it(self):
        self.assertEqual(self.repos("--path", os.path.join(self.lib.path, "file.txt"))["lib"].checkout, self.lib.path)


class NestedRepositoryTests(ScanCase):
    def test_a_repository_inside_anothers_working_tree_is_not_listed(self):
        init_repo(os.path.join(self.web.path, "vendor", "inner"), with_origin=False)
        self.assertEqual(sorted(self.repos()), ["api", "web"])


class BareRepositoryTests(ScanCase):
    def setUp(self):
        super().setUp()
        self.bare = self.path("code/svc/svc.git")
        git(self.tmp, "clone", "-q", "--bare", self.api.path, self.bare)
        git(self.bare, "remote", "set-url", "origin", "git@example.com:org/svc.git")
        self.main = self.path("code/svc/main")
        git(self.bare, "worktree", "add", "-q", self.main, "main")

    def test_the_bare_repository_is_the_main_checkout(self):
        self.assertEqual(self.repos("--path", self.main)["svc"].checkout, self.bare)


class DuplicateNameTests(ScanCase):
    def setUp(self):
        super().setUp()
        self.old = self.repo("api", self.path("code/old"))

    def test_a_note_names_every_row_that_shares_the_name(self):
        self.assertIn(f"Name api is on 2 rows ({self.api.path}, {self.old.path}): give each its own name", self.notes())

    def test_write_refuses_the_proposal(self):
        self.scan()
        self.assertEqual(self.write(), (1, f"Name api is on more than one row in {self.out}; give each repository its own name"))


class NotARepositoryTests(ScanCase):
    def test_a_worktree_outside_git_is_refused(self):
        plain = self.path("plain")
        os.makedirs(plain)
        self.assertEqual(run_script("config-setup", "scan", plain, "--out", self.out, env=self.env), (1, f"{plain} is not in a git repository"))


class HomeRootTests(ScanCase):
    def refusal(self, root):
        return run_script("config-setup", "scan", self.feat, "--out", self.out, "--root", root, env=self.env)

    def test_home_is_refused_in_one_line(self):
        self.assertEqual(self.refusal(self.home), (1, f"search root {self.home} is or contains $HOME; name a directory below it"))

    def test_a_root_containing_home_is_refused(self):
        self.assertEqual(self.refusal(self.tmp)[0], 1)

    def test_nothing_is_proposed(self):
        self.refusal(self.home)
        self.assertFalse(os.path.exists(self.out))


class WriteTests(ScanCase):
    def setUp(self):
        super().setUp()
        self.scan()

    def test_it_writes_the_config_under_home_and_prints_its_path(self):
        self.assertEqual(self.write(), (0, self.config_path()))
        self.assertEqual([r.name for r in config.load(self.config_path()).repos], ["api", "web"])

    def test_a_missing_main_checkout_is_refused(self):
        text = read(self.out).replace(self.web.path, self.path("code/web/moved"))
        write_file(self.out, text)
        self.assertEqual(self.write(), (1, f"main checkout {self.path('code/web/moved')} does not exist; fix or remove its row in {self.out}"))
        self.assertFalse(os.path.exists(self.config_path()))

    def test_a_main_checkout_that_is_not_a_git_checkout_is_refused(self):
        plain = self.path("code/web/plain")
        os.makedirs(plain)
        write_file(self.out, read(self.out).replace(self.web.path, plain))
        self.assertEqual(self.write(), (1, f"main checkout {plain} is not a git checkout; fix or remove its row in {self.out}"))

    def test_a_file_without_the_sections_is_refused(self):
        write_file(self.out, "# notes\n")
        code, out = self.write()
        self.assertEqual((code, out), (1, f"{self.out} does not parse: no ## Search roots, ## Repositories, ## Worktrees section"))


class RescanTests(ScanCase):
    def setUp(self):
        super().setUp()
        self.scan()
        text = read(self.out).replace("| api ", "| api-server ").replace("<repo parent>/<branch>", "<repo parent>/wt/<branch>")
        write_file(self.out, text)
        self.write()
        self.worker = self.repo("worker")

    def test_the_users_edits_are_kept(self):
        cfg = self.proposal()
        self.assertEqual((cfg.repos[0].name, cfg.pattern), ("api-server", "<repo parent>/wt/<branch>"))

    def test_a_new_repository_is_appended(self):
        self.assertEqual([r.name for r in self.proposal().repos], ["api-server", "web", "worker"])

    def test_the_new_repository_is_noted(self):
        self.assertIn("new: worker", self.notes())

    def test_a_main_branch_that_matches_origin_head_is_not_noted(self):
        self.assertEqual([n for n in self.notes() if n.startswith("main moved")], [])

    def test_a_main_branch_that_differs_from_origin_head_is_noted(self):
        self.api.git("update-ref", "refs/remotes/origin/trunk", "HEAD")
        self.api.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        self.assertIn(f"main moved: api-server has Main branch main, but origin/HEAD in {self.api.path} is trunk; update the cell", self.notes())

    def test_a_registered_checkout_that_is_gone_is_noted(self):
        os.rename(self.web.path, self.path("code/web/moved"))
        self.assertIn(f"missing: web {self.web.path} no longer exists", self.notes())


if __name__ == "__main__":
    unittest.main()

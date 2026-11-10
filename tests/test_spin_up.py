import contextlib
import datetime
import io
import os
import re
import subprocess
import sys
import unittest
from unittest import mock

from helpers import GIT_ENV, SCRIPTS, TempCase, add_cleanup, add_followup, add_idea, drop_backlog_title, git, init_repo, plugin_text_files, run_ok, run_script, write_config, write_file
import paths

sys.path.insert(0, SCRIPTS)
import backlog
import config
import records

spin_up = records.load_script("spin-up.py")

TODAY = datetime.date.today().isoformat()

USER_WORKTREE_TOOLING = re.compile(r"\bgit[ -]work\b|(?<!\w)\.work\b")


class SpinUpCase(TempCase):
    def setUp(self):
        super().setUp()
        self.home = self.path("home")
        os.makedirs(self.home)
        self.env = {**GIT_ENV, "HOME": self.home}
        self.env.pop(config.ENV, None)
        self.api = init_repo(self.path("api/api-main"))

    def config_path(self):
        return os.path.join(self.home, ".claude", "clerk-dev", "local.md")

    def configure(self, repos=(), pattern="", after_create="", main="main"):
        write_config(self.config_path(), [(name, path, main) for name, path in repos], pattern, after_create)

    def idea(self, title="Phone digits"):
        return add_idea(self.api.path, title, "--scope", "new", "--why", "faster lookups", "--when", "after launch", env=self.env)

    def followup(self, title="Handle exportId"):
        return add_followup(self.api.path, title, "--scope", "new", "--contract", "changed: GET /x: now requires exportId", env=self.env)

    def cleanup(self, title="Remove the export flag"):
        return add_cleanup(self.api.path, title, "--scope", "new", env=self.env)

    def attempt(self, *args):
        return run_script("spin-up", *args, env=self.env)

    def create(self, branch, item, wt=None):
        return run_ok("spin-up", "create", wt or self.api.path, branch, "--item", item, env=self.env)

    def where(self, branch, *extra, wt=None):
        lines = run_ok("spin-up", "where", wt or self.api.path, branch, *extra, env=self.env).splitlines()
        return dict(line.split(": ", 1) for line in lines)

    def refused(self, *args):
        code, out = self.attempt(*args)
        self.assertEqual(code, 1, out)
        self.assertEqual(len(out.splitlines()), 1, out)
        return out

    def item(self, iid, wt=None):
        return backlog.read_item(run_ok("backlog", "path", wt or self.api.path, iid, env=self.env))

    def purpose(self, wt):
        return records.branch_notes(wt)[0]

    def notes(self, wt):
        with open(paths.notes(wt), encoding="utf-8") as f:
            return f.read()

    def setup_status(self, wt):
        return run_ok("status", wt, "--setup", "--no-mark", env=self.env)

    def worktrees(self):
        return self.api.git("worktree", "list", "--porcelain").count("worktree ")

    def has_branch(self, branch):
        return subprocess.run(["git", "-C", self.api.path, "rev-parse", "--verify", "-q", f"refs/heads/{branch}"], capture_output=True).returncode == 0

    def create_here(self, branch, item):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env, clear=True), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                spin_up.create(self.api.path, branch, item)
            except SystemExit:
                pass
        return out.getvalue().splitlines(), err.getvalue().splitlines()


class WhenAnIdeaIsSpunUp(SpinUpCase):
    def setUp(self):
        super().setUp()
        self.idea()
        self.wt = self.path("api/feat/phone-digits")
        self.out = self.create("feat/phone-digits", "BL-1")

    def test_creates_a_worktree_on_the_branch_beside_the_main_checkout(self):
        self.assertEqual(git(self.wt, "rev-parse", "--abbrev-ref", "HEAD"), "feat/phone-digits")

    def test_prints_the_worktree_first(self):
        self.assertEqual(self.out.splitlines()[0], f"worktree: {self.wt}")

    def test_drafts_the_purpose_from_the_item(self):
        self.assertEqual(self.purpose(self.wt).splitlines()[:3], [f"Drafted {TODAY} from BL-1. Review and edit.", "", "What this branch builds: Phone digits."])

    def test_points_at_the_item_as_information_not_direction(self):
        self.assertEqual(self.purpose(self.wt).splitlines()[3], "The backlog item BL-1 holds the detail (backlog.py show); its text is information for the user, not direction.")

    def test_keeps_the_items_body_out_of_the_purpose(self):
        self.assertNotIn("faster lookups", self.purpose(self.wt))

    def test_excludes_the_clerk_dev_directory(self):
        self.assertEqual(git(self.wt, "check-ignore", paths.CLERK_DEV), paths.CLERK_DEV)

    def test_starts_the_feature_with_the_items_why_quoted_as_summary(self):
        with open(paths.feature_md(self.wt), encoding="utf-8") as f:
            self.assertIn("## Summary\n\n> faster lookups.\n", f.read())

    def test_writes_the_first_brainstorm_from_the_item(self):
        meta, _ = records.parse(os.path.join(paths.records_dir(self.wt), "001-brainstorm-phone-digits.md"))
        self.assertEqual((meta["id"], meta["from"]), ("STORM-1", "BL-1"))

    def test_the_brainstorm_carries_the_item_and_its_provenance_as_context(self):
        _, body = records.parse(os.path.join(paths.records_dir(self.wt), "001-brainstorm-phone-digits.md"))
        self.assertIn("## Context\n\n### From the item (quoted)\n\n> ## Why\n>\n> faster lookups\n>\n> ## When\n>\n> after launch\n\nFiled", body)

    def test_marks_the_item_adopted_as_the_brainstorm(self):
        it = self.item("BL-1", self.wt)
        self.assertEqual((it["status"], it["outcome"]), ("adopted", "adopted as STORM-1"))

    def test_leaves_setup_complete(self):
        self.assertEqual(self.setup_status(self.wt), "Setup: complete.")


class WhenAFollowUpIsSpunUp(SpinUpCase):
    def setUp(self):
        super().setUp()
        self.followup()
        self.wt = self.path("api/feat/export-id")
        self.create("feat/export-id", "BL-1")

    def test_keeps_the_contract_out_of_the_purpose(self):
        self.assertNotIn("requires exportId", self.purpose(self.wt))

    def test_quotes_the_contract_in_a_section_apart_from_purpose_and_guidance(self):
        self.assertIn("## From the item (quoted, not Purpose or Guidance)\n\n> Contract: changed: GET /x: now requires exportId", self.notes(self.wt))

    def test_starts_no_feature(self):
        self.assertFalse(os.path.exists(paths.feature_dir(self.wt)))

    def test_rescopes_the_item_to_the_branch_and_leaves_it_owed(self):
        it = self.item("BL-1", self.wt)
        self.assertEqual((it["scope"], it["status"]), ("feat/export-id", "owed"))


class WhenACleanupIsSpunUp(SpinUpCase):
    def setUp(self):
        super().setUp()
        self.cleanup()
        self.wt = self.path("api/chore/remove-the-export-flag")
        self.create("chore/remove-the-export-flag", "BL-1")

    def test_lists_nothing_it_removes_as_deployed_code_it_changes(self):
        self.assertNotIn("EXPORT_V2_FLAG", self.purpose(self.wt))
        self.assertNotIn("Deployed code it changes on purpose", self.notes(self.wt))

    def test_quotes_what_it_removes_apart_from_purpose(self):
        self.assertIn("> Removes: EXPORT_V2_FLAG", self.notes(self.wt))

    def test_leaves_setup_complete(self):
        self.assertEqual(self.setup_status(self.wt), "Setup: complete.")


class WithNoConfig(SpinUpCase):
    def setUp(self):
        super().setUp()
        self.found = self.where("feat/x")

    def test_puts_the_worktree_at_the_repo_parent_and_branch(self):
        self.assertEqual(self.found["path"], self.path("api/feat/x"))

    def test_runs_no_after_create_command(self):
        self.assertEqual(self.found["after-create"], "none")

    def test_bases_on_the_local_main_branch(self):
        self.assertEqual(self.found["base"], "main (local; even with origin/main)")


class TheBase(SpinUpCase):
    def test_counts_local_commits_ahead_of_origin_main(self):
        self.api.commit("local only")
        self.assertEqual(self.where("feat/x")["base"], "main (local; 1 ahead of and 0 behind origin/main)")

    def test_is_origin_main_when_there_is_no_local_main(self):
        self.api.git("checkout", "-q", "-b", "elsewhere")
        self.api.git("branch", "-q", "-D", "main")
        self.assertEqual(self.where("feat/x")["base"], "origin/main (no local main)")


class ThePattern(SpinUpCase):
    def test_places_the_worktree_where_the_pattern_says(self):
        self.configure(pattern="<repo parent>/trees/<repo>-<branch>")
        self.assertEqual(self.where("x")["path"], self.path("api/trees/origin-x"))

    def test_takes_a_relative_pattern_from_the_repo_parent(self):
        self.configure(pattern="trees/<branch>")
        self.assertEqual(self.where("x")["path"], self.path("api/trees/x"))

    def test_creates_the_worktree_there(self):
        self.configure(pattern="trees/<branch>")
        self.idea()
        self.create("x", "BL-1")
        self.assertEqual(git(self.path("api/trees/x"), "rev-parse", "--abbrev-ref", "HEAD"), "x")


class TheAfterCreateCommand(SpinUpCase):
    def setUp(self):
        super().setUp()
        self.idea()
        self.wt = self.path("api/feat/x")

    def test_runs_in_the_new_worktree(self):
        self.configure(after_create="touch spun-up")
        self.create("feat/x", "BL-1")
        self.assertTrue(os.path.exists(os.path.join(self.wt, "spun-up")))

    def test_is_named_by_where(self):
        self.configure(after_create="touch spun-up")
        self.assertEqual(self.where("feat/x")["after-create"], "touch spun-up")

    def test_a_failure_says_to_rerun_it(self):
        self.configure(after_create="exit 3")
        self.assertIn(f"after-create: exit 3 failed with exit 3; rerun it in {self.wt}", self.create("feat/x", "BL-1").splitlines())

    def test_a_failure_does_not_stop_the_seeding(self):
        self.configure(after_create="exit 3")
        self.create("feat/x", "BL-1")
        self.assertTrue(self.purpose(self.wt))

    def test_runs_after_the_seeding(self):
        self.configure(after_create=f"test -f {os.path.relpath(paths.notes(self.wt), self.wt)} && touch seeded-first")
        self.create("feat/x", "BL-1")
        self.assertTrue(os.path.exists(os.path.join(self.wt, "seeded-first")))

    def test_an_interruption_says_to_rerun_it(self):
        with mock.patch.object(spin_up.subprocess, "run", side_effect=KeyboardInterrupt):
            self.assertEqual(spin_up.run_after_create("make setup", self.wt), f"after-create: make setup interrupted; rerun it in {self.wt}")


class WhenTheNameIsTaken(SpinUpCase):
    def setUp(self):
        super().setUp()
        self.idea()
        self.before = self.worktrees()

    def assertNothingCreated(self):
        self.assertEqual(self.worktrees(), self.before)
        self.assertEqual(self.item("BL-1")["status"], "open")

    def test_refuses_a_local_branch(self):
        self.api.git("branch", "feat/x")
        self.assertIn("already exists", self.refused("create", self.api.path, "feat/x", "--item", "BL-1"))
        self.assertNothingCreated()

    def test_refuses_a_branch_on_origin(self):
        self.api.git("push", "-q", "origin", "main:feat/x")
        self.api.git("fetch", "-q", "origin")
        self.assertIn("on origin", self.refused("create", self.api.path, "feat/x", "--item", "BL-1"))
        self.assertNothingCreated()

    def test_refuses_an_existing_path(self):
        os.makedirs(self.path("api/feat/x"))
        self.assertIn("already exists", self.refused("create", self.api.path, "feat/x", "--item", "BL-1"))
        self.assertNothingCreated()


class WhenTheItemIsClosed(SpinUpCase):
    def test_refuses_it(self):
        self.idea()
        run_ok("backlog", "set", self.api.path, "BL-1", "dropped", "--ref", "not needed", env=self.env)
        self.assertEqual("BL-1 is dropped; spin-up takes up open and owed items, and in-progress ones whose branch is gone", self.refused("create", self.api.path, "feat/x", "--item", "BL-1"))


class WhenTheItemIsInProgress(SpinUpCase):
    def setUp(self):
        super().setUp()
        self.followup()
        run_ok("backlog", "set", self.api.path, "BL-1", "in-progress", "--ref", "feat/y", env=self.env)


class OnABranchThatStillExists(WhenTheItemIsInProgress):
    def setUp(self):
        super().setUp()
        self.api.git("branch", "feat/y")

    def test_refuses_it_naming_where_it_is_in_progress(self):
        self.assertEqual(self.refused("create", self.api.path, "feat/x", "--item", "BL-1"), "BL-1 is in-progress on feat/y; spin-up takes up open and owed items, and in-progress ones whose branch is gone")

    def test_leaves_its_scope_alone(self):
        self.refused("create", self.api.path, "feat/x", "--item", "BL-1")
        self.assertEqual(self.item("BL-1")["scope"], "new")


class ScopedToABranchThatStillExists(SpinUpCase):
    def test_refuses_it_naming_that_branch(self):
        self.api.git("branch", "feat/z")
        add_followup(self.api.path, "Handle exportId", "--scope", "feat/z", env=self.env)
        run_ok("backlog", "set", self.api.path, "BL-1", "in-progress", "--ref", "BRIEF-3", env=self.env)
        self.assertIn("BL-1 is in-progress on feat/z;", self.refused("create", self.api.path, "feat/x", "--item", "BL-1"))


class WhenItsBranchIsGone(WhenTheItemIsInProgress):
    def setUp(self):
        super().setUp()
        self.wt = self.path("api/feat/x")
        self.out = self.create("feat/x", "BL-1")

    def test_takes_it_up(self):
        self.assertEqual(self.item("BL-1", self.wt)["scope"], "feat/x")

    def test_sets_it_back_to_owed(self):
        it = self.item("BL-1", self.wt)
        self.assertEqual((it["status"], it.get("ref", "")), ("owed", ""))

    def test_says_it_is_owed_again(self):
        self.assertIn("backlog: BL-1 owed again", self.out.splitlines())


class WhenTheItemHasNoTitle(SpinUpCase):
    def test_drafts_the_purpose_from_its_id(self):
        self.idea()
        drop_backlog_title(self.api.path, "BL-1", env=self.env)
        wt = self.path("api/feat/x")
        self.create("feat/x", "BL-1")
        self.assertEqual(self.purpose(wt).splitlines()[2], "What this branch builds: BL-1.")


class WhenGitWorktreeAddFails(SpinUpCase):
    def setUp(self):
        super().setUp()
        self.followup()
        write_file(self.path("api/feat"), "a file where the worktree's parent would go\n")
        self.out = self.refused("create", self.api.path, "feat/x", "--item", "BL-1")

    def test_says_what_git_said(self):
        self.assertIn("git worktree add -b feat/x", self.out)

    def test_leaves_the_items_scope_and_status_unchanged(self):
        it = self.item("BL-1")
        self.assertEqual((it["scope"], it["status"]), ("new", "owed"))

    def test_leaves_no_branch_behind(self):
        self.assertFalse(self.has_branch("feat/x"))


class WhenSeedingFails(SpinUpCase):
    def setUp(self):
        super().setUp()
        self.followup()
        self.wt = self.path("api/feat/x")
        with mock.patch.object(backlog, "rescope", side_effect=SystemExit("disk full")):
            self.out, self.err = self.create_here("feat/x", "BL-1")

    def undo(self):
        return re.search(r"to retry, run: (.*), then run spin-up.py create again$", self.err[-1]).group(1)

    def test_names_the_new_worktree_and_branch_first(self):
        self.assertEqual(self.out[:2], [f"worktree: {self.wt}", "branch: feat/x"])

    def test_leaves_the_item_unchanged(self):
        self.assertEqual(self.item("BL-1")["scope"], "new")

    def test_the_printed_step_lets_create_run_again(self):
        subprocess.run(self.undo(), shell=True, check=True, env=self.env, capture_output=True)
        self.create("feat/x", "BL-1")
        self.assertEqual(self.item("BL-1", self.wt)["scope"], "feat/x")


class Seeding(SpinUpCase):
    def setUp(self):
        super().setUp()
        self.idea()
        self.wt = self.path("api/feat/x")
        self.create("feat/x", "BL-1")

    def test_refuses_a_worktree_that_already_has_a_purpose(self):
        with mock.patch.dict(os.environ, {"HOME": self.home}), self.assertRaises(SystemExit) as refused:
            spin_up.seed(self.wt, "BL-1")
        self.assertIn("already has a Purpose", str(refused.exception))


class FromAnotherRepository(SpinUpCase):
    def setUp(self):
        super().setUp()
        self.web = init_repo(self.path("web/web-main"))
        self.idea()

    def test_creates_the_worktree_in_the_owning_repository(self):
        self.configure(repos=[("api", self.api.path)])
        self.create("feat/x", "api:BL-1", wt=self.web.path)
        self.assertEqual(git(self.path("api/feat/x"), "rev-parse", "--git-common-dir"), os.path.join(self.api.path, ".git"))

    def test_refuses_without_the_registry(self):
        self.assertIn("No clerk-dev config", self.refused("create", self.web.path, "feat/x", "--item", "api:BL-1"))

    def test_refuses_a_repository_the_config_does_not_name(self):
        self.configure(repos=[("web", self.web.path)])
        self.assertEqual(self.refused("create", self.web.path, "feat/x", "--item", "api:BL-1"), f"repository api is not in {self.config_path()}")

    def test_refuses_a_main_checkout_that_is_not_a_git_checkout(self):
        os.makedirs(self.path("plain"))
        self.configure(repos=[("api", self.path("plain"))])
        self.assertIn(f"{self.path('plain')}, the main checkout of api in {self.config_path()}, is not a git checkout", self.refused("create", self.web.path, "feat/x", "--item", "api:BL-1"))


class WhenTheConfiguredMainBranchDiffersFromOriginHead(SpinUpCase):
    def setUp(self):
        super().setUp()
        self.api.git("push", "-q", "origin", "main:master")
        self.api.git("fetch", "-q", "origin")
        self.configure(repos=[("api", self.api.path)], main="master")
        self.found = self.where("feat/x")

    def test_warns_naming_both_and_the_config_cell(self):
        self.assertEqual(self.found["warning"], f"the Main branch cell of api in {self.config_path()} says master, but origin/HEAD is main; basing on master")

    def test_bases_on_the_configured_branch(self):
        self.assertEqual(self.found["base"], "origin/master (no local master)")


class WhenTheConfiguredMainBranchMatchesOriginHead(SpinUpCase):
    def test_does_not_warn(self):
        self.configure(repos=[("api", self.api.path)], main="main")
        self.assertNotIn("warning", self.where("feat/x"))


class WhenTheConfiguredMainBranchIsMissing(SpinUpCase):
    def test_refuses_naming_the_config_cell(self):
        self.configure(repos=[("api", self.api.path)], main="trunk")
        self.assertEqual(self.refused("where", self.api.path, "feat/x"), f"origin/trunk does not exist in {self.api.path}; fix the Main branch cell of api in {self.config_path()}")


class InABareRepositoryLayout(SpinUpCase):
    def setUp(self):
        super().setUp()
        bare = self.path("svc/svc.git")
        git(self.tmp, "clone", "-q", "--bare", self.api.origin, bare)
        git(bare, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
        git(bare, "fetch", "-q", "origin")
        git(bare, "remote", "set-head", "origin", "main")
        self.main = self.path("svc/main")
        git(bare, "worktree", "add", "-q", self.main, "main")

    def test_puts_the_worktree_beside_the_bare_repository(self):
        self.assertEqual(self.where("feat/x", wt=self.main)["path"], self.path("svc/feat/x"))


class FromAFeatureWorktree(SpinUpCase):
    def test_places_the_new_worktree_beside_the_main_checkout(self):
        self.idea()
        feature = self.path("api/feat/other")
        self.api.git("worktree", "add", "-q", "-b", "feat/other", feature)
        self.create("feat/x", "BL-1", wt=feature)
        self.assertEqual(git(self.path("api/feat/x"), "rev-parse", "--abbrev-ref", "HEAD"), "feat/x")


class ThePluginText(unittest.TestCase):
    def test_names_no_users_own_worktree_tooling(self):
        named = []
        for path in plugin_text_files():
            with open(path, encoding="utf-8") as f:
                named += [f"{path}:{n}" for n, line in enumerate(f, 1) if USER_WORKTREE_TOOLING.search(line)]
        self.assertEqual(named, [])


if __name__ == "__main__":
    unittest.main()

import datetime
import os
import re
import sys
import unittest
from unittest import mock

from helpers import GIT_ENV, SCRIPTS, TempCase, add_backlog_item, git, init_repo, plugin_text_files, run_ok, run_script, write_file

sys.path.insert(0, SCRIPTS)
import backlog
import config
import records

spin_up = records.load_script("spin-up.py")

TODAY = datetime.date.today().isoformat()

CONFIG = """# clerk-dev config

## Search roots

## Repositories

| Name | Main checkout | Main branch |
| ---- | ------------- | ----------- |
{rows}
## Worktrees

Pattern: {pattern}
After create: {after_create}
"""

USER_WORKTREE_TOOLING = re.compile(r"\bgit[ -]work\b|(?<!\w)\.work\b")


class SpinUpCase(TempCase):
    def setUp(self):
        super().setUp()
        self.home = self.path("home")
        os.makedirs(self.home)
        self.env = {**GIT_ENV, "HOME": self.home}
        self.env.pop(config.ENV, None)
        self.api = init_repo(self.path("api/api-main"))

    def configure(self, repos=(), pattern=config.DEFAULT_PATTERN, after_create=""):
        rows = "".join(f"| {name} | {path} | main |\n" for name, path in repos)
        write_file(os.path.join(self.home, ".claude", "clerk-dev", "local.md"), CONFIG.format(rows=rows, pattern=pattern, after_create=after_create))

    def file(self, kind, title, *extra, wt=None):
        return add_backlog_item(wt or self.api.path, kind, title, "--scope", "new", *extra, env=self.env)

    def idea(self, title="Phone digits"):
        return self.file("idea", title, "--why", "faster lookups", "--when", "after launch")

    def followup(self, title="Handle exportId"):
        return self.file("followup", title, "--origin", "web 7c1e2ab", "--contract", "changed: GET /x: now requires exportId")

    def cleanup(self, title="Remove the export flag"):
        return self.file("cleanup", title, "--removes", "EXPORT_V2_FLAG")

    def attempt(self, *args):
        return run_script("spin-up", *args, env=self.env)

    def create(self, branch, item, wt=None):
        return run_ok("spin-up", "create", wt or self.api.path, branch, "--item", item, env=self.env)

    def where(self, branch, *extra):
        lines = run_ok("spin-up", "where", self.api.path, branch, *extra, env=self.env).splitlines()
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

    def setup_status(self, wt):
        return run_ok("status", wt, "--setup", "--no-mark", env=self.env)

    def worktrees(self):
        return self.api.git("worktree", "list", "--porcelain").count("worktree ")


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
        self.assertEqual(self.purpose(self.wt).splitlines()[:3], [f"Drafted {TODAY} from BL-1. Edit freely.", "", "What this branch builds: Phone digits."])

    def test_excludes_the_clerk_dev_directory(self):
        self.assertEqual(git(self.wt, "check-ignore", ".clerk-dev"), ".clerk-dev")

    def test_starts_the_feature_with_the_items_why_as_summary(self):
        with open(os.path.join(self.wt, ".clerk-dev", "feature", "feature.md"), encoding="utf-8") as f:
            self.assertIn("## Summary\n\nfaster lookups\n", f.read())

    def test_writes_the_first_brainstorm_from_the_item(self):
        meta, _ = records.parse(os.path.join(self.wt, ".clerk-dev", "feature", "records", "001-brainstorm-phone-digits.md"))
        self.assertEqual((meta["id"], meta["from"]), ("STORM-1", "BL-1"))

    def test_the_brainstorm_carries_the_item_and_its_provenance_as_context(self):
        _, body = records.parse(os.path.join(self.wt, ".clerk-dev", "feature", "records", "001-brainstorm-phone-digits.md"))
        self.assertIn("## Context\n\n### Why\n\nfaster lookups\n\n### When\n\nafter launch\n\nFiled", body)

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

    def test_puts_the_contract_on_the_first_line_of_what_it_builds(self):
        self.assertIn("What this branch builds: Handle exportId. Contract: changed: GET /x: now requires exportId.", self.purpose(self.wt))

    def test_starts_no_feature(self):
        self.assertFalse(os.path.exists(os.path.join(self.wt, ".clerk-dev", "feature")))

    def test_rescopes_the_item_to_the_branch_and_leaves_it_owed(self):
        it = self.item("BL-1", self.wt)
        self.assertEqual((it["scope"], it["status"]), ("feat/export-id", "owed"))


class WhenACleanupIsSpunUp(SpinUpCase):
    def setUp(self):
        super().setUp()
        self.cleanup()
        self.wt = self.path("api/chore/remove-the-export-flag")
        self.create("chore/remove-the-export-flag", "BL-1")

    def test_lists_what_it_removes_as_deployed_code_it_changes(self):
        self.assertIn("Deployed code it changes on purpose (change with care, state rollout):\n- EXPORT_V2_FLAG", self.purpose(self.wt))

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
        self.assertIn("open items only", self.refused("create", self.api.path, "feat/x", "--item", "BL-1"))


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

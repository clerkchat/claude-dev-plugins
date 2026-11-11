import datetime
import os
import sys
import unittest
from unittest import mock

from helpers import SCRIPTS, TempCase, add_backlog_item, add_cleanup, add_followup, add_idea, git, init_repo, run_ok, run_script, write_config, write_file
import paths

sys.path.insert(0, SCRIPTS)
import backlog
import config

def workspace_md(hub, rows):
    table = "".join(f"| {name} | {path} | |\n" for name, path in rows)
    return f"Hub: {hub}\n\n| Repo | Worktree | Main |\n| --- | --- | --- |\n{table}"


class BacklogCase(TempCase):
    def setUp(self):
        super().setUp()
        self.env = {**os.environ, config.ENV: self.path("absent.md")}
        self.api = init_repo(self.path("api/api-main"), with_origin=False)
        self.feat = self.worktree(self.api, "api/feat", "feat/x")

    def worktree(self, repo, name, branch):
        wt = self.path(name)
        git(repo.path, "worktree", "add", "-q", "-b", branch, wt)
        return wt

    def registry(self, *repos):
        write_config(self.path("local.md"), repos)
        self.env[config.ENV] = self.path("local.md")

    def link_workspace(self, hub_wt, hub, rows):
        text = workspace_md(hub, rows)
        write_file(paths.workspace(hub_wt), text)
        for _, wt in rows:
            if wt != hub_wt:
                os.makedirs(paths.ledger(wt), exist_ok=True)
                os.symlink(paths.workspace(hub_wt), paths.workspace(wt))

    def attempt(self, *args):
        return run_script("backlog", *args, env=self.env)

    def ok(self, *args):
        return run_ok("backlog", *args, env=self.env)

    def refused(self, *args):
        code, out = self.attempt(*args)
        self.assertEqual(code, 1, out)
        self.assertEqual(len(out.splitlines()), 1, out)
        return out

    def add(self, kind, title="An item", wt=None, *extra):
        return add_backlog_item(wt or self.feat, kind, title, *extra, env=self.env)

    def idea(self, title="An idea", *extra, wt=None):
        return add_idea(wt or self.feat, title, *extra, env=self.env)

    def cleanup(self, title="Remove EXPORT_V2_FLAG", *extra, wt=None):
        return add_cleanup(wt or self.feat, title, *extra, env=self.env)

    def followup(self, title="Handle exportId", *extra, wt=None):
        return add_followup(wt or self.feat, title, *extra, env=self.env)

    def meta(self, iid, wt=None):
        return backlog.read_item(self.ok("path", wt or self.feat, iid))

    def listed(self, *args, wt=None):
        return self.ok("list", wt or self.feat, *args).splitlines()

    def ids_listed(self, *args, wt=None):
        return [line.split()[0] for line in self.listed(*args, wt=wt)]

    def backlog_dir(self, repo):
        return os.path.join(repo.path, ".git", "clerk-dev", "backlog")


class AddTests(BacklogCase):
    def test_an_idea_is_filed_open_in_this_repositorys_backlog(self):
        self.assertEqual(self.idea(), "BL-1")
        self.assertTrue(os.path.exists(os.path.join(self.backlog_dir(self.api), "001.md")))
        self.assertEqual(self.meta("BL-1")["status"], "open")

    def test_the_scope_defaults_to_the_hubs_branch(self):
        self.idea()
        self.assertEqual(self.meta("BL-1")["scope"], "feat/x")

    def test_a_cleanup_and_a_follow_up_are_owed(self):
        self.cleanup()
        self.followup()
        self.assertEqual([self.meta("BL-1")["status"], self.meta("BL-2")["status"]], ["owed", "owed"])

    def test_provenance_comes_from_the_worktree(self):
        self.idea()
        m = self.meta("BL-1")
        self.assertEqual((m["repo"], m["branch"], m["date"], m["from"]), ("api-main", "feat/x", datetime.date.today().isoformat(), "this session"))

    def test_from_is_free_text(self):
        self.idea("An idea", "--from", "2026-11-06-review 8")
        self.assertEqual(self.meta("BL-1")["from"], "2026-11-06-review 8")

    def test_why_and_when_become_body_sections_under_the_heading(self):
        self.idea("Phone digits", "--why", "faster", "--when", "after launch")
        self.assertEqual(self.meta("BL-1")["body"], "\n# BL-1. Phone digits\n\n## Why\n\nfaster\n\n## When\n\nafter launch\n")

    def test_a_body_file_is_written_under_the_heading(self):
        write_file(self.path("body.md"), "The need, as a paragraph.\n")
        self.followup("Handle exportId", "--body", self.path("body.md"))
        self.assertEqual(self.meta("BL-1")["body"], "\n# BL-1. Handle exportId\n\nThe need, as a paragraph.\n")

    def test_sections_with_nothing_to_say_are_left_out(self):
        self.idea("Phone digits", "--when", "after launch")
        self.assertNotIn("## Why", self.meta("BL-1")["body"])

    def test_repos_and_area_are_kept(self):
        self.idea("An idea", "--repos", "web, worker", "--area", "Delivery Path")
        m = self.meta("BL-1")
        self.assertEqual((m["repos"], m["area"]), ("web, worker", "delivery-path"))

    def test_the_cleanup_fields_are_kept(self):
        self.cleanup("Remove EXPORT_V2_FLAG", "--trigger", "flag at 100%")
        m = self.meta("BL-1")
        self.assertEqual((m["removes"], m["trigger"]), ("EXPORT_V2_FLAG", "flag at 100%"))

    def test_the_follow_up_fields_are_kept(self):
        self.followup("Handle exportId", "--contract", "changed: x", "--finding", "web 8")
        m = self.meta("BL-1")
        self.assertEqual((m["origin"], m["contract"], m["finding"]), ("web 7c1e2ab", "changed: x", "web 8"))

    def test_numbering_continues_after_a_higher_existing_number(self):
        write_file(os.path.join(self.backlog_dir(self.api), "007.md"), "---\nid: BL-7\nkind: idea\ntitle: Old\nstatus: open\nscope: new\n---\n")
        self.assertEqual(self.idea(), "BL-8")

    def test_a_scope_of_new_stays_in_this_repository(self):
        self.assertEqual(self.idea("An idea", "--scope", "new"), "BL-1")
        self.assertEqual(self.meta("BL-1")["scope"], "new")


class AddRefusalTests(BacklogCase):
    def test_a_detached_hub_needs_a_scope(self):
        git(self.feat, "checkout", "-q", "--detach")
        self.assertIn("detached", self.refused("add", self.feat, "x", "--kind", "idea"))
        self.assertEqual(self.idea("x", "--scope", "new"), "BL-1")

    def test_another_kinds_fields_are_refused(self):
        out = self.refused("add", self.feat, "x", "--kind", "idea", "--removes", "y", "--origin", "a b")
        self.assertEqual(out, "--removes, --origin: not a field of an idea")

    def test_a_cleanup_needs_a_trigger_or_what_it_removes(self):
        self.assertIn("--trigger or --removes", self.refused("add", self.feat, "x", "--kind", "cleanup"))

    def test_a_follow_up_needs_an_origin(self):
        self.assertIn("--origin", self.refused("add", self.feat, "x", "--kind", "followup"))

    def test_a_title_blank_after_its_dots_is_refused(self):
        self.assertEqual(self.refused("add", self.feat, "...", "--kind", "idea"), "the title is blank; give the item a title")

    def test_repo_without_workspace_or_config_gives_the_setup_line(self):
        out = self.refused("add", self.feat, "x", "--kind", "followup", "--origin", "a b", "--repo", "web")
        self.assertEqual(out, config.MISSING.format(self.path("absent.md")))


class TwoRepositoryCase(BacklogCase):
    def setUp(self):
        super().setUp()
        self.web = init_repo(self.path("web/web-main"), with_origin=False)
        self.web_feat = self.worktree(self.web, "web/feat", "feat/web-x")


class HubTests(TwoRepositoryCase):
    def setUp(self):
        super().setUp()
        self.link_workspace(self.feat, "api", [("api", self.feat), ("web", self.web_feat)])

    def test_a_feature_idea_from_the_other_repository_lands_in_the_hubs_backlog_qualified(self):
        self.assertEqual(self.idea(wt=self.web_feat), "api:BL-1")
        self.assertTrue(os.path.exists(os.path.join(self.backlog_dir(self.api), "001.md")))

    def test_the_idea_is_scoped_to_the_hubs_branch_with_its_own_provenance(self):
        self.idea(wt=self.web_feat)
        m = self.meta("BL-1")
        self.assertEqual((m["scope"], m["repo"], m["branch"]), ("feat/x", "web", "feat/web-x"))

    def test_a_follow_up_from_the_other_repository_stays_in_its_own_backlog(self):
        self.assertEqual(self.followup(wt=self.web_feat), "BL-1")
        self.assertTrue(os.path.exists(os.path.join(self.backlog_dir(self.web), "001.md")))

    def test_repo_files_through_the_workspace_rows(self):
        self.assertEqual(self.followup("Handle exportId", "--repo", "web"), "web:BL-1")
        self.assertEqual(self.meta("web:BL-1")["repo"], "api")

    def test_the_other_repository_lists_the_hubs_feature_ideas_qualified(self):
        self.idea("Phone digits", wt=self.web_feat)
        self.assertEqual(self.listed(wt=self.web_feat), ["api:BL-1 idea open feat/x: Phone digits  [from this session]"])

    def test_a_qualified_id_reaches_the_item_from_the_other_repository(self):
        self.idea(wt=self.web_feat)
        self.assertEqual(self.ok("set", self.web_feat, "api:BL-1", "adopted", "--ref", "STORM-1"), "api:BL-1 adopted (adopted as STORM-1)")
        self.assertEqual(self.ok("path", self.web_feat, "api:bl1"), os.path.join(self.backlog_dir(self.api), "001.md"))

    def test_a_bare_id_only_in_the_hub_reaches_it_from_the_other_repository(self):
        self.idea(wt=self.web_feat)
        self.assertEqual(self.ok("path", self.web_feat, "BL-1"), os.path.join(self.backlog_dir(self.api), "001.md"))

    def test_an_id_that_is_not_a_backlog_id_is_refused(self):
        self.assertIn("not a backlog id", self.refused("show", self.feat, "DEC-4"))


class SameIdInBothBacklogsTests(TwoRepositoryCase):
    def setUp(self):
        super().setUp()
        self.link_workspace(self.feat, "api", [("api", self.feat), ("web", self.web_feat)])
        self.idea("Hub feature idea")
        self.idea("Web's own idea", "--scope", "new", wt=self.web_feat)

    def test_a_bare_id_is_refused_naming_both(self):
        self.assertEqual(self.refused("set", self.web_feat, "BL-1", "adopted", "--ref", "DEC-1"), "BL-1 is in more than one backlog; name one: web:BL-1 or api:BL-1")

    def test_the_qualified_hub_id_leaves_the_own_item_alone(self):
        self.ok("set", self.web_feat, "api:BL-1", "adopted", "--ref", "DEC-1")
        self.assertEqual(self.meta("web:BL-1", wt=self.web_feat)["status"], "open")

    def test_from_the_hub_the_bare_id_is_the_hubs_own(self):
        self.assertEqual(self.ok("path", self.feat, "BL-1"), os.path.join(self.backlog_dir(self.api), "001.md"))


class StaleWorkspaceRowTests(TwoRepositoryCase):
    def setUp(self):
        super().setUp()
        write_file(paths.workspace(self.feat), workspace_md("api", [("api", self.feat), ("web", self.path("web/removed"))]))

    def test_repo_falls_through_to_the_registry(self):
        self.registry(("web", self.web.path, "main"))
        self.followup("Handle exportId", "--repo", "web", "--scope", "new")
        self.assertTrue(os.path.exists(os.path.join(self.backlog_dir(self.web), "001.md")))

    def test_repo_without_a_registry_is_refused(self):
        out = self.refused("add", self.feat, "x", "--kind", "followup", "--origin", "a b", "--repo", "web")
        self.assertEqual(out, config.MISSING.format(self.path("absent.md")))

    def test_nothing_is_filed_outside_a_checkout(self):
        os.makedirs(self.path("plain"))
        out = self.refused("add", self.path("plain"), "x", "--kind", "idea", "--scope", "new")
        self.assertEqual(out, f"{self.path('plain')} is not a git checkout, so plain has no backlog there")


class NonHubFollowUpTests(TwoRepositoryCase):
    def setUp(self):
        super().setUp()
        self.link_workspace(self.feat, "api", [("api", self.feat), ("web", self.web_feat)])
        self.followup("Handle exportId", "--scope", "feat/web-x", wt=self.web_feat)

    def test_a_follow_up_scoped_to_the_worktrees_own_branch_is_in_the_default_view(self):
        self.assertEqual(self.ids_listed("--kind", "followup", wt=self.web_feat), ["BL-1"])

    def test_it_is_not_marked_orphaned_in_its_own_repository(self):
        self.assertNotIn("branch gone", self.listed("--kind", "followup", wt=self.web_feat)[0])


class ListTests(BacklogCase):
    def setUp(self):
        super().setUp()
        git(self.api.path, "branch", "-q", "feat/other")
        self.idea("Feature idea")
        self.idea("New idea", "--scope", "new")
        self.idea("Other feature idea", "--scope", "feat/other")
        self.cleanup("Remove flag", "--scope", "new")
        self.followup("Owed here")
        self.followup("Owed to another feature", "--scope", "feat/other")
        self.ok("set", self.feat, "BL-5", "done", "--ref", "1a2b3c4")

    def test_the_default_list_shows_this_features_and_new_work_open_items(self):
        self.assertEqual(self.ids_listed(), ["BL-1", "BL-2", "BL-4"])

    def test_all_shows_everything(self):
        self.assertEqual(self.ids_listed("--all"), ["BL-1", "BL-2", "BL-3", "BL-4", "BL-5", "BL-6"])

    def test_scope_narrows(self):
        self.assertEqual(self.ids_listed("--scope", "new"), ["BL-2", "BL-4"])

    def test_kind_narrows(self):
        self.assertEqual(self.ids_listed("--kind", "idea"), ["BL-1", "BL-2"])

    def test_an_item_without_a_title_still_lists(self):
        write_file(os.path.join(self.backlog_dir(self.api), "007.md"), "---\nid: BL-7\nkind: idea\nstatus: open\nscope: new\n---\n")
        self.assertEqual(self.listed("--kind", "idea")[-1], "BL-7 idea open new: ")

    def test_the_line_carries_id_kind_status_scope_and_title(self):
        self.assertEqual(self.listed("--kind", "cleanup"), ["BL-4 cleanup owed new: Remove flag  [from this session]"])

    def test_the_in_process_reader_returns_the_frontmatter_with_path_owner_and_body(self):
        with mock.patch.dict(os.environ, self.env):
            found = backlog.read(self.feat, kind="followup", include_closed=True)
        self.assertEqual([(it["id"], it["owner"], it["qualified"], it["orphaned"]) for it in found], [("BL-5", "api-main", "BL-5", False), ("BL-6", "api-main", "BL-6", False)])
        self.assertIn("# BL-5. Owed here", found[0]["body"])
        self.assertTrue(found[0]["path"].endswith("005.md"))


class OrphanTests(BacklogCase):
    def setUp(self):
        super().setUp()
        self.worktree(self.api, "api/gone", "feat/gone")
        self.idea("Will be orphaned", "--scope", "feat/gone")
        self.followup("Owed to the gone branch", "--scope", "feat/gone")

    def test_an_item_whose_branch_exists_is_not_orphaned(self):
        self.assertEqual(self.ids_listed(), [])

    def test_a_branch_checked_out_in_a_worktree_still_counts(self):
        self.assertEqual(self.ids_listed("--scope", "feat/gone"), ["BL-1", "BL-2"])
        self.assertNotIn("branch gone", self.listed("--scope", "feat/gone")[0])

    def test_items_are_marked_once_the_branch_is_gone(self):
        git(self.api.path, "worktree", "remove", self.path("api/gone"))
        git(self.api.path, "branch", "-q", "-D", "feat/gone")
        self.assertEqual(self.listed()[0], "BL-1 idea open feat/gone: Will be orphaned  [from this session; from feat/gone, branch gone]")

    def test_a_failed_git_call_exits_rather_than_reading_as_no_branches(self):
        with self.assertRaisesRegex(SystemExit, "^git worktree list --porcelain failed in "):
            backlog.branches(self.path("nowhere"))

    def test_orphans_show_whatever_the_scope_filter_says(self):
        git(self.api.path, "worktree", "remove", self.path("api/gone"))
        git(self.api.path, "branch", "-q", "-D", "feat/gone")
        self.assertEqual(self.ids_listed("--scope", "new"), ["BL-1", "BL-2"])


class OwedTests(BacklogCase):
    def setUp(self):
        super().setUp()
        git(self.api.path, "branch", "-q", "feat/other")
        self.worktree(self.api, "api/gone", "feat/gone")
        self.followup("Owed here")
        self.followup("New work", "--scope", "new")
        self.followup("Owed to another feature", "--scope", "feat/other")
        self.followup("Owed to the gone branch", "--scope", "feat/gone")
        self.idea("Feature idea")
        self.followup("Done here")
        self.ok("set", self.feat, "BL-6", "done", "--ref", "1a2b3c4")
        git(self.api.path, "worktree", "remove", self.path("api/gone"))
        git(self.api.path, "branch", "-q", "-D", "feat/gone")

    def test_lists_only_the_open_follow_ups_scoped_to_this_branch(self):
        self.assertEqual(self.ids_listed("--owed"), ["BL-1"])

    def test_all_adds_the_closed_ones_scoped_here(self):
        self.assertEqual(self.ids_listed("--owed", "--all"), ["BL-1", "BL-6"])

    def test_the_in_process_read_is_the_same_set(self):
        self.assertEqual([it["id"] for it in backlog.owed_followups(self.feat)], ["BL-1"])

    def test_a_kind_or_scope_beside_it_is_refused(self):
        self.assertEqual(self.refused("list", self.feat, "--owed", "--scope", "new"), "--owed and --parked take no --kind, --scope, or --repo")


class ParkedTests(TwoRepositoryCase):
    def setUp(self):
        super().setUp()
        self.link_workspace(self.feat, "api", [("api", self.feat), ("web", self.web_feat)])
        self.idea("Phone digits", wt=self.web_feat)
        self.idea("Web's own new idea", "--scope", "new", wt=self.web_feat)

    def test_lists_the_features_ideas_from_the_hub(self):
        self.assertEqual(self.ids_listed("--parked", wt=self.web_feat), ["api:BL-1"])

    def test_matches_the_count_status_gives(self):
        self.assertEqual(len(self.listed("--parked", wt=self.web_feat)), len(backlog.feature_ideas(self.web_feat)))


class FollowUpLineTests(BacklogCase):
    def setUp(self):
        super().setUp()
        self.followup("Handle exportId", "--contract", "changed: GET /download now requires exportId", "--finding", "api 8")
        self.ok("instruct", self.feat, "BL-1", "Refine")

    def test_the_line_shows_its_origin_as_where_it_came_from(self):
        self.assertEqual(self.listed("--owed"), ["BL-1 followup owed feat/x: Handle exportId  [from web 7c1e2ab]"])

    def test_full_puts_contract_finding_and_instruction_under_it(self):
        self.assertEqual(self.listed("--owed", "--full")[1:], ["  contract: changed: GET /download now requires exportId", "  finding: api 8", "  instruction: Refine"])


class IdeaLineTests(BacklogCase):
    def setUp(self):
        super().setUp()
        self.idea("Phone digits", "--why", "Fewer typos.", "--when", "After the card ships.")

    def test_full_puts_why_and_when_under_it(self):
        self.assertEqual(self.listed("--parked", "--full")[1:], ["  why: Fewer typos", "  when: After the card ships"])

    def test_without_full_it_is_one_line(self):
        self.assertEqual(len(self.listed("--parked")), 1)


class SetTests(BacklogCase):
    def setUp(self):
        super().setUp()
        self.idea()
        self.followup()

    def test_in_progress_writes_the_ref(self):
        self.assertEqual(self.ok("set", self.feat, "BL-2", "in-progress", "--ref", "BRIEF-12"), "BL-2 in-progress (BRIEF-12)")
        self.assertEqual(self.meta("BL-2")["ref"], "BRIEF-12")

    def test_done_writes_the_outcome_and_clears_the_ref(self):
        self.ok("set", self.feat, "BL-2", "in-progress", "--ref", "BRIEF-12")
        self.ok("set", self.feat, "BL-2", "done", "--ref", "1a2b3c4")
        m = self.meta("BL-2")
        self.assertEqual((m["status"], m["outcome"], m.get("ref")), ("done", "done in 1a2b3c4", None))

    def test_done_keeps_the_brief_a_grown_follow_up_names(self):
        self.ok("set", self.feat, "BL-2", "done", "--ref", "1a2b3c4 (BRIEF-62)")
        self.assertEqual(self.meta("BL-2")["outcome"], "done in 1a2b3c4 (BRIEF-62)")

    def test_dropped_writes_the_reason(self):
        self.ok("set", self.feat, "BL-1", "dropped", "--ref", "not worth it")
        self.assertEqual(self.meta("BL-1")["outcome"], "dropped: not worth it")

    def test_adopted_writes_the_record(self):
        self.ok("set", self.feat, "BL-1", "adopted", "--ref", "DEC-60")
        self.assertEqual(self.meta("BL-1")["outcome"], "adopted as DEC-60")

    def test_owed_clears_ref_and_outcome(self):
        self.ok("set", self.feat, "BL-2", "done", "--ref", "1a2b3c4")
        self.ok("set", self.feat, "BL-2", "owed")
        m = self.meta("BL-2")
        self.assertEqual((m["status"], m.get("ref"), m.get("outcome")), ("owed", None, None))

    def test_the_body_and_provenance_survive_a_rewrite(self):
        before = self.meta("BL-1")
        self.ok("set", self.feat, "BL-1", "adopted", "--ref", "DEC-60")
        after = self.meta("BL-1")
        self.assertEqual(after["body"], before["body"])
        self.assertEqual({k: after[k] for k in backlog.PROVENANCE}, {k: before[k] for k in backlog.PROVENANCE})

    def test_another_kinds_status_is_refused(self):
        self.assertEqual(self.refused("set", self.feat, "BL-1", "owed"), "BL-1 is an idea; its statuses are open, adopted, dropped")
        self.assertIn("owed, in-progress, done, dropped", self.refused("set", self.feat, "BL-2", "adopted", "--ref", "x"))

    def test_a_closing_status_needs_a_ref(self):
        self.assertEqual(self.refused("set", self.feat, "BL-2", "done"), "done needs --ref")
        self.assertEqual(self.refused("set", self.feat, "BL-2", "in-progress"), "in-progress needs --ref")

    def test_a_missing_item_is_refused(self):
        self.assertIn("BL-9 not found", self.refused("set", self.feat, "BL-9", "owed"))


class InstructTests(BacklogCase):
    def setUp(self):
        super().setUp()
        self.idea()
        self.followup()

    def test_sets_the_instruction_with_its_note(self):
        self.assertEqual(self.ok("instruct", self.feat, "BL-2", "fix as noted", "--note", "use the banner"), "BL-2: Fix as noted: use the banner")
        self.assertEqual(self.meta("BL-2")["instruction"], "Fix as noted: use the banner")

    def test_an_unknown_word_is_refused(self):
        self.assertIn("unknown instruction", self.refused("instruct", self.feat, "BL-2", "Ponder"))

    def test_only_a_follow_up_takes_one(self):
        self.assertEqual(self.refused("instruct", self.feat, "BL-1", "Refine"), "BL-1 is an idea; only a follow-up takes an instruction")


class RescopeTests(BacklogCase):
    def setUp(self):
        super().setUp()
        self.followup()

    def test_changes_the_scope_only(self):
        before = self.meta("BL-1")
        self.assertEqual(self.ok("rescope", self.feat, "BL-1", "new"), "BL-1 scoped to new")
        after = self.meta("BL-1")
        self.assertEqual(after["scope"], "new")
        self.assertEqual({k: v for k, v in after.items() if k != "scope"}, {k: v for k, v in before.items() if k != "scope"})


class RegistryTests(TwoRepositoryCase):
    def setUp(self):
        super().setUp()
        self.registry(("api", self.api.path, "main"), ("web", self.web.path, "main"))

    def test_repo_files_through_the_registry_and_prints_the_qualified_id(self):
        self.assertEqual(self.followup("Handle exportId", "--repo", "web", "--scope", "new"), "web:BL-1")
        self.assertEqual(self.meta("web:BL-1")["scope"], "new")

    def test_items_elsewhere_naming_this_repository_are_cross_repo_rows(self):
        self.idea("Shared idea", "--scope", "new", "--repos", "api, worker", wt=self.web_feat)
        self.assertEqual(self.listed(), ["web:BL-1 idea open new: Shared idea  [from this session; owned by web, also touches api]"])

    def test_items_elsewhere_not_naming_this_repository_are_not_shown(self):
        self.idea("Web only", "--scope", "new", wt=self.web_feat)
        self.assertEqual(self.listed(), [])

    def test_kind_followup_reads_this_repository_only(self):
        self.followup("Shared", "--scope", "new", "--repos", "api", wt=self.web_feat)
        self.assertEqual(self.listed("--kind", "followup"), [])
        self.assertEqual(self.ids_listed("--kind", "cleanup"), [])

    def test_repo_lists_that_repositorys_backlog(self):
        self.idea("Web only", "--scope", "new", wt=self.web_feat)
        self.assertEqual(self.ids_listed("--repo", "web"), ["web:BL-1"])

    def test_an_unregistered_name_is_refused(self):
        self.assertIn("worker", self.refused("list", self.feat, "--repo", "worker"))

    def test_a_registered_checkout_that_is_not_a_git_checkout_is_refused(self):
        os.makedirs(self.path("plain"))
        self.registry(("worker", self.path("plain"), "main"))
        out = self.refused("add", self.feat, "x", "--kind", "followup", "--origin", "a b", "--repo", "worker")
        self.assertEqual(out, f"repository worker is not in the workspace manifest ({paths.workspace(self.feat)}) or {self.path('local.md')}, and {self.path('plain')} is not a git checkout")


class HubWithRegistryTests(TwoRepositoryCase):
    def setUp(self):
        super().setUp()
        self.registry(("api", self.api.path, "main"), ("web", self.web.path, "main"))
        self.link_workspace(self.feat, "api", [("api", self.feat), ("web", self.web_feat)])

    def test_a_hub_idea_naming_this_repository_is_listed_once(self):
        self.idea("Contact card shows number", "--repos", "web", wt=self.web_feat)
        self.assertEqual(self.listed("--kind", "idea", wt=self.web_feat), ["api:BL-1 idea open feat/x: Contact card shows number  [from this session]"])


class CheckCase(TempCase):
    def setUp(self):
        super().setUp()
        self.env = {**os.environ, config.ENV: self.path("absent.md")}
        self.api = init_repo(self.path("api/api-main"))
        self.feat = self.path("api/feat")
        git(self.api.path, "worktree", "add", "-q", "-b", "feat/x", self.feat)
        self.api.commit("EXPORT_V2_FLAG = true", "flags.txt")
        self.api.git("push", "-q", "origin", "main")
        self.iid = run_ok("backlog", "add", self.feat, "Remove EXPORT_V2_FLAG", "--kind", "cleanup", "--scope", "new", "--removes", "EXPORT_V2_FLAG", env=self.env)

    def check(self, *args):
        return run_ok("backlog", "check", self.feat, *args, env=self.env).splitlines()

    def remove_the_flag(self):
        write_file(os.path.join(self.api.path, "flags.txt"), "nothing here\n")
        self.api.git("commit", "-qam", "remove the flag")
        self.api.git("push", "-q", "origin", "main")


class CheckTests(CheckCase):
    def test_a_key_on_origin_main_is_still_present(self):
        self.assertEqual(self.check()[0], "BL-1 Remove EXPORT_V2_FLAG: EXPORT_V2_FLAG still present on origin/main")

    def test_a_removed_key_is_gone(self):
        self.remove_the_flag()
        self.assertEqual(self.check()[0], "BL-1 Remove EXPORT_V2_FLAG: EXPORT_V2_FLAG gone from origin/main")

    def test_a_local_removal_not_on_origin_does_not_count(self):
        write_file(os.path.join(self.api.path, "flags.txt"), "nothing here\n")
        self.api.git("commit", "-qam", "remove the flag")
        self.assertIn("still present", self.check()[0])

    def test_an_in_progress_cleanup_shows_its_ref(self):
        run_ok("backlog", "set", self.feat, "BL-1", "in-progress", "--ref", "BRIEF-3", env=self.env)
        self.assertTrue(self.check()[0].endswith("(in progress: BRIEF-3)"))

    def test_a_done_cleanup_is_not_checked(self):
        run_ok("backlog", "set", self.feat, "BL-1", "done", "--ref", "1a2b3c4", env=self.env)
        self.assertEqual(len(self.check()), 1)

    def test_a_trigger_only_cleanup_shows_its_trigger_and_age(self):
        run_ok("backlog", "add", self.feat, "Drop v1", "--kind", "cleanup", "--scope", "new", "--trigger", "all clients on v2", env=self.env)
        self.assertEqual(self.check()[1], "BL-2 Drop v1: trigger: all clients on v2, 0 days old")

    def test_the_last_line_is_the_fetch_time(self):
        self.assertRegex(self.check()[-1], r"^last fetch: \d{4}-\d{2}-\d{2} \d{2}:\d{2} \(.* ago\)$")

    def test_one_item_checks_that_item(self):
        self.assertEqual(len(self.check("BL-1")), 2)

    def test_the_registrys_main_branch_wins(self):
        write_config(self.path("local.md"), [("api", self.api.path, "master")])
        self.env[config.ENV] = self.path("local.md")
        code, out = run_script("backlog", "check", self.feat, env=self.env)
        self.assertEqual(code, 1)
        self.assertIn("origin/master", out)

    def test_without_a_remote_main_it_refuses_in_one_line(self):
        self.api.git("remote", "remove", "origin")
        code, out = run_script("backlog", "check", self.feat, env=self.env)
        self.assertEqual((code, len(out.splitlines())), (1, 1))
        self.assertIn("no remote main", out)

    def test_a_non_cleanup_is_refused(self):
        run_ok("backlog", "add", self.feat, "An idea", "--kind", "idea", env=self.env)
        code, out = run_script("backlog", "check", self.feat, "BL-2", env=self.env)
        self.assertEqual((code, out), (1, "BL-2 is an idea; check looks at cleanups"))


if __name__ == "__main__":
    unittest.main()

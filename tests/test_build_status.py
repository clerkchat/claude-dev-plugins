import os
import shutil
import stat
import unittest

from helpers import (
    TempCase,
    clone,
    init_repo,
    run_script,
    write_feature_md,
    write_record,
)

PLAN_BODY = (
    "1. Piece one, spec R5. Done: when five is built.\n"
    "2. Piece two, the second thing. Done: when it is.\n"
    "3. Piece three, decisions R1 and R3. Done: when both are.\n"
    "4. Piece four, decision R1. Done: when R3 is.\n"
    "5. Piece five, nothing named. Done: never."
)

SPEC_BODY = "## Requirements\n\n1. {a}.\n2. {b}.\n\n## Baseline\n\nClean."

OVERVIEW = """# Overview

## Plan

| Piece | Spec | Built |
|---|---|---|
| 1 Piece one | R5 | 2 of 2 built |
| 2 Piece two | none | built, abc1234 |
| 3 Piece three | none | not started |
| 4 Piece four | none | Built |
"""


def digest_head(repo, record_id):
    for line in repo.digest().splitlines():
        if line.startswith(f"===== {record_id} "):
            return line
    raise AssertionError(f"no digest line for {record_id}")


def progress_section(repo):
    lines = repo.digest().splitlines()
    start = lines.index("# Build progress")
    end = lines.index("# Ideas")
    return "\n".join(lines[start : end + 1])


class StatusCase(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("work"))
        self.repo.git("checkout", "-q", "-b", "feat")
        root = self.repo.path
        write_feature_md(root)
        write_record(root, "R1", "decision", "Decision one", body="## Decision\n\nOne.")
        write_record(root, "R3", "decision", "Decision three", body="## Decision\n\nThree.")
        write_record(root, "R4", "plan", "Active plan", body=PLAN_BODY)
        write_record(root, "R5", "spec", "Spec five", body=SPEC_BODY.format(a="Five one", b="Five two"))
        write_record(root, "R6", "spec", "Spec six", body=SPEC_BODY.format(a="Six one", b="Six two"))
        write_record(root, "R9", "spec", "Spec nine", body=SPEC_BODY.format(a="Nine one", b="Nine two"))
        with open(os.path.join(root, ".clerk-dev", "feature", "overview.md"), "w") as f:
            f.write(OVERVIEW)
        self.c1 = self.repo.commit("feat: decision one")
        self.c2 = self.repo.commit("feat: plan step two")
        self.c3 = self.repo.commit("feat: spec six")
        self.c4 = self.repo.commit("feat: spec five")
        self.c5 = self.repo.commit("feat: unlogged work")
        self.repo.build_ok("built", "R1", "--commit", self.c1)
        self.repo.build_ok("built", "R4.2", "--commit", self.c2)
        self.repo.build_ok("built", "R6", "--commit", self.c3)
        self.repo.build_ok("add", "Five piece", "--spec", "R5", "--reqs", "1,2")
        self.repo.build_ok("done", "BUILD-4", "--commit", self.c4)

    def implementation(self, repo=None):
        code, out = (repo or self.repo).status("--focus", "implementation")
        self.assertEqual(code, 0, out)
        return out

    def everything(self, repo=None):
        code, out = (repo or self.repo).status()
        self.assertEqual(code, 0, out)
        return out


class DigestBuiltMarkTests(StatusCase):
    def test_a_decision_an_entry_names_reads_built_yes_with_its_commit(self):
        self.assertTrue(digest_head(self.repo, "DEC-1").endswith(f"; built: yes ({self.c1}))"))

    def test_a_decision_no_entry_names_reads_built_no(self):
        self.assertTrue(digest_head(self.repo, "DEC-3").endswith("; built: no)"))

    def test_a_spec_built_through_pieces_reads_built_yes(self):
        self.assertTrue(digest_head(self.repo, "BRIEF-5").endswith("; built: yes)"))

    def test_a_spec_built_by_a_whole_spec_entry_reads_built_yes(self):
        self.assertTrue(digest_head(self.repo, "BRIEF-6").endswith("; built: yes)"))

    def test_a_spec_with_nothing_logged_reads_built_no(self):
        self.assertTrue(digest_head(self.repo, "BRIEF-9").endswith("; built: no)"))

    def test_a_plan_reads_n_of_m_steps(self):
        self.assertTrue(digest_head(self.repo, "PLAN-4").endswith("; built: 3 of 5 steps (1, 2, 4))"))


class DigestProgressTests(StatusCase):
    def test_per_spec_lines_stay_first(self):
        lines = progress_section(self.repo).splitlines()
        self.assertEqual(lines[2], "origin: BRIEF-5 Spec five: 2 of 2 requirements done")

    def test_records_built_directly_are_listed_per_repository(self):
        self.assertIn(
            f"origin: records built directly: DEC-1 ({self.c1}), PLAN-4.2 ({self.c2}), BRIEF-6 ({self.c3})",
            progress_section(self.repo),
        )

    def test_each_plans_built_steps_come_after_the_records_line(self):
        section = progress_section(self.repo)
        self.assertIn("origin: PLAN-4 steps built: 1, 2, 4", section)
        self.assertGreater(section.index("steps built"), section.index("records built directly"))


class NamesTests(StatusCase):
    def names(self):
        return run_script("records", "names", self.repo.path, "B1", "BUILD-2", "b4", "R4.2", "R5.1", "R4.9", "R6.7")[1]

    def test_a_record_entry_reads_as_a_handoff_for_its_record(self):
        self.assertIn("B1: handoff for DEC-1: Decision one", self.names())

    def test_a_plan_step_entry_reads_as_a_handoff_for_the_step(self):
        self.assertIn("BUILD-2: handoff for PLAN-4.2: Piece two, the second thing", self.names())

    def test_a_brief_handoff_reads_as_a_handoff(self):
        self.assertIn("b4: handoff: Five piece", self.names())

    def test_a_plan_step_reference_reads_as_the_steps_piece(self):
        self.assertIn("R4.2: step 2 of plan PLAN-4: Piece two, the second thing", self.names())

    def test_a_spec_requirement_still_reads_as_a_requirement(self):
        self.assertIn("R5.1: requirement of BRIEF-5: Five one", self.names())

    def test_a_missing_step_or_requirement_is_unknown(self):
        names = self.names()
        self.assertIn("R4.9: unknown", names)
        self.assertIn("R6.7: unknown", names)


class DesignViewTests(StatusCase):
    def design(self):
        code, out = self.repo.status("--focus", "design")
        self.assertEqual(code, 0, out)
        return out

    def test_a_built_cell_reads_built_without_a_brief_with_its_commit(self):
        self.assertIn("- 2 Piece two: built without a brief (abc1234)", self.design())

    def test_a_built_cell_with_no_commit_reads_built_without_a_brief(self):
        out = self.design()
        self.assertIn("- 4 Piece four: built without a brief", out)
        self.assertNotIn("4 Piece four: built without a brief (", out)

    def test_a_row_with_no_brief_and_not_built_still_needs_one(self):
        self.assertIn("- 3 Piece three: no brief", self.design())

    def test_the_write_the_brief_step_names_only_the_unbuilt_row(self):
        out = self.design()
        self.assertIn("Write the brief for 3 Piece three, next in the plan without one.", out)
        self.assertNotIn("Write the brief for 2", out)
        self.assertNotIn("more after it", out)


class AuditTests(StatusCase):
    def test_only_the_unlogged_commit_is_listed(self):
        out = self.implementation()
        self.assertIn("- Commits on the branch: 5, 1 not in the build log:", out)
        self.assertIn(f"`{self.repo.git('rev-parse', '--short=9', self.c5)}` feat: unlogged work", out)

    def test_a_whole_spec_entry_is_not_reported_as_none_logged(self):
        out = self.implementation()
        self.assertNotIn("BRIEF-6 Spec six: 2 requirements, none logged", out)
        self.assertIn("BRIEF-9 Spec nine: 2 requirements, none logged as built", out)

    def test_the_log_the_built_work_step_names_requirements_or_records(self):
        self.assertIn(
            'Log the 1 commit already built, each against the requirements it covers or the record it built, so progress is counted: "log the built work".',
            self.implementation(),
        )

    def test_no_re_find_lines_before_a_rebase(self):
        self.assertNotIn("Build log:", self.implementation())


class RebaseStatusTests(StatusCase):
    def test_implementation_focus_lists_re_pointed_entries_in_one_line(self):
        self.repo.main_moves()
        self.assertRegex(
            self.implementation(),
            r"(?m)^- Build log: 4 entries re-pointed after a rebase \(BUILD-1 .*, BUILD-2 .*, BUILD-3, BUILD-4\)$",
        )

    def test_re_pointed_commits_count_as_named_in_the_audit(self):
        self.repo.main_moves()
        self.assertIn("- Commits on the branch: 5, 1 not in the build log:", self.implementation())

    def test_focus_all_lists_the_re_pointed_entries(self):
        self.repo.main_moves()
        self.assertRegex(self.everything(), r"(?m)^- Build log: 4 entries re-pointed after a rebase")

    def reword_logged_decision(self):
        sha = self.repo.commit("feat: decision three")
        self.repo.build_ok("built", "R3", "--commit", sha)
        self.repo.git("commit", "-q", "--amend", "-m", "feat: decision three, reworded")
        return sha

    def test_an_unlinked_entry_is_listed_with_its_id_old_commit_and_subject(self):
        sha = self.reword_logged_decision()
        self.assertRegex(
            self.implementation(),
            rf'(?m)^- Build log: BUILD-5 .*unlinked, its commit {sha} is not on the branch: "feat: decision three"$',
        )

    def test_an_unlinked_entry_gets_a_re_link_step_before_the_log_step(self):
        self.reword_logged_decision()
        out = self.implementation()
        self.assertRegex(
            out,
            r'(?m)^[0-9]+\. Re-link BUILD-5 \(Decision three\) by hand to the commit that built it: "re-link BUILD-5 to <sha>"\.$',
        )
        self.assertLess(out.index("Re-link BUILD-5"), out.index("Log the 2 commits"))

    def test_the_old_commit_is_listed_as_not_in_the_log(self):
        self.reword_logged_decision()
        out = self.implementation()
        self.assertIn("- Commits on the branch: 6, 2 not in the build log:", out)
        self.assertIn("feat: decision three, reworded", out)

    def test_focus_all_reports_the_unlinked_entry_and_step(self):
        sha = self.reword_logged_decision()
        out = self.everything()
        self.assertIn(f"unlinked, its commit {sha} is not on the branch", out)
        self.assertRegex(out, r"(?m)^[0-9]+\. Re-link BUILD-5")

    def test_after_a_re_link_by_hand_nothing_is_unlinked(self):
        self.reword_logged_decision()
        self.repo.build_ok("relink", "BUILD-5", "--commit", "HEAD")
        out = self.implementation()
        self.assertNotIn("Build log:", out)
        self.assertIn("- Commits on the branch: 6, 1 not in the build log:", out)
        self.assertNotIn("is merged", out)

    def test_a_merged_branch_says_its_log_is_history_once(self):
        self.repo.squash_merge()
        self.repo.reset_to_origin()
        out = self.implementation()
        self.assertIn("- Build log: the branch is merged; its log is history and is no longer re-pointed.", out)
        self.assertEqual(out.count("Build log:"), 1)
        self.assertIn("- Build log: the branch is merged", self.everything())


class WorkspaceTests(StatusCase):
    def setUp(self):
        super().setUp()
        self.other = init_repo(self.path("other"), with_origin=False)
        self.other.commit("feat: decision three elsewhere")
        self.other_commit = self.other.head()
        self.write_workspace(self.other.path)
        os.makedirs(os.path.join(self.other.path, ".clerk-dev"), exist_ok=True)
        with open(os.path.join(self.other.path, ".clerk-dev", "review-workspace.md"), "w") as f:
            f.write("Hub: hub\n\n" + self.workspace_table(self.other.path))
        self.other.build_ok("built", "R3", "--commit", self.other_commit)

    def workspace_table(self, other_path):
        return f"| Repo | Worktree |\n|---|---|\n| hub | {self.repo.path} |\n| other | {other_path} |\n"

    def write_workspace(self, other_path):
        with open(os.path.join(self.repo.path, ".clerk-dev", "review-workspace.md"), "w") as f:
            f.write(self.workspace_table(other_path))

    def test_a_decision_built_in_another_worktree_reads_built(self):
        head = digest_head(self.repo, "DEC-3")
        self.assertIn("; built: yes (", head)
        self.assertIn(self.other_commit, head)

    def test_a_step_whose_records_are_built_across_worktrees_reads_built(self):
        self.assertTrue(digest_head(self.repo, "PLAN-4").endswith("; built: 4 of 5 steps (1, 2, 3, 4))"))

    def test_the_other_worktrees_records_line_names_its_repository(self):
        self.assertIn(f"other: records built directly: DEC-3 ({self.other_commit})", progress_section(self.repo))

    def test_the_plan_line_uses_the_built_ness_of_every_worktree(self):
        self.assertIn("hub: PLAN-4 steps built: 1, 2, 3, 4", progress_section(self.repo))

    def break_other_log(self):
        with open(os.path.join(self.other.path, ".clerk-dev", "build.md"), "a") as f:
            f.write("garbage line\n")

    def test_a_record_built_in_a_readable_worktree_keeps_its_mark_beside_an_unreadable_log(self):
        self.break_other_log()
        self.assertIn("; built: yes (", digest_head(self.repo, "DEC-1"))
        self.assertTrue(digest_head(self.repo, "BRIEF-5").endswith("; built: yes)"))

    def test_what_no_readable_log_proves_reads_unknown_not_no(self):
        self.break_other_log()
        self.assertTrue(digest_head(self.repo, "BRIEF-9").endswith("; built: unknown)"))

    def test_a_plan_keeps_the_steps_proven_built_marked_unknown(self):
        self.break_other_log()
        self.assertTrue(
            digest_head(self.repo, "PLAN-4").endswith("; built: unknown (at least 3 of 5 steps: 1, 2, 4))")
        )

    def test_the_unreadable_log_is_reported_and_the_hubs_lines_stay(self):
        self.break_other_log()
        section = progress_section(self.repo)
        self.assertIn("other: (build log unreadable: ", section)
        self.assertIn("hub: BRIEF-5 Spec five: 2 of 2 requirements done", section)
        self.assertIn("hub: records built directly: DEC-1 (", section)

    def test_a_missing_worktree_is_reported_and_other_marks_stay(self):
        gone = self.path("gone")
        self.write_workspace(gone)
        section = progress_section(self.repo)
        self.assertIn(f"other: (worktree {gone} does not exist; its build log is not counted)", section)
        self.assertIn("; built: yes (", digest_head(self.repo, "DEC-1"))
        self.assertTrue(digest_head(self.repo, "BRIEF-9").endswith("; built: unknown)"))

    @unittest.skipIf(os.geteuid() == 0, "root can read a mode 0 directory")
    def test_an_unreadable_worktree_is_reported_and_other_marks_stay(self):
        os.chmod(self.other.path, 0)
        self.addCleanup(os.chmod, self.other.path, stat.S_IRWXU)
        section = progress_section(self.repo)
        self.assertIn(f"other: (worktree {self.other.path} cannot be read; its build log is not counted)", section)
        self.assertIn("hub: records built directly: DEC-1 (", section)

    def test_with_every_worktree_readable_nothing_is_unknown(self):
        self.assertTrue(digest_head(self.repo, "BRIEF-9").endswith("; built: no)"))


class DecisionsOnlyCase(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("nospec"))
        self.repo.git("checkout", "-q", "-b", "feat")
        self.write_decision(self.repo.path)
        self.first = self.repo.commit("feat: built the decision")

    def write_decision(self, root):
        write_feature_md(root)
        write_record(root, "R1", "decision", "Only decision", body="## Decision\n\nOne.")

    def implementation(self, repo):
        code, out = repo.status("--focus", "implementation")
        self.assertEqual(code, 0, out)
        return out


class DecisionsOnlyTests(DecisionsOnlyCase):
    def test_unlogged_commits_with_no_specs_still_get_the_log_step(self):
        out = self.implementation(self.repo)
        self.assertIn("- Commits on the branch: 1, 1 not in the build log:", out)
        self.assertIn('"log the built work"', out)


class NoUsableBaseTests(DecisionsOnlyCase):
    def test_no_origin_is_not_merged_and_has_no_audit(self):
        bare = init_repo(self.path("noorigin"), with_origin=False)
        bare.git("checkout", "-q", "-b", "feat")
        self.write_decision(bare.path)
        bare.commit("feat: built with no origin")
        bare.build_ok("built", "R1", "--commit", "HEAD")
        out = self.implementation(bare)
        self.assertNotIn("Build log:", out)
        self.assertNotIn("Commits on the branch", out)

    def advance_origin(self):
        self.repo.git("push", "-q", "origin", "feat")
        self.repo.main_moves(back_to="feat", rebase=False)

    def test_a_shallow_clone_with_no_merge_base_is_not_merged_and_has_no_audit(self):
        self.advance_origin()
        shallow = clone(
            "file://" + self.repo.origin,
            self.path("shallow"),
            "--depth",
            "1",
            "--no-single-branch",
        )
        shallow.git("checkout", "-q", "feat")
        self.write_decision(shallow.path)
        shallow.build_ok("built", "R1", "--commit", "HEAD")
        out = self.implementation(shallow)
        self.assertNotIn("Build log:", out)
        self.assertNotIn("Commits on the branch", out)
        self.assertNotIn("could not be read", out)

    def test_a_fresh_branch_with_only_a_handed_off_entry_is_not_merged(self):
        fresh = clone(self.repo.origin, self.path("fresh"))
        fresh.git("checkout", "-q", "-b", "feat2")
        self.write_decision(fresh.path)
        fresh.build_ok("add", "First piece", "--spec", "R1", "--reqs", "1")
        self.assertNotIn("is merged", self.implementation(fresh))

    def test_a_detached_head_on_a_branch_commit_keeps_its_range_and_is_not_merged(self):
        self.advance_origin()
        self.repo.git("checkout", "-q", "--detach")
        self.repo.build_ok("built", "R1", "--commit", "HEAD")
        out = self.implementation(self.repo)
        self.assertIn("- Commits on the branch: 1, 0 not in the build log.", out)
        self.assertNotIn("is merged", out)


class GitFailureTests(DecisionsOnlyCase):
    def outside_git(self, with_log):
        self.repo.build_ok("built", "R1", "--commit", "HEAD")
        outside = self.path("norepo")
        os.makedirs(outside)
        shutil.copytree(os.path.join(self.repo.path, ".clerk-dev"), os.path.join(outside, ".clerk-dev"))
        if not with_log:
            os.remove(os.path.join(outside, ".clerk-dev", "build.md"))
        code, out = run_script("status", outside, "--focus", "implementation", "--no-mark")
        self.assertEqual(code, 0, out)
        return out

    def test_outside_a_git_repository_status_reports_the_build_log_error_once(self):
        out = self.outside_git(with_log=True)
        self.assertIn("**Implementation:** the build log could not be read: git rev-parse --git-dir failed in", out)
        self.assertEqual(out.count("git rev-parse --git-dir failed"), 1)
        self.assertNotIn("Commits on the branch", out)
        self.assertIn("**Next:**", out)

    def test_with_no_build_log_a_git_failure_in_the_audit_is_reported_in_its_place(self):
        out = self.outside_git(with_log=False)
        self.assertIn("- Commits on the branch: could not be read: git rev-parse --git-dir failed in", out)

    def corrupt_range(self):
        self.repo.build_ok("built", "R1", "--commit", "HEAD")
        middle = self.repo.git("rev-parse", "HEAD")
        self.repo.commit("feat: tip")
        os.remove(os.path.join(self.repo.path, ".git", "objects", middle[:2], middle[2:]))

    def test_a_corrupt_object_in_the_range_is_a_build_log_error_not_an_empty_range(self):
        self.corrupt_range()
        out = self.implementation(self.repo)
        self.assertIn(
            f"**Implementation:** the build log could not be read: git merge-base HEAD origin/main failed in {self.repo.path}: ",
            out,
        )
        self.assertNotIn("is merged", out)
        self.assertNotIn("Commits on the branch", out)

    def test_focus_all_reports_it_the_same_way(self):
        self.corrupt_range()
        code, out = self.repo.status()
        self.assertEqual(code, 0, out)
        self.assertIn("**Implementation:** the build log could not be read: git merge-base", out)


class SupersededStepTests(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("chain"), with_origin=False)
        root = self.repo.path
        write_feature_md(root)
        write_record(root, "R10", "decision", "First take", "superseded", "superseded_by: R11\n", "## Decision\n\nA.")
        write_record(root, "R11", "decision", "Second take", "superseded", "supersedes: R10\nsuperseded_by: R13\n", "## Decision\n\nB.")
        write_record(root, "R13", "decision", "Third take", "active", "supersedes: R11\n", "## Decision\n\nC.")
        write_record(root, "R14", "decision", "Old other", "superseded", "superseded_by: R15\n", "## Decision\n\nD.")
        write_record(root, "R15", "decision", "New other", "active", "supersedes: R14\n", "## Decision\n\nE.")
        write_record(root, "R16", "decision", "Gone", "discarded", "", "## Decision\n\nF.")
        write_record(
            root,
            "R12",
            "plan",
            "Plan",
            body="1. Piece one, decision R10. Done: when built.\n"
            "2. Piece two, decision R14. Done: when built.\n"
            "3. Piece three, decision R16. Done: when built.\n"
            "4. Piece four, decision R13. Done: when R15 is built.",
        )

    def plan_mark(self):
        return digest_head(self.repo, "PLAN-12")

    def test_nothing_built_no_step_counts(self):
        self.assertTrue(self.plan_mark().endswith("; built: 0 of 4 steps)"))

    def test_a_chain_of_supersessions_counts_the_active_end_and_ignores_ids_after_done(self):
        self.repo.build_ok("built", "R13", "--commit", "HEAD")
        self.assertTrue(self.plan_mark().endswith("; built: 2 of 4 steps (1, 4))"))

    def test_a_discarded_record_has_no_successor_so_its_step_stays_unbuilt(self):
        self.repo.build_ok("built", "R13", "--commit", "HEAD")
        self.repo.build_ok("built", "R15", "--commit", "HEAD")
        self.assertTrue(self.plan_mark().endswith("; built: 3 of 4 steps (1, 2, 4))"))


if __name__ == "__main__":
    unittest.main()


class StartBuildingTests(TempCase):
    def test_a_brief_with_nothing_built_points_at_the_building_skill(self):
        repo = init_repo(self.path("fresh"))
        repo.git("checkout", "-q", "-b", "feat")
        write_feature_md(repo.path)
        write_record(repo.path, "R5", "spec", "Spec five", body=SPEC_BODY.format(a="Five one", b="Five two"))
        code, out = repo.status("--focus", "implementation")
        self.assertEqual(code, 0, out)
        self.assertIn("Start building BRIEF-5: cut its requirements into handoffs and send the first (the building skill).", out)

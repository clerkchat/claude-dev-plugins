import os
import shutil
import unittest

from helpers import (
    FeatureRepoCase,
    TempCase,
    init_repo,
    log_error,
    log_unlinked_commit,
    write_feature_md,
    write_log,
    write_record,
)


def block_keys(repo, entry_id):
    keys = []
    on = False
    for line in repo.log_text().splitlines():
        if line.startswith("- [") and f" {entry_id}. " in line:
            on = True
        elif on and line.startswith("  - "):
            keys.append(line[4:].split(":")[0])
        elif on:
            break
    return keys


class BuiltTests(FeatureRepoCase):
    def test_built_on_a_decision(self):
        out = self.repo.build_ok("built", "R1", "--commit", self.c1)
        self.assertEqual(out, f"B1 built: R1 in {self.c1}")
        self.assertEqual(self.repo.field("B1", "Record"), "R1")
        self.assertEqual(self.repo.field("B1", "Spec"), "")
        self.assertEqual(self.repo.field("B1", "Status"), "done")
        self.assertEqual(self.repo.field("B1", "Commit"), self.c1)

    def test_built_takes_the_record_title(self):
        self.repo.build_ok("built", "R1", "--commit", self.c1)
        self.assertIn("- [x] B1. Decision one\n", self.repo.log_text())

    def test_built_on_a_plan_step_is_titled_with_its_piece(self):
        self.repo.build_ok("built", "r4.2", "--commit", self.c2)
        self.assertEqual(self.repo.field("B1", "Record"), "R4.2")
        self.assertIn("- [x] B1. Piece two, the second thing\n", self.repo.log_text())

    def test_built_on_a_whole_spec_takes_a_given_title(self):
        self.repo.build_ok("built", "R6", "--commit", self.c3, "--title", "Spec six whole.")
        self.assertEqual(self.repo.field("B1", "Record"), "R6")
        self.assertIn("- [x] B1. Spec six whole\n", self.repo.log_text())

    def test_built_writes_the_subject(self):
        self.repo.build_ok("built", "R1", "--commit", self.c1)
        self.repo.build_ok("built", "R6", "--commit", self.c3)
        self.assertEqual(self.repo.field("B1", "Subject"), "feat: decision one")
        self.assertEqual(self.repo.field("B2", "Subject"), "feat: spec six")

    def test_record_and_subject_sit_in_field_order(self):
        self.repo.build_ok("built", "R1", "--commit", self.c1)
        self.assertEqual(
            block_keys(self.repo, "B1"),
            ["Record", "Status", "Commit", "Subject", "Started"],
        )

    def test_one_entry_per_commit_for_a_record(self):
        self.repo.build_ok("built", "R1", "--commit", self.c1)
        out = self.repo.build_ok("built", "R1", "--commit", self.c2)
        self.assertEqual(out, f"B2 built: R1 in {self.c2}")

    def test_done_writes_the_subject(self):
        self.repo.build_ok("add", "Five piece", "--spec", "R5", "--reqs", "1")
        self.repo.build_ok("done", "B1", "--commit", self.c4)
        self.assertEqual(self.repo.field("B1", "Subject"), "feat: spec five piece")
        self.assertEqual(self.repo.field("B1", "Commit"), self.c4)

    def test_a_whole_spec_is_one_entry_per_commit(self):
        self.repo.build_ok("built", "R6", "--commit", self.c3)
        self.repo.build_ok("built", "R6", "--commit", self.c4)
        self.assertIn("R6 Spec six: 2 of 2", self.repo.build_ok("progress"))
        self.assertEqual(self.repo.field("B2", "Record"), "R6")


class BuiltRefusalTests(FeatureRepoCase):
    def refuses(self, want, *args):
        code, out = self.repo.build("built", *args)
        self.assertNotEqual(code, 0, out)
        self.assertIn(want, out)
        self.assertFalse(os.path.exists(os.path.join(self.repo.path, ".clerk-dev", "build.md")))

    def test_a_record_not_in_the_hub(self):
        self.refuses("R99 is not a record in the hub", "R99", "--commit", self.c1)

    def test_an_inactive_record_names_its_successor(self):
        self.refuses("R2 is superseded by R3", "R2", "--commit", self.c1)

    def test_a_step_of_an_inactive_plan(self):
        self.refuses("plan R8 is superseded (by R4)", "R8.1", "--commit", self.c1)

    def test_a_missing_plan_step(self):
        self.refuses("plan R4 has no step 9", "R4.9", "--commit", self.c1)

    def test_a_step_of_a_record_that_is_not_a_plan(self):
        self.refuses("R5 is not a plan record", "R5.1", "--commit", self.c1)

    def test_a_type_that_is_not_decision_plan_or_spec(self):
        self.refuses("R7 is a brainstorm", "R7", "--commit", self.c1)

    def test_a_commit_that_does_not_exist(self):
        self.refuses("is not a commit here", "R3", "--commit", "deadbeef")

    def test_a_bare_plan_points_at_its_steps(self):
        self.refuses("R4 is a plan; log its steps instead, such as R4.1", "R4", "--commit", "HEAD")

    def test_a_second_entry_for_the_same_record_and_commit(self):
        self.repo.build_ok("built", "R1", "--commit", self.c1)
        before = self.repo.log_text()
        code, out = self.repo.build("built", "R1", "--commit", self.c1)
        self.assertNotEqual(code, 0)
        self.assertIn(f"B1 already logs R1 as built in {self.c1}", out)
        self.assertEqual(self.repo.log_text(), before)

    def test_a_whole_spec_that_already_has_pieces(self):
        self.repo.build_ok("add", "Five piece", "--spec", "R5", "--reqs", "1")
        self.repo.build_ok("done", "B1", "--commit", self.c4)
        code, out = self.repo.build("built", "R5", "--commit", self.c4)
        self.assertNotEqual(code, 0)
        self.assertIn(
            "R5 already has pieces in the build log (B1); log its remaining requirements as pieces instead",
            out,
        )
        self.assertNotIn("Record: R5", self.repo.log_text())

    def test_a_whole_plan_is_never_logged(self):
        self.repo.build("built", "R4", "--commit", self.c1)
        self.repo.build_ok("built", "R1", "--commit", self.c1)
        self.assertNotIn("R4 (", self.repo.build_ok("records"))

    def test_a_commit_is_required(self):
        code, out = self.repo.build("built", "R1")
        self.assertNotEqual(code, 0, out)


class ReaderTests(FeatureRepoCase):
    def setUp(self):
        super().setUp()
        self.repo.build_ok("built", "R1", "--commit", self.c1)
        self.repo.build_ok("built", "R4.2", "--commit", self.c2)
        self.repo.build_ok("built", "R6", "--commit", self.c3, "--title", "Spec six whole.")
        self.repo.build_ok("built", "R1", "--commit", self.c2)
        self.repo.build_ok("add", "Five piece", "--spec", "R5", "--reqs", "1")
        self.repo.build_ok("done", "B5", "--commit", self.c4)

    def test_a_whole_spec_entry_counts_every_requirement(self):
        self.assertIn("R6 Spec six: 2 of 2 requirements done", self.repo.build_ok("progress"))

    def test_decision_and_step_entries_appear_under_no_spec(self):
        out = self.repo.build_ok("progress")
        self.assertNotRegex(out, r"(?m)^R(1|4)")
        self.assertIn("R5 Spec five: 1 of 2", out)

    def test_checklist_attributes_a_whole_spec_to_its_entry(self):
        out = self.repo.build_ok("checklist", "--spec", "R6")
        self.assertEqual(sum(l.startswith("- [x] ") and l.endswith(" (B3)") for l in out.splitlines()), 2)

    def test_list_prints_a_record_entry_with_its_record(self):
        lines = self.repo.build_ok("list").splitlines()
        self.assertIn(f"B1 Decision one  [R1; done; {self.c1}]", lines)
        self.assertIn(f"B2 Piece two, the second thing  [R4.2; done; {self.c2}]", lines)

    def test_list_prints_a_spec_piece_as_before(self):
        lines = self.repo.build_ok("list").splitlines()
        self.assertIn(f"B5 Five piece  [R5: 1 done; done; sonnet medium; {self.c4}]", lines)

    def test_records_prints_one_line_per_record_entry(self):
        expected = "\n".join(
            [
                f"R1 built in {self.c1} (B1)",
                f"R1 built in {self.c2} (B4)",
                f"R4.2 built in {self.c2} (B2)",
                f"R6 built in {self.c3} (B3)",
            ]
        )
        self.assertEqual(self.repo.build_ok("records"), expected)


class RelinkTests(FeatureRepoCase):
    def setUp(self):
        super().setUp()
        self.repo.build_ok("built", "R1", "--commit", self.c1)
        self.repo.build_ok("built", "R4.2", "--commit", self.c2)
        self.repo.build_ok("built", "R6", "--commit", self.c3)
        self.repo.build_ok("built", "R1", "--commit", self.c2)
        self.repo.build_ok("add", "Five piece", "--spec", "R5", "--reqs", "1")
        self.repo.build_ok("done", "B5", "--commit", self.c4)
        self.all = ["B1", "B2", "B3", "B4", "B5"]

    def test_nothing_is_re_pointed_before_a_rebase(self):
        self.assertEqual(self.repo.state(), ([], []))

    def test_the_log_re_finds_rebased_commits_by_subject(self):
        self.repo.main_moves()
        self.assertEqual(self.repo.state(), (self.all, []))

    def test_a_reader_does_not_write(self):
        self.repo.main_moves()
        before = self.repo.log_text()
        self.repo.state()
        self.repo.build_ok("list")
        self.assertEqual(self.repo.log_text(), before)

    def test_list_shows_the_re_found_hash(self):
        self.repo.main_moves()
        lines = self.repo.build_ok("list").splitlines()
        self.assertIn(f"B1 Decision one  [R1; done; {self.repo.find('feat: decision one')}]", lines)

    def test_an_entry_on_a_moved_commit_is_re_pointed_by_its_own_subject(self):
        self.repo.main_moves()
        out = self.repo.build_ok("list")
        self.assertRegex(out, rf"B4 .*\[R1; done; {self.repo.find('feat: plan step two')}\]")

    def test_relink_persists_the_re_found_hashes(self):
        self.repo.main_moves()
        out = self.repo.build_ok("relink")
        self.assertEqual(self.repo.field("B1", "Commit"), self.repo.find("feat: decision one"))
        self.assertEqual(self.repo.field("B3", "Commit"), self.repo.find("feat: spec six"))
        self.assertIn("re-pointed: B1, B2, B3, B4, B5", out)
        self.assertEqual(self.repo.state(), ([], []))

    def test_progress_is_unchanged_by_the_re_find(self):
        self.repo.main_moves()
        self.assertIn("R6 Spec six: 2 of 2 requirements done", self.repo.build_ok("progress"))

    def test_a_writer_persists_re_found_hashes(self):
        self.repo.main_moves()
        self.repo.build_ok("add", "Five two", "--spec", "R5", "--reqs", "2")
        self.assertEqual(self.repo.field("B1", "Commit"), self.repo.find("feat: decision one"))
        self.assertEqual(self.repo.state(), ([], []))

    def test_a_reworded_subject_is_unlinked_and_keeps_its_commit(self):
        self.repo.commit("feat: new decision")
        self.repo.build_ok("built", "R3", "--commit", "HEAD")
        old = self.repo.field("B6", "Commit")
        self.repo.git("commit", "-q", "--amend", "-m", "feat: reworded")
        self.assertEqual(self.repo.state(), ([], ["B6"]))
        self.assertEqual(log_unlinked_commit(self.repo.path, "B6"), old)
        out = self.repo.build_ok("relink")
        self.assertIn(f'unlinked: B6 {old} "feat: new decision"', out)

    def test_relink_by_hand_re_points_and_refreshes_the_subject(self):
        self.repo.commit("feat: new decision")
        self.repo.build_ok("built", "R3", "--commit", "HEAD")
        self.repo.git("commit", "-q", "--amend", "-m", "feat: reworded")
        self.repo.build_ok("relink", "B6", "--commit", "HEAD")
        self.assertEqual(self.repo.field("B6", "Commit"), self.repo.head())
        self.assertEqual(self.repo.field("B6", "Subject"), "feat: reworded")
        self.assertEqual(self.repo.state(), ([], []))

    def test_relink_by_hand_needs_both_an_entry_and_a_commit(self):
        self.assertRefusesRelink("give both an entry and --commit", "B1")

    def test_relink_by_hand_refuses_an_open_piece(self):
        self.repo.build_ok("add", "Open piece", "--spec", "R5", "--reqs", "2")
        self.assertRefusesRelink("B6 is briefed, not done", "B6", "--commit", "HEAD")

    def test_relink_by_hand_refuses_an_unknown_entry(self):
        code, out = self.repo.build("relink", "B99", "--commit", "HEAD")
        self.assertNotEqual(code, 0, out)

    def test_relink_by_hand_refuses_a_commit_that_does_not_exist(self):
        code, out = self.repo.build("relink", "B1", "--commit", "deadbeef")
        self.assertNotEqual(code, 0, out)
        self.assertEqual(self.repo.field("B1", "Commit"), self.c1)

    def assertRefusesRelink(self, want, *args):
        code, out = self.repo.build("relink", *args)
        self.assertNotEqual(code, 0, out)
        self.assertIn(want, out)

    def test_several_matching_subjects_leave_the_entry_unlinked(self):
        self.repo.commit("feat: same subject")
        second = self.repo.commit("feat: same subject")
        self.repo.build_ok("built", "R1", "--commit", second)
        with open(os.path.join(self.repo.path, "file.txt"), "a") as f:
            f.write("more\n")
        self.repo.git("add", "file.txt")
        self.repo.git("commit", "-q", "--amend", "--no-edit")
        self.assertEqual(self.repo.state(), ([], ["B6"]))
        self.repo.build_ok("relink", "B6", "--commit", "HEAD")
        self.assertEqual(self.repo.state(), ([], []))

    def test_an_entry_on_an_ancestor_of_the_base_is_never_touched(self):
        self.repo.commit("base")
        self.repo.build_ok("built", "R3", "--commit", self.base)
        self.assertEqual(self.repo.state(), ([], []))
        self.assertEqual(self.repo.field("B6", "Commit"), self.base)

    def test_a_moved_entry_with_no_subject_is_unlinked(self):
        self.repo.build_ok("built", "R3", "--commit", self.c4)
        text = self.repo.log_text()
        marker = "- [x] B6."
        head, tail = text.split(marker)
        tail = "\n".join(l for l in tail.split("\n") if not l.startswith("  - Subject: "))
        write_log(self.repo.path, head + marker + tail)
        self.repo.main_moves()
        self.assertEqual(self.repo.state(), (self.all, ["B6"]))
        self.assertEqual(self.repo.field("B6", "Subject"), "")

    def test_a_squash_merged_branch_is_not_re_pointed(self):
        self.repo.main_moves()
        self.repo.build_ok("relink")
        self.repo.squash_merge()
        self.assertEqual(self.repo.state(), ([], []))
        before = self.repo.log_text()
        self.assertEqual(self.repo.build_ok("relink"), "nothing to re-point")
        self.assertEqual(self.repo.log_text(), before)

    def test_a_merged_branch_reset_onto_main_is_not_re_pointed(self):
        self.repo.main_moves()
        self.repo.build_ok("relink")
        kept = self.repo.field("B1", "Commit")
        self.repo.squash_merge()
        self.repo.reset_to_origin()
        self.assertEqual(self.repo.state(), ([], []))
        self.assertEqual(self.repo.field("B1", "Commit"), kept)

    def test_an_old_entry_with_no_subject_still_reads(self):
        old = init_repo(self.path("old"))
        self.write_records(old.path)
        write_log(
            old.path,
            "- [x] B1. Old\n  - Spec: R5\n  - Requirements: 1 done\n  - Status: done\n"
            "  - Commit: abc1234\n  - Started: 2026-10-21\n",
        )
        self.assertEqual(old.build_ok("list"), "B1 Old  [R5: 1 done; done; None; abc1234]")


class EdgeTests(FeatureRepoCase):
    def setUp(self):
        TempCase.setUp(self)
        self.repo = init_repo(self.path("edge"))
        self.base = self.repo.base
        self.repo.git("checkout", "-q", "-b", "other")
        self.other = self.repo.commit("feat: on another branch")
        self.repo.git("checkout", "-q", "main")
        self.repo.git("checkout", "-q", "-b", "feat")
        self.own = self.repo.commit("feat: on this branch")
        self.write_records(self.repo.path)

    def test_a_commit_on_the_branch_is_logged_with_no_note(self):
        out = self.repo.build_ok("built", "R1", "--commit", self.own)
        self.assertEqual(out, f"B1 built: R1 in {self.own}")

    def test_a_commit_on_main_is_noted_and_still_logged(self):
        out = self.repo.build_ok("built", "R1", "--commit", self.base)
        self.assertIn(
            f"note: {self.base} is not on this branch: it is on the main branch, older than this branch's base; logged anyway",
            out,
        )
        self.assertEqual(self.repo.field("B1", "Commit"), self.base)
        self.assertEqual(self.repo.state(), ([], []))

    def test_a_commit_head_does_not_reach_is_noted_and_unlinked(self):
        out = self.repo.build_ok("built", "R1", "--commit", self.other)
        self.assertIn(f"note: {self.other} is not on this branch: HEAD does not reach it", out)
        self.assertEqual(self.repo.field("B1", "Commit"), self.other)
        self.assertEqual(self.repo.state(), ([], ["B1"]))
        self.repo.build_ok("relink", "B1", "--commit", self.own)
        self.assertEqual(self.repo.state(), ([], []))

    def test_an_odd_subject_is_stored_whole_on_one_line(self):
        sha = self.odd_commit()
        self.repo.build_ok("built", "R3", "--commit", sha)
        self.assertEqual(self.repo.field("B1", "Subject"), self.stored_subject)
        self.assertEqual(self.repo.state(), ([], []))

    def test_an_odd_subject_is_re_found_exactly_after_a_rebase(self):
        sha = self.odd_commit()
        self.repo.build_ok("built", "R3", "--commit", sha)
        self.repo.main_moves("main moves")
        self.assertEqual(self.repo.state(), (["B1"], []))
        self.repo.build_ok("relink")
        self.assertEqual(self.repo.field("B1", "Commit"), self.repo.head())

    def odd_commit(self):
        subject = "  feat: lead\ttab   sep \x1c fs"
        self.stored_subject = subject.strip()
        with open(os.path.join(self.repo.path, "file.txt"), "a") as f:
            f.write("odd\n")
        self.repo.git("add", "file.txt")
        self.repo.git("commit", "-qm", subject)
        return self.repo.head()

    def add_legacy_entries(self):
        write_log(
            self.repo.path,
            "\n- [x] B1. Legacy piece\n  - Spec: R5\n  - Requirements: 1 done\n  - Status: done\n"
            "  - Commit: 1234567\n  - Started: 2026-10-01\n\n"
            "- [x] B2. Legacy record\n  - Record: R1\n  - Status: done\n  - Started: 2026-10-01\n",
        )

    def test_a_legacy_entry_with_no_subject_and_a_missing_commit_is_unlinked(self):
        self.add_legacy_entries()
        self.assertEqual(self.repo.state(), ([], ["B1"]))

    def test_relink_gives_the_reason_it_cannot_follow_a_legacy_entry(self):
        self.add_legacy_entries()
        code, out = self.repo.build("relink")
        self.assertEqual(out, "unlinked: B1 1234567 no subject to re-find it by")

    def test_records_reads_an_entry_with_no_commit(self):
        self.add_legacy_entries()
        code, out = self.repo.build("records")
        self.assertEqual(code, 0, out)
        self.assertIn("R1 built in no commit logged (B2)", out)

    def test_list_reads_the_legacy_entries(self):
        self.add_legacy_entries()
        code, out = self.repo.build("list")
        self.assertEqual(code, 0, out)
        self.assertIn("B1 Legacy piece  [R5: 1 done; done; None; 1234567]", out)
        self.assertIn("B2 Legacy record  [R1; done]", out)

    def test_outside_a_git_repository_the_read_stops_with_git_reason(self):
        self.add_legacy_entries()
        bare = self.path("norepo")
        os.makedirs(os.path.join(bare, ".clerk-dev"))
        shutil.copy(
            os.path.join(self.repo.path, ".clerk-dev", "build.md"),
            os.path.join(bare, ".clerk-dev", "build.md"),
        )
        self.assertIn(f"git rev-parse --git-dir failed in {bare}: fatal: not a git repository", log_error(bare))

    def test_a_corrupt_object_in_the_range_stops_the_read_on_one_line(self):
        self.repo.commit("feat: second")
        self.repo.build_ok("built", "R1", "--commit", "HEAD")
        middle = self.repo.git("rev-parse", "HEAD~1")
        os.remove(os.path.join(self.repo.path, ".git", "objects", middle[:2], middle[2:]))
        message = self.repo.error()
        self.assertIn(f"failed in {self.repo.path}: ", message)
        self.assertIn(middle, message)
        self.assertEqual(len(message.splitlines()), 1)


class NoteWordingTests(TempCase):
    def test_with_no_remote_an_unreachable_commit_is_not_promised_a_warning(self):
        repo = init_repo(self.path("nomain"), with_origin=False)
        repo.git("checkout", "-q", "-b", "side")
        side = repo.commit("side")
        repo.git("checkout", "-q", "main")
        self.write_hub(repo)
        out = repo.build_ok("built", "R1", "--commit", side)
        self.assertIn("HEAD does not reach it, and nothing will flag that later", out)
        self.assertNotIn("status lists", out)

    def test_a_merge_commit_on_the_branch_is_not_called_a_main_commit(self):
        repo = init_repo(self.path("merge"))
        base = repo.base
        self.write_hub(repo)
        repo.git("checkout", "-q", "-b", "feat")
        repo.commit("feat work")
        repo.git("checkout", "-q", "-b", "sub", base)
        repo.commit("sub work", "sub.txt")
        repo.git("checkout", "-q", "feat")
        repo.git("merge", "-q", "--no-ff", "sub", "-m", "merge sub")
        out = repo.build_ok("built", "R1", "--commit", repo.head())
        self.assertIn("it is a merge commit", out)
        self.assertNotIn("main branch", out)

    def write_hub(self, repo):
        write_feature_md(repo.path)
        write_record(repo.path, "R1", "decision", "Decision one", body="## Decision\n\nOne.")


if __name__ == "__main__":
    unittest.main()

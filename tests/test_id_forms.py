import datetime
import hashlib
import os
import re
import unittest

from helpers import (
    TempCase,
    init_repo,
    run_ok,
    run_script,
    write_feature_md,
    write_log,
    write_record,
)

SPEC_BODY = "## Requirements\n\n1. {a}.\n2. {b}.\n\n## Baseline\n\nClean."


def feature_dir(root):
    return os.path.join(root, ".clerk-dev", "feature")


def write_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def read_file(path):
    with open(path) as f:
        return f.read()


def frontmatter(path):
    head = read_file(path).split("---\n")[1]
    return dict(line.split(": ", 1) for line in head.splitlines())


class OldRecordsCase(TempCase):
    def setUp(self):
        super().setUp()
        self.root = self.path("hub")
        os.makedirs(self.root)
        write_feature_md(self.root)
        write_record(self.root, "R1", "decision", "Decision one", body="## Decision\n\nOne.")
        write_record(self.root, "R2", "spec", "Spec two", body=SPEC_BODY.format(a="Two one", b="Two two"))

    def records(self, *args):
        return run_ok("records", args[0], self.root, *args[1:])

    def record_file(self, name):
        return os.path.join(feature_dir(self.root), "records", name)


class RecordsTests(OldRecordsCase):
    def test_old_records_are_listed_by_their_types_prefix(self):
        lines = self.records("list").splitlines()
        self.assertTrue(lines[0].startswith("DEC-1 decision: Decision one"), lines)
        self.assertTrue(lines[1].startswith("BRIEF-2 brief: Spec two"), lines)

    def test_any_form_of_the_number_finds_the_record(self):
        want = self.record_file("R2.md")
        for text in ("R2", "r2", "BRIEF-2", "brief2", "DEC-2", "2"):
            with self.subTest(text=text):
                self.assertEqual(self.records("path", text), want)

    def test_a_new_record_is_written_in_the_new_form(self):
        out = self.records("new", "decision", "Decision three", "--from", "r1,brief2,I4,this session", "--supersedes", "R1")
        path = out.split()[1]
        self.assertTrue(out.startswith("DEC-3 "), out)
        self.assertTrue(path.endswith("003-decision-decision-three.md"))
        meta = frontmatter(path)
        self.assertEqual(meta["id"], "DEC-3")
        self.assertEqual(meta["from"], "DEC-1, BRIEF-2, IDEA-4, this session")
        self.assertEqual(meta["supersedes"], "DEC-1")
        self.assertIn("# DEC-3. Decision three", read_file(path))

    def test_superseding_an_old_record_keeps_its_own_id(self):
        self.records("new", "decision", "Decision three", "--supersedes", "R1")
        meta = frontmatter(self.record_file("R1.md"))
        self.assertEqual(meta["id"], "R1")
        self.assertEqual(meta["superseded_by"], "DEC-3")

    def test_old_and_new_records_share_one_sequence(self):
        self.records("new", "spec", "Spec three")
        out = self.records("new", "plan", "The plan")
        self.assertTrue(out.startswith("PLAN-4 "), out)

    def test_old_citations_read_in_the_new_form(self):
        write_record(self.root, "R3", "decision", "Decision three", "superseded", "from: R1, I4\nsuperseded_by: R5\n")
        write_record(self.root, "R5", "decision", "Decision five", "active", "supersedes: R3\n")
        line = next(l for l in self.records("list").splitlines() if l.startswith("DEC-3 "))
        self.assertIn("from: DEC-1, IDEA-4; superseded_by: DEC-5", line)

    def test_names_reads_old_and_new_forms(self):
        out = self.records("names", "R1", "dec-1", "BRIEF-2.1", "R2.2", "R9").splitlines()
        self.assertEqual(
            out,
            [
                "R1: decision: Decision one",
                "dec-1: decision: Decision one",
                "BRIEF-2.1: requirement of BRIEF-2: Two one",
                "R2.2: requirement of BRIEF-2: Two two",
                "R9: unknown",
            ],
        )


class CheckTests(OldRecordsCase):
    def setUp(self):
        super().setUp()
        checks = os.path.join(feature_dir(self.root), "checks")
        write_file(
            os.path.join(checks, "R2-1.md"),
            "# Check\n\nChecked against: R2, R1.\n\n- [ ] Q1. Old question\n  - Weight: settle-first\n",
        )
        write_file(
            os.path.join(checks, "BRIEF-2-2.md"),
            "# Check\n\nChecked against: BRIEF-2.\n\n- [ ] Q-1. New question\n  - Weight: minor\n",
        )

    def test_the_index_names_checks_in_the_new_form_and_links_their_files(self):
        self.records("index")
        text = read_file(os.path.join(feature_dir(self.root), "feature.md"))
        self.assertIn("| [BRIEF-2-1](checks/R2-1.md) | BRIEF-2, DEC-1 | 1 | 0 |", text)
        self.assertIn("| [BRIEF-2-2](checks/BRIEF-2-2.md) | BRIEF-2 | 1 | 0 |", text)

    def test_questions_in_either_form_are_named(self):
        out = self.records("names", "BRIEF-2-1.Q-1", "R2-1.Q1", "R2-2.Q-1", "brief-2-2", "BRIEF-2-3").splitlines()
        self.assertEqual(
            out,
            [
                "BRIEF-2-1.Q-1: design question: Old question",
                "R2-1.Q1: design question: Old question",
                "R2-2.Q-1: design question: New question",
                "brief-2-2: design check of BRIEF-2",
                "BRIEF-2-3: unknown",
            ],
        )

    def test_the_digest_cites_open_questions_by_the_new_check_name(self):
        repo = init_repo(self.path("digest"), with_origin=False)
        os.rename(os.path.join(self.root, ".clerk-dev"), os.path.join(repo.path, ".clerk-dev"))
        out = run_ok("records", "digest", repo.path)
        self.assertIn("- BRIEF-2-1.Q1 (settle-first): Old question", out)
        self.assertIn("- BRIEF-2-2.Q-1 (minor): New question", out)


class OverviewTests(OldRecordsCase):
    def overview(self, stamp):
        write_file(os.path.join(feature_dir(self.root), "overview.md"), f"# Overview\n\n{stamp}\n\nBody.\n")

    def old_basis(self):
        key = "R1:active::Decision one|R2:active::Spec two"
        return hashlib.sha1(key.encode()).hexdigest()[:10]

    def test_an_overview_stamped_before_the_new_forms_stays_current(self):
        self.overview(f"Generated 2026-10-01 through R2 (basis {self.old_basis()}). Do not edit.")
        self.assertIn("current (through BRIEF-2)", self.records("overview-status"))

    def test_a_stamp_cites_the_last_record_in_the_new_form(self):
        self.overview("")
        self.assertEqual(self.records("stamp-overview"), "overview stamped through BRIEF-2")
        self.assertIn("current (through BRIEF-2)", self.records("overview-status"))

    def test_with_no_records_the_stamp_reads_none_and_the_old_sentinel_still_reads(self):
        for name in os.listdir(os.path.join(feature_dir(self.root), "records")):
            os.remove(os.path.join(feature_dir(self.root), "records", name))
        empty = hashlib.sha1(b"").hexdigest()[:10]
        self.overview(f"Generated 2026-10-01 through R0 (basis {empty}). Do not edit.")
        self.assertIn("current (through R0)", self.records("overview-status"))
        self.assertEqual(self.records("stamp-overview"), "overview stamped through none")
        self.assertIn("current (through none)", self.records("overview-status"))


class IdeaTests(OldRecordsCase):
    def setUp(self):
        super().setUp()
        write_file(
            os.path.join(feature_dir(self.root), "ideas.md"),
            "# Ideas\n\n- [ ] I1. An old idea.\n  - Added: 2026-10-01\n  - Status: open\n",
        )

    def test_a_new_idea_follows_the_old_numbers_in_the_new_form(self):
        self.assertEqual(self.records("idea", "A new idea", "--from", "R1"), "IDEA-2 parked")
        self.assertIn("- [ ] IDEA-2. A new idea.\n  - From: DEC-1\n", read_file(os.path.join(feature_dir(self.root), "ideas.md")))

    def test_an_old_idea_is_adopted_by_any_form_and_cites_the_record_newly(self):
        self.assertEqual(self.records("adopt", "idea1", "--by", "r2"), "I1 adopted")
        self.assertIn("adopted as BRIEF-2", read_file(os.path.join(feature_dir(self.root), "ideas.md")))


class BuildLogTests(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("work"))
        self.repo.git("checkout", "-q", "-b", "feat")
        write_feature_md(self.repo.path)
        write_record(self.repo.path, "R2", "spec", "Spec two", body=SPEC_BODY.format(a="Two one", b="Two two"))
        write_record(self.repo.path, "R3", "plan", "The plan", body="1. Piece one, spec R2. Done: when two is built.")
        self.c1 = self.repo.commit("feat: two one")
        write_log(
            self.repo.path,
            "- [x] B1. Two one\n  - Spec: R2\n  - Requirements: 1 done\n  - Status: done\n"
            f"  - Commit: {self.c1}\n  - Subject: feat: two one\n  - Started: 2026-10-01\n\n"
            "- [ ] M1. Piece one\n  - Spec: R2\n  - Plan: R3.1\n  - Passes: edge-cases\n  - Started: 2026-10-01\n",
        )

    def test_a_new_entry_follows_the_old_numbers_in_the_new_form(self):
        out = self.repo.build_ok("add", "Two two", "--brief", "brief2", "--reqs", "BRIEF-2.2")
        self.assertEqual(out, "BUILD-2 handed off: BRIEF-2 requirements 2")
        self.assertIn("- [ ] BUILD-2. Two two\n  - Brief: BRIEF-2\n", self.repo.log_text())
        self.assertIn("- [x] B1. Two one\n  - Brief: R2\n", self.repo.log_text())

    def test_old_and_new_entries_count_toward_one_spec(self):
        self.repo.build_ok("add", "Two two", "--spec", "R2", "--reqs", "R2.2")
        c2 = self.repo.commit("feat: two two")
        self.repo.build_ok("done", "B2", "--commit", c2)
        self.assertEqual(self.repo.build_ok("progress"), "BRIEF-2 Spec two: 2 of 2 requirements done")
        self.assertEqual(self.repo.build_ok("progress", "--spec", "r2"), "BRIEF-2 Spec two: 2 of 2 requirements done")

    def test_entries_are_found_by_any_form(self):
        for text in ("B1", "b1", "BUILD-1", "build1", "1"):
            with self.subTest(text=text):
                self.assertEqual(self.repo.build_ok("relink", text, "--commit", self.c1), f"B1 re-linked to {self.c1}")
        self.assertEqual(self.repo.build_ok("skip", "mile1", "edge-cases", "--why", "covered"), "M1: edge-cases skipped")

    def test_a_new_milestone_cites_the_plan_step_in_the_new_form(self):
        out = self.repo.build_ok("milestone", "--step", "r3.1", "--passes", "edge-cases")
        self.assertEqual(out, "MILE-2 planned from PLAN-3.1: edge-cases")
        self.assertIn("- [ ] MILE-2. Piece one, spec R2\n  - Brief: BRIEF-2\n  - Plan: PLAN-3.1\n", self.repo.log_text())

    def test_a_pass_on_the_spec_in_either_form_counts_for_the_milestone(self):
        write_file(
            os.path.join(self.repo.path, ".clerk-dev", "passes.md"),
            "- [ ] PASS-1. edge-cases on BRIEF-2\n  - Piece: BRIEF-2\n  - Status: open\n",
        )
        self.assertIn("edge-cases: PASS-1 open", self.repo.build_ok("milestones"))

    def test_records_built_cite_old_entries_in_the_new_form(self):
        self.repo.build_ok("built", "R3.1", "--commit", self.c1)
        write_log(
            self.repo.path,
            self.repo.log_text() + "\n- [x] B9. Old record entry\n  - Record: R3.1\n  - Status: done\n  - Started: 2026-10-01\n",
        )
        out = self.repo.build_ok("records").splitlines()
        self.assertEqual(out, [f"PLAN-3.1 built in {self.c1} (BUILD-2)", "PLAN-3.1 built in no commit logged (B9)"])


class ItemListTests(TempCase):
    def setUp(self):
        super().setUp()
        self.root = self.path("items")
        write_file(
            os.path.join(self.root, ".clerk-dev", "deferred.md"),
            "# Deferred\n\n- [ ] D3. An old gap.\n  - From: this session\n  - Path: none\n  - Open: all\n  - Status: open\n",
        )

    def test_a_new_deferred_item_follows_the_old_numbers_in_the_new_form(self):
        out = run_ok("deferred", "add", self.root, "A new gap", "--from", "this session", "--path", "p", "--open", "o")
        self.assertTrue(out.startswith("DEFER-4 added"), out)

    def test_an_old_item_is_closed_by_any_form(self):
        for text in ("defer3", "D3"):
            with self.subTest(text=text):
                run_ok("deferred", "reopen", self.root, text)
                run_ok("deferred", "close", self.root, text, "--ref", "done")
                self.assertIn("- [x] D3. An old gap.", read_file(os.path.join(self.root, ".clerk-dev", "deferred.md")))

    def test_follow_ups_keep_their_form(self):
        out = run_ok("followups", "add", self.root, "Owed work", "--from", "api abc1234", "--contract", "changed: GET /a: x to y")
        self.assertTrue(out.startswith("F1 added"), out)

    def test_a_follow_up_takes_either_form_of_contract(self):
        for n, contract in enumerate(("changed: GET /a: x to y", "wanted: GET /a?q= matches z; today it does not"), 1):
            with self.subTest(contract=contract):
                out = run_ok("followups", "add", self.root, "Owed work", "--from", "api abc1234", "--contract", contract)
                self.assertTrue(out.startswith(f"F{n} added"), out)
                self.assertIn(f"  - Contract: {contract}\n", read_file(os.path.join(self.root, ".clerk-dev", "followups.md")))

    def test_a_follow_up_grown_into_a_brief_stays_open_until_closed_with_the_commit(self):
        run_ok("followups", "add", self.root, "Owed work", "--from", "api abc1234", "--contract", "changed: GET /a: x to y")
        followups = os.path.join(self.root, ".clerk-dev", "followups.md")
        today = datetime.date.today().isoformat()
        run_ok("items", "status", followups, "F1", "in-progress", "--ref", "BRIEF-62")
        listed = run_ok("followups", "list", self.root, "--open")
        self.assertRegex(listed, rf"(?m)^  F1\. Owed work.*Status: in-progress; Outcome: {today} BRIEF-62\]$")
        run_ok("followups", "close", self.root, "F1", "--ref", "in 1a2b3c4 (BRIEF-62)")
        text = read_file(followups)
        self.assertIn("- [x] F1. Owed work", text)
        self.assertIn(f"  - Outcome: {today} in 1a2b3c4 (BRIEF-62)\n", text)
        self.assertNotIn("F1.", run_ok("followups", "list", self.root, "--open"))

    def test_a_follow_up_without_a_contract_is_refused(self):
        code, out = run_script("followups", "add", self.root, "Owed work", "--from", "api abc1234")
        self.assertNotEqual(code, 0, out)
        self.assertIn("--contract", out)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".clerk-dev", "followups.md")))

    def test_a_follow_up_with_a_blank_contract_is_refused(self):
        code, out = run_script("followups", "add", self.root, "Owed work", "--from", "api abc1234", "--contract", "  ")
        self.assertNotEqual(code, 0, out)
        self.assertIn("--contract must not be blank", out)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".clerk-dev", "followups.md")))


class PassStepTests(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("work"))
        self.repo.git("checkout", "-q", "-b", "feat")
        write_feature_md(self.repo.path)
        write_record(self.repo.path, "R5", "spec", "Spec five", body=SPEC_BODY.format(a="Five one", b="Five two"))
        write_record(self.repo.path, "R9", "spec", "Spec nine", body=SPEC_BODY.format(a="Nine one", b="Nine two"))
        head = self.repo.head()
        write_log(self.repo.path, "- [ ] M1. Piece five\n  - Spec: R5\n  - Passes: edge-cases\n  - Started: 2026-10-01\n")
        entries = [f"- [ ] P{n}. tests on R9\n  - Piece: R9\n  - Status: abandoned\n" for n in range(2, 12)]
        write_file(
            os.path.join(self.repo.path, ".clerk-dev", "passes.md"),
            f"- [ ] P1. edge-cases on R5\n  - Piece: R5\n  - Status: open\n  - Start: {head}\n\n"
            + "\n".join(entries)
            + f"\n- [ ] P12. tests on R9\n  - Piece: R9\n  - Status: open\n  - Start: {head}\n",
        )

    def test_a_pass_whose_id_starts_another_does_not_hide_its_step(self):
        code, out = self.repo.status("--focus", "implementation")
        self.assertEqual(code, 0, out)
        self.assertIn("Finish pass P12", out)
        self.assertNotIn("Finish pass P1 ", out)


if __name__ == "__main__":
    unittest.main()

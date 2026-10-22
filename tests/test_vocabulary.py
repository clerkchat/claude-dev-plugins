import os
import unittest

from helpers import (
    TempCase,
    init_repo,
    run_ok,
    write_feature_md,
    write_log,
    write_record,
)

BRIEF_BODY = "## Requirements\n\n1. {a}.\n2. {b}.\n\n## Baseline\n\nClean.\n\n## Open items\n\n- [ ] {a} needs a name."


def frontmatter(path):
    with open(path) as f:
        head = f.read().split("---\n")[1]
    return dict(line.split(": ", 1) for line in head.splitlines())


class RecordTypeTests(TempCase):
    def setUp(self):
        super().setUp()
        self.root = self.path("hub")
        os.makedirs(self.root)
        write_feature_md(self.root)
        write_record(self.root, "R2", "spec", "Old brief", body=BRIEF_BODY.format(a="Two one", b="Two two"))
        write_record(self.root, "R3", "capabilities", "Old pieces", body="1. A piece.")

    def records(self, *args):
        return run_ok("records", args[0], self.root, *args[1:])

    def test_old_types_read_as_the_new_ones(self):
        lines = self.records("list").splitlines()
        self.assertTrue(lines[0].startswith("BRIEF-2 brief: Old brief"), lines)
        self.assertTrue(lines[1].startswith("PIECES-3 pieces: Old pieces"), lines)

    def test_listing_by_type_takes_either_name(self):
        for name in ("brief", "spec"):
            with self.subTest(name=name):
                out = self.records("list", "--type", name)
                self.assertTrue(out.startswith("BRIEF-2 brief: Old brief"), out)
                self.assertNotIn("PIECES-3", out)

    def test_a_new_brief_is_written_with_the_new_type_and_file_name(self):
        out = self.records("new", "brief", "Brief four")
        path = out.split()[1]
        self.assertTrue(out.startswith("BRIEF-4 "), out)
        self.assertTrue(path.endswith("004-brief-brief-four.md"), path)
        self.assertEqual(frontmatter(path)["type"], "brief")

    def test_the_old_type_names_write_the_new_types(self):
        for old, new, lead in (("spec", "brief", "BRIEF-4"), ("capabilities", "pieces", "PIECES-5")):
            with self.subTest(old=old):
                out = self.records("new", old, f"From {old}")
                path = out.split()[1]
                self.assertTrue(out.startswith(lead + " "), out)
                self.assertIn(f"-{new}-from-{old}.md", path)
                self.assertEqual(frontmatter(path)["type"], new)

    def test_an_old_record_file_keeps_its_type(self):
        self.records("discard", "R2", "--note", "replaced")
        meta = frontmatter(os.path.join(self.root, ".clerk-dev", "feature", "records", "R2.md"))
        self.assertEqual(meta["type"], "spec")

    def test_the_digest_lists_open_items_of_old_briefs(self):
        digest = self.records("digest")
        self.assertIn("# Open items in active briefs", digest)
        self.assertIn("- BRIEF-2: Two one needs a name.", digest)


class BuildWordsCase(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("work"))
        self.repo.git("checkout", "-q", "-b", "feat")
        write_feature_md(self.repo.path)
        write_record(self.repo.path, "R2", "spec", "Old brief", body=BRIEF_BODY.format(a="Two one", b="Two two"))
        write_record(self.repo.path, "R3", "brief", "New brief", body=BRIEF_BODY.format(a="Three one", b="Three two"))
        write_record(self.repo.path, "R4", "plan", "The plan", body="1. Piece one, brief BRIEF-3. Done: when three is built.")
        write_log(
            self.repo.path,
            "- [ ] B1. Old open entry\n  - Spec: R2\n  - Requirements: 1\n  - Model: sonnet medium\n"
            "  - Status: briefed\n  - Attempts: 1\n  - Started: 2026-10-01\n",
        )

    def implementation(self):
        code, out = self.repo.status("--focus", "implementation")
        self.assertEqual(code, 0, out)
        return out


class OldLogTests(BuildWordsCase):
    def test_a_briefed_entry_reads_as_handed_off(self):
        self.assertIn("B1 Old open entry  [R2: 1; handed-off; sonnet medium]", self.repo.build_ok("list", "--open"))
        progress = self.repo.build_ok("progress", "--brief", "R2")
        self.assertIn("in progress: BRIEF-2.1", progress)
        self.assertIn("B1 Old open entry: handed-off", progress)

    def test_a_briefed_entry_takes_a_note_and_is_written_in_the_new_words(self):
        self.assertEqual(self.repo.build_ok("note", "B1", "finish the parser"), "B1 note set")
        self.assertEqual(self.repo.field("B1", "Status"), "handed-off")
        self.assertEqual(self.repo.field("B1", "Brief"), "R2")
        self.assertNotIn("Spec:", self.repo.log_text())

    def test_status_asks_to_land_an_old_briefed_entry(self):
        self.assertIn("Land B1 (Old open entry): handed off and not committed", self.implementation())

    def test_the_old_flag_still_names_the_brief(self):
        self.assertEqual(self.repo.build_ok("add", "Two two", "--spec", "R2", "--reqs", "2"), "BUILD-2 handed off: BRIEF-2 requirements 2")
        self.assertEqual(self.repo.field("BUILD-2", "Brief"), "BRIEF-2")
        self.assertIn("BRIEF-2 Old brief", self.repo.build_ok("checklist", "--spec", "BRIEF-2"))


class NewWordsTests(BuildWordsCase):
    def test_a_new_entry_is_handed_off_against_its_brief(self):
        self.assertEqual(self.repo.build_ok("add", "Three one", "--brief", "BRIEF-3", "--reqs", "1"), "BUILD-2 handed off: BRIEF-3 requirements 1")
        self.assertEqual(self.repo.field("BUILD-2", "Status"), "handed-off")
        out = self.repo.build_ok("resend", "BUILD-2", "--note", "narrower")
        self.assertEqual(out, "BUILD-2 handed off again (attempt 2, sonnet medium)")

    def test_a_plan_step_naming_its_brief_gives_the_milestone_its_brief(self):
        self.assertEqual(self.repo.build_ok("milestone", "--step", "PLAN-4.1", "--passes", "edge-cases"), "MILE-1 planned from PLAN-4.1: edge-cases")
        self.assertEqual(self.repo.field("MILE-1", "Brief"), "BRIEF-3")

    def test_status_shows_next_step_notes(self):
        self.repo.build_ok("note", "B1", "finish the parser")
        out = self.implementation()
        self.assertIn("**Next-step notes:**\n- B1 Old open entry: finish the parser", out)
        self.assertNotIn("Handoff notes", out)

    def test_the_overview_plan_reads_a_brief_column(self):
        with open(os.path.join(self.repo.path, ".clerk-dev", "feature", "overview.md"), "w") as f:
            f.write("# Overview\n\n## Plan\n\n| Piece | Brief | Built |\n|---|---|---|\n| 1 Piece one | BRIEF-3 | not started |\n| 2 Piece two | none | not started |\n")
        code, out = self.repo.status("--focus", "design")
        self.assertEqual(code, 0, out)
        self.assertIn("- 1 Piece one (BRIEF-3): not ready: no design check", out)
        self.assertIn("- 2 Piece two: no brief", out)


if __name__ == "__main__":
    unittest.main()

import os
import unittest

from helpers import TempCase, init_repo, run_script, write_feature_md, write_record

CHECK = """# Design check: R5 Spec five

Checked 2026-10-21: R5.

- [ ] Q-1. Which store holds it?
  - Weight: settle-first
- [ ] Q-2. What is the name?
  - Weight: minor
"""

FINDING = "- id: {n}\n  lens: tests\n  severity: minor\n  file: a.py\n  line: 1\n  title: Finding {n}\n"


class BlockersCase(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("work"))
        self.repo.git("checkout", "-q", "-b", "feat")
        write_feature_md(self.repo.path)
        write_record(self.repo.path, "R5", "spec", "Spec five", body="## Requirements\n\n1. One.\n\n## Baseline\n\nClean.")

    def blockers(self):
        code, out = self.repo.status("--focus", "blockers")
        self.assertEqual(code, 0, out)
        return out

    def write_check(self):
        checks = os.path.join(self.repo.path, ".clerk-dev", "feature", "checks")
        os.makedirs(checks, exist_ok=True)
        with open(os.path.join(checks, "R5-1.md"), "w") as f:
            f.write(CHECK)

    def write_run(self, sections, instructions=(), statuses=()):
        run = os.path.join(self.repo.path, ".clerk-dev", "latest")
        os.makedirs(run, exist_ok=True)
        head = self.repo.git("rev-parse", "HEAD")
        files = {
            "merged.md": "```findings\n" + "".join(FINDING.format(n=n) for n in sections) + "```\n",
            "target.txt": f"branch\n{self.repo.git('rev-parse', 'main')}\n{head}\n",
            "numbers.tsv": "number\tmerged_id\tsection\n" + "".join(f"{n}\t{n}\t{s}\n" for n, s in sections.items()),
            "instructions.tsv": "merged_id\tchoice\n" + "".join(f"{n}\t{c}\n" for n, c in instructions),
            "status.tsv": "merged_id\tstatus\tref\tdate\n" + "".join(f"{n}\t{s}\tabc\t\n" for n, s in statuses),
        }
        for name, text in files.items():
            with open(os.path.join(run, name), "w") as f:
                f.write(text)


class BlockersTests(BlockersCase):
    def test_nothing_blocking(self):
        out = self.blockers()
        self.assertIn("## What blocks", out)
        self.assertIn("Nothing blocking.", out)
        self.assertNotIn("**Next:**", out)

    def test_a_stopped_handoff_appears_with_its_question(self):
        self.repo.build_ok("add", "Five piece", "--spec", "R5", "--reqs", "1")
        self.repo.build_ok("stop", "BUILD-1", "--question", "Which store holds it?")
        out = self.blockers()
        self.assertIn("**Handoffs stopped on a question:**", out)
        self.assertIn("BUILD-1", out)
        self.assertIn("Which store holds it?", out)
        self.assertNotIn("Nothing blocking.", out)
        self.assertIn("1. Answer the question of the stopped handoff", out)

    def test_a_settle_first_question_appears_and_another_does_not(self):
        self.write_check()
        out = self.blockers()
        self.assertIn("**Settle-first design questions:**", out)
        self.assertIn("-1.Q-1", out)
        self.assertNotIn("Q-2", out)
        self.assertIn("walk the design questions", out)

    def test_an_open_follow_up_appears_and_status_seen_is_not_written(self):
        code, out = run_script("followups", "add", self.repo.path, "Send exportId back", "--from", "api abc1234")
        self.assertEqual(code, 0, out)
        out = self.blockers()
        self.assertIn("**Follow-ups owed here:**", out)
        self.assertIn("Send exportId back", out)
        self.assertIn("go through the follow-ups", out)
        self.assertFalse(os.path.exists(os.path.join(self.repo.path, ".clerk-dev", "status-seen")))

    def test_a_fix_section_finding_appears_whatever_its_mark_and_a_closed_one_does_not(self):
        self.write_run(
            {1: "fix", 2: "fix", 3: "fix", 4: "look"},
            instructions=[(2, "fix"), (3, "ignore")],
        )
        out = self.blockers()
        self.assertIn("**Findings to fix before merging:** 2 (1, 2)", out)
        self.assertIn("work the queue", out)

    def test_a_fixed_finding_does_not_appear(self):
        self.write_run({1: "fix"}, statuses=[(1, "fixed")])
        self.assertIn("Nothing blocking.", self.blockers())

    def test_other_sections_do_not_block(self):
        self.write_run({1: "look", 2: "debt"})
        self.assertIn("Nothing blocking.", self.blockers())


if __name__ == "__main__":
    unittest.main()

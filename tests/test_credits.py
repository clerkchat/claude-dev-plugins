import datetime
import os
import shutil
import sys
import unittest

from helpers import SCRIPTS, RenderRunCase, RunCase, defect, merged_md, run_ok, write_file

sys.path.insert(0, SCRIPTS)
import records
import run_files

sf = records.load_script("stale-findings.py")

def credit(mid, path, line=20):
    return (
        f"- id: {mid}\n  lens: credit\n  slice: api\n  confidence: 90\n  file: {path}\n  line: {line}\n"
        f"  title: Guards the retry\n  claim: Credit {mid} guards the retry before it sends.\n"
        f"  context: The sibling handler sends twice.\n  evidence: read {path}\n"
    )


CONFIRMED = "verdict: confirmed | confidence: 90 | severity: major"


class CreditCase(RenderRunCase):
    def setUp(self):
        super().setUp()
        self.write_run(defect(7, "a.py"), credit(9, "c.py"))

    def write_run(self, *entries):
        self.write_merged(*entries)
        for entry in entries:
            self.write(f"verify/{entry.split()[2]}.md", CONFIRMED)


class NoCreditsTest(CreditCase):
    def setUp(self):
        super().setUp()
        self.write_run(defect(7, "a.py"))
        self.out = self.render()

    def test_leaves_the_count_out_of_the_front_matter(self):
        self.assertNotIn("credits:", self.report())

    def test_leaves_the_count_out_of_the_summary_line(self):
        self.assertNotIn("credits", self.out)

    def test_has_no_credits_section(self):
        self.assertNotIn("\n## Credits\n", self.report())


class CreditsSectionTest(CreditCase):
    def setUp(self):
        super().setUp()
        self.out = self.render()

    def test_comes_after_the_defects_and_before_the_closing_sections(self):
        report = self.report()
        self.assertLess(report.index("#### 1. "), report.index("## Credits"))
        self.assertLess(report.index("## Credits"), report.index("## Not reviewed this run"))

    def test_heads_the_section(self):
        self.assertIn("\n## Credits\n", self.report())

    def test_carries_the_counts_in_its_intro(self):
        self.assertIn("1 credit, 0 marked Post.", self.report())

    def test_numbers_the_credit_in_its_section(self):
        self.assertIn("2\t9\tcredit\n", self.read("numbers.tsv"))

    def test_counts_credits_in_the_front_matter(self):
        self.assertIn(", credits: 1, below: 0 }", self.report())

    def test_names_the_count_in_the_summary_line(self):
        self.assertIn("credits 1", self.out)

    def test_shows_credit_as_the_glance_action(self):
        self.assertRegex(self.report(), r"\| 2 +\| Guards the retry +\|.*\| credit +\|")

    def test_leaves_credits_out_of_the_triage_line(self):
        self.assertIn("0 post, 1 not decided.", self.report())


class MarkedCreditTest(CreditCase):
    def setUp(self):
        super().setUp()
        self.render()
        self.render("--instruct", "2=post")

    def test_counts_the_credit_marked_post_in_the_intro(self):
        self.assertIn("1 credit, 1 marked Post.", self.report())

    def test_leaves_it_out_of_the_triage_line(self):
        self.assertIn("0 post, 1 not decided.", self.report())


class PostedCreditThreadTest(CreditCase):
    def setUp(self):
        super().setUp()
        self.render()
        self.render("--instruct", "2=post")
        run_files.write_posted(self.run_dir, {9: {"state": "posted", "kind": "line", "comment_id": "5", "path": "c.py", "line": "20"}})
        run_files.write_threads(self.run_dir, {9: {"comment_id": "5", "state": "resolved", "outdated": "0", "replies": [("bob", "Thanks.")]}})
        self.render()

    def test_shows_the_replies(self):
        self.assertIn("Replies: @bob: Thanks.", self.card(2))

    def test_shows_the_state(self):
        self.assertIn("State: marked resolved on GitHub.", self.card(2))


class CreditCardTest(CreditCase):
    def setUp(self):
        super().setUp()
        self.render()
        self.text = self.card(2)

    def test_names_the_kind_and_area(self):
        self.assertIn("**Credit** · Api", self.text)

    def test_names_the_focus(self):
        self.assertIn("Focus: credits", self.text)

    def test_shows_the_claim(self):
        self.assertIn("Credit 9 guards the retry before it sends.", self.text)

    def test_shows_the_context(self):
        self.assertIn("##### Context\n\nThe sibling handler sends twice.", self.text)

    def test_has_no_status_line(self):
        self.assertNotIn("- [ ] Open", self.text)

    def test_has_no_defect_sections(self):
        self.assertNotRegex(self.text, r"Why it matters|How it goes wrong|Recommendation")

    def test_lists_post_and_ignore_only(self):
        self.assertIn("##### Instruction\n\n- [ ] Post\n- [ ] Ignore\n\nNotes:", self.text)


class CreditSecondOpinionTest(CreditCase):
    def opinion(self, note):
        self.write("verify/9.md", f"verdict: adjusted | confidence: 80 | note: {note}")
        self.render()
        return self.card(2)

    def test_shows_the_verifier_note(self):
        self.assertIn("##### Second opinion\n\nTrue for one path only.", self.opinion("True for one path only."))

    def test_shows_a_note_with_a_pipe_whole(self):
        self.assertIn("True for string | null only.", self.opinion("True for string | null only."))


class CreditInstructTest(CreditCase):
    def setUp(self):
        super().setUp()
        self.render()

    def test_sets_post(self):
        self.render("--instruct", "2=post:say it warmly")
        self.assertEqual(self.instruction(9)["choice"], "post")

    def test_refuses_another_choice_naming_the_two(self):
        self.assertIn("is a credit: use N=post[:note], N=ignore[:note], N=none", self.render_fails("--instruct", "2=fix"))

    def test_refuses_a_status(self):
        self.assertIn("is a credit, which has no status", self.render_fails("--set", "2=fixed:abc1234"))


class CreditIgnoreTest(CreditCase):
    def setUp(self):
        super().setUp()
        self.render()
        self.render("--instruct", "2=ignore")

    def test_records_the_instruction(self):
        self.assertEqual(self.instruction(9)["choice"], "ignore")

    def test_sets_no_status(self):
        self.assertIsNone(self.status(9))

    def test_writes_no_rendered_status_row(self):
        self.assertNotIn("9\t", self.read("rendered-status.tsv"))


class CreditStatusRowTest(CreditCase):
    def test_drops_a_status_row_for_a_credit(self):
        self.write_status({9: ("fixed", "abc")})
        self.render()
        self.assertIsNone(self.status(9))


class CreditTickTest(CreditCase):
    def setUp(self):
        super().setUp()
        self.render()

    def test_imports_a_ticked_post_as_an_instruction(self):
        self.edit_report("- [ ] Post\n- [ ] Ignore", "- [x] Post\n- [ ] Ignore")
        self.render()
        self.assertEqual(self.instruction(9)["choice"], "post")

    def test_does_not_import_a_ticked_post_as_a_status(self):
        self.edit_report("- [ ] Post\n- [ ] Ignore", "- [x] Post\n- [ ] Ignore")
        self.render()
        self.assertIsNone(self.status(9))

    def test_drops_a_tick_on_another_label_with_a_warning(self):
        self.edit_report("- [ ] Post\n- [ ] Ignore", "- [ ] Post\n- [ ] Ignore\n- [x] Discuss")
        self.assertIn("merged id 9 is a credit; dropped the tick on Discuss: only Post and Ignore apply", self.render())

    def test_leaves_the_instruction_unset_after_the_dropped_tick(self):
        self.edit_report("- [ ] Post\n- [ ] Ignore", "- [ ] Post\n- [ ] Ignore\n- [x] Discuss")
        self.render()
        self.assertEqual(self.instruction(9).get("choice", ""), "")


class OverlapCase(CreditCase):
    def setUp(self):
        super().setUp()
        self.write_run(defect(7, "a.py"), credit(9, "a.py", line=4))


class CreditOverlappingADefectTest(OverlapCase):
    def setUp(self):
        super().setUp()
        self.render()

    def test_is_not_numbered(self):
        self.assertNotIn("\t9\t", self.read("numbers.tsv"))

    def test_is_counted_in_about_this_review(self):
        self.assertIn("1 credit dropped for overlapping a confirmed defect.", self.report())


class PostedCreditOverlappingADefectTest(OverlapCase):
    def setUp(self):
        super().setUp()
        run_files.write_posted(self.run_dir, {9: {"state": "posted", "kind": "line", "path": "a.py", "line": "4"}})
        self.render()

    def test_is_kept(self):
        self.assertIn("2\t9\tcredit\n", self.read("numbers.tsv"))

    def test_names_the_finding_it_overlaps(self):
        self.assertIn("Overlaps finding 1.", self.card(2))


class DraftedCreditOverlappingADefectTest(OverlapCase):
    def test_is_dropped(self):
        run_files.write_posted(self.run_dir, {9: {"state": "drafted", "note": ""}})
        self.render()
        self.assertNotIn("\t9\t", self.read("numbers.tsv"))


class CreditEditedAfterPostingOverlappingADefectTest(OverlapCase):
    def test_is_kept(self):
        run_files.write_posted(self.run_dir, {9: {"state": "edited", "kind": "line", "path": "a.py", "line": "4"}})
        self.render()
        self.assertIn("2\t9\tcredit\n", self.read("numbers.tsv"))


class CreditOverlappingAFixedDefectTest(OverlapCase):
    def test_stays_dropped(self):
        self.render()
        self.render("--set", "1=fixed:abc1234")
        self.assertNotIn("\t9\t", self.read("numbers.tsv"))


class NumberedCreditLaterOverlappedCase(CreditCase):
    def setUp(self):
        super().setUp()
        self.render()
        self.write_run(defect(7, "a.py"), defect(8, "c.py", line=20), credit(9, "c.py"))
        self.render()


class NumberedCreditLaterOverlappedTest(NumberedCreditLaterOverlappedCase):
    def test_keeps_its_number_as_hidden(self):
        self.assertIn("2\t9\thidden\n", self.read("numbers.tsv"))

    def test_gives_the_new_defect_the_next_number(self):
        self.assertIn("3\t8\tfix\n", self.read("numbers.tsv"))


class NumberedCreditBackAfterTheOverlapGoesTest(NumberedCreditLaterOverlappedCase):
    def setUp(self):
        super().setUp()
        self.write("verify/8.md", "verdict: rejected | confidence: 10 | note: not real")
        self.render()

    def test_returns_with_its_number(self):
        self.assertIn("2\t9\tcredit\n", self.read("numbers.tsv"))


class CreditWithoutALineTest(CreditCase):
    def setUp(self):
        super().setUp()
        self.write_run(defect(7, "a.py"), credit(9, "a.py", line=""))
        self.render()

    def test_is_kept_beside_a_defect_in_its_file(self):
        self.assertIn("2\t9\tcredit\n", self.read("numbers.tsv"))

    def test_shows_its_file_as_the_location(self):
        self.assertIn("Focus: credits\n\na.py\n", self.card(2))


class CreditsOnlyRunTest(CreditCase):
    def setUp(self):
        super().setUp()
        self.write_run(credit(9, "c.py"))
        self.render()

    def test_numbers_the_credit_first(self):
        self.assertIn("1\t9\tcredit\n", self.read("numbers.tsv"))

    def test_counts_nothing_to_decide(self):
        self.assertIn("0 post, 0 not decided.", self.report())


class EmptyRunTest(CreditCase):
    def setUp(self):
        super().setUp()
        self.write_run()
        self.render()

    def test_has_no_credits_section(self):
        self.assertNotIn("\n## Credits\n", self.report())


class SinceCase(CreditCase):
    def compare(self, *rows):
        self.write("reconcile/previous.txt", "prev\n")
        self.write("reconcile/matches.tsv", "cur_id\tprev_id\thow\tprev_number\tprev_status\tprev_ref\n" + "".join(rows))
        self.render()


class CreditCarriedWithALegacyStatusTest(SinceCase):
    def setUp(self):
        super().setUp()
        self.write_status({9: ("fixed", "abc1234")})
        self.compare("7\t7\tcarried\t1\topen\t\n", "9\t9\tcarried\t2\tfixed\tabc1234\n")

    def test_is_left_out_of_still_open(self):
        self.assertIn("- Still open: 1\n", self.report())

    def test_stays_in_credits(self):
        self.assertIn("2\t9\tcredit\n", self.read("numbers.tsv"))


class CreditResolvedByRecheckTest(SinceCase):
    def setUp(self):
        super().setUp()
        self.write("reconcile/since.tsv", "prev_id\toutcome\tnote\n9\tresolved\t\n")
        self.compare("7\t7\tcarried\t1\topen\t\n", "9\t9\tcarried\t2\tfixed\tabc1234\n")

    def test_is_left_out_of_resolved(self):
        self.assertIn("- Resolved, confirmed by recheck: 0\n", self.report())


class CreditNewSinceThePreviousReviewTest(SinceCase):
    def test_is_left_out_of_new(self):
        self.compare("7\t7\tcarried\t1\topen\t\n")
        self.assertIn("- New: 0\n", self.report())


class CarryTickedCreditTest(CreditCase):
    def setUp(self):
        super().setUp()
        self.render()
        self.cur = self.path("cur")

    def carry_tick(self, label):
        boxes = "- [ ] Post\n- [ ] Ignore\n"
        self.edit_report(boxes, boxes.replace(f"- [ ] {label}", f"- [x] {label}"))
        run_ok("carry", self.run_dir, self.cur)
        return run_files.read_instructions(self.cur).get(9, {}).get("choice"), run_files.read_status(self.cur).get(9)

    def test_carries_a_ticked_post_as_an_instruction_only(self):
        self.assertEqual(self.carry_tick("Post"), ("post", None))

    def test_carries_a_ticked_ignore_as_an_instruction_only(self):
        self.assertEqual(self.carry_tick("Ignore"), ("ignore", None))


class CarryAgreesWithRenderTest(CreditCase):
    def setUp(self):
        super().setUp()
        self.render()
        self.edit_report("- [ ] Ignore", "- [x] Ignore")
        self.write_status({9: ("fixed", "abc1234")})
        self.twin = self.path("twin")
        shutil.copytree(self.run_dir, self.twin)
        run_ok("carry", self.run_dir, self.path("cur"))
        run_ok("render-report", self.twin, "--target", "t", "--repo", self.tmp, "--date", datetime.date.today().isoformat(), "--wrap", "0")

    def both(self, name):
        with open(os.path.join(self.twin, name), encoding="utf-8") as f:
            return self.read(name), f.read()

    def test_mirrors_the_ignore_into_status(self):
        self.assertEqual(self.status(7)["status"], "wont-fix")

    def test_writes_the_status_render_writes(self):
        carried, rendered = self.both("status.tsv")
        self.assertEqual(carried, rendered)

    def test_writes_the_instructions_render_writes(self):
        carried, rendered = self.both("instructions.tsv")
        self.assertEqual(carried, rendered)


class CreditOverlappingAProposalTest(CreditCase):
    def test_is_kept(self):
        self.write_run(defect(7, "a.py", extra="  debt: cleanup\n"), credit(9, "a.py", line=4))
        self.render()
        self.assertIn("\t9\tcredit\n", self.read("numbers.tsv"))


class RejectedCreditTest(CreditCase):
    def test_is_not_numbered(self):
        self.write("verify/9.md", "verdict: rejected | confidence: 20 | note: not true")
        self.render()
        self.assertNotIn("\t9\t", self.read("numbers.tsv"))


class LoadFindingsTest(CreditCase):
    def test_hides_credits(self):
        self.assertEqual(list(sf.load_findings(self.run_dir)), [7])


class ReconcileCase(RunCase):
    def setUp(self):
        super().setUp()
        self.prev = self.run_dir
        self.cur = self.path("cur")
        self.write_merged(defect(7, "a.py"), credit(9, "c.py"))
        self.write_numbers({7: "fix", 9: "credit"})


class ReconcileUnmatchedTest(ReconcileCase):
    def setUp(self):
        super().setUp()
        os.makedirs(self.cur)
        with open(os.path.join(self.cur, "merged.md"), "w") as f:
            f.write("```findings\n```\n")
        run_ok("reconcile", self.prev, self.cur)
        with open(os.path.join(self.cur, "reconcile", "unmatched.tsv")) as f:
            self.rows = [line.split("\t")[0] for line in f.read().splitlines()[1:]]

    def test_leaves_an_unmatched_credit_out(self):
        self.assertNotIn("9", self.rows)

    def test_keeps_an_unmatched_defect(self):
        self.assertIn("7", self.rows)


class ReconcileOnlyCreditsCase(ReconcileCase):
    def reconcile(self, *cur_entries):
        os.makedirs(self.cur)
        with open(os.path.join(self.cur, "merged.md"), "w") as f:
            f.write("```findings\n" + "".join(cur_entries) + "```\n")
        run_ok("reconcile", self.prev, self.cur)

    def rows(self, name):
        with open(os.path.join(self.cur, "reconcile", name)) as f:
            return [line.split("\t")[:2] for line in f.read().splitlines()[1:]]


class ReconcileOnlyCreditsNowTest(ReconcileOnlyCreditsCase):
    def setUp(self):
        super().setUp()
        self.reconcile(credit(1, "c.py"))

    def test_matches_the_credit_to_the_previous_credit(self):
        self.assertIn(["1", "9"], self.rows("matches.tsv"))

    def test_lists_the_previous_defect_as_unmatched(self):
        self.assertEqual([r[0] for r in self.rows("unmatched.tsv")], ["7"])


class ReconcileOnlyCreditsBeforeTest(ReconcileOnlyCreditsCase):
    def setUp(self):
        super().setUp()
        self.write_merged(credit(9, "c.py"))
        self.write_numbers({9: "credit"})
        self.reconcile(defect(1, "c.py", line=20))

    def test_matches_nothing(self):
        self.assertEqual(self.rows("matches.tsv"), [])

    def test_lists_nothing_as_unmatched(self):
        self.assertEqual(self.rows("unmatched.tsv"), [])


class ReconcileMatchTest(ReconcileCase):
    def test_never_matches_a_credit_with_a_defect(self):
        os.makedirs(self.cur)
        with open(os.path.join(self.cur, "merged.md"), "w") as f:
            f.write("```findings\n- id: 1\n  lens: credit\n  confidence: 90\n  file: a.py\n  line: 3\n  claim: Finding 7 breaks.\n```\n")
        run_ok("reconcile", self.prev, self.cur)
        with open(os.path.join(self.cur, "reconcile", "matches.tsv")) as f:
            self.assertEqual(f.read().splitlines()[1:], [])


class AppendCase(RunCase):
    def setUp(self):
        super().setUp()
        self.write_merged(defect(7, "a.py"), credit(9, "c.py"))
        self.new = self.path("new.md")
        write_file(self.new, merged_md(credit(1, "c.py")))

    def append(self, judged):
        write_file(self.path("judged.tsv"), "new_id\tcarried_id\tverdict\n" + judged)
        return run_ok("reconcile", "--append", self.new, self.run_dir, "--judged", self.path("judged.tsv"))

    def appended(self):
        return self.read("reconcile/appended.tsv").splitlines()[1:]


class AppendCreditJudgedStaleTest(AppendCase):
    def setUp(self):
        super().setUp()
        self.out = self.append("1\t9\tstale\n")

    def test_does_not_drop_the_new_credit(self):
        self.assertEqual(self.read("reconcile/dropped.tsv"), "")

    def test_folds_its_evidence_into_the_carried_credit(self):
        self.assertIn("evidence: read c.py | read c.py", self.read("merged.md"))

    def test_warns_that_it_is_taken_as_a_duplicate(self):
        self.assertIn("new finding 1: a credit judged stale; treating it as a duplicate of 9", self.out)


class AppendCreditJudgedRegressedTest(AppendCase):
    def setUp(self):
        super().setUp()
        self.out = self.append("1\t9\tregressed\n")

    def test_does_not_drop_the_new_credit(self):
        self.assertEqual(self.read("reconcile/dropped.tsv"), "")

    def test_appends_nothing(self):
        self.assertEqual(self.appended(), [])

    def test_warns_that_it_is_taken_as_a_duplicate(self):
        self.assertIn("new finding 1: a credit judged regressed; treating it as a duplicate of 9", self.out)


class AppendJudgedAgainstNothingTest(AppendCase):
    def setUp(self):
        super().setUp()
        self.out = self.append("1\t\tduplicate\n")

    def test_appends_the_new_finding(self):
        self.assertEqual(self.appended(), ["10"])

    def test_warns_that_the_verdict_is_ignored(self):
        self.assertIn("new finding 1: judged against nothing", self.out)


class AppendDefectBesideACarriedCreditTest(AppendCase):
    def setUp(self):
        super().setUp()
        write_file(self.new, merged_md(defect(1, "c.py", line=20)))
        self.out = self.append("1\t9\tduplicate\n")

    def test_appends_the_defect(self):
        self.assertEqual(self.appended(), ["10"])

    def test_ignores_the_verdict_against_the_credit(self):
        self.assertIn("new finding 1: judged against 9, which was not among its candidates", self.out)


class AppendJudgedAgainstANonCandidateTest(AppendCase):
    def setUp(self):
        super().setUp()
        self.out = self.append("1\t7\tduplicate\n")

    def test_appends_the_new_finding(self):
        self.assertEqual(self.appended(), ["10"])

    def test_warns_that_the_verdict_is_ignored(self):
        self.assertIn("new finding 1: judged against 7, which was not among its candidates", self.out)


class FinalReportTest(RunCase):
    def test_names_the_credit_lens_as_left_out_by_design(self):
        self.write_merged(defect(7, "a.py"))
        self.write_numbers({7: "fix"})
        self.write_target("branch", "a" * 40, "b" * 40)
        self.write("raw/security.md", "")
        run_ok("final-report", self.run_dir)
        left_out = next(l for l in self.read("final-review-report.md").splitlines() if l.startswith("Left out by design"))
        self.assertIn("credits", left_out)

    def test_leaves_out_a_credit_appended_by_an_incremental_review(self):
        self.write_merged(defect(7, "a.py"), credit(9, "c.py"))
        self.write_numbers({7: "fix", 9: "credit"})
        self.write_target("branch", "a" * 40, "b" * 40)
        self.write("raw/security.md", "")
        self.write("reconcile/appended.tsv", "merged_id\n9\n")
        run_ok("final-report", self.run_dir)
        self.assertNotIn("Guards the retry", self.read("final-review-report.md"))

    def test_names_an_appended_finding_missing_from_merged_by_its_id(self):
        self.write_merged(defect(7, "a.py"))
        self.write_numbers({7: "fix", 12: "look"})
        self.write_target("branch", "a" * 40, "b" * 40)
        self.write("raw/security.md", "")
        self.write("reconcile/appended.tsv", "merged_id\n12\n")
        run_ok("final-report", self.run_dir)
        self.assertIn("merged 12", self.read("final-review-report.md"))


if __name__ == "__main__":
    unittest.main()

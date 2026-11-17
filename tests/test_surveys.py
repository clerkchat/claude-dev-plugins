import os
import re
import sys
import unittest

from helpers import SCRIPTS, TempCase, feature_md_link, init_repo, read_feature_md, run_ok, run_script, write_feature_md, write_file, write_record
import paths

sys.path.insert(0, SCRIPTS)
import records

SURVEY = """# Survey: src/export

Surveyed 2026-10-30: src/export. For: {target}. Lenses: tech-debt, tenancy.

- [ ] Q-1. Extract the export query helper
  - Lens: tech-debt
  - Kind: refactor
  - Weight: do-first
  - Status: open
- [ ] Q-2. Tenant missing on the export job
  - Lens: tenancy
  - Kind: trap
  - Weight: worth-doing
  - Status: open
"""

BRIEF_BODY = "## Requirements\n\n1. Five one.\n\n## Baseline\n\nClean."


def section(text, heading):
    m = re.search(rf"^# {heading}\n(.*?)(?=^# |\Z)", text, re.S | re.M)
    return m.group(1) if m else ""


class SurveyFileCase(TempCase):
    target = "BRIEF-5"

    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("work"), with_origin=False)
        self.root = self.repo.path
        write_feature_md(self.root)
        write_record(self.root, "BRIEF-5", "brief", "Spec five", body=BRIEF_BODY)
        self.survey = os.path.join(paths.checks_dir(self.root), "SURVEY-1.md")
        write_file(self.survey, SURVEY.format(target=self.target))

    def status(self, *args):
        code, out = self.repo.status(*args)
        self.assertEqual(code, 0, out)
        return out

    def index(self):
        run_ok("records", "index", self.root)
        return read_feature_md(self.root)

    def survey_row(self, cells):
        return f"| [SURVEY-1]({feature_md_link(self.root, self.survey)}) | {cells} |"


class SurveyHeaderTests(SurveyFileCase):
    def test_the_header_reader_returns_a_survey_and_its_for_record(self):
        with open(self.survey) as f:
            self.assertEqual(records.check_header(f.read()), (records.SURVEY, ["BRIEF-5"]))

    def test_the_index_lists_the_survey_under_checks_with_its_record(self):
        self.assertIn(self.survey_row("BRIEF-5 | 2 | 0"), self.index())

    def test_names_glosses_the_survey(self):
        self.assertEqual(run_ok("records", "names", self.root, "SURVEY-1"), "SURVEY-1: survey of src/export")

    def test_names_glosses_an_item_of_the_survey(self):
        out = run_ok("records", "names", self.root, "SURVEY-1.Q-2")
        self.assertEqual(out, "SURVEY-1.Q-2: item 2 of survey of src/export: Tenant missing on the export job")


class SurveyForNoRecordTests(SurveyFileCase):
    target = "none"

    def test_the_index_lists_paths_as_its_records(self):
        self.assertIn(self.survey_row("paths | 2 | 0"), self.index())

    def test_no_brief_counts_it_as_its_design_check(self):
        self.assertIn("- BRIEF-5 Spec five: not ready: no design check", self.status("--focus", "design"))


class SurveyNamesUnknownTests(SurveyFileCase):
    def test_a_survey_whose_file_is_missing_is_unknown(self):
        self.assertEqual(run_ok("records", "names", self.root, "SURVEY-9"), "SURVEY-9: unknown")

    def test_an_item_id_that_is_not_in_the_file_is_unknown(self):
        self.assertEqual(run_ok("records", "names", self.root, "SURVEY-1.Q-9"), "SURVEY-1.Q-9: unknown")

    def test_an_item_of_a_missing_survey_is_unknown(self):
        self.assertEqual(run_ok("records", "names", self.root, "SURVEY-9.Q-1"), "SURVEY-9.Q-1: unknown")


class WrappedHeaderTests(unittest.TestCase):
    def test_a_surveyed_line_that_wraps_before_for_still_names_its_record(self):
        text = "# Survey: x\n\nSurveyed 2026-11-03: BRIEF-85, src/a.py,\nsrc/b.py. For: BRIEF-85. Lenses: tech debt.\n"
        self.assertEqual(records.check_header(text, "SURVEY-2"), (records.SURVEY, ["BRIEF-85"]))

    def test_a_checked_line_that_wraps_in_its_record_list_names_every_record(self):
        text = "# Check\n\nChecked 2026-11-03: BRIEF-85,\nBRIEF-86. Lenses: tech debt.\n"
        self.assertEqual(records.check_header(text, "BRIEF-85-1"), (records.DESIGN_CHECK, ["BRIEF-85", "BRIEF-86"]))

    def test_a_surveyed_line_does_not_read_a_for_from_the_next_paragraph(self):
        for gap in ("\n\n", "\n  \n", "\r\n\r\n"):
            with self.subTest(gap=repr(gap)):
                text = f"Surveyed 2026-11-03: src/a.py.{gap}For: BRIEF-9.\n"
                self.assertEqual(records.check_header(text, "SURVEY-2"), (records.SURVEY, []))


class SurveyWithoutSurveyedLineTests(SurveyFileCase):
    def setUp(self):
        super().setUp()
        write_file(self.survey, "# Survey: src/export\n\nSurveyed on some day.\n")

    def test_the_header_reader_reads_the_file_as_a_survey_by_its_name(self):
        self.assertEqual(records.check_header("Surveyed on some day.\n", "SURVEY-1"), (records.SURVEY, []))

    def test_the_index_lists_it_as_a_survey_of_paths(self):
        self.assertIn(self.survey_row("paths | 0 | 0"), self.index())

    def test_a_design_check_without_a_checked_line_stays_a_design_check(self):
        self.assertEqual(records.check_header("# Check\n", "BRIEF-5-1"), (records.DESIGN_CHECK, []))


class SurveyStatusTests(SurveyFileCase):
    def test_a_survey_for_a_brief_is_not_its_design_check(self):
        self.assertIn("- BRIEF-5 Spec five: not ready: no design check", self.status("--focus", "design"))

    def test_the_feature_lists_the_survey_items_open(self):
        self.assertIn("- survey items open in SURVEY-1 (survey of src/export): 2", self.status())

    def test_the_feature_counts_no_design_questions(self):
        out = self.status()
        self.assertNotIn("design questions open", out)
        self.assertNotIn("open design question", out)


class SurveyDigestTests(SurveyFileCase):
    def setUp(self):
        super().setUp()
        self.digest = run_ok("records", "digest", self.root)

    def test_lists_the_open_items_under_open_survey_items(self):
        self.assertEqual(
            section(self.digest, "Open survey items").strip().splitlines(),
            ["- SURVEY-1.Q-1 (do-first): Extract the export query helper", "- SURVEY-1.Q-2 (worth-doing): Tenant missing on the export job"],
        )

    def test_lists_no_survey_item_as_a_design_question(self):
        self.assertNotIn("SURVEY-1", section(self.digest, "Open design questions"))


class SurveyBoxCheckedButStatusOpenTests(SurveyFileCase):
    def setUp(self):
        super().setUp()
        with open(self.survey) as f:
            text = f.read()
        write_file(self.survey, text.replace("- [ ] Q-1.", "- [x] Q-1."))

    def test_the_index_counts_the_item_open(self):
        self.assertIn(self.survey_row("BRIEF-5 | 2 | 0"), self.index())

    def test_the_feature_counts_the_item_open(self):
        self.assertIn("- survey items open in SURVEY-1 (survey of src/export): 2", self.status())

    def test_the_digest_lists_the_item_open(self):
        digest = run_ok("records", "digest", self.root)
        self.assertIn("- SURVEY-1.Q-1 (do-first)", section(digest, "Open survey items"))


class ValidateSurveyItemsTests(SurveyFileCase):
    def setUp(self):
        super().setUp()
        with open(self.survey) as f:
            self.text = f.read().replace("  - Kind: refactor\n", "  - Kind: refactor\n  - Where: /repo/src/export/job.ts:42\n")

    def validate(self, text=None):
        write_file(self.survey, self.text if text is None else text)
        return run_script("items", "validate", self.survey)

    def test_a_valid_survey_passes(self):
        code, out = self.validate()
        self.assertEqual(code, 0, out)

    def test_a_weight_with_a_trailing_note_passes(self):
        code, out = self.validate(self.text.replace("Weight: do-first", "Weight: do-first (the next change needs it)"))
        self.assertEqual(code, 0, out)

    def test_rejects_a_weight_of_a_design_check(self):
        code, out = self.validate(self.text.replace("Weight: do-first", "Weight: settle-first"))
        self.assertNotEqual(code, 0)
        self.assertIn("Q-1: weight", out)

    def test_rejects_a_kind_other_than_refactor_or_trap(self):
        code, out = self.validate(self.text.replace("Kind: trap", "Kind: bug"))
        self.assertNotEqual(code, 0)
        self.assertIn("Q-2: kind", out)

    def test_rejects_a_relative_where(self):
        code, out = self.validate(self.text.replace("/repo/src/export/job.ts:42", "src/export/job.ts:42"))
        self.assertNotEqual(code, 0)
        self.assertIn("Q-1: where", out)

    def test_rejects_a_where_without_a_line(self):
        code, out = self.validate(self.text.replace("/repo/src/export/job.ts:42", "/repo/src/export/job.ts"))
        self.assertNotEqual(code, 0)
        self.assertIn("Q-1: where", out)


class ValidateDesignCheckWeightTests(SurveyFileCase):
    def setUp(self):
        super().setUp()
        self.check = os.path.join(paths.checks_dir(self.root), "CHECK-1.md")

    def validate(self, weight):
        write_file(self.check, f"# Check\n\nChecked 2026-10-30: BRIEF-5.\n\n- [ ] Q-1. A question\n  - Weight: {weight}\n  - Status: open\n")
        return run_script("items", "validate", self.check)

    def test_accepts_a_design_check_weight(self):
        code, out = self.validate("worth-settling")
        self.assertEqual(code, 0, out)

    def test_rejects_a_survey_weight(self):
        code, out = self.validate("do-first")
        self.assertNotEqual(code, 0)
        self.assertIn("Q-1: weight", out)


if __name__ == "__main__":
    unittest.main()

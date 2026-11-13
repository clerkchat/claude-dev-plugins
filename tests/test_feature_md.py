import os
import re
import unittest

from helpers import TempCase, feature_md_link, init_repo, read_feature_md, records, run_ok, write_file, write_record
import paths


def headings(text, level=2):
    return re.findall(rf"^{'#' * level} .*$", text, re.M)


def section(text, heading):
    m = re.search(rf"^## {heading}\n\n(.*?)\n*(?=^## |\Z)", text, re.S | re.M)
    return m.group(1).splitlines() if m else []


class FeatureCase(TempCase):
    def setUp(self):
        super().setUp()
        self.root = init_repo(self.path("work"), with_origin=False).path
        self.records("start", "Phone digits", "--summary", "Faster lookups.")

    def records(self, cmd, *args):
        return run_ok("records", cmd, self.root, *args)

    def text(self):
        return read_feature_md(self.root)

    def link(self, record_file):
        return feature_md_link(self.root, os.path.join(paths.records_dir(self.root), record_file))


class WhenTheFeatureStartsTests(FeatureCase):
    def test_opens_with_the_name_then_says_it_is_generated(self):
        self.assertEqual(self.text().splitlines()[:3], ["# Feature: Phone digits", "", records.GENERATED])

    def test_names_the_feature(self):
        self.assertEqual(headings(self.text(), 1), ["# Feature: Phone digits"])

    def test_carries_the_summary(self):
        self.assertEqual(section(self.text(), "Summary"), ["Faster lookups."])

    def test_lists_no_records(self):
        self.assertEqual(section(self.text(), "Contents"), ["None yet."])

    def test_the_ledger_file_holds_only_the_name_and_summary(self):
        with open(paths.feature_meta(self.root)) as f:
            self.assertEqual(re.findall(r"^#+ .*$", f.read(), re.M), ["# Feature: Phone digits", "## Summary"])

    def test_the_name_reads_from_the_ledger_file(self):
        self.assertEqual(records.feature_name(self.root), "Phone digits")

    def test_the_summary_reads_from_the_ledger_file(self):
        self.assertEqual(records.feature_summary(self.root), "Faster lookups.")

    def test_status_names_the_feature(self):
        self.assertIn("**Feature:** Phone digits: 0 records", run_ok("status", self.root, "--no-mark"))


class WithRecordsCase(FeatureCase):
    def setUp(self):
        super().setUp()
        write_record(self.root, "DEC-1", "decision", "Poll", extra="area: delivery\n", body="## Decision\n\nPoll it.")
        write_record(self.root, "STORM-2", "brainstorm", "Ideas", status="", body="## Leaning\n\nPoll.")
        write_record(self.root, "DESIGN-3", "design", "Shape", body="## Shape\n\n```\n# not a heading\n```")
        write_record(self.root, "DEC-4", "decision", "Push", body="## Decision\n\nPush it.")
        write_record(self.root, "GUIDE-5", "guidance", "Small", extra="area: delivery\n", body="## Rule\n\nKeep it small.")
        write_record(self.root, "DEC-6", "decision", "Old push", status="superseded", extra="superseded_by: DEC-4\n")
        write_record(self.root, "DEC-7", "decision", "Dropped", status="discarded", extra="note: not needed\n")
        self.records("index")


class WhenPlanStepsSitUnderAHeadingTests(FeatureCase):
    def test_indexing_warns_that_they_are_not_read(self):
        write_record(self.root, "PLAN-1", "plan", "Headed", body="## Steps\n\n1. Piece one. Done: when it is.")
        self.assertIn("warning: plan PLAN-1 has numbered steps under a '## ' heading", self.records("index"))

    def test_indexing_stays_quiet_for_steps_under_the_title(self):
        write_record(self.root, "PLAN-1", "plan", "Plain", body="1. Piece one. Done: when it is.")
        self.assertNotIn("warning", self.records("index"))


class WhenARecordFileIsBrokenTests(FeatureCase):
    def write_raw(self, name, text):
        with open(os.path.join(paths.records_dir(self.root), name), "w") as f:
            f.write(text)

    def test_indexing_names_a_file_whose_header_is_missing(self):
        write_record(self.root, "PLAN-1", "plan", "Plain", body="1. Piece one. Done: when it is.")
        self.write_raw("BRIEF-2-bare.md", "# BRIEF-2. Bare\n\nbody only\n")
        out = self.records("index")
        self.assertIn("warning: BRIEF-2-bare.md has no record header with an id: the body replaced the header", out)

    def test_indexing_names_two_files_sharing_an_id(self):
        write_record(self.root, "PLAN-1", "plan", "First", body="1. A. Done: when it is.")
        self.write_raw("PLAN-1-copy.md", "---\nid: PLAN-1\ntype: plan\ntitle: Copy\n---\n\n1. B. Done: when it is.\n")
        self.assertIn("warning: PLAN-1 is used by both PLAN-1-copy.md and PLAN-1.md", self.records("index"))

    def test_indexing_stays_quiet_for_whole_distinct_records(self):
        write_record(self.root, "PLAN-1", "plan", "First", body="1. A. Done: when it is.")
        write_record(self.root, "DESIGN-2", "design", "Second", body="## Shape\n\nX.")
        self.assertNotIn("warning", self.records("index"))


class ConcatenationTests(WithRecordsCase):
    def test_contents_list_the_current_records_in_body_order(self):
        self.assertEqual(
            [line for line in section(self.text(), "Contents") if line.startswith("- ")],
            ["- DESIGN-3: Shape", "- DEC-4: Push", "- STORM-2: Ideas", "- GUIDE-5: Small", "- DEC-1: Poll"],
        )

    def test_groups_by_area_feature_wide_first_and_ends_with_the_past(self):
        self.assertEqual(headings(self.text()), ["## Summary", "## Contents", "## Feature-wide", "## delivery", "## Superseded and discarded"])

    def test_orders_records_by_type_with_brainstorms_last_within_an_area(self):
        self.assertEqual(headings(self.text(), 3), ["### DESIGN-3. Shape", "### DEC-4. Push", "### STORM-2. Ideas", "### GUIDE-5. Small", "### DEC-1. Poll"])

    def test_demotes_a_records_sections_two_levels(self):
        self.assertEqual(headings(self.text(), 4), ["#### Shape", "#### Decision", "#### Leaning", "#### Rule", "#### Decision"])

    def test_leaves_lines_inside_code_fences_alone(self):
        self.assertIn("```\n# not a heading\n```", self.text())

    def test_carries_each_records_body(self):
        self.assertIn("Keep it small.", section(self.text(), "delivery"))

    def test_lists_superseded_and_discarded_records_with_their_fate(self):
        self.assertEqual(
            section(self.text(), "Superseded and discarded"),
            [f"- DEC-6: [Old push]({self.link('DEC-6.md')}), superseded by DEC-4", f"- DEC-7: [Dropped]({self.link('DEC-7.md')}), discarded: not needed"],
        )

    def test_leaves_superseded_and_discarded_records_out_of_the_body(self):
        self.assertNotRegex(self.text(), r"^### DEC-[67]\.")

    def test_is_written_whole(self):
        write_file(paths.feature_md(self.root), "## Hand-written\n")
        self.records("index")
        self.assertNotIn("## Hand-written", self.text())


class WhenAnOverviewExistsTests(WithRecordsCase):
    def setUp(self):
        super().setUp()
        write_file(paths.overview(self.root), "# Overview\n")
        self.records("stamp-overview")

    def test_the_overview_link_resolves_from_feature_md(self):
        target = re.search(r"\[overview\.md\]\(([^)]+)\)", self.text()).group(1)
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(paths.feature_md(self.root)), target)))


class RegenerationTests(FeatureCase):
    def setUp(self):
        super().setUp()
        self.records("new", "decision", "First", "--area", "delivery")
        write_file(paths.feature_md(self.root), "stale\n")

    def first_file(self):
        return os.path.basename(self.records("path", "DEC-1"))

    def test_after_new(self):
        self.records("new", "decision", "Second")
        self.assertIn("- DEC-2: Second", section(self.text(), "Contents"))

    def test_after_new_superseding(self):
        self.records("new", "decision", "Second", "--supersedes", "DEC-1")
        self.assertIn(f"- DEC-1: [First]({self.link(self.first_file())}), superseded by DEC-2", self.text())

    def test_after_discard(self):
        self.records("discard", "DEC-1", "--note", "not needed")
        self.assertIn(f"- DEC-1: [First]({self.link(self.first_file())}), discarded: not needed", self.text())

    def test_after_reactivate(self):
        self.records("discard", "DEC-1")
        write_file(paths.feature_md(self.root), "stale\n")
        self.records("reactivate", "DEC-1")
        self.assertEqual(section(self.text(), "Contents"), ["- DEC-1: First"])

    def test_after_tag(self):
        self.records("tag", "DEC-1")
        self.assertIn("## Feature-wide", headings(self.text()))

    def test_after_rename_area(self):
        self.records("rename-area", "delivery", "export")
        self.assertIn("## export", headings(self.text()))

    def test_after_index(self):
        self.records("index")
        self.assertIn(records.GENERATED, self.text().splitlines())

    def test_after_stamp_overview(self):
        write_file(paths.overview(self.root), "# Overview\n")
        self.records("stamp-overview")
        self.assertIn(records.GENERATED, self.text().splitlines())


if __name__ == "__main__":
    unittest.main()

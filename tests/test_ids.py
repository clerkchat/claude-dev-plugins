import re
import sys
import unittest

from helpers import SCRIPTS

sys.path.insert(0, SCRIPTS)
import ids


class FormatTests(unittest.TestCase):
    def test_record(self):
        self.assertEqual(ids.record(36), "R36")
        self.assertEqual(ids.record(36, "decision"), "R36")

    def test_items(self):
        expected = {ids.IDEA: "I29", ids.PASS: "P29", ids.BUILD: "B29", ids.MILESTONE: "M29",
                    ids.DEFERRED: "D29", ids.QUESTION: "Q29", ids.FOLLOWUP: "F29"}
        self.assertEqual({kind: ids.item(kind, 29) for kind in ids.ITEMS}, expected)

    def test_parts_of_a_record(self):
        self.assertEqual(ids.ref("R34", 7), "R34.7")
        self.assertEqual(ids.ref_prefix("R34"), "R34.")
        self.assertEqual(ids.check("R13", 1), "R13-1")
        self.assertEqual(ids.in_check("R13-1", "Q6"), "R13-1.Q6")

    def test_file_names(self):
        self.assertEqual(ids.record_file(7, "decision", "poll-export-status"), "007-decision-poll-export-status.md")
        self.assertEqual(ids.check_file("R13-1"), "R13-1.md")
        self.assertEqual(ids.check_from_file("R13-1.md"), "R13-1")
        self.assertIsNone(ids.check_from_file("notes.txt"))


class ParseTests(unittest.TestCase):
    def test_record_round_trip(self):
        self.assertEqual(ids.parse(ids.record(36)), ids.Id(ids.RECORD, 36, record="R36"))

    def test_item_round_trips(self):
        for kind in ids.ITEMS:
            with self.subTest(kind=kind):
                self.assertEqual(ids.parse(ids.item(kind, 3)), ids.Id(kind, 3))

    def test_ref_round_trip(self):
        self.assertEqual(ids.parse(ids.ref("R34", 7)), ids.Id(ids.REF, 34, 7, record="R34"))

    def test_check_round_trips(self):
        self.assertEqual(ids.parse(ids.check("R13", 1)), ids.Id(ids.CHECK, 13, 1, record="R13"))
        question = ids.in_check(ids.check("R18", 1), ids.item(ids.QUESTION, 6))
        self.assertEqual(ids.parse(question), ids.Id(ids.CHECK, 18, 1, 6, "R18"))

    def test_check_file_round_trip(self):
        name = ids.check("R13", 2)
        self.assertEqual(ids.check_from_file(ids.check_file(name)), name)

    def test_not_ids(self):
        for text in ("", "R", "X3", "r7", "R7.", "R7-", "R7-1.Q", "R7-1.P2", "B", "3", " R7", "R7.3.4"):
            with self.subTest(text=text):
                self.assertIsNone(ids.parse(text))

    def test_kind_and_number(self):
        self.assertEqual(ids.kind_of("M1"), ids.MILESTONE)
        self.assertEqual(ids.kind_of("R8.2"), ids.REF)
        self.assertIsNone(ids.kind_of("C"))
        self.assertEqual(ids.number("B30"), 30)
        self.assertEqual(ids.number("R34.7"), 34)
        with self.assertRaises(ValueError):
            ids.number("X3")

    def test_same(self):
        self.assertTrue(ids.same("R7", "R7"))
        self.assertTrue(ids.same("R7", "R07"))
        self.assertFalse(ids.same("F3", "D3"))
        self.assertFalse(ids.same("R7", "R7.1"))
        self.assertFalse(ids.same("X3", "X3"))

    def test_sort_key(self):
        refs = ["R32.4", "R27", "R32", "R4", "R32.10"]
        self.assertEqual(sorted(refs, key=ids.sort_key), ["R4", "R27", "R32", "R32.4", "R32.10"])

    def test_next_number(self):
        self.assertEqual(ids.next_number([], ids.BUILD), 1)
        self.assertEqual(ids.next_number(["B1", "M4", "B2"], ids.BUILD), 3)
        self.assertEqual(ids.next_number(["B1", "M4", "B2"], ids.MILESTONE), 5)
        self.assertEqual(ids.next_number(["R3", "R10"], ids.RECORD), 11)

    def test_complete(self):
        self.assertEqual(ids.complete("7", ids.RECORD), "R7")
        self.assertEqual(ids.complete("r7.2", ids.RECORD), "R7.2")
        self.assertEqual(ids.complete("3", ids.BUILD, ids.MILESTONE), "B3")
        self.assertEqual(ids.complete("m2", ids.BUILD, ids.MILESTONE), "M2")
        self.assertEqual(ids.complete("p4", ids.PASS), "P4")


class PatternTests(unittest.TestCase):
    def test_pattern_matches_only_its_kinds(self):
        rx = re.compile(ids.pattern(ids.BUILD, ids.MILESTONE))
        self.assertTrue(rx.fullmatch("B3"))
        self.assertTrue(rx.fullmatch("M12"))
        self.assertFalse(rx.fullmatch("P3"))
        self.assertFalse(rx.fullmatch("R3"))

    def test_pattern_has_no_groups(self):
        self.assertEqual(re.compile(ids.pattern(*ids.ORDER)).groups, 0)

    def test_pattern_prefers_refs_to_records(self):
        rx = re.compile(ids.pattern(ids.RECORD, ids.REF))
        self.assertEqual(rx.match("R52.7 and more").group(0), "R52.7")

    def test_records_in(self):
        text = "Checked R13.4 and R5, then R6-1; not XR7 or R8x."
        self.assertEqual(ids.records_in(text), ["R13", "R5", "R6"])
        self.assertEqual(ids.records_in(text, refs=False), ["R5", "R6"])


if __name__ == "__main__":
    unittest.main()

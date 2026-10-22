import re
import sys
import unittest

from helpers import SCRIPTS

sys.path.insert(0, SCRIPTS)
import ids


class FormatTests(unittest.TestCase):
    def test_records_take_their_types_prefix(self):
        expected = {"brainstorm": "IDEAS-1", "design": "DESIGN-1", "decision": "DEC-1", "guidance": "GUIDE-1",
                    "pieces": "PIECES-1", "plan": "PLAN-1", "brief": "BRIEF-1"}
        self.assertEqual({rtype: ids.record(1, rtype) for rtype in ids.RECORD_TYPES}, expected)

    def test_old_type_names_read_as_the_new_ones(self):
        self.assertEqual(ids.record_type("spec"), "brief")
        self.assertEqual(ids.record_type("capabilities"), "pieces")
        for rtype in ids.RECORD_TYPES:
            with self.subTest(rtype=rtype):
                self.assertEqual(ids.record_type(rtype), rtype)

    def test_a_record_needs_a_known_type(self):
        with self.assertRaises(ValueError):
            ids.record(3, "memo")
        with self.assertRaises(ValueError):
            ids.record(3, None)

    def test_items(self):
        expected = {ids.IDEA: "IDEA-29", ids.PASS: "PASS-29", ids.BUILD: "BUILD-29", ids.MILESTONE: "MILE-29",
                    ids.DEFERRED: "DEFER-29", ids.QUESTION: "Q-29", ids.FOLLOWUP: "F29"}
        self.assertEqual({kind: ids.item(kind, 29) for kind in ids.ITEMS}, expected)

    def test_parts_of_a_record(self):
        self.assertEqual(ids.ref("PLAN-37", 8), "PLAN-37.8")
        self.assertEqual(ids.ref("BRIEF-34", 7), "BRIEF-34.7")
        self.assertEqual(ids.check("BRIEF-13", 1), "BRIEF-13-1")
        self.assertEqual(ids.in_check("BRIEF-13-1", "Q-6"), "BRIEF-13-1.Q-6")

    def test_file_names(self):
        self.assertEqual(ids.record_file(7, "decision", "poll-export-status"), "007-decision-poll-export-status.md")
        self.assertEqual(ids.check_file("BRIEF-13-1"), "BRIEF-13-1.md")
        self.assertEqual(ids.check_from_file("BRIEF-13-1.md"), "BRIEF-13-1")
        self.assertEqual(ids.check_from_file("R13-1.md"), "R13-1")
        self.assertIsNone(ids.check_from_file("notes.txt"))


class ParseTests(unittest.TestCase):
    def test_record_round_trips(self):
        for rtype in ids.RECORD_TYPES:
            with self.subTest(rtype=rtype):
                rid = ids.record(36, rtype)
                self.assertEqual(ids.parse(rid), ids.Id(ids.RECORD, 36, record=rid))

    def test_item_round_trips(self):
        for kind in ids.ITEMS:
            with self.subTest(kind=kind):
                self.assertEqual(ids.parse(ids.item(kind, 3)), ids.Id(kind, 3))

    def test_ref_round_trip(self):
        self.assertEqual(ids.parse(ids.ref("BRIEF-34", 7)), ids.Id(ids.REF, 34, 7, record="BRIEF-34"))

    def test_check_round_trips(self):
        self.assertEqual(ids.parse(ids.check("BRIEF-13", 1)), ids.Id(ids.CHECK, 13, 1, record="BRIEF-13"))
        question = ids.in_check(ids.check("BRIEF-18", 1), ids.item(ids.QUESTION, 6))
        self.assertEqual(ids.parse(question), ids.Id(ids.CHECK, 18, 1, 6, "BRIEF-18"))

    def test_check_file_round_trip(self):
        name = ids.check("BRIEF-13", 2)
        self.assertEqual(ids.check_from_file(ids.check_file(name)), name)

    def test_not_ids(self):
        for text in ("", None, "R", "X3", "r7", "R7.", "R7-", "R7-1.Q", "R7-1.P2", "B", "3", " R7", "R7.3.4",
                     "dec-39", "DEC39", "DEC-", "BRIEF-34.7.1", "IDEAS29", "MILE1", "Q-", "F-3", "REC-3"):
            with self.subTest(text=text):
                self.assertIsNone(ids.parse(text))

    def test_kind_and_number(self):
        self.assertEqual(ids.kind_of("MILE-1"), ids.MILESTONE)
        self.assertEqual(ids.kind_of("PLAN-8.2"), ids.REF)
        self.assertEqual(ids.kind_of("IDEAS-1"), ids.RECORD)
        self.assertEqual(ids.kind_of("IDEA-1"), ids.IDEA)
        self.assertIsNone(ids.kind_of("C"))
        self.assertEqual(ids.number("BUILD-30"), 30)
        self.assertEqual(ids.number("BRIEF-34.7"), 34)
        with self.assertRaises(ValueError):
            ids.number("X3")

    def test_any_record_prefix_with_the_number_is_the_same_record(self):
        self.assertTrue(ids.same("DEC-39", "DEC-39"))
        self.assertTrue(ids.same("DEC-39", "BRIEF-39"))
        self.assertTrue(ids.same("DEC-7", "DEC-07"))
        self.assertTrue(ids.same("PLAN-37.8", "DESIGN-37.8"))
        self.assertFalse(ids.same("DEC-7", "DEC-7.1"))
        self.assertFalse(ids.same("F3", "DEFER-3"))
        self.assertFalse(ids.same("IDEA-1", "IDEAS-1"))
        self.assertFalse(ids.same("X3", "X3"))
        self.assertFalse(ids.same(None, None))

    def test_sort_key(self):
        refs = ["PLAN-32.4", "DEC-27", "PLAN-32", "R4", "PLAN-32.10"]
        self.assertEqual(sorted(refs, key=ids.sort_key), ["R4", "DEC-27", "PLAN-32", "PLAN-32.4", "PLAN-32.10"])

    def test_sort_key_refuses_what_is_not_an_id(self):
        for text in ("X3", "", None):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    ids.sort_key(text)

    def test_next_number(self):
        self.assertEqual(ids.next_number([], ids.BUILD), 1)
        self.assertEqual(ids.next_number(["BUILD-1", "MILE-4", "BUILD-2"], ids.BUILD), 3)
        self.assertEqual(ids.next_number(["BUILD-1", "MILE-4", "BUILD-2"], ids.MILESTONE), 5)
        self.assertEqual(ids.next_number(["DEC-3", "BRIEF-10"], ids.RECORD), 11)


class AliasTests(unittest.TestCase):
    OLD_AND_NEW = [
        ("R36", "DEC-36"), ("R34.7", "BRIEF-34.7"), ("R13-1", "BRIEF-13-1"), ("R13-1.Q6", "BRIEF-13-1.Q-6"),
        ("I29", "IDEA-29"), ("P2", "PASS-2"), ("B30", "BUILD-30"), ("M1", "MILE-1"), ("D6", "DEFER-6"), ("Q3", "Q-3"),
    ]

    def test_every_old_form_reads_as_its_new_form(self):
        for old, new in self.OLD_AND_NEW:
            with self.subTest(old=old):
                self.assertTrue(ids.same(old, new))
                self.assertEqual(ids.kind_of(old), ids.kind_of(new))

    def test_old_and_new_forms_mix_inside_one_id(self):
        self.assertEqual(ids.key("BRIEF-13-1.Q6"), ids.key("R13-1.Q-6"))
        self.assertTrue(ids.same("R13-1.Q6", "BRIEF-13-1.Q-6"))

    def test_an_old_check_file_names_the_same_check(self):
        self.assertTrue(ids.same(ids.check_from_file("R13-1.md"), "BRIEF-13-1"))

    def test_aliases_are_never_written(self):
        written = [*ids.RECORD_LEADS.values(), *ids.ITEM_LEADS.values()]
        self.assertFalse(set(ids.ALIASES) & set(written))

    def test_follow_ups_keep_their_form(self):
        self.assertEqual(ids.item(ids.FOLLOWUP, 3), "F3")
        self.assertEqual(ids.kind_of("F3"), ids.FOLLOWUP)

    def test_next_number_counts_both_forms(self):
        self.assertEqual(ids.next_number(["B1", "BUILD-2", "B7"], ids.BUILD), 8)
        self.assertEqual(ids.next_number(["R3", "DEC-10", "R12"], ids.RECORD), 13)


class InputTests(unittest.TestCase):
    def test_normalize_uppercases_and_adds_the_missing_dash(self):
        cases = {"dec39": "DEC-39", "brief-34.7": "BRIEF-34.7", "brief34.7": "BRIEF-34.7", "ideas1": "IDEAS-1",
                 "idea29": "IDEA-29", "mile1": "MILE-1", "q3": "Q-3", " pass2 ": "PASS-2", "r7.2": "R7.2",
                 "b3": "B3", "f3": "F3", "brief13-1.q6": "BRIEF-13-1.Q6", "c": "C"}
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(ids.normalize(text), want)

    def test_read_takes_any_form_and_bare_numbers(self):
        self.assertEqual(ids.read("dec39", ids.RECORD), ids.Id(ids.RECORD, 39, record="DEC-39"))
        self.assertEqual(ids.read("r7", ids.RECORD), ids.Id(ids.RECORD, 7, record="R7"))
        self.assertEqual(ids.read("7", ids.RECORD, ids.REF), ids.Id(ids.RECORD, 7))
        self.assertEqual(ids.read("7.2", ids.RECORD, ids.REF), ids.Id(ids.REF, 7, 2))
        self.assertEqual(ids.read("3", ids.BUILD, ids.MILESTONE), ids.Id(ids.BUILD, 3))
        self.assertIsNone(ids.read("7.2", ids.RECORD))
        self.assertIsNone(ids.read("DEC-3", ids.BUILD))
        self.assertIsNone(ids.read("x", ids.BUILD))

    def test_complete_writes_items_in_the_new_form(self):
        self.assertEqual(ids.complete("3", ids.BUILD, ids.MILESTONE), "BUILD-3")
        self.assertEqual(ids.complete("m2", ids.BUILD, ids.MILESTONE), "MILE-2")
        self.assertEqual(ids.complete("mile2", ids.BUILD, ids.MILESTONE), "MILE-2")
        self.assertEqual(ids.complete("p4", ids.PASS), "PASS-4")
        self.assertEqual(ids.complete("pass-4", ids.PASS), "PASS-4")
        self.assertEqual(ids.complete("x9", ids.PASS), "X9")

    def test_render_needs_the_type_for_a_record(self):
        self.assertEqual(ids.render(ids.read("r34.7", ids.REF), "brief"), "BRIEF-34.7")
        self.assertEqual(ids.render(ids.read("7", ids.RECORD), "decision"), "DEC-7")
        self.assertEqual(ids.render(ids.read("b3", ids.BUILD)), "BUILD-3")
        with self.assertRaises(ValueError):
            ids.render(ids.read("r34", ids.RECORD))


class CanonicalTests(unittest.TestCase):
    TYPES = {13: "brief", 34: "brief", 37: "plan", 39: "decision"}

    def test_a_record_id_takes_its_types_prefix(self):
        cases = {"R39": "DEC-39", "BRIEF-39": "DEC-39", "R34.7": "BRIEF-34.7", "R37.8": "PLAN-37.8",
                 "R13-1": "BRIEF-13-1", "R13-1.Q6": "BRIEF-13-1.Q-6", "DEC-39": "DEC-39"}
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(ids.canonical(text, self.TYPES), want)

    def test_an_unknown_record_and_text_that_is_not_an_id_stay_as_they_are(self):
        self.assertEqual(ids.canonical("R99", self.TYPES), "R99")
        self.assertEqual(ids.canonical("C core harness", self.TYPES), "C core harness")
        self.assertEqual(ids.canonical("", self.TYPES), "")

    def test_items_take_their_new_form(self):
        self.assertEqual(ids.canonical("I30", {}), "IDEA-30")
        self.assertEqual(ids.canonical("F3", {}), "F3")

    def test_rewrite_canonicalizes_every_id_in_a_text(self):
        text = "R39, R34.7 and I30, from this session; not R99 or XR7"
        self.assertEqual(ids.rewrite(text, self.TYPES), "DEC-39, BRIEF-34.7 and IDEA-30, from this session; not R99 or XR7")


class PatternTests(unittest.TestCase):
    def test_pattern_matches_only_its_kinds(self):
        rx = re.compile(ids.pattern(ids.BUILD, ids.MILESTONE))
        for text in ("BUILD-3", "MILE-12", "B3", "M12"):
            self.assertTrue(rx.fullmatch(text), text)
        for text in ("PASS-3", "P3", "DEC-3", "R3"):
            self.assertFalse(rx.fullmatch(text), text)

    def test_pattern_has_no_groups(self):
        self.assertEqual(re.compile(ids.pattern(*ids.ORDER)).groups, 0)

    def test_pattern_prefers_refs_to_records(self):
        rx = re.compile(ids.pattern(ids.RECORD, ids.REF))
        self.assertEqual(rx.match("BRIEF-52.7 and more").group(0), "BRIEF-52.7")
        self.assertEqual(rx.match("R52.7 and more").group(0), "R52.7")

    def test_records_in(self):
        text = "Checked BRIEF-13.4 and DEC-5, then R6-1 and R8; not XR7, DEC-9x, or IDEA-3."
        self.assertEqual(ids.records_in(text), ["BRIEF-13", "DEC-5", "R6", "R8"])
        self.assertEqual(ids.records_in(text, refs=False), ["DEC-5", "R6", "R8"])

    def test_mentions_finds_whole_ids_only(self):
        text = "Finish pass P12 (edge-cases on BRIEF-9), then PASS-3; P1x is not one"
        self.assertEqual(ids.mentions(text, ids.PASS), ["P12", "PASS-3"])
        self.assertFalse(any(ids.same(x, "P1") for x in ids.mentions(text, ids.PASS)))


if __name__ == "__main__":
    unittest.main()

import os
import sys
import unittest

from helpers import SCRIPTS, RunCase, run_ok, run_script, write_file

sys.path.insert(0, SCRIPTS)
import records

render = records.load_script("render-report.py")

DATE = "2026-11-05"
LONG = "word " * 30


def finding(mid, path, lens="correctness", extra=""):
    return (
        f"- id: {mid}\n  lens: {lens}\n  severity: major\n  confidence: 90\n"
        f"  file: {path}\n  line: 3\n  claim: Finding {mid} breaks.\n  fix: Repair finding {mid}.\n{extra}"
    )


class RenderCase(RunCase):
    def setUp(self):
        super().setUp()
        self.write_merged(finding(7, "a.py"), finding(8, "b.py"))
        for mid in (7, 8):
            self.write(f"verify/{mid}.md", "verdict: confirmed | confidence: 90 | severity: major")
        self.render()

    def args(self, *extra):
        return (self.run_dir, "--target", "t", "--repo", self.tmp, "--date", DATE, "--wrap", "0", *extra)

    def render(self, *extra):
        return run_ok("render-report", *self.args(*extra))

    def render_fails(self, *extra):
        code, out = run_script("render-report", *self.args(*extra))
        self.assertNotEqual(code, 0)
        return out

    def instruction(self, mid):
        return render.read_instructions(self.run_dir).get(mid, {})

    def status(self, mid):
        return render.read_status(self.run_dir).get(mid, {})

    def edit_report(self, old, new):
        text = self.read("report.md")
        self.assertIn(old, text)
        self.write("report.md", text.replace(old, new, 1))

    def card(self, number):
        return self.read("report.md").split(f"#### {number}. ", 1)[1].split("\n#### ", 1)[0]


class NumbersTest(RenderCase):
    def test_numbers_findings_in_document_order(self):
        self.assertIn("1\t7\tfix\n2\t8\tfix\n", self.read("numbers.tsv"))


class SetTest(RenderCase):
    def test_sets_a_status_by_finding_number(self):
        self.render("--set", "2=wont-fix:not ours")
        self.assertEqual(self.status(8)["ref"], "not ours")

    def test_sets_a_status_by_merged_id(self):
        self.render("--set", "#7=deferred:later")
        self.assertEqual(self.status(7)["status"], "deferred")

    def test_rejects_a_number_not_in_numbers_tsv(self):
        self.assertIn("finding 9 not in numbers.tsv", self.render_fails("--set", "9=fixed"))


class InstructTest(RenderCase):
    def test_sets_the_choice_and_note_by_finding_number(self):
        self.render("--instruct", "2=noted:keep it short")
        self.assertEqual((self.instruction(8)["choice"], self.instruction(8)["note"]), ("noted", "keep it short"))

    def test_sets_the_choice_by_merged_id(self):
        self.render("--instruct", "#7=discuss")
        self.assertEqual(self.instruction(7)["choice"], "discuss")

    def test_keeps_the_picked_alternative_of_a_fix(self):
        self.render("--instruct", "1=fix(a, b)")
        self.assertEqual(self.instruction(7)["option"], "a,b")

    def test_mirrors_ignore_into_the_status(self):
        self.render("--instruct", "1=ignore:not ours")
        self.assertEqual((self.status(7)["status"], self.status(7)["ref"]), ("wont-fix", "not ours"))

    def test_none_clears_the_choice(self):
        self.render("--instruct", "1=discuss")
        self.render("--instruct", "1=none")
        self.assertEqual(self.instruction(7).get("choice", ""), "")

    def test_rejects_an_unknown_choice_with_the_usage(self):
        self.assertIn(
            "use N=fix[:note], N=fix(a)[:note], N=noted[:note], N=discuss[:note], N=defer[:ref], N=ignore[:reason], N=post[:note], N=none",
            self.render_fails("--instruct", "1=maybe"),
        )

    def test_rejects_an_alternative_on_another_choice(self):
        self.assertIn("bad --instruct", self.render_fails("--instruct", "1=discuss(a)"))

    def test_rejects_a_number_not_in_numbers_tsv(self):
        self.assertIn("finding 9 not in numbers.tsv", self.render_fails("--instruct", "9=fix"))

    def test_counts_each_choice_in_the_triage_line(self):
        self.render("--instruct", "1=noted", "--instruct", "2=defer")
        self.assertIn("Triage: 0 fix, 1 fix as noted, 0 discuss, 1 defer, 0 ignore, 0 post, 0 not decided.", self.read("report.md"))

    def test_words_the_choice_in_the_glance_table(self):
        self.render("--instruct", "1=noted")
        self.assertIn("| fix as noted |", self.read("report.md"))

    def test_sets_post_with_a_note(self):
        self.render("--instruct", "1=post:keep it short")
        self.assertEqual((self.instruction(7)["choice"], self.instruction(7)["note"]), ("post", "keep it short"))

    def test_counts_post_in_the_triage_line(self):
        self.render("--instruct", "1=post")
        self.assertIn("0 ignore, 1 post, 1 not decided.", self.read("report.md"))

    def test_post_leaves_a_declined_status_alone(self):
        self.render("--instruct", "1=ignore:not ours")
        self.render("--instruct", "1=post")
        self.assertEqual(self.status(7)["status"], "wont-fix")


class InstructionTickTest(RenderCase):
    def test_imports_a_ticked_box(self):
        self.edit_report("- [ ] Discuss", "- [x] Discuss: who owns this")
        self.render()
        self.assertEqual((self.instruction(7)["choice"], self.instruction(7)["note"]), ("discuss", "who owns this"))

    def test_imports_the_notes_line(self):
        self.edit_report("Notes:", "Notes: use the helper")
        self.render()
        self.assertEqual(self.instruction(7)["text"], "use the helper")

    def test_ignores_an_unchanged_block_from_an_older_render(self):
        stale = self.read("report.md")
        self.render("--instruct", "1=discuss")
        self.write("report.md", stale)
        self.render()
        self.assertEqual(self.instruction(7)["choice"], "discuss")

    def test_imports_a_ticked_post_box(self):
        self.edit_report("- [ ] Post", "- [x] Post: as a question")
        self.render()
        self.assertEqual((self.instruction(7)["choice"], self.instruction(7)["note"]), ("post", "as a question"))

    def test_warns_on_two_ticked_boxes(self):
        self.edit_report("- [ ] Discuss", "- [x] Discuss")
        self.edit_report("- [ ] Defer", "- [x] Defer")
        self.assertIn("has 2 instructions ticked; using discuss", self.render())


class StatusTickTest(RenderCase):
    def test_imports_a_ticked_status_box(self):
        self.edit_report("- [ ] Open", "- [x] Won't fix: out of scope")
        self.render()
        self.assertEqual(self.status(7)["status"], "wont-fix")

    def test_ignores_an_unchanged_status_line_from_an_older_render(self):
        stale = self.read("report.md")
        self.render("--set", "1=fixed:abc1234")
        self.write("report.md", stale)
        self.render()
        self.assertEqual(self.status(7)["status"], "fixed")


class NoteTest(RenderCase):
    def setUp(self):
        super().setUp()
        self.note = self.path("note.txt")
        write_file(self.note, "Prefer the shared helper.\n")

    def test_appends_to_the_notes_by_finding_number(self):
        self.render("--note", f"2={self.note}")
        self.assertEqual(self.instruction(8)["text"], "Prefer the shared helper.")

    def test_appends_to_the_notes_by_merged_id(self):
        self.render("--note", f"#7={self.note}")
        self.assertEqual(self.instruction(7)["text"], "Prefer the shared helper.")

    def test_appends_a_second_note_as_a_paragraph(self):
        self.render("--note", f"1={self.note}", "--note", f"1={self.note}")
        self.assertEqual(self.instruction(7)["text"], "Prefer the shared helper.\n\nPrefer the shared helper.")

    def test_rejects_a_number_not_in_numbers_tsv(self):
        self.assertIn("finding 9 not in numbers.tsv", self.render_fails("--note", f"9={self.note}"))


class CardTailTest(RenderCase):
    def test_puts_the_resolution_before_the_instruction(self):
        self.write("resolution/7.md", "Fixed it the other way.\n")
        self.render()
        tail = self.card(1).split("##### Resolution", 1)[1]
        self.assertTrue(tail.lstrip().startswith("Fixed it the other way.\n\n##### Instruction"))


class PullRequestCardTailTest(RenderCase):
    def setUp(self):
        super().setUp()
        pr = finding(9, "c.py", lens="pr-review", extra="  author: bob\n")
        self.write_merged(finding(7, "a.py"), finding(8, "b.py"), pr)
        self.write("verify/9.md", "verdict: confirmed | confidence: 90 | severity: major | note: The comment holds.")
        self.write("resolution/9.md", "Answered on the thread.\n")
        self.render()

    def test_orders_second_opinion_resolution_and_instruction(self):
        card = self.card(3)
        order = [card.index(h) for h in ("##### Second opinion", "##### Resolution", "##### Instruction")]
        self.assertEqual(order, sorted(order))


class PostCase(RenderCase):
    def setUp(self):
        super().setUp()
        self.render("--instruct", "1=post:keep it short")
        self.draft = self.path("draft.md")
        write_file(self.draft, "Say it plainly.\n")

    def posted(self, mid):
        return render.read_posted(self.run_dir).get(mid, {})

    def posted_section(self, number):
        return self.card(number).split("##### Posted", 1)[1]


class PostedBlockTest(PostCase):
    def test_says_the_text_is_not_drafted_yet(self):
        self.assertIn("Posted text: not drafted yet.", self.posted_section(1))

    def test_comes_after_the_instruction(self):
        self.assertIn("##### Instruction", self.card(1).split("##### Posted", 1)[0])

    def test_is_absent_from_a_card_not_marked_post(self):
        self.assertNotIn("##### Posted", self.card(2))

    def test_fences_text_that_holds_a_suggestion_with_a_longer_fence(self):
        write_file(self.draft, "Try:\n\n````suggestion\nx = 1\n````\n")
        self.render("--posted", f"1={self.draft}")
        self.assertIn("`````\nTry:", self.posted_section(1))


class PostedFlagTest(PostCase):
    def test_writes_the_posted_text(self):
        self.render("--posted", f"1={self.draft}")
        self.assertEqual(self.read("posted/7.md"), "Say it plainly.\n")

    def test_takes_a_merged_id(self):
        self.render("--posted", f"#7={self.draft}")
        self.assertEqual(self.read("posted/7.md"), "Say it plainly.\n")

    def test_records_it_as_drafted_with_the_note_it_followed(self):
        self.render("--posted", f"1={self.draft}")
        self.assertEqual((self.posted(7)["state"], self.posted(7)["note"]), ("drafted", "keep it short"))

    def test_renders_the_text_in_a_four_backtick_fence(self):
        self.render("--posted", f"1={self.draft}")
        self.assertIn("````\nSay it plainly.\n````", self.posted_section(1))

    def test_rejects_a_missing_file(self):
        self.assertIn("bad --posted", self.render_fails("--posted", "1=nope.md"))

    def test_rejects_an_empty_file(self):
        write_file(self.draft, "  \n\n")
        self.assertIn("the file is empty", self.render_fails("--posted", f"1={self.draft}"))


class WhenABatchHoldsAnEmptyDraftTest(PostCase):
    def setUp(self):
        super().setUp()
        self.render("--posted", f"1={self.draft}")
        redraft, empty = self.path("redraft.md"), self.path("empty.md")
        write_file(redraft, "Say it better.\n")
        write_file(empty, "  \n")
        self.render_fails("--posted", f"1={redraft}", "--posted", f"2={empty}")

    def test_records_none_of_the_batch(self):
        self.assertEqual(self.read("posted/7.md"), "Say it plainly.\n")


class DraftedNoteChangeTest(PostCase):
    def setUp(self):
        super().setUp()
        self.render("--posted", f"1={self.draft}")

    def test_asks_for_a_redraft(self):
        self.assertIn("finding 1: note changed; redraft the posted text", self.render("--instruct", "1=post:longer"))

    def test_asks_for_a_redraft_after_a_ticked_note_change(self):
        self.edit_report("- [x] Post: keep it short", "- [x] Post: longer")
        self.assertIn("finding 1: note changed; redraft the posted text", self.render())

    def test_says_the_text_is_to_be_redrafted(self):
        self.render("--instruct", "1=post:longer")
        self.assertIn("Posted text: to be redrafted; the note changed.", self.posted_section(1))

    def test_a_new_draft_clears_it(self):
        self.render("--instruct", "1=post:longer")
        self.render("--posted", f"1={self.draft}")
        self.assertIn("Say it plainly.", self.posted_section(1))


class PostedEditTest(PostCase):
    def setUp(self):
        super().setUp()
        self.render("--posted", f"1={self.draft}")

    def edit_text(self, new):
        self.edit_report("Say it plainly.", new)
        self.render()

    def test_saves_the_edit(self):
        self.edit_text("Say it gently.")
        self.assertEqual(self.read("posted/7.md"), "Say it gently.\n")

    def test_marks_the_finding_edited(self):
        self.edit_text("Say it gently.")
        self.assertEqual(self.posted(7)["state"], "edited")

    def test_keeps_a_heading_line_inside_the_fence_as_text(self):
        self.edit_text("# Heads up\nSay it gently.")
        self.assertEqual(self.read("posted/7.md"), "# Heads up\nSay it gently.\n")

    def test_ignores_a_rewrapped_but_unchanged_text(self):
        self.edit_text("Say it\nplainly.")
        self.assertEqual(self.posted(7)["state"], "drafted")

    def test_ignores_an_unchanged_block_from_an_older_render(self):
        stale = self.read("report.md")
        write_file(self.draft, "Say it gently.\n")
        self.render("--posted", f"1={self.draft}")
        self.write("report.md", stale)
        self.render()
        self.assertEqual(self.read("posted/7.md"), "Say it gently.\n")


class EditedNoteChangeTest(PostCase):
    def setUp(self):
        super().setUp()
        self.render("--posted", f"1={self.draft}")
        self.edit_report("Say it plainly.", "Say it gently.")
        self.render()

    def test_warns_that_the_edit_stands(self):
        self.assertIn(
            "warning: finding 1: note changed after its posted text was edited; the edit stands",
            self.render("--instruct", "1=post:longer"),
        )

    def test_keeps_showing_the_edit(self):
        self.render("--instruct", "1=post:longer")
        self.assertIn("Say it gently.", self.posted_section(1))

    def test_warns_once(self):
        self.render("--instruct", "1=post:longer")
        self.assertNotIn("note changed", self.render())


class PostedLinkTest(PostCase):
    URL = "https://github.com/o/r/pull/1#discussion_r5"

    def setUp(self):
        super().setUp()
        self.render("--posted", f"1={self.draft}")
        row = {**self.posted(7), "state": "posted", "comment_id": "5", "url": self.URL,
               "path": "a.py", "line": "12", "end_line": "14", "side": "RIGHT", "kind": "range"}
        render.write_posted(self.run_dir, {7: row})
        self.render()

    def test_links_the_posted_comment(self):
        self.assertIn(f"Posted on `a.py:12-14`, [comment]({self.URL}).", self.posted_section(1))

    def test_marks_a_later_edit_as_changed_since_posting(self):
        self.edit_report("Say it plainly.", "Say it gently.")
        self.render()
        self.assertIn("; changed since posting.", self.posted_section(1))

    def test_keeps_the_comment_after_a_later_edit(self):
        self.edit_report("Say it plainly.", "Say it gently.")
        self.render()
        self.assertEqual((self.posted(7)["state"], self.posted(7)["comment_id"]), ("edited", "5"))


class CarryPostedTest(PostCase):
    def carry(self):
        cur = self.path("cur")
        run_ok("carry", self.run_dir, cur)
        return cur

    def carried(self, cur, name):
        with open(os.path.join(cur, name), encoding="utf-8") as f:
            return f.read()

    def test_carries_a_run_without_posted_texts_without_creating_them(self):
        self.render()
        cur = self.carry()
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "posted.tsv")))
        self.assertFalse(os.path.exists(os.path.join(cur, "posted.tsv")))

    def test_carries_the_drafted_text_and_its_state(self):
        self.render("--posted", f"1={self.draft}")
        cur = self.carry()
        self.assertEqual(self.carried(cur, "posted/7.md"), "Say it plainly.\n")
        self.assertIn("drafted", self.carried(cur, "posted.tsv"))

    def test_carries_a_text_edited_in_the_report_but_not_yet_rendered(self):
        self.render("--posted", f"1={self.draft}")
        self.edit_report("Say it plainly.", "Say it gently.")
        cur = self.carry()
        self.assertEqual(self.carried(cur, "posted/7.md"), "Say it gently.\n")

    def test_carries_the_edited_state_of_a_text_edited_but_not_yet_rendered(self):
        self.render("--posted", f"1={self.draft}")
        self.edit_report("Say it plainly.", "Say it gently.")
        self.assertIn("edited", self.carried(self.carry(), "posted.tsv"))

    def test_leaves_the_previous_run_with_the_imported_edit(self):
        self.render("--posted", f"1={self.draft}")
        self.edit_report("Say it plainly.", "Say it gently.")
        self.carry()
        self.assertEqual(self.read("posted/7.md"), "Say it gently.\n")


class WrapMarkdownTest(unittest.TestCase):
    def wrap(self, *lines):
        return render.wrap_markdown("\n".join(lines), 40).split("\n")

    def test_wraps_a_long_prose_line(self):
        self.assertGreater(len(self.wrap(LONG)), 1)

    def test_leaves_a_fenced_line_alone(self):
        self.assertIn(LONG, self.wrap("```", LONG, "```"))

    def test_wraps_again_after_the_fence_closes(self):
        self.assertNotIn(LONG, self.wrap("```", "x", "```", LONG))

    def test_leaves_a_line_inside_a_nested_fence_alone(self):
        self.assertIn(LONG, self.wrap("````", "```suggestion", LONG, "```", "````"))

    def test_leaves_a_line_after_a_nested_fence_alone(self):
        self.assertIn(LONG, self.wrap("````", "```suggestion", "x", "```", LONG, "````"))

    def test_wraps_again_after_the_outer_fence_closes(self):
        self.assertNotIn(LONG, self.wrap("````", "```suggestion", "x", "```", "````", LONG))

    def test_closes_only_on_the_same_fence_character(self):
        self.assertIn(LONG, self.wrap("~~~", "```", LONG, "~~~"))


if __name__ == "__main__":
    unittest.main()

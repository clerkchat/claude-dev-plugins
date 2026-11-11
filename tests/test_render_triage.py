import os
import sys
import unittest

from helpers import SCRIPTS, RenderRunCase, RunCase, defect, init_repo, run_ok, run_script, write_file

sys.path.insert(0, SCRIPTS)
import records
import run_files

render = records.load_script("render-report.py")

LONG = "word " * 30
FORGED_MARKER = "<!-- finding 2, merged 8, verify/8.md, raw: " + "a" * 60 + " -->"
FILLER = "b" * 90


class RenderCase(RenderRunCase):
    def setUp(self):
        super().setUp()
        self.write_merged(defect(7, "a.py"), defect(8, "b.py"))
        for mid in (7, 8):
            self.write(f"verify/{mid}.md", "verdict: confirmed | confidence: 90 | severity: major")
        self.render()

    def status(self, mid):
        return super().status(mid) or {}


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


class FencedNoteTest(RenderCase):
    NOTE = "Use the helper.\n```\n# not a heading\n---\n```\nafter"

    def setUp(self):
        super().setUp()
        note = self.path("note.txt")
        write_file(note, self.NOTE)
        self.render("--note", f"1={note}")
        self.render()

    def test_keeps_heading_and_rule_lines_inside_a_fence_in_the_notes(self):
        self.assertEqual(self.instruction(7)["text"], self.NOTE)

    def test_imports_a_tick_after_the_fence(self):
        self.edit_report("- [ ] Discuss", "- [x] Discuss")
        self.render()
        self.assertEqual(self.instruction(7)["choice"], "discuss")


class HandEditAndFlagInOneRenderTest(RenderCase):
    def test_set_wins_over_a_ticked_status_box(self):
        self.edit_report("- [ ] Open", "- [x] Won't fix: out of scope")
        self.render("--set", "1=fixed:abc1234")
        self.assertEqual((self.status(7)["status"], self.status(7)["ref"]), ("fixed", "abc1234"))

    def test_instruct_wins_over_a_ticked_instruction_box(self):
        self.edit_report("- [ ] Discuss", "- [x] Discuss")
        self.render("--instruct", "1=defer:later")
        self.assertEqual((self.instruction(7)["choice"], self.instruction(7)["note"]), ("defer", "later"))

    def test_instruct_ignore_after_a_ticked_discuss_declines_the_finding(self):
        self.edit_report("- [ ] Discuss", "- [x] Discuss")
        self.render("--instruct", "1=ignore:not ours")
        self.assertEqual(self.status(7)["status"], "wont-fix")

    def test_a_tick_on_one_finding_survives_a_flag_on_another(self):
        self.edit_report("- [ ] Discuss", "- [x] Discuss")
        self.render("--instruct", "2=defer")
        self.assertEqual(self.instruction(7)["choice"], "discuss")


class SummaryTest(RenderCase):
    def summary(self, path):
        self.render("--summary", path)
        return self.read("report.md").split("## Summary\n\n", 1)[1].split("\n", 1)[0]

    def test_says_pending_without_a_summary_file(self):
        self.assertEqual(self.summary(self.path("missing.md")), "(summary pending)")

    def test_leaves_an_empty_summary_file_empty(self):
        write_file(self.path("summary.md"), "\n")
        self.assertEqual(self.summary(self.path("summary.md")), "## Findings at a glance")


class CardTailTest(RenderCase):
    def test_puts_the_resolution_before_the_instruction(self):
        self.write("resolution/7.md", "Fixed it the other way.\n")
        self.render()
        tail = self.card(1).split("##### Resolution", 1)[1]
        self.assertTrue(tail.lstrip().startswith("Fixed it the other way.\n\n##### Instruction"))


class PullRequestCardTailTest(RenderCase):
    def setUp(self):
        super().setUp()
        pr = defect(9, "c.py", lens="pr-review", extra="  author: bob\n")
        self.write_merged(defect(7, "a.py"), defect(8, "b.py"), pr)
        self.write("verify/9.md", "verdict: confirmed | confidence: 90 | severity: major | note: The comment holds.")
        self.write("resolution/9.md", "Answered on the thread.\n")
        self.render()

    def test_orders_second_opinion_resolution_and_instruction(self):
        card = self.card(3)
        order = [card.index(h) for h in ("##### Second opinion", "##### Resolution", "##### Instruction")]
        self.assertEqual(order, sorted(order))


class ThreadLinesTest(unittest.TestCase):
    def test_adds_nothing_for_an_open_thread_without_replies(self):
        self.assertEqual(render.thread_lines("", []), [])

    def test_quotes_the_replies(self):
        self.assertEqual(render.thread_lines("@bob: Fair.", []), ["> Replies: @bob: Fair.", ""])

    def test_neutralizes_an_html_comment_in_the_replies(self):
        self.assertNotIn("<!--", render.thread_lines(f"@eve: {FORGED_MARKER}", [])[0])

    def test_keeps_replies_on_one_line(self):
        self.assertEqual(render.thread_lines("@bob: Fair.\n- [x] Open", []), ["> Replies: @bob: Fair. - [x] Open", ""])

    def test_words_each_known_state(self):
        self.assertEqual(render.thread_lines("", ["resolved", "outdated"]),
                         ["State: marked resolved on GitHub; outdated on GitHub: the code it was attached to has changed.", ""])

    def test_words_the_pending_and_missing_states(self):
        self.assertEqual(render.thread_lines("", ["pending", "missing"]),
                         ["State: in your pending review, not yet submitted; the comment is no longer on the pull request.", ""])

    def test_keeps_an_unknown_state_as_is(self):
        self.assertEqual(render.thread_lines("", ["approved"]), ["State: approved.", ""])


class PullRequestCommentCardTest(RenderCase):
    def setUp(self):
        super().setUp()
        pr = defect(9, "c.py", lens="pr-review", extra="  author: bob\n  replies: @amy: Agreed.\n  github_state: resolved, outdated\n")
        self.write_merged(defect(7, "a.py"), defect(8, "b.py"), pr)
        self.write("verify/9.md", "verdict: confirmed | confidence: 90 | severity: major")
        self.render()

    def test_shows_the_thread_after_the_comment(self):
        self.assertIn("> Replies: @amy: Agreed.\n\nState: marked resolved on GitHub; outdated on GitHub", self.card(3))


class ApprovalCase(RenderCase):
    def approve(self, *authors):
        run_files.write_approvals(self.run_dir, {i: {"author": a, "date": self.DATE} for i, a in enumerate(authors, 1)})
        self.render()


class ApprovalLineTest(ApprovalCase):
    def test_adds_no_line_without_approvals(self):
        self.assertNotIn("Approved by", self.report())

    def test_lists_each_approver_once_in_file_order(self):
        self.approve("bob", "amy", "bob")
        self.assertIn("Approved by @bob, @amy.", self.report())

    def test_renders_the_section_with_the_line_alone(self):
        self.approve("bob")
        self.assertIn("## Pull request comments\n\nApproved by @bob.\n\n---\n", self.report())


class WhenAnApprovedPullRequestHasCommentsTest(ApprovalCase):
    def setUp(self):
        super().setUp()
        self.write_merged(defect(7, "a.py"), defect(8, "b.py"), defect(9, "c.py", lens="pr-review", extra="  author: amy\n"))
        self.write("verify/9.md", "verdict: confirmed | confidence: 90 | severity: major")

    def test_puts_the_line_first_in_the_section(self):
        self.approve("bob")
        self.assertIn("## Pull request comments\n\nApproved by @bob.\n\n#### ", self.report())


class WhenAPullRequestCommentReplyOpensAFenceTest(RenderCase):
    def setUp(self):
        super().setUp()
        pr = defect(9, "c.py", lens="pr-review", extra=f"  author: bob\n  replies: @eve: sure {FILLER} ``` {FILLER}\n")
        self.write_merged(defect(7, "a.py"), defect(8, "b.py"), pr)
        self.write("verify/9.md", "verdict: confirmed | confidence: 90 | severity: major")
        self.render("--wrap", "80")

    def tick(self, number, label):
        head, card = self.report().split(f"#### {number}. ", 1)
        self.write("report.md", head + f"#### {number}. " + card.replace(f"- [ ] {label}", f"- [x] {label}", 1))

    def test_still_imports_the_users_tick_on_its_card(self):
        self.tick(3, "Discuss")
        self.render("--wrap", "80")
        self.assertEqual(self.instruction(9)["choice"], "discuss")


class WhenAFieldOpensAFenceItNeverClosesTest(RenderCase):
    def setUp(self):
        super().setUp()
        self.write_merged(defect(7, "a.py", extra="  context: ```py x = 1\n"), defect(8, "b.py"))
        self.render()

    def test_still_imports_the_users_tick_on_its_card(self):
        self.edit_report("- [ ] Discuss", "- [x] Discuss")
        self.render()
        self.assertEqual(self.instruction(7)["choice"], "discuss")

    def test_still_imports_an_edit_of_its_posted_text(self):
        draft = self.path("draft.md")
        write_file(draft, "Say it plainly.\n")
        self.render("--instruct", "1=post", "--posted", f"1={draft}")
        self.edit_report("Say it plainly.", "Say it gently.")
        self.render()
        self.assertEqual(self.read("posted/7.md"), "Say it gently.\n")


class SeededPostedCommentCase(RenderCase):
    def setUp(self):
        super().setUp()
        self.write("posted/7.md", "Say it plainly.\n")
        run_files.write_posted(self.run_dir, {7: {"state": "posted", "kind": "line", "comment_id": "5", "path": "a.py", "line": "3"}})

    def card_of(self, mid):
        return self.report().split(f", merged {mid}, ", 1)[1].split("\n#### ", 1)[0]


class WhenTheVerifierRejectsAPostedFindingTest(SeededPostedCommentCase):
    def setUp(self):
        super().setUp()
        self.write("verify/7.md", "verdict: rejected | confidence: 20 | note: partly fixed")
        self.render()

    def test_keeps_its_card(self):
        self.assertIn(", merged 7, ", self.report())

    def test_keeps_its_posted_block(self):
        self.assertIn("##### Posted\n\n> Say it plainly.\n", self.card_of(7))


class WhenAPostedFindingFallsBelowTheBarTest(SeededPostedCommentCase):
    def setUp(self):
        super().setUp()
        self.write("verify/7.md", "verdict: confirmed | confidence: 30 | severity: minor")
        self.render()

    def test_keeps_its_card_below_the_bar(self):
        self.assertIn("\t7\tbelow\n", self.read("numbers.tsv"))


class PostCase(RenderCase):
    def setUp(self):
        super().setUp()
        self.render("--instruct", "1=post:keep it short")
        self.draft = self.path("draft.md")
        write_file(self.draft, "Say it plainly.\n")

    def posted(self, mid):
        return run_files.read_posted(self.run_dir).get(mid, {})

    def posted_section(self, number):
        return self.card(number).split("##### Posted", 1)[1]


class PostedBlockTest(PostCase):
    def test_says_the_text_is_not_drafted_yet(self):
        self.assertIn("Posted text: not drafted yet.", self.posted_section(1))

    def test_comes_after_the_instruction(self):
        self.assertIn("##### Instruction", self.card(1).split("##### Posted", 1)[0])

    def test_is_absent_from_a_card_not_marked_post(self):
        self.assertNotIn("##### Posted", self.card(2))

    def test_quotes_a_suggestion_inside_the_text(self):
        write_file(self.draft, "Try:\n\n```suggestion\nx = 1\n```\n")
        self.render("--posted", f"1={self.draft}")
        self.assertIn("> Try:\n>\n> ```suggestion\n> x = 1\n> ```\n", self.posted_section(1))


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

    def test_renders_the_text_as_a_blockquote(self):
        self.render("--posted", f"1={self.draft}")
        self.assertIn("\n> Say it plainly.\n", self.posted_section(1))

    def test_rejects_a_missing_file(self):
        self.assertIn("bad --posted", self.render_fails("--posted", "1=nope.md"))

    def test_rejects_an_empty_file(self):
        write_file(self.draft, "  \n\n")
        self.assertIn("the file is empty", self.render_fails("--posted", f"1={self.draft}"))


class CoveredPostedBlockTest(PostCase):
    def setUp(self):
        super().setUp()
        self.render("--instruct", "2=post", "--posted", f"1={self.draft}")
        run_files.write_groups(self.run_dir, {8: {"lead": "7", "date": "2026-11-10"}})

    def post_lead(self):
        run_files.write_posted(self.run_dir, {7: {**self.posted(7), "state": "posted", "kind": "line", "comment_id": "5", "path": "a.py", "line": "3"}})
        self.render()

    def test_says_the_member_is_covered_by_the_lead(self):
        self.render()
        self.assertIn("Covered by finding 1.", self.posted_section(2))

    def test_shows_the_leads_posted_line_once_the_lead_is_posted(self):
        self.post_lead()
        self.assertIn("Posted on `a.py:3`", self.posted_section(2))

    def test_writes_no_posted_row_for_the_member(self):
        self.post_lead()
        self.assertNotIn(8, run_files.read_posted(self.run_dir))

    def test_leaves_the_instruction_block_as_it_was(self):
        self.render()
        self.assertIn("##### Instruction", self.card(2).split("##### Posted", 1)[0])

    def test_leaves_the_leads_block_unchanged(self):
        self.render()
        self.assertIn("Say it plainly.", self.posted_section(1))

    def test_refuses_a_posted_text_for_the_member(self):
        self.assertIn("finding 2 is covered by finding 1; draft it under 1", self.render_fails("--posted", f"2={self.draft}"))


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


class DraftAnchorCase(PostCase):
    DRAFTED_ON, REVIEWED_LATER = "a" * 40, "c" * 40

    def setUp(self):
        super().setUp()
        self.write_target("t", "b" * 40, self.DRAFTED_ON)
        self.render("--posted", f"1={self.draft}")


class DraftAnchorTest(DraftAnchorCase):
    def test_records_the_lines_and_commit_it_was_drafted_for(self):
        self.assertEqual({k: self.posted(7)[k] for k in run_files.DRAFT_FIELDS},
                         {"draft_path": "a.py", "draft_line": "3", "draft_end_line": "3", "draft_commit": self.DRAFTED_ON})

    def test_shows_the_text_while_the_code_stays(self):
        self.assertIn("Say it plainly.", self.posted_section(1))

    def test_asks_for_no_redraft_while_the_code_stays(self):
        self.assertNotIn("code moved", self.render())


class WhenTheReviewedCommitMovedSinceDraftingTest(DraftAnchorCase):
    def setUp(self):
        super().setUp()
        self.write_target("t", "b" * 40, self.REVIEWED_LATER)
        self.out = self.render()

    def test_says_the_text_is_to_be_redrafted(self):
        self.assertIn("Posted text: to be redrafted; the code moved.", self.posted_section(1))

    def test_asks_for_a_redraft(self):
        self.assertIn("finding 1: code moved since drafting; redraft the posted text", self.out)

    def test_a_new_draft_clears_it(self):
        self.render("--posted", f"1={self.draft}")
        self.assertIn("Say it plainly.", self.posted_section(1))


class WhenTheFindingMovedToOtherLinesSinceDraftingTest(DraftAnchorCase):
    def test_says_the_text_is_to_be_redrafted(self):
        self.write("overrides/7.md", "line: 9\n")
        self.render()
        self.assertIn("Posted text: to be redrafted; the code moved.", self.posted_section(1))


class WhenAPostedCommentsCodeMovedTest(DraftAnchorCase):
    def test_asks_for_no_redraft(self):
        run_files.write_posted(self.run_dir, {7: {**self.posted(7), "state": "posted", "comment_id": "5", "kind": "line"}})
        self.write_target("t", "b" * 40, self.REVIEWED_LATER)
        self.render()
        self.assertNotIn("to be redrafted", self.posted_section(1))


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

    def test_keeps_a_quoted_heading_line_as_text(self):
        self.edit_text("# Heads up\n> Say it gently.")
        self.assertEqual(self.read("posted/7.md"), "# Heads up\nSay it gently.\n")

    def test_reads_a_blank_line_that_lost_its_quote_marker_as_a_blank_line(self):
        self.edit_text("Say it\n\n> gently.")
        self.assertEqual(self.read("posted/7.md"), "Say it\n\ngently.\n")

    def test_ignores_a_rewrapped_but_unchanged_text(self):
        self.edit_text("Say it\n> plainly.")
        self.assertEqual(self.posted(7)["state"], "drafted")

    def test_ignores_an_unchanged_block_from_an_older_render(self):
        stale = self.read("report.md")
        write_file(self.draft, "Say it gently.\n")
        self.render("--posted", f"1={self.draft}")
        self.write("report.md", stale)
        self.render()
        self.assertEqual(self.read("posted/7.md"), "Say it gently.\n")


class PostedRoundTripTest(PostCase):
    def round_trip(self, text):
        write_file(self.draft, text + "\n\nSay it plainly.\n")
        self.render("--posted", f"1={self.draft}")
        self.edit_report("Say it plainly.", "Say it gently.")
        self.render()
        return self.read("posted/7.md")

    def assertRoundTrips(self, text):
        self.assertEqual(self.round_trip(text), text + "\n\nSay it gently.\n")

    def test_keeps_a_suggestion_block(self):
        self.assertRoundTrips("Try:\n\n```suggestion\nx = 1\n```")

    def test_keeps_blank_lines(self):
        self.assertRoundTrips("One.\n\n\nTwo.")

    def test_keeps_indented_code_lines(self):
        self.assertRoundTrips("Like:\n\n    x = 1\n        y = 2")

    def test_keeps_a_line_that_starts_with_a_quote_marker(self):
        self.assertRoundTrips("> You said this.\n>\n> > And this.")


class WhenAPostedEditBreaksItsQuoteTest(PostCase):
    def setUp(self):
        super().setUp()
        write_file(self.draft, "Say it plainly.\nThen stop.\n")
        self.render("--posted", f"1={self.draft}")
        self.edit_report("Say it plainly.", "Say it gently.\nAn unquoted line.")
        self.out = self.render()

    def test_warns_that_the_edit_was_not_read(self):
        self.assertIn("warning: finding 1: its Posted text has a line without `>` in the middle; the edit was not read", self.out)

    def test_keeps_the_stored_text(self):
        self.assertEqual(self.read("posted/7.md"), "Say it plainly.\nThen stop.\n")

    def test_shows_the_stored_text_again(self):
        self.assertIn("\n> Say it plainly.\n> Then stop.\n", self.posted_section(1))


class WhenAReportStillHoldsAFencedPostedTextTest(PostCase):
    def setUp(self):
        super().setUp()
        self.render("--posted", f"1={self.draft}")
        self.edit_report("> Say it plainly.", "````\nSay it gently.\n````")
        self.render()

    def test_keeps_the_stored_text(self):
        self.assertEqual(self.read("posted/7.md"), "Say it plainly.\n")

    def test_records_no_edit(self):
        self.assertEqual(self.posted(7)["state"], "drafted")

    def test_shows_the_stored_text_as_a_blockquote(self):
        self.assertIn("\n> Say it plainly.\n", self.posted_section(1))


class WhenARenderWithAPostedEditStopsOnABadFlagTests:
    def setUp(self):
        super().setUp()
        self.render("--posted", f"1={self.draft}")
        self.edit_report("Say it plainly.", "Say it gently.")
        self.render_fails(*self.BAD_FLAG)

    def test_leaves_the_posted_text_as_it_was(self):
        self.assertEqual(self.read("posted/7.md"), "Say it plainly.\n")

    def test_marks_the_edit_on_the_next_render(self):
        self.render()
        self.assertEqual(self.posted(7)["state"], "edited")


class WhenABadSetStopsARenderWithAPostedEditTest(WhenARenderWithAPostedEditStopsOnABadFlagTests, PostCase):
    BAD_FLAG = ("--set", "1=maybe")


class WhenABadInstructStopsARenderWithAPostedEditTest(WhenARenderWithAPostedEditStopsOnABadFlagTests, PostCase):
    BAD_FLAG = ("--instruct", "1=maybe")


class WhenABadNoteStopsARenderWithAPostedEditTest(WhenARenderWithAPostedEditStopsOnABadFlagTests, PostCase):
    BAD_FLAG = ("--note", "1=nope.md")


class WhenABadPostedStopsARenderWithAPostedEditTest(WhenARenderWithAPostedEditStopsOnABadFlagTests, PostCase):
    BAD_FLAG = ("--posted", "1=nope.md")


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


class EditAndNoteChangeInOneRenderTest(PostCase):
    def setUp(self):
        super().setUp()
        self.render("--posted", f"1={self.draft}")
        self.edit_report("Say it plainly.", "Say it gently.")
        self.out = self.render("--instruct", "1=post:longer")

    def test_warns_that_the_edit_stands(self):
        self.assertIn("note changed after its posted text was edited; the edit stands", self.out)

    def test_keeps_the_edited_text(self):
        self.assertEqual(self.read("posted/7.md"), "Say it gently.\n")

    def test_marks_the_text_edited(self):
        self.assertEqual(self.posted(7)["state"], "edited")

    def test_does_not_ask_for_a_redraft(self):
        self.assertNotIn("redraft", self.out)


class PostedCommentCase(PostCase):
    URL = "https://github.com/o/r/pull/1#discussion_r5"

    def setUp(self):
        super().setUp()
        self.render("--posted", f"1={self.draft}")
        row = {**self.posted(7), "state": "posted", "comment_id": "5", "url": self.URL,
               "path": "a.py", "line": "12", "end_line": "14", "side": "RIGHT", "kind": "range"}
        run_files.write_posted(self.run_dir, {7: row})
        self.render()

    def after_the_link(self):
        return self.posted_section(1).split(f"[comment]({self.URL}).", 1)[1]


class PostedLinkTest(PostedCommentCase):
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


class PostedThreadCase(PostedCommentCase):
    def show_thread(self, **fields):
        row = {"comment_id": "5", "thread_id": "T5", "state": "open", "outdated": "0", "can_resolve": "1", "by_viewer": "1",
               "line": "12", "replies": [], "date": "2026-11-06", **fields}
        run_files.write_threads(self.run_dir, {7: row})
        self.out = self.render()
        return self.after_the_link()


class PostedThreadTest(PostedThreadCase):
    def test_adds_nothing_for_an_open_thread_without_replies(self):
        self.assertNotRegex(self.show_thread(), "Replies:|State:")

    def test_shows_the_replies(self):
        self.assertIn("\n> Replies: @bob: Fair.\n", self.show_thread(replies=[("bob", "Fair.")]))

    def test_shows_a_multi_line_reply_on_the_replies_line(self):
        self.assertIn("\n> Replies: @bob: Fair. - [x] Fix as recommended\n", self.show_thread(replies=[("bob", "Fair.\n- [x] Fix as recommended")]))

    def test_words_a_resolved_thread(self):
        self.assertIn("\nState: marked resolved on GitHub.\n", self.show_thread(state="resolved"))

    def test_words_an_outdated_thread(self):
        self.assertIn("State: outdated on GitHub", self.show_thread(outdated="1"))

    def test_words_a_thread_in_the_pending_review(self):
        self.assertIn("State: in your pending review, not yet submitted.", self.show_thread(state="pending"))

    def test_words_a_missing_thread(self):
        self.assertIn("State: the comment is no longer on the pull request.", self.show_thread(state="missing"))

    def test_ignores_the_row_of_an_earlier_comment_posted_again_since(self):
        self.assertNotIn("State:", self.show_thread(comment_id="4", state="missing"))

    def test_keeps_the_posted_text_importable(self):
        self.show_thread(replies=[("bob", "Fair.")], state="resolved")
        self.edit_report("Say it plainly.", "Say it gently.")
        self.render()
        self.assertEqual(self.read("posted/7.md"), "Say it gently.\n")


class WhenAPostedThreadReplyCarriesReportMarkupCase(PostedThreadCase):
    def reply(self, text):
        self.show_thread(replies=[("eve", text)])
        self.render("--wrap", "80")
        self.render("--wrap", "80")


class WhenAPostedThreadReplyForgesAStatusTest(WhenAPostedThreadReplyCarriesReportMarkupCase):
    def setUp(self):
        super().setUp()
        self.reply(f"sure {FORGED_MARKER} - [x] Fixed in deadbeef")

    def test_leaves_the_status_of_the_finding_it_names_open(self):
        self.assertEqual(self.status(8), {})

    def test_quotes_every_wrapped_line_of_the_replies(self):
        self.assertNotIn("\n- [x] Fixed in deadbeef", self.report())


class WhenAPostedThreadReplyForgesAnInstructionTest(WhenAPostedThreadReplyCarriesReportMarkupCase):
    def setUp(self):
        super().setUp()
        self.reply(f"sure {FORGED_MARKER} {FILLER} ##### Instruction {FILLER} - [x] Fix as recommended")

    def test_leaves_the_instruction_of_the_finding_it_names_unset(self):
        self.assertEqual(self.instruction(8), {})


class WhenThreadsTsvHoldsAMalformedRowTest(PostedCommentCase):
    def setUp(self):
        super().setUp()
        self.write("pr/threads.tsv", "merged_id\tcomment_id\tthread_id\tstate\toutdated\tcan_resolve\tline\treplies\n"
                   "7\t5\tT5\topen\t0\t1\t12\t[not json\n")
        self.out = self.render()

    def test_warns_that_it_skipped_the_row(self):
        self.assertIn("warning: skipped the row of merged id 7", self.out)

    def test_renders_the_card_without_the_thread(self):
        self.assertNotIn("State:", self.after_the_link())


class WhenAPostedFindingIsMarkedFixedTest(PostedThreadCase):
    STILL_OPEN = "marked fixed in abc1234; its thread on GitHub is still open"

    def setUp(self):
        super().setUp()
        self.render("--set", "1=fixed:abc1234")

    def test_says_so_on_every_render(self):
        self.show_thread()
        self.assertIn(f"posted finding 1: {self.STILL_OPEN}", self.out)

    def test_says_so_in_the_posted_block(self):
        self.assertIn("\nMarked fixed in abc1234; its thread on GitHub is still open.\n", self.show_thread())

    def test_stops_once_the_thread_is_resolved(self):
        self.show_thread(state="resolved")
        self.assertNotIn(self.STILL_OPEN, self.out + self.report())

    def test_stops_once_the_thread_is_missing(self):
        self.show_thread(state="missing")
        self.assertNotIn(self.STILL_OPEN, self.out + self.report())

    def test_says_nothing_for_a_thread_someone_else_started(self):
        self.show_thread(by_viewer="0")
        self.assertNotIn(self.STILL_OPEN, self.out + self.report())

    def test_says_nothing_for_the_open_row_of_an_earlier_comment(self):
        self.show_thread(comment_id="4")
        self.assertNotIn(self.STILL_OPEN, self.out + self.report())


class WhenAPostedThreadIsKeptOpenTest(PostedThreadCase):
    def setUp(self):
        super().setUp()
        self.render("--set", "1=fixed:abc1234")
        run_files.write_kept_open(self.run_dir, {7: {"reason": "the author wants a follow-up", "date": ""}})

    def test_says_it_is_kept_open_with_the_reason(self):
        self.assertIn("\n> Thread kept open: the author wants a follow-up.\n", self.show_thread())

    def test_no_longer_says_it_is_still_open(self):
        self.show_thread()
        self.assertNotIn("still open", self.out + self.report())


class WhenAPostedFindingIsNoLongerMarkedPostTest(PostedThreadCase):
    def setUp(self):
        super().setUp()
        self.render("--instruct", "1=none")

    def test_still_shows_the_posted_block(self):
        self.assertIn(f"[comment]({self.URL})", self.posted_section(1))

    def test_shows_the_thread(self):
        self.assertIn("\n> Replies: @bob: Fair.\n", self.show_thread(replies=[("bob", "Fair.")]))

    def test_does_not_ask_for_a_redraft(self):
        self.assertNotIn("to be redrafted", self.posted_section(1))


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

    def test_carries_the_note_of_a_text_edited_but_not_yet_rendered(self):
        self.render("--posted", f"1={self.draft}")
        self.edit_report("Say it plainly.", "Say it gently.")
        self.assertEqual(run_files.read_posted(self.carry())[7]["note"], "keep it short")

    def test_leaves_the_previous_run_with_the_imported_edit(self):
        self.render("--posted", f"1={self.draft}")
        self.edit_report("Say it plainly.", "Say it gently.")
        self.carry()
        self.assertEqual(self.read("posted/7.md"), "Say it gently.\n")


class CarryWithoutMergedTest(RunCase):
    def setUp(self):
        super().setUp()
        self.write_status({7: ("wont-fix", "not ours")})
        self.cur = self.path("cur")
        self.code, self.out = run_script("carry", self.run_dir, self.cur)

    def test_fails(self):
        self.assertEqual(self.code, 1)

    def test_says_the_previous_run_has_no_merged_findings(self):
        self.assertIn(f"nothing carried; {self.run_dir}/merged.md does not exist", self.out)

    def test_creates_no_run(self):
        self.assertFalse(os.path.exists(self.cur))

    def test_leaves_the_previous_run_as_it_was(self):
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "instructions.tsv")))


VERDICT = "verdict: confirmed | confidence: 90 | severity: major"


class CarryVerdictsCase(RunCase):
    def setUp(self):
        super().setUp()
        self.write_merged(defect(7, "a.py"))
        self.write("verify/7.md", VERDICT)
        self.cur = self.path("cur")

    def write_cur(self, name, text):
        write_file(os.path.join(self.cur, name), text)

    def carried_verdict(self):
        run_ok("carry", self.run_dir, self.cur)
        with open(os.path.join(self.cur, "verify", "7.md"), encoding="utf-8") as f:
            return f.read()


class CarryVerdictsTest(CarryVerdictsCase):
    def test_carries_the_verdicts(self):
        self.assertEqual(self.carried_verdict(), VERDICT)


class WhenTheRunAlreadyHasAVerifyDirectoryTest(CarryVerdictsCase):
    def setUp(self):
        super().setUp()
        self.write_cur("verify/9.md", "verdict: rejected")

    def test_carries_the_verdicts_into_it(self):
        self.assertEqual(self.carried_verdict(), VERDICT)


class WhenTheRunAlreadyJudgedTheFindingTest(CarryVerdictsCase):
    def setUp(self):
        super().setUp()
        self.write_cur("verify/7.md", "verdict: rejected")

    def test_keeps_its_own_verdict(self):
        self.assertEqual(self.carried_verdict(), "verdict: rejected")


TWO_CHOICES = [render.Choice("post", "Post", "post"), render.Choice("ignore", "Ignore", "ignore", note="reason")]


class ChoicesTest(unittest.TestCase):
    def test_lists_only_the_given_choices(self):
        self.assertEqual(render.instruction_lines({"choice": "post"}, TWO_CHOICES), ["- [x] Post", "- [ ] Ignore"])

    def test_names_the_chosen_label_of_the_given_choices_on_a_conflict(self):
        block = render.instruction_block({"choice": "ignore", "also": "post"}, TWO_CHOICES)
        self.assertIn("More than one instruction is ticked; using Ignore until the others are cleared.", block)

    def test_matches_a_given_choice(self):
        self.assertTrue(render.instruct_re(TWO_CHOICES).match("1=post"))

    def test_refuses_a_choice_outside_the_given_ones(self):
        self.assertIsNone(render.instruct_re(TWO_CHOICES).match("1=fix"))

    def test_words_the_usage_from_the_given_choices(self):
        self.assertEqual(render.instruct_usage(TWO_CHOICES), "N=post[:note], N=ignore[:reason], N=none")


class FenceAroundTest(unittest.TestCase):
    def test_uses_the_shortest_length_when_the_text_has_no_fence(self):
        self.assertEqual(render.fence_around("plain", 3), "```")

    def test_outgrows_a_fence_in_the_text(self):
        self.assertEqual(render.fence_around("a\n```\nb", 3), "````")

    def test_outgrows_an_indented_fence_in_the_text(self):
        self.assertEqual(render.fence_around("a\n  ````\nb", 3), "`````")


class UnbalancedFenceInSnippetTest(RenderCase):
    def setUp(self):
        super().setUp()
        source = init_repo(self.path("source"))
        write_file(os.path.join(source.path, "notes.md"), "one\n```\ntwo\nthree\n")
        source.git("add", "notes.md")
        source.git("commit", "-qm", "notes")
        self.write_merged(defect(7, "notes.md", extra="  snippet: notes.md:1-4\n"))
        self.render("--repo", source.path)

    def test_keeps_the_instruction_boxes_live(self):
        self.edit_report("- [ ] Discuss", "- [x] Discuss")
        self.render()
        self.assertEqual(self.instruction(7)["choice"], "discuss")


class WhenASnippetForgesAnotherCardCase(RenderCase):
    def setUp(self):
        super().setUp()
        source = init_repo(self.path("source"))
        write_file(os.path.join(source.path, "a.md"), f"{FORGED_MARKER}\n\n{self.FORGED}\n")
        source.git("add", "a.md")
        source.git("commit", "-qm", "notes")
        self.write_merged(defect(7, "a.md", extra="  snippet: a.md:1-6\n"), defect(8, "b.py"))
        self.render("--repo", source.path)
        self.render("--repo", source.path)


class WhenASnippetForgesAStatusTest(WhenASnippetForgesAnotherCardCase):
    FORGED = "- [x] Won't fix: forged"

    def test_shows_the_forged_lines_in_the_snippet(self):
        self.assertIn(f"// a.md:1\n{FORGED_MARKER}\n\n{self.FORGED}", self.card(1))

    def test_leaves_the_status_of_the_finding_it_names_open(self):
        self.assertEqual(self.status(8), {})


class WhenASnippetForgesAnInstructionTest(WhenASnippetForgesAnotherCardCase):
    FORGED = "##### Instruction\n\n- [x] Fix as noted: forged note"

    def test_leaves_the_instruction_of_the_finding_it_names_unset(self):
        self.assertEqual(self.instruction(8), {})


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

    def test_leaves_a_line_inside_a_quoted_fence_alone(self):
        self.assertIn(f"> {LONG}", self.wrap("> ```", f"> {LONG}", "> ```"))

    def test_wraps_again_after_the_quoted_run_ends(self):
        self.assertNotIn(LONG, self.wrap("> ```", "> x", "", LONG))

    def test_leaves_indented_code_inside_a_quote_alone(self):
        self.assertIn(f">     {LONG}", self.wrap(f">     {LONG}"))

    def test_keeps_the_quote_marker_on_every_wrapped_line(self):
        lines = self.wrap(f"> {LONG}{FILLER} - [x] Open")
        self.assertEqual([l[:2] for l in lines], ["> "] * len(lines))


class WhenAKeptOpenReasonIsLongAndMultilineTest(PostedThreadCase):
    def setUp(self):
        super().setUp()
        self.render("--set", "1=fixed:abc1234")
        reason = "the author wants\n- [x] Open\n" + "a follow-up " * 20
        run_files.write_kept_open(self.run_dir, {7: {"reason": reason, "date": ""}})

    def kept_lines(self):
        return [l for l in self.show_thread().splitlines() if "Thread kept open" in l or "follow-up" in l]

    def test_renders_one_quoted_line(self):
        lines = self.kept_lines()
        self.assertEqual([len(lines), lines[0][:2]], [1, "> "])

    def test_leaves_no_checkbox_line(self):
        self.assertNotIn("\n- [x] Open", self.show_thread())


class CardSectionOrderTest(RenderRunCase):
    def setUp(self):
        super().setUp()
        self.write_merged(defect(7, "a.py", extra="  context: Why it is here.\n  steps: |\n    1. First.\n    2. Second.\n"))
        self.write("verify/7.md", "verdict: confirmed | confidence: 90 | severity: major")
        self.render()

    def test_puts_the_cause_before_the_cost(self):
        card = self.card(1)
        order = [card.index(m) for m in ("a.py:3", "##### Context", "##### How it goes wrong", "##### Why it matters", "##### Recommendation")]
        self.assertEqual(order, sorted(order))


if __name__ == "__main__":
    unittest.main()

import io
import os
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

from helpers import SCRIPTS, RunCase, TempCase, defect, init_repo, merged_md

sys.path.insert(0, SCRIPTS)
import run_files


class LineSpanTest(unittest.TestCase):
    def test_names_a_single_line(self):
        self.assertEqual(run_files.line_span(3, 3), "3")

    def test_names_a_range(self):
        self.assertEqual(run_files.line_span(3, 5), "3-5")

    def test_names_the_start_when_there_is_no_end(self):
        self.assertEqual(run_files.line_span(3, None), "3")

    def test_names_the_start_when_the_end_is_empty(self):
        self.assertEqual(run_files.line_span("3", ""), "3")


class TsvCase(RunCase):
    FIELDS = ("status", "ref")

    def tsv_path(self):
        return os.path.join(self.run_dir, "t.tsv")

    def written(self):
        with open(self.tsv_path(), encoding="utf-8") as fh:
            return fh.read()


class ReadRowsTest(TsvCase):
    def parse(self, text, **kw):
        self.write("t.tsv", text)
        return run_files.read_rows(self.tsv_path(), **kw)

    def test_reads_nothing_from_a_missing_file(self):
        self.assertEqual(run_files.read_rows(self.tsv_path()), [])

    def test_skips_the_header(self):
        self.assertEqual(self.parse("merged_id\tstatus\n3\tfixed\n"), [["3", "fixed"]])

    def test_strips_the_cells(self):
        self.assertEqual(self.parse("3\t fixed \n"), [["3", "fixed"]])

    def test_keeps_the_empty_cells(self):
        self.assertEqual(self.parse("3\t\tabc\n"), [["3", "", "abc"]])

    def test_takes_the_rows_a_key_function_accepts(self):
        self.assertEqual(self.parse("thread:1\t4\nbad\t5\n", key=lambda text: text if text.startswith("thread:") else None),
                         [["thread:1", "4"]])


class WriteRowsTest(TsvCase):
    def test_writes_the_header_then_the_rows(self):
        run_files.write_rows(self.tsv_path(), ["a", "b"], [["1", "2"]])
        self.assertEqual(self.written(), "a\tb\n1\t2\n")

    def test_writes_no_header_when_none_is_given(self):
        run_files.write_rows(self.tsv_path(), None, [["1", "2"]])
        self.assertEqual(self.written(), "1\t2\n")

    def test_creates_the_directories_of_the_path(self):
        path = os.path.join(self.run_dir, "deep", "er", "t.tsv")
        run_files.write_rows(path, None, [["1"]])
        self.assertEqual(run_files.read_rows(path), [["1"]])

    def test_replaces_a_tab_or_a_line_break_in_a_cell_with_a_space(self):
        run_files.write_rows(self.tsv_path(), None, [["1", "a\tb\nc\rd"]])
        self.assertEqual(self.written(), "1\ta b c d\n")

    def test_replaces_the_file_it_wrote_before(self):
        run_files.write_rows(self.tsv_path(), None, [["1"], ["2"]])
        run_files.write_rows(self.tsv_path(), None, [["3"]])
        self.assertEqual(self.written(), "3\n")


class WhenWritingRowsFailsTest(TsvCase):
    def setUp(self):
        super().setUp()
        run_files.write_rows(self.tsv_path(), None, [["1"]])

    def rows_that_fail(self):
        yield ["2"]
        raise OSError("disk full")

    def test_keeps_the_rows_written_before_when_the_rows_fail_partway(self):
        with self.assertRaises(OSError):
            run_files.write_rows(self.tsv_path(), None, self.rows_that_fail())
        self.assertEqual(self.written(), "1\n")

    def test_leaves_no_partial_file_when_the_replace_fails(self):
        with mock.patch.object(run_files.os, "replace", side_effect=OSError("disk full")), self.assertRaises(OSError):
            run_files.write_rows(self.tsv_path(), None, [["2"]])
        self.assertEqual(os.listdir(self.run_dir), ["t.tsv"])


class ReadKeyedTest(TsvCase):
    def parse(self, text, **kw):
        self.write("t.tsv", text)
        return run_files.read_keyed(self.tsv_path(), self.FIELDS, **kw)

    def test_skips_the_header_and_keys_rows_by_merged_id(self):
        self.assertEqual(self.parse("merged_id\tstatus\tref\n3\tfixed\tabc\n"), {3: {"status": "fixed", "ref": "abc"}})

    def test_fills_an_empty_cell_from_the_defaults(self):
        self.assertEqual(self.parse("3\t\tabc\n", defaults={"status": "open"})[3]["status"], "open")

    def test_strips_the_cells(self):
        self.assertEqual(self.parse("3\t fixed \tabc\n")[3]["status"], "fixed")

    def test_takes_string_keys(self):
        self.assertEqual(self.parse("thread:1\t4\n", key=str), {"thread:1": {"status": "4", "ref": ""}})

    def test_skips_a_row_with_only_a_key(self):
        self.assertEqual(self.parse("3\n"), {})

    def test_ignores_a_cell_past_the_known_fields(self):
        self.assertEqual(self.parse("3\tfixed\tabc\textra\n"), {3: {"status": "fixed", "ref": "abc"}})


class WriteKeyedTest(TsvCase):
    ROWS = {5: {"status": "open"}, 2: {"status": "fixed", "ref": "abc"}}

    def write_rows(self, rows=None, **kw):
        run_files.write_keyed(self.tsv_path(), self.FIELDS, rows or self.ROWS, **kw)
        return self.written()

    def test_writes_the_header_and_the_rows_by_key(self):
        self.assertEqual(self.write_rows(), "merged_id\tstatus\tref\n2\tfixed\tabc\n5\topen\t\n")

    def test_names_the_key_column(self):
        self.assertTrue(self.write_rows(header="number").startswith("number\tstatus\tref\n"))

    def test_writes_no_header(self):
        self.assertEqual(self.write_rows(header=None), "2\tfixed\tabc\n5\topen\t\n")

    def test_keeps_the_given_order(self):
        self.assertEqual(self.write_rows(header=None, order=list), "5\topen\t\n2\tfixed\tabc\n")

    def test_keeps_a_cell_with_a_tab_or_a_line_break_in_its_row(self):
        rows = {2: {"status": "wont-fix", "ref": "not\tours\nreally\rso"}}
        self.assertEqual(self.write_rows(rows, header=None), "2\twont-fix\tnot ours really so\n")

    def test_reads_back_what_it_wrote(self):
        self.write_rows()
        self.assertEqual(run_files.read_keyed(self.tsv_path(), self.FIELDS), {2: {"status": "fixed", "ref": "abc"}, 5: {"status": "open", "ref": ""}})


class ThreadRowsTest(RunCase):
    ROW = {"comment_id": "5", "thread_id": "T5", "state": "open", "outdated": "0", "can_resolve": "1", "by_viewer": "1", "line": "3-4",
           "date": "2026-11-06"}

    def write_threads(self, **replies):
        run_files.write_threads(self.run_dir, {7: {**self.ROW, **replies}})

    def read_threads(self):
        with redirect_stderr(io.StringIO()):
            return run_files.read_threads(self.run_dir)

    def test_reads_back_the_replies_with_their_authors(self):
        self.write_threads(replies=[("bob", "Fair."), ("amy", "Agreed.")])
        self.assertEqual(self.read_threads()[7]["replies"], [("bob", "Fair."), ("amy", "Agreed.")])

    def test_keeps_a_reply_of_several_lines_in_one_row(self):
        self.write_threads(replies=[("bob", "Fair.\n\n- [x] Fix as recommended\ttabbed")])
        self.assertEqual(self.read_threads()[7]["replies"], [("bob", "Fair.\n\n- [x] Fix as recommended\ttabbed")])

    def test_keeps_a_reply_with_other_scripts(self):
        self.write_threads(replies=[("bob", "Gut, danke ✓")])
        self.assertEqual(self.read_threads()[7]["replies"], [("bob", "Gut, danke ✓")])

    def test_reads_a_thread_without_replies(self):
        self.write_threads()
        self.assertEqual(self.read_threads()[7]["replies"], [])

    def test_reads_back_the_other_fields(self):
        self.write_threads()
        self.assertEqual({k: v for k, v in self.read_threads()[7].items() if k != "replies"}, self.ROW)


class MalformedThreadRowTest(RunCase):
    def setUp(self):
        super().setUp()
        good = {"comment_id": "5", "replies": [("bob", "Fair.")]}
        run_files.write_threads(self.run_dir, {7: good, 8: good})

    def corrupt(self, cell):
        path = run_files.threads_path(self.run_dir)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace('[["bob", "Fair."]]', cell, 1))

    def read_threads(self):
        self.err = io.StringIO()
        with redirect_stderr(self.err):
            return run_files.read_threads(self.run_dir)

    def test_skips_a_row_whose_replies_are_not_json(self):
        self.corrupt("[not json")
        self.assertEqual(sorted(self.read_threads()), [8])

    def test_skips_a_row_whose_replies_are_not_author_and_text_pairs(self):
        self.corrupt('["bob"]')
        self.assertEqual(sorted(self.read_threads()), [8])

    def test_skips_a_row_whose_replies_are_not_a_list(self):
        self.corrupt('{"bob": "Fair."}')
        self.assertEqual(sorted(self.read_threads()), [8])

    def test_says_which_row_it_skipped(self):
        self.corrupt("[not json")
        self.read_threads()
        self.assertIn("skipped the row of merged id 7", self.err.getvalue())


class ReplyTextTest(unittest.TestCase):
    def test_joins_the_replies_on_one_line_each_with_its_author(self):
        self.assertEqual(run_files.joined_replies([("bob", "Fair."), ("amy", "Agreed.")]), "@bob: Fair.; @amy: Agreed.")

    def test_folds_the_whitespace_of_a_reply(self):
        self.assertEqual(run_files.reply_line("bob", "Fair.\n  - [x] Open"), "@bob: Fair. - [x] Open")


class PostedRowTest(unittest.TestCase):
    def test_a_posted_line_comment_has_a_thread(self):
        self.assertTrue(run_files.has_thread({"kind": "line", "comment_id": "5", "state": "posted"}))

    def test_a_review_body_posting_has_no_thread(self):
        self.assertFalse(run_files.has_thread({"kind": "body", "comment_id": "", "state": "posted"}))

    def test_a_drafted_text_has_no_thread(self):
        self.assertFalse(run_files.has_thread({"kind": "", "comment_id": "", "state": "drafted"}))

    def test_an_edited_comment_still_has_a_thread(self):
        self.assertTrue(run_files.has_thread({"kind": "line", "comment_id": "5", "state": "edited"}))

    def test_an_edited_comment_is_not_in_the_posted_state(self):
        self.assertFalse(run_files.is_posted({"kind": "line", "comment_id": "5", "state": "edited"}))


class CommitsNamedTest(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("repo"), with_origin=False)
        self.sha = self.repo.git("rev-parse", "HEAD")
        self.blob = self.repo.git("rev-parse", "HEAD:file.txt")

    def named(self, text):
        return run_files.commits_named(self.repo.path, text)

    def test_names_the_commit_of_a_short_sha(self):
        self.assertEqual(self.named(f"fixed in {self.sha[:7]}"), [self.sha])

    def test_names_the_commit_of_a_full_sha(self):
        self.assertEqual(self.named(self.sha), [self.sha])

    def test_names_each_commit_in_the_text(self):
        second = self.repo.commit("second")
        full_second = self.repo.git("rev-parse", second)
        self.assertEqual(self.named(f"{self.sha[:7]} then {second}"), [self.sha, full_second])

    def test_leaves_out_a_number_that_names_no_object(self):
        self.assertEqual(self.named("see ticket 1234567"), [])

    def test_leaves_out_an_object_that_is_not_a_commit(self):
        self.assertEqual(self.named(f"see {self.blob[:10]}"), [])

    def test_leaves_out_hex_inside_a_longer_word(self):
        self.assertEqual(self.named(f"x{self.sha[:7]}z"), [])

    def test_names_nothing_in_text_without_a_sha(self):
        self.assertEqual(self.named("the working tree"), [])


class CommitsUnknownTest(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("repo"), with_origin=False)
        self.sha = self.repo.git("rev-parse", "HEAD")

    def unknown(self, text):
        return run_files.commits_unknown(self.repo.path, text)

    def test_leaves_out_a_short_sha_the_clone_has(self):
        self.assertEqual(self.unknown(f"fixed in {self.sha[:7]}"), [])

    def test_names_a_full_sha_the_clone_lacks(self):
        self.assertEqual(self.unknown("fixed in " + "d" * 40), ["d" * 40])

    def test_names_every_unknown_token_once(self):
        self.assertEqual(self.unknown(f"deadbee, {self.sha[:7]}, 1234567 and deadbee"), ["deadbee", "1234567"])

    def test_names_nothing_in_text_without_a_sha(self):
        self.assertEqual(self.unknown("the working tree"), [])


class ClosableCase(RunCase):
    def setUp(self):
        super().setUp()
        self.write_merged(defect(1, "a.py"), defect(2, "b.py"), defect(3, "c.py", lens="credit"))
        self.posted, self.statuses, self.threads = {}, {}, {}
        self.add(1)

    def add(self, mid, status="fixed", **thread):
        self.posted[mid] = {"state": "posted", "kind": "line", "comment_id": str(900 + mid), "thread_id": f"T{mid}"}
        self.statuses[mid] = (status, "")
        self.threads[mid] = {"comment_id": str(900 + mid), "thread_id": f"T{mid}", "state": "open", "by_viewer": "1", "replies": [], **thread}
        self.save()

    def save(self):
        run_files.write_posted(self.run_dir, self.posted)
        self.write_status(self.statuses)
        run_files.write_threads(self.run_dir, self.threads)

    def closable(self):
        return sorted(run_files.closable(self.run_dir))


class ClosableTest(ClosableCase):
    def test_takes_a_posted_finding_marked_fixed_whose_thread_is_open(self):
        self.assertEqual(self.closable(), [1])

    def test_pairs_the_finding_with_its_posted_row_status_and_thread(self):
        found = run_files.closable(self.run_dir)[1]
        self.assertEqual((found.posted["comment_id"], found.status["status"], found.thread["thread_id"]), ("901", "fixed", "T1"))

    def test_takes_every_such_finding_in_order(self):
        self.add(2)
        self.assertEqual(self.closable(), [1, 2])

    def test_leaves_out_a_finding_not_marked_fixed(self):
        self.add(1, status="open")
        self.assertEqual(self.closable(), [])

    def test_leaves_out_a_finding_marked_wont_fix(self):
        self.add(1, status="wont-fix")
        self.assertEqual(self.closable(), [])

    def test_leaves_out_a_finding_posted_in_the_review_body(self):
        self.posted[1]["kind"] = "body"
        self.save()
        self.assertEqual(self.closable(), [])

    def test_leaves_out_a_credit(self):
        self.add(3)
        self.assertEqual(self.closable(), [1])

    def test_leaves_out_a_thread_kept_open(self):
        run_files.write_kept_open(self.run_dir, {1: {"reason": "", "date": ""}})
        self.assertEqual(self.closable(), [])

    def test_leaves_out_a_resolved_thread(self):
        self.add(1, state="resolved")
        self.assertEqual(self.closable(), [])

    def test_leaves_out_a_thread_in_the_pending_review(self):
        self.add(1, state="pending")
        self.assertEqual(self.closable(), [])

    def test_leaves_out_a_missing_thread(self):
        self.add(1, state="missing")
        self.assertEqual(self.closable(), [])

    def test_leaves_out_a_thread_row_of_an_earlier_comment(self):
        self.add(1, comment_id="899")
        self.assertEqual(self.closable(), [])

    def test_leaves_out_a_thread_the_viewer_did_not_start(self):
        self.add(1, by_viewer="0")
        self.assertEqual(self.closable(), [])

    def test_leaves_out_a_finding_without_a_thread_row(self):
        del self.threads[1]
        self.save()
        self.assertEqual(self.closable(), [])

    def test_leaves_out_a_finding_with_no_status_row(self):
        del self.statuses[1]
        self.save()
        self.assertEqual(self.closable(), [])


class KeptOpenTest(RunCase):
    def test_reads_back_the_reason_and_the_date(self):
        run_files.write_kept_open(self.run_dir, {4: {"reason": "the author wants a follow-up", "date": "2026-11-06"}})
        self.assertEqual(run_files.read_kept_open(self.run_dir), {4: {"reason": "the author wants a follow-up", "date": "2026-11-06"}})

    def test_reads_nothing_when_no_thread_was_kept_open(self):
        self.assertEqual(run_files.read_kept_open(self.run_dir), {})


class FencedLinesTest(unittest.TestCase):
    def kinds(self, *lines):
        return [kind for _, kind in run_files.fenced_lines(lines)]

    def test_marks_prose_fences_and_bodies(self):
        self.assertEqual(self.kinds("a", "```", "b", "```", "c"), ["", "fence", "body", "fence", ""])

    def test_walks_a_tilde_fence(self):
        self.assertEqual(self.kinds("~~~", "x", "~~~", "y"), ["fence", "body", "fence", ""])

    def test_holds_a_backtick_fence_inside_a_tilde_fence_as_body(self):
        self.assertEqual(self.kinds("~~~", "```", "x", "```", "~~~", "y"), ["fence", "body", "body", "body", "fence", ""])

    def test_holds_a_shorter_fence_inside_a_longer_one_as_body(self):
        self.assertEqual(self.kinds("````", "```suggestion", "x", "```", "````", "y"), ["fence", "body", "body", "body", "fence", ""])

    def test_closes_on_a_longer_fence(self):
        self.assertEqual(self.kinds("```", "x", "````", "y"), ["fence", "body", "fence", ""])

    def test_does_not_close_on_a_fence_with_an_info_string(self):
        self.assertEqual(self.kinds("```", "```js", "x"), ["fence", "body", "body"])

    def test_holds_the_rest_after_an_unclosed_fence_as_body(self):
        self.assertEqual(self.kinds("```", "a", "##### Instruction"), ["fence", "body", "body"])


if __name__ == "__main__":
    unittest.main()

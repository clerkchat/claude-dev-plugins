import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from helpers import SCRIPTS, RunCase, TempCase, merged_md, run_ok, write_file

sys.path.insert(0, SCRIPTS)
import gh_api
import records

post = records.load_script("post-review.py")

HEAD = "a" * 40
PATCH = (
    "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n"
    "@@ -1,3 +10,6 @@\n ctx\n+one\n+two\n+three\n ctx\n ctx\n"
    "@@ -20,2 +40,4 @@\n ctx\n+four\n+five\n ctx\n"
)


def finding(mid, path, line):
    where = (f"  file: {path}\n" if path else "") + (f"  line: {line}\n" if line else "")
    return f"- id: {mid}\n  lens: correctness\n  severity: major\n  confidence: 90\n{where}  title: Finding {mid}\n  claim: Finding {mid} breaks.\n"


FINDINGS = {1: ("src/a.py", "11-13"), 2: ("src/a.py", "30"), 3: ("src/b.py", "5"), 4: ("src/c.py", "2"), 5: ("", "")}


def thread_data(n):
    return {"data": {"addPullRequestReviewThread": {"thread": {"id": f"PRRT_{n}", "comments": {"nodes": [
        {"id": f"PRRC_{n}", "databaseId": 900 + n, "url": f"https://gh/c/{900 + n}"}]}}}}}


class PostCase(RunCase):
    def setUp(self):
        super().setUp()
        self.write_merged(*(finding(m, *f) for m, f in FINDINGS.items()))
        self.write_numbers(FINDINGS)
        self.write("patch/all.patch", PATCH)
        self.write_target("pr 7", "b" * 40, HEAD)
        self.marks = {}
        self.ctx = {"owner": "acme", "name": "widgets", "pr": 7, "head": HEAD, "files": ["src/a.py", "src/b.py"], "pending": None}
        patcher = mock.patch.object(post, "fetch_pr", side_effect=lambda *a: self.ctx)
        patcher.start()
        self.addCleanup(patcher.stop)

    def mark(self, mid, note="", text=None):
        self.marks[mid] = note
        self.write_instructions({m: ("post", n) for m, n in self.marks.items()})
        if text is not False: self.write(f"posted/{mid}.md", text or f"Finding {mid} text.")

    def pend(self, commit=HEAD, comments=None):
        self.ctx["pending"] = {"id": 55, "node_id": "PRR_55", "commit_id": commit, "html_url": "https://gh/r/55", "comments": comments or {}}

    def posted_row(self, mid, state="posted", **fields):
        row = {"state": state, "note": self.marks.get(mid, ""), "kind": "line", "path": "src/a.py", "line": "11", "end_line": "11",
               "side": "RIGHT", "thread_id": "PRRT_1", "comment_id": "901", "url": "https://gh/c/901", "review_id": "55", **fields}
        rows = post.rr.read_posted(self.run_dir); rows[mid] = row
        post.rr.write_posted(self.run_dir, rows)

    def main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            post.main([self.run_dir, *args])
        return out.getvalue()

    def calls(self, *args):
        self.main("--post", "--dry-run", *args)
        with open(os.path.join(self.run_dir, "posted", "payload.json"), encoding="utf-8") as fh:
            return json.load(fh)["calls"]

    def call_for(self, mid):
        return next(c for c in self.calls() if c.get("finding") == mid)

    def thread_vars(self, mid):
        return self.call_for(mid)["variables"]

    def review_body(self):
        return next(c["fields"]["body"] for c in self.calls() if c.get("method") in ("POST", "PUT") and "finding" not in c)

    def refusal(self):
        with self.assertRaises(SystemExit) as raised:
            self.main("--post", "--dry-run")
        return str(raised.exception)


class UnwrapTest(unittest.TestCase):
    def test_joins_the_lines_of_a_paragraph(self):
        self.assertEqual(post.unwrap("one\ntwo\n\nthree"), "one two\n\nthree")

    def test_keeps_lines_inside_a_code_fence(self):
        self.assertEqual(post.unwrap("say\n```suggestion\na\nb\n```\nafter"), "say\n```suggestion\na\nb\n```\nafter")

    def test_keeps_list_items_on_their_own_lines(self):
        self.assertEqual(post.unwrap("- one\n  more\n- two"), "- one more\n- two")


class AnchorTest(PostCase):
    def test_anchors_a_range_on_the_right_side(self):
        self.mark(1)
        self.assertEqual({k: v for k, v in self.thread_vars(1).items() if k not in ("pullRequestReviewId", "body")},
                         {"path": "src/a.py", "subjectType": "LINE", "line": 13, "side": "RIGHT", "startLine": 11, "startSide": "RIGHT"})

    def test_moves_a_line_outside_the_diff_to_the_nearest_hunk(self):
        self.mark(2)
        self.assertEqual((self.thread_vars(2)["line"], "startLine" in self.thread_vars(2)), (40, False))

    def test_falls_back_to_the_file_when_the_file_has_no_diff_lines(self):
        self.mark(3)
        self.assertEqual(self.thread_vars(3)["subjectType"], "FILE")

    def test_sends_a_finding_without_a_file_in_the_review_body(self):
        self.mark(5)
        self.assertIn("Finding 5 text.", self.review_body())

    def test_flags_the_fallback_in_the_preview(self):
        self.mark(2)
        self.assertIn("fallback: src/a.py:30 is outside the diff; moved to 40", self.main())


class NotePlacementTest(PostCase):
    def test_a_line_in_the_note_wins(self):
        self.mark(1, note="on src/a.py:41-42, keep it short")
        self.assertEqual((self.thread_vars(1)["startLine"], self.thread_vars(1)["line"]), (41, 42))

    def test_a_file_in_the_note_makes_a_file_comment(self):
        self.mark(1, note="on src/b.py.")
        self.assertEqual((self.thread_vars(1)["path"], self.thread_vars(1)["subjectType"]), ("src/b.py", "FILE"))

    def test_the_review_body_in_the_note_moves_it_there(self):
        self.mark(1, note="in the review body")
        self.assertIn("**`src/a.py`**\n\nFinding 1 text.", self.review_body())


class PostedTextTest(PostCase):
    SUGGESTION = "Use this:\n```suggestion\nfixed()\n```"

    def test_goes_out_unwrapped(self):
        self.mark(1, text="First line\nsecond line.")
        self.assertEqual(self.thread_vars(1)["body"], "First line second line.")

    def test_keeps_a_suggestion_on_its_own_lines(self):
        self.mark(1, text=self.SUGGESTION)
        self.assertIn("```suggestion", self.thread_vars(1)["body"])

    def test_sends_a_suggestion_whose_anchor_fell_back_as_a_plain_fence(self):
        self.mark(2, text=self.SUGGESTION)
        self.assertEqual(self.thread_vars(2)["body"], "Use this:\n```\nfixed()\n```")


class RefusalTest(PostCase):
    def test_refuses_a_file_outside_the_pull_request(self):
        self.mark(1); self.mark(4)
        self.assertIn("finding 4: its file src/c.py is not in the pull request", self.refusal())

    def test_refuses_a_finding_without_posted_text(self):
        self.mark(1, text=False)
        self.assertIn("finding 1: it has no posted text", self.refusal())

    def test_sends_nothing_when_it_refuses(self):
        self.mark(4)
        self.refusal()
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "posted", "payload.json")))


class NewReviewTest(PostCase):
    def setUp(self):
        super().setUp()
        self.mark(1)

    def test_creates_the_pending_review_on_the_reviewed_commit_first(self):
        first = self.calls()[0]
        self.assertEqual((first["method"], first["fields"]["commit_id"], "event" in first["fields"]), ("POST", HEAD, False))

    def test_adds_threads_to_the_review_it_creates(self):
        self.assertEqual(self.thread_vars(1)["pullRequestReviewId"], "{review.node_id}")

    def test_sends_the_default_body_without_review_md(self):
        self.assertEqual(self.review_body(), post.DEFAULT_BODY)

    def test_sends_review_md_as_the_body(self):
        self.write("posted/review.md", "Nice work\noverall.")
        self.assertEqual(self.review_body(), "Nice work overall.")


class PendingReviewTest(PostCase):
    def setUp(self):
        super().setUp()
        self.mark(1)
        self.pend()

    def test_adds_threads_to_the_existing_pending_review(self):
        self.assertEqual(self.thread_vars(1)["pullRequestReviewId"], "PRR_55")

    def test_sets_its_body_last(self):
        last = self.calls()[-1]
        self.assertEqual((last["method"], last["path"]), ("PUT", "repos/acme/widgets/pulls/7/reviews/55"))

    def test_says_it_adds_to_it(self):
        self.assertIn("pending review: 55 on aaaaaaaaa exists", self.main())

    def test_names_a_pending_review_on_another_commit(self):
        self.pend(commit="c" * 40)
        self.assertIn("exists on ccccccccc, another commit than the reviewed aaaaaaaaa", self.main())


class RepostTest(PostCase):
    def setUp(self):
        super().setUp()
        self.mark(1); self.mark(3)

    def test_skips_a_finding_already_posted_and_unchanged(self):
        self.posted_row(1)
        self.assertEqual([c.get("finding") for c in self.calls() if "finding" in c], [3])

    def test_updates_a_comment_edited_since_posting_in_the_pending_review(self):
        self.pend(comments={901: "PRRC_901"})
        self.posted_row(1, state="edited")
        self.assertEqual(self.call_for(1)["variables"], {"pullRequestReviewCommentId": "PRRC_901", "body": "Finding 1 text."})

    def test_updates_a_comment_of_a_submitted_review_through_rest(self):
        self.posted_row(1, state="edited")
        self.assertEqual((self.call_for(1)["method"], self.call_for(1)["path"]), ("PATCH", "repos/acme/widgets/pulls/comments/901"))


class SubmitTest(PostCase):
    def submit(self, *args):
        self.main("--submit", *args, "--dry-run")
        with open(os.path.join(self.run_dir, "posted", "payload.json"), encoding="utf-8") as fh:
            return json.load(fh)["calls"]

    def test_requires_a_verdict(self):
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
            post.main([self.run_dir, "--submit", "--dry-run"])
        self.assertEqual(raised.exception.code, 2)

    def test_refuses_without_a_pending_review(self):
        with self.assertRaises(SystemExit):
            self.submit("approve")

    def test_sends_the_verdict_with_the_review_body(self):
        self.pend()
        self.assertEqual(self.submit("request-changes"), [{"method": "POST", "path": "repos/acme/widgets/pulls/7/reviews/55/events",
                                                           "fields": {"event": "REQUEST_CHANGES", "body": post.DEFAULT_BODY}}])


class LivePostTest(PostCase):
    def setUp(self):
        super().setUp()
        self.mark(1); self.mark(3)
        self.graphql = self.stub("graphql", side_effect=lambda q, v, cwd: thread_data(1 if v.get("path") == "src/a.py" else 3))
        self.rest = self.stub("rest", return_value={"id": 55, "node_id": "PRR_55", "html_url": "https://gh/r/55"})

    def stub(self, name, **kw):
        patcher = mock.patch.object(gh_api, name, **kw)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_records_each_posted_comment_in_posted_tsv(self):
        self.main("--post")
        row = post.rr.read_posted(self.run_dir)[1]
        self.assertEqual({k: row[k] for k in ("state", "thread_id", "comment_id", "url", "kind", "line", "end_line", "side", "review_id")},
                         {"state": "posted", "thread_id": "PRRT_1", "comment_id": "901", "url": "https://gh/c/901", "kind": "range",
                          "line": "11", "end_line": "13", "side": "RIGHT", "review_id": "55"})

    def test_rolls_back_the_batch_when_github_rejects_a_comment(self):
        self.graphql.side_effect = [thread_data(1), gh_api.GhError("rejected"), {"data": {}}]
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            post.main([self.run_dir, "--post"])
        self.assertEqual((self.graphql.call_args_list[-1].args[1], self.rest.call_args.args[:2]),
                         ({"id": "PRRC_1"}, ("DELETE", "repos/acme/widgets/pulls/7/reviews/55")))


class FetchPrTest(unittest.TestCase):
    def test_finds_the_pending_review_and_its_comment_nodes(self):
        lists = {"repos/o/r/pulls/7/files": [{"filename": "a.py"}],
                 "repos/o/r/pulls/7/reviews": [{"id": 1, "state": "COMMENTED"}, {"id": 2, "node_id": "N2", "state": "PENDING", "commit_id": HEAD}],
                 "repos/o/r/pulls/7/reviews/2/comments": [{"id": 9, "node_id": "C9"}]}
        with mock.patch.object(gh_api, "repo_owner_name", return_value=["o", "r"]), \
             mock.patch.object(gh_api, "gh", return_value=json.dumps({"headRefOid": HEAD})), \
             mock.patch.object(gh_api, "rest_list", side_effect=lambda path, cwd: lists[path]):
            ctx = post.fetch_pr("/w", "/nowhere", 7)
        self.assertEqual((ctx["pending"]["id"], ctx["pending"]["comments"]), (2, {9: "C9"}))


class CarryTest(TempCase):
    def test_carries_posted_texts_and_posted_tsv(self):
        prev, cur = self.path("prev"), self.path("cur")
        write_file(os.path.join(prev, "merged.md"), merged_md(finding(1, "a.py", "3")))
        write_file(os.path.join(prev, "posted", "1.md"), "Text.\n")
        write_file(os.path.join(prev, "posted.tsv"), "merged_id\tstate\n1\tdrafted\n")
        run_ok("carry", prev, cur)
        self.assertEqual([os.path.exists(os.path.join(cur, p)) for p in ("posted/1.md", "posted.tsv")], [True, True])


if __name__ == "__main__":
    unittest.main()

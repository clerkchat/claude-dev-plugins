import os
import sys
import unittest
from unittest import mock

from helpers import SCRIPTS, RunCase, merged_md

sys.path.insert(0, SCRIPTS)
import records

pr_comments = records.load_script("pr-comments.py")
render = records.load_script("render-report.py")

DATE = "2026-11-06"


def comment(gid, body, review_state, login="me"):
    return {"databaseId": gid, "author": {"login": login}, "body": body, "url": f"u{gid}", "pullRequestReview": {"state": review_state}}


def thread(gid, state="COMMENTED", body="Looks off.", replies=(), reply_state=None, **fields):
    comments = [comment(gid, body, state)]
    comments += [comment(gid * 10 + n, r, reply_state or state, "you") for n, r in enumerate(replies, 1)]
    return {"id": f"T{gid}", "path": "a.py", "line": 3, "originalLine": 3, "isResolved": False, "isOutdated": False,
            "viewerCanResolve": True, "comments": {"nodes": comments}, **fields}


def review(gid, state, body="Summary."):
    return {"databaseId": gid, "author": {"login": "me"}, "body": body, "state": state, "url": f"u{gid}"}


def pull_request(threads=(), reviews=()):
    return {"number": 7, "url": "https://gh/pull/7", "headRefName": "feat",
            "reviewThreads": {"nodes": list(threads)}, "reviews": {"nodes": list(reviews)}, "comments": {"nodes": []}}


def posted_row(comment_id, kind="line"):
    return {"state": "posted", "kind": kind, "comment_id": str(comment_id), "thread_id": f"T{comment_id}", "path": "a.py", "line": "3"}


class GithubItemsTest(unittest.TestCase):
    def items(self, threads=(), reviews=()):
        return [(kind, gid) for kind, gid, *_ in pr_comments.github_items(pull_request(reviews=reviews), threads)]

    def test_brings_in_the_given_threads_and_submitted_reviews(self):
        self.assertEqual(self.items([thread(1)], [review(2, "COMMENTED")]), [("thread", 1), ("review", 2)])

    def test_skips_a_pending_review(self):
        self.assertEqual(self.items(reviews=[review(2, "PENDING")]), [])

    def test_keeps_the_submitted_reviews_beside_pending_ones(self):
        self.assertEqual(self.items(reviews=[review(2, "PENDING"), review(4, "APPROVED")]), [("review", 4)])

    def test_leaves_out_a_pending_reply_on_a_submitted_thread(self):
        submitted = thread(1, replies=["Unsent draft."], reply_state="PENDING")
        self.assertEqual(pr_comments.github_items(pull_request(), [submitted])[0][5]["replies"], [])

    def test_skips_a_review_without_a_body(self):
        self.assertEqual(self.items(reviews=[review(2, "COMMENTED", body="  ")]), [])


    def test_skips_a_review_posted_by_this_plugin(self):
        items = pr_comments.github_items(pull_request(reviews=[review(2, "COMMENTED"), review(4, "COMMENTED")]), [], {"2"})
        self.assertEqual([gid for _, gid, *_ in items], [4])


class SortThreadsTest(unittest.TestCase):
    def sort(self, *threads, linking=None):
        return pr_comments.sort_threads(pull_request(threads), linking or {})

    def test_imports_a_submitted_thread(self):
        self.assertEqual([t["id"] for t in self.sort(thread(1)).imported], ["T1"])

    def test_leaves_out_a_thread_of_a_pending_review(self):
        self.assertEqual(self.sort(thread(1, "PENDING")).imported, [])

    def test_counts_the_pending_threads_left_out(self):
        self.assertEqual(self.sort(thread(1, "PENDING"), thread(2, "PENDING"), thread(3)).left_out, 2)

    def test_skips_a_thread_with_no_comments(self):
        empty = {**thread(1), "comments": {"nodes": []}}
        self.assertEqual(self.sort(empty).imported, [])

    def test_links_a_thread_whose_root_comment_was_posted_under_its_finding(self):
        self.assertEqual(list(self.sort(thread(1), linking={1: 40}).linked), [40])

    def test_does_not_import_a_linked_thread(self):
        self.assertEqual(self.sort(thread(1), linking={1: 40}).imported, [])

    def test_links_a_pending_posted_thread_rather_than_leaving_it_out(self):
        self.assertEqual(self.sort(thread(1, "PENDING"), linking={1: 40}).left_out, 0)


class FoldInCase(RunCase):
    def setUp(self):
        super().setUp()
        self.write("merged.md", merged_md())

    def fold(self, *threads, reviews=()):
        return pr_comments.fold_in(self.run_dir, pull_request(threads, reviews), DATE)


class FoldInTest(FoldInCase):
    def test_a_pending_comment_never_reaches_the_run(self):
        self.fold(thread(1, "PENDING", "Draft finding text."), reviews=[review(2, "PENDING", "Draft summary.")])
        self.assertNotIn("Draft", self.read("merged.md"))

    def test_a_submitted_comment_becomes_a_finding(self):
        self.fold(thread(1, body="Real comment."))
        self.assertIn("Real comment.", self.read("merged.md"))

    def test_returns_the_new_ids(self):
        self.assertEqual(self.fold(thread(1), reviews=[review(2, "COMMENTED")]).new_ids, [1, 2])

    def test_counts_the_pending_threads_left_out(self):
        self.assertEqual(self.fold(thread(1, "PENDING")).left_out, 1)

    def test_records_each_comment_as_seen(self):
        self.fold(thread(1))
        self.assertEqual(self.read("pr/seen.tsv"), "thread:1\t1\n")

    def test_keeps_the_payload_and_the_pull_request(self):
        self.fold()
        self.assertEqual(self.read("pr/pr.txt"), "7\thttps://gh/pull/7\n")

    def test_a_comment_posted_after_a_fetch_is_added_once_submitted(self):
        self.fold(thread(1, "PENDING", "Soon."))
        self.fold(thread(1, body="Soon."))
        self.assertEqual(self.read("merged.md").count("- id: "), 1)

    def test_joins_the_replies_into_the_entry(self):
        self.fold(thread(1, replies=["Fair.", "Done."]))
        self.assertIn("replies: @you: Fair.; @you: Done.", self.read("merged.md"))

    def test_writes_no_threads_file_without_posted_findings(self):
        self.fold(thread(1))
        self.assertFalse(os.path.exists(render.threads_path(self.run_dir)))


class WhenAKnownCommentChangesTest(FoldInCase):
    def setUp(self):
        super().setUp()
        self.fold(thread(1, body="First words."))
        self.write("merged.md", self.read("merged.md").replace("```\n", "  duplicate_of: 9\n```\n"))
        self.folded = self.fold(thread(1, body="Edited words."))

    def test_counts_it_as_updated(self):
        self.assertEqual(self.folded.updated, 1)

    def test_counts_it_as_not_new(self):
        self.assertEqual(self.folded.new_ids, [])

    def test_refreshes_it_in_place(self):
        self.assertIn("Edited words.", self.read("merged.md"))

    def test_keeps_its_link(self):
        self.assertIn("duplicate_of: 9", self.read("merged.md"))


class PostedThreadCase(FoldInCase):
    def setUp(self):
        super().setUp()
        render.write_posted(self.run_dir, {40: posted_row(1), 41: posted_row(2, kind="range"), 42: posted_row(3, kind="body")})

    def row(self, mid):
        return render.read_threads(self.run_dir)[mid]


class PostedThreadTest(PostedThreadCase):
    def setUp(self):
        super().setUp()
        self.folded = self.fold(thread(1, body="Posted text.", replies=["Fair."]), thread(5, body="Their comment."))

    def test_does_not_import_it(self):
        self.assertNotIn("Posted text.", self.read("merged.md"))

    def test_does_not_mark_it_seen(self):
        self.assertNotIn("thread:1", self.read("pr/seen.tsv"))

    def test_leaves_it_off_the_new_ids(self):
        self.assertEqual(self.folded.new_ids, [1])

    def test_counts_it_as_linked(self):
        self.assertEqual(self.folded.linked, 1)

    def test_still_imports_a_comment_of_someone_else(self):
        self.assertIn("Their comment.", self.read("merged.md"))

    def test_writes_its_row_under_the_finding(self):
        self.assertEqual(self.row(40), {"comment_id": "1", "thread_id": "T1", "state": "open", "outdated": "0", "can_resolve": "1",
                                        "line": "3", "replies": "@you: Fair.", "date": DATE})

    def test_marks_a_posting_the_fetch_did_not_return_missing(self):
        self.assertEqual((self.row(41)["state"], self.row(41)["thread_id"]), ("missing", "T2"))

    def test_writes_no_row_for_a_body_posting(self):
        self.assertNotIn(42, render.read_threads(self.run_dir))


class PostedReviewTest(PostedThreadCase):
    def setUp(self):
        super().setUp()
        posted = render.read_posted(self.run_dir)
        posted[42]["review_id"] = "2"
        render.write_posted(self.run_dir, posted)
        self.folded = self.fold(reviews=[review(2, "COMMENTED", "Our summary."), review(4, "COMMENTED", "Their summary.")])

    def test_does_not_import_it(self):
        self.assertNotIn("Our summary.", self.read("merged.md"))

    def test_counts_it_as_linked(self):
        self.assertEqual(self.folded.linked, 1)

    def test_still_imports_a_review_of_someone_else(self):
        self.assertIn("Their summary.", self.read("merged.md"))


class PostedThreadStateTest(PostedThreadCase):
    def test_marks_a_resolved_thread(self):
        self.fold(thread(1, isResolved=True))
        self.assertEqual(self.row(40)["state"], "resolved")

    def test_marks_a_thread_of_the_pending_review(self):
        self.fold(thread(1, "PENDING"))
        self.assertEqual(self.row(40)["state"], "pending")

    def test_flags_an_outdated_thread(self):
        self.fold(thread(1, isOutdated=True, line=None))
        self.assertEqual((self.row(40)["outdated"], self.row(40)["line"]), ("1", ""))

    def test_flags_a_thread_the_viewer_cannot_resolve(self):
        self.fold(thread(1, viewerCanResolve=False))
        self.assertEqual(self.row(40)["can_resolve"], "0")

    def test_rewrites_the_row_from_the_live_pull_request(self):
        self.fold(thread(1, isResolved=True))
        self.fold()
        self.assertEqual(self.row(40)["state"], "missing")


class ShortlistTest(RunCase):
    def test_a_credit_is_never_a_candidate_for_a_comment(self):
        self.write("merged.md", merged_md(
            "- id: 1\n  lens: credit\n  file: a.py\n  line: 1\n  title: Looks off\n  claim: Looks off here.\n",
            "- id: 2\n  lens: correctness\n  file: a.py\n  line: 1\n  title: Looks off\n  claim: Looks off here.\n"))
        folded = pr_comments.fold_in(self.run_dir, pull_request([thread(1, body="Looks off.")]), DATE)
        pr_comments.shortlist(self.run_dir, folded.new_ids)
        self.assertEqual(self.read("pr/candidates.tsv").split("\n")[1].split("\t")[1], "2")
        self.assertNotIn("\t1\t", self.read("pr/candidates.tsv"))


class SummaryTest(unittest.TestCase):
    def summary(self, linked=0, left_out=0):
        return pr_comments.summary(12, pr_comments.Folded([5, 6, 7], 1, linked, left_out), [(5, 1, 0.5)])

    def test_counts_new_updated_and_candidates(self):
        self.assertEqual(self.summary(), "PR #12: 3 new comments, 1 updated, 1 candidate links for 1 comments to judge")

    def test_adds_the_linked_count(self):
        self.assertIn("1 updated, 2 posted findings linked, ", self.summary(linked=2))

    def test_adds_the_pending_threads_left_out(self):
        self.assertIn(", 2 threads of your own pending review left out, ", self.summary(left_out=2))


class MainTest(RunCase):
    def test_fetches_the_pull_request_and_folds_it_in(self):
        self.write("merged.md", merged_md())
        graphql = {"data": {"repository": {"pullRequest": pull_request([thread(1, body="Real comment.")])}}}
        with mock.patch.object(pr_comments, "graphql", return_value=graphql), \
                mock.patch.object(pr_comments, "repo_owner_name", return_value=["o", "r"]), \
                mock.patch.object(sys, "argv", ["pr-comments", self.run_dir, "--pr", "7", "--repo", self.tmp]):
            pr_comments.main()
        self.assertIn("Real comment.", self.read("merged.md"))


if __name__ == "__main__":
    unittest.main()

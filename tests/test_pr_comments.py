import sys
import unittest
from unittest import mock

from helpers import SCRIPTS, RunCase, merged_md

sys.path.insert(0, SCRIPTS)
import records

pr_comments = records.load_script("pr-comments.py")


def thread(gid, state, body="Looks off.", replies=(), reply_state=None):
    comments = [{"databaseId": gid, "author": {"login": "me"}, "body": body, "url": f"u{gid}", "state": state}]
    comments += [{"databaseId": gid * 10 + n, "author": {"login": "you"}, "body": r, "url": "u", "state": reply_state or state}
                 for n, r in enumerate(replies, 1)]
    return {"path": "a.py", "line": 3, "originalLine": 3, "isResolved": False, "isOutdated": False,
            "comments": {"nodes": comments}}


def review(gid, state, body="Summary."):
    return {"databaseId": gid, "author": {"login": "me"}, "body": body, "state": state, "url": f"u{gid}"}


def pull_request(threads=(), reviews=()):
    return {"number": 7, "url": "https://gh/pull/7", "headRefName": "feat",
            "reviewThreads": {"nodes": list(threads)}, "reviews": {"nodes": list(reviews)}, "comments": {"nodes": []}}


class GithubItemsTest(unittest.TestCase):
    def items(self, threads=(), reviews=()):
        return [(kind, gid) for kind, gid, *_ in pr_comments.github_items(pull_request(threads, reviews))]

    def test_brings_in_submitted_reviews_and_threads(self):
        self.assertEqual(self.items([thread(1, "SUBMITTED")], [review(2, "COMMENTED")]), [("thread", 1), ("review", 2)])

    def test_skips_a_pending_review(self):
        self.assertEqual(self.items(reviews=[review(2, "PENDING")]), [])

    def test_skips_a_thread_of_a_pending_review(self):
        self.assertEqual(self.items([thread(1, "PENDING")]), [])

    def test_leaves_out_a_pending_reply_on_a_submitted_thread(self):
        submitted = thread(1, "SUBMITTED", replies=["Unsent draft."], reply_state="PENDING")
        self.assertEqual(pr_comments.github_items(pull_request([submitted]))[0][5]["replies"], [])

    def test_skips_a_thread_with_no_comments(self):
        empty = {**thread(1, "SUBMITTED"), "comments": {"nodes": []}}
        self.assertEqual(self.items([empty]), [])

    def test_keeps_the_submitted_ones_beside_pending_ones(self):
        got = self.items([thread(1, "PENDING"), thread(3, "SUBMITTED")], [review(2, "PENDING"), review(4, "APPROVED")])
        self.assertEqual(got, [("thread", 3), ("review", 4)])

    def test_skips_a_review_without_a_body(self):
        self.assertEqual(self.items(reviews=[review(2, "COMMENTED", body="  ")]), [])


class ImportingCommentsTest(RunCase):
    def setUp(self):
        super().setUp()
        self.write("merged.md", merged_md())

    def fetch(self, pr):
        graphql = {"data": {"repository": {"pullRequest": pr}}}
        with mock.patch.object(pr_comments, "graphql", return_value=graphql), \
                mock.patch.object(pr_comments, "repo_owner_name", return_value=["o", "r"]), \
                mock.patch.object(sys, "argv", ["pr-comments", self.run_dir, "--pr", "7", "--repo", self.tmp]):
            pr_comments.main()

    def test_a_pending_comment_never_reaches_the_run(self):
        self.fetch(pull_request([thread(1, "PENDING", "Draft finding text.")], [review(2, "PENDING", "Draft summary.")]))
        self.assertNotIn("Draft", self.read("merged.md"))

    def test_a_submitted_comment_becomes_a_finding(self):
        self.fetch(pull_request([thread(1, "SUBMITTED", "Real comment.")]))
        self.assertIn("Real comment.", self.read("merged.md"))

    def test_a_comment_posted_after_a_fetch_is_added_once_submitted(self):
        self.fetch(pull_request([thread(1, "PENDING", "Soon.")]))
        self.fetch(pull_request([thread(1, "SUBMITTED", "Soon.")]))
        self.assertEqual(self.read("merged.md").count("- id: "), 1)

    def test_a_credit_is_never_a_candidate_for_a_comment(self):
        self.write("merged.md", merged_md(
            "- id: 1\n  lens: credit\n  file: a.py\n  line: 1\n  title: Looks off\n  claim: Looks off here.\n",
            "- id: 2\n  lens: correctness\n  file: a.py\n  line: 1\n  title: Looks off\n  claim: Looks off here.\n"))
        self.fetch(pull_request([thread(1, "SUBMITTED", "Looks off.")]))
        self.assertEqual(self.read("pr/candidates.tsv").split("\n")[1].split("\t")[1], "2")
        self.assertNotIn("\t1\t", self.read("pr/candidates.tsv"))


if __name__ == "__main__":
    unittest.main()

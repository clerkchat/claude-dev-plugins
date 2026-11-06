import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from helpers import SCRIPTS, RunCase, TempCase, init_repo, merged_md, run_ok, write_file

sys.path.insert(0, SCRIPTS)
import gh_api
import records

post = records.load_script("post-review.py")
REAL_PR_PATCH = post.pr_patch

HEAD = "a" * 40
MERGE_BASE = "b" * 40
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


NO_COMMENT = {"data": {"addPullRequestReviewThread": {"thread": None}}}


def thread_answer(variables):
    return thread_data(1 if variables.get("path") == "src/a.py" else 3)


def review_comment(n, path):
    return {"id": 900 + n, "node_id": f"PRRC_{n}", "html_url": f"https://gh/c/{900 + n}", "path": path, "body": f"Finding {n} text."}


class PostCase(RunCase):
    def setUp(self):
        super().setUp()
        self.write_merged(*(finding(m, *f) for m, f in FINDINGS.items()))
        self.write_numbers(dict.fromkeys(FINDINGS, "fix"))
        self.write_target("pr 7", MERGE_BASE, HEAD)
        self.marks = {}
        self.ctx = {"owner": "acme", "name": "widgets", "pr": 7, "head": HEAD, "merge_base": MERGE_BASE, "files": ["src/a.py", "src/b.py"],
                    "pending": None, "review_ids": {"55"}, "comment_ids": {"901"}}
        patcher = mock.patch.object(post, "fetch_pr", side_effect=lambda *a: self.ctx)
        patcher.start()
        self.addCleanup(patcher.stop)
        diff = mock.patch.object(post, "pr_patch", return_value=PATCH)
        self.pr_diff = diff.start()
        self.addCleanup(diff.stop)

    def stub(self, name, **kw):
        patcher = mock.patch.object(gh_api, name, **kw)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def mark(self, mid, note="", text=None):
        self.marks[mid] = note
        self.write_instructions({m: ("post", n) for m, n in self.marks.items()})
        if text is not False: self.write(f"posted/{mid}.md", text or f"Finding {mid} text.")

    def pend(self, commit=HEAD, comments=None, body=""):
        self.ctx["pending"] = {"id": 55, "node_id": "PRR_55", "commit_id": commit, "html_url": "https://gh/r/55", "body": body,
                               "comments": comments or {}}

    def posted_row(self, mid, state="posted", **fields):
        row = {"state": state, "note": self.marks.get(mid, ""), "kind": "line", "path": "src/a.py", "line": "11", "end_line": "11",
               "side": "RIGHT", "thread_id": "PRRT_1", "comment_id": "901", "url": "https://gh/c/901", "review_id": "55", **fields}
        rows = post.rr.read_posted(self.run_dir); rows[mid] = row
        post.rr.write_posted(self.run_dir, rows)

    def main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            post.main([self.run_dir, *args])
        self.err = err.getvalue()
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

    def refusal(self, *args):
        with self.assertRaises(SystemExit) as raised:
            self.main(*(args or ("--post", "--dry-run")))
        return str(raised.exception)


class UnwrapTest(unittest.TestCase):
    def test_joins_the_lines_of_a_paragraph(self):
        self.assertEqual(post.unwrap("one\ntwo\n\nthree"), "one two\n\nthree")

    def test_keeps_lines_inside_a_code_fence(self):
        self.assertEqual(post.unwrap("say\n```suggestion\na\nb\n```\nafter"), "say\n```suggestion\na\nb\n```\nafter")

    def test_keeps_list_items_on_their_own_lines(self):
        self.assertEqual(post.unwrap("- one\n  more\n- two"), "- one more\n- two")


class ReadHunksTest(unittest.TestCase):
    def test_counts_a_line_with_a_bare_carriage_return_as_one_line(self):
        patch = "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1,2 +1,3 @@\n a\rb\n c\n+++ y\n@@ -9 +10 @@\n+d\n"
        self.assertEqual(post.read_hunks(patch), {"x": [(1, 3), (10, 10)]})


class AfterAnIncrementalReviewTest(PostCase):
    def setUp(self):
        super().setUp()
        repo = init_repo(self.path("work"), with_origin=False)
        self.commit_lines(repo, {"src/a.py": 20, "src/b.py": 20}, "pr base")
        self.ctx["merge_base"] = repo.git("rev-parse", "HEAD")
        first = self.commit_lines(repo, {"src/a.py": 20}, "first review", changed=10)
        self.ctx["head"] = self.commit_lines(repo, {"src/b.py": 20}, "re-review", changed=5)
        self.write_target("pr 7", first, self.ctx["head"])
        self.write("patch/all.patch", repo.git("diff", first, self.ctx["head"]) + "\n")
        self.repo = repo.path
        self.pr_diff.side_effect = REAL_PR_PATCH
        self.write_merged(finding(1, "src/a.py", "10"))
        self.mark(1)

    def commit_lines(self, repo, files, subject, changed=None):
        for name, count in files.items():
            write_file(os.path.join(repo.path, name), "".join(f"{subject if i == changed else 'line'} {i}\n" for i in range(1, count + 1)))
        repo.git("add", "-A")
        repo.git("commit", "-qm", subject)
        return repo.git("rev-parse", "HEAD")

    def calls(self, *args):
        return super().calls("--repo", self.repo, *args)

    def test_anchors_a_carried_finding_on_its_line_in_the_pull_requests_diff(self):
        self.assertEqual({k: self.thread_vars(1).get(k) for k in ("subjectType", "line")}, {"subjectType": "LINE", "line": 10})


class AnchorTest(PostCase):
    def test_anchors_a_range_on_the_right_side(self):
        self.mark(1)
        self.assertEqual({k: v for k, v in self.thread_vars(1).items() if k not in ("pullRequestReviewId", "body")},
                         {"path": "src/a.py", "subjectType": "LINE", "line": 13, "side": "RIGHT", "startLine": 11, "startSide": "RIGHT"})

    def test_orders_a_range_whose_end_comes_before_its_start(self):
        self.write_merged(finding(1, "src/a.py", "13-11"))
        self.mark(1)
        self.assertEqual((self.thread_vars(1)["startLine"], self.thread_vars(1)["line"]), (11, 13))

    def test_anchors_on_the_line_an_override_sets(self):
        self.write("overrides/1.md", "line: 12\n")
        self.mark(1)
        self.assertEqual((self.thread_vars(1)["line"], "startLine" in self.thread_vars(1)), (12, False))

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


CREDIT = "- id: 6\n  lens: credit\n  confidence: 90\n  file: src/a.py\n  line: 11\n  title: Guards the retry\n  claim: It guards the retry.\n"


class CreditCase(PostCase):
    def setUp(self):
        super().setUp()
        self.write_merged(*(finding(m, *f) for m, f in FINDINGS.items()), CREDIT)
        self.mark(6)

    def number_credit(self, section):
        self.write_numbers({**dict.fromkeys(FINDINGS, "fix"), 6: section})


class ShownCreditTest(CreditCase):
    def test_posts_on_its_lines(self):
        self.number_credit("credit")
        self.assertEqual(self.thread_vars(6)["line"], 11)


class CreditTheReportDroppedTest(CreditCase):
    def test_refuses_a_credit_never_numbered(self):
        self.assertIn("finding #6: it is a credit the report no longer shows; clear its Post with --instruct #6=none", self.refusal())

    def test_refuses_a_credit_numbered_before_and_now_hidden(self):
        self.number_credit("hidden")
        self.assertIn("finding 6: it is a credit the report no longer shows", self.refusal())

    def test_skips_one_already_posted(self):
        self.posted_row(6)
        self.assertIn("already posted", self.main())


class PreviewTitleTest(PostCase):
    def test_shows_the_title_an_override_sets_over_titles_tsv(self):
        self.write("titles.tsv", "1\tShort title\n")
        self.write("overrides/1.md", "title: Overridden title\n")
        self.mark(1)
        self.assertIn("finding 1: Overridden title", self.main())


class NotePlacementTest(PostCase):
    def test_a_line_in_the_note_wins(self):
        self.mark(1, note="on src/a.py:41-42, keep it short")
        self.assertEqual((self.thread_vars(1)["startLine"], self.thread_vars(1)["line"]), (41, 42))

    def test_a_reversed_range_in_the_note_is_ordered(self):
        self.mark(1, note="on src/a.py:42-41")
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

    def test_refuses_a_whitespace_only_posted_text(self):
        self.mark(1, text="  \n\n")
        self.assertIn("finding 1: it has no posted text", self.refusal())

    def test_refuses_a_text_drafted_for_another_note(self):
        self.mark(1, note="as a question")
        self.posted_row(1, state="drafted", note="keep it short", kind="", comment_id="", review_id="")
        self.assertIn("finding 1: its posted text is to be redrafted; the note changed", self.refusal())

    def test_sends_nothing_when_it_refuses(self):
        self.mark(4)
        self.refusal()
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "posted", "payload.json")))


class LocalPathTest(PostCase):
    def test_refuses_a_text_naming_the_run_directory(self):
        self.mark(1, text=f"See {self.run_dir}/merged.md.")
        self.assertIn(f"finding 1: its text names a local path of this machine ({self.run_dir})", self.refusal())

    def test_refuses_a_text_naming_the_home_directory(self):
        with mock.patch.dict(os.environ, {"HOME": "/Users/reviewer"}):
            self.mark(1, text="It reads /Users/reviewer/notes.txt.")
            self.assertIn("its text names a local path of this machine (/Users/reviewer)", self.refusal())

    def test_refuses_a_review_body_naming_a_local_path(self):
        self.mark(1)
        self.write("posted/review.md", f"Reviewed in {self.run_dir}.")
        self.assertIn("the review body: its text names a local path", self.refusal())

    def test_says_so_in_the_preview(self):
        self.mark(1, text=f"See {self.run_dir}.")
        self.assertIn("cannot post: its text names a local path", self.main())


class InternalMaterialWarningTest(PostCase):
    CASES = {".clerk-dev/latest/merged.md": "a .clerk-dev path", "~/code/x": "a home-directory path", "DEC-17": "a record id",
             "confidence 90": "a confidence", "the security lens": "a lens", "finding 12": "a finding number",
             "20261105-1200-branch": "a run label"}

    def test_warns_on_each_kind_in_the_preview(self):
        for text, what in self.CASES.items():
            with self.subTest(text):
                self.mark(1, text=f"Look at {text} here.")
                self.assertIn(f"warning: the text names {what}", self.main())

    def test_still_posts_the_text(self):
        self.mark(1, text="Per DEC-17 this breaks.")
        self.assertEqual(self.thread_vars(1)["body"], "Per DEC-17 this breaks.")


class IssueReferenceTest(PostCase):
    def test_warns_that_github_links_an_issue_reference(self):
        self.mark(1, text="Same as in #12 and #3.")
        self.assertIn("warning: the text names #12, #3; GitHub links each to that issue or pull request", self.main())

    def test_ignores_an_issue_reference_in_inline_code(self):
        self.mark(1, text="The `#12` anchor.")
        self.assertNotIn("GitHub links", self.main())

    def test_refuses_a_cross_reference_token_of_the_review(self):
        self.mark(1, text="Same root cause as {#12}.")
        self.assertIn("finding 1: its text holds a cross-reference token of the review ({#12})", self.refusal())


class MentionWarningTest(PostCase):
    def test_warns_that_a_mention_notifies(self):
        self.mark(1, text="Ask @octocat and @acme/core.")
        self.assertIn("warning: the text mentions @acme/core, @octocat; GitHub notifies them", self.main())

    def test_ignores_a_mention_in_inline_code(self):
        self.mark(1, text="Use the `@octocat` decorator.")
        self.assertNotIn("mentions", self.main())

    def test_warns_on_a_mention_after_an_unclosed_backtick(self):
        self.mark(1, text="Use the `@octocat decorator.")
        self.assertIn("warning: the text mentions @octocat", self.main())

    def test_ignores_a_mention_in_a_code_span_closed_by_a_run_of_the_same_length(self):
        self.mark(1, text="Use ``@octocat ` here``.")
        self.assertNotIn("mentions", self.main())

    def test_ignores_a_mention_in_a_code_fence(self):
        self.mark(1, text="Use:\n```suggestion\n@decorator\n```")
        self.assertNotIn("mentions", self.main())

    def test_ignores_an_email_address(self):
        self.mark(1, text="Mail dev@example.com.")
        self.assertNotIn("mentions", self.main())

    def test_warns_on_a_mention_in_the_review_body(self):
        self.mark(1)
        self.write("posted/review.md", "Thanks @octocat.")
        self.assertIn("warning: the text mentions @octocat", self.main().split("review body:")[1])


class NoWriteCallTest(PostCase):
    def setUp(self):
        super().setUp()
        self.mark(1); self.mark(3)
        self.pend()
        self.posted_row(1, state="edited")
        self.writes = [self.stub("rest"), self.stub("graphql")]

    def assertNoWriteCall(self):
        self.assertEqual([w.call_count for w in self.writes], [0, 0])

    def test_the_preview_makes_none(self):
        self.main()
        self.assertNoWriteCall()

    def test_a_dry_run_of_post_makes_none(self):
        self.main("--post", "--dry-run")
        self.assertNoWriteCall()

    def test_a_dry_run_of_submit_makes_none(self):
        self.main("--submit", "comment", "--dry-run")
        self.assertNoWriteCall()


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


class WhenThePendingReviewHasABodyTest(PostCase):
    def setUp(self):
        super().setUp()
        self.mark(1)
        self.pend(body="My summary.")

    def test_keeps_it_above_the_review_body(self):
        self.write("posted/review.md", "Nice work.")
        self.assertEqual(self.review_body(), "My summary.\n\nNice work.")

    def test_sends_no_default_sentence_below_it(self):
        self.assertEqual(self.review_body(), "My summary.")

    def test_shows_it_in_the_preview(self):
        self.assertIn("review body:\n    My summary.\n  keeps the text already in pending review 55 on GitHub", self.main())

    def test_keeps_only_the_text_saved_when_this_run_first_posted_to_it(self):
        self.write("posted/pending-55.md", "My summary.")
        self.posted_row(3)
        self.pend(body="My summary.\n\nComments from an earlier batch.")
        self.assertEqual(self.review_body(), "My summary.")

    def test_takes_none_once_this_run_posted_to_it_without_saving_any(self):
        self.posted_row(3)
        self.assertEqual(self.review_body(), post.DEFAULT_BODY)


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


class DeletedOnGitHubTest(PostCase):
    def setUp(self):
        super().setUp()
        self.ctx["comment_ids"] = set()

    def test_posts_a_comment_deleted_on_github_again(self):
        self.mark(1); self.posted_row(1)
        self.assertEqual(self.call_for(1)["graphql"], "addPullRequestReviewThread")

    def test_says_so_in_the_preview(self):
        self.mark(1); self.posted_row(1)
        self.assertIn("its earlier comment is no longer on GitHub (review 55)", self.main())

    def test_posts_a_body_comment_of_a_deleted_review_again(self):
        self.mark(1, note="in the review body")
        self.posted_row(1, kind="body", comment_id="", review_id="54")
        self.assertIn("Finding 1 text.", self.review_body())


class SubmitTest(PostCase):
    def setUp(self):
        super().setUp()
        self.mark(1)
        self.pend()
        self.posted_row(1)

    def submit(self, *args):
        self.main("--submit", *args, "--dry-run")
        with open(os.path.join(self.run_dir, "posted", "payload.json"), encoding="utf-8") as fh:
            return json.load(fh)["calls"]

    def test_requires_a_verdict(self):
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
            post.main([self.run_dir, "--submit", "--dry-run"])
        self.assertEqual(raised.exception.code, 2)

    def test_refuses_without_a_pending_review(self):
        self.ctx["pending"] = None
        with self.assertRaises(SystemExit):
            self.submit("approve")

    def test_refuses_a_pending_review_this_run_did_not_post_to(self):
        self.posted_row(1, review_id="54")
        self.assertIn("pending review 55 holds nothing this run posted", self.refusal("--submit", "comment", "--dry-run"))

    def test_refuses_a_review_body_naming_a_local_path(self):
        self.write("posted/review.md", f"Reviewed in {self.run_dir}.")
        self.assertIn("the review body: its text names a local path", self.refusal("--submit", "comment", "--dry-run"))

    def test_says_nothing_changed_when_github_rejects_it(self):
        self.stub("rest", side_effect=gh_api.GhError("cannot approve your own pull request"))
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
            post.main([self.run_dir, "--submit", "approve"])
        self.assertIn("GitHub rejected the request; nothing changed on GitHub", str(raised.exception))

    def test_shows_the_review_body_warnings(self):
        self.write("posted/review.md", "Thanks @octocat.")
        self.submit("comment")
        self.assertIn("review body:\n  warning: the text mentions @octocat", self.err)

    def test_keeps_the_text_saved_from_the_pending_review(self):
        self.write("posted/pending-55.md", "My summary.")
        self.assertEqual(self.submit("comment")[0]["fields"]["body"], "My summary.")

    def test_sends_the_verdict_with_the_review_body(self):
        self.assertEqual(self.submit("request-changes"), [{"method": "POST", "path": "repos/acme/widgets/pulls/7/reviews/55/events",
                                                           "fields": {"event": "REQUEST_CHANGES", "body": post.DEFAULT_BODY}}])


class LiveCase(PostCase):
    def setUp(self):
        super().setUp()
        self.mark(1); self.mark(3)
        self.graphql = self.stub("graphql", side_effect=lambda q, v, cwd: thread_answer(v))
        self.rest = self.stub("rest", return_value={"id": 55, "node_id": "PRR_55", "html_url": "https://gh/r/55"})
        self.listed = self.stub("rest_list", return_value=[])

    def graphql_rejects(self, refused):
        def answer(query, variables, cwd):
            if refused(query, variables): raise gh_api.GhError("rejected")
            return thread_answer(variables)
        self.graphql.side_effect = answer

    def graphql_answers(self, path, reply):
        def answer(query, variables, cwd):
            if variables.get("path") != path: return thread_answer(variables)
            if isinstance(reply, BaseException): raise reply
            return reply
        self.graphql.side_effect = answer

    def rest_rejects(self, method, error=None):
        def answer(m, path, fields, cwd):
            if m == method: raise error or gh_api.GhError("refused")
            return {"id": 55, "node_id": "PRR_55", "html_url": "https://gh/r/55"}
        self.rest.side_effect = answer

    def deleted_comments(self):
        return [c.args[1] for c in self.graphql.call_args_list if "deletePullRequestReviewComment" in c.args[0]]

    def stopped(self, error):
        err = io.StringIO()
        with self.assertRaises(error), redirect_stderr(err):
            post.main([self.run_dir, "--post"])
        return err.getvalue()

    def posted_body(self):
        return next(c.args[1]["body"] for c in self.graphql.call_args_list if c.args[1].get("path") == "src/a.py")

    def rejected(self):
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
            post.main([self.run_dir, "--post"])
        return str(raised.exception)


class LivePostTest(LiveCase):
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


class WhenPostingToAPendingReviewWithABodyTest(LiveCase):
    def test_saves_the_body_it_keeps(self):
        self.pend(body="My summary.")
        self.main("--post")
        self.assertEqual(self.read("posted/pending-55.md"), "My summary.\n")


class PlaceholderLookalikeTest(LiveCase):
    def test_sends_a_text_that_looks_like_a_placeholder_as_written(self):
        self.mark(1, text="{review.id}")
        self.main("--post")
        self.assertEqual(self.posted_body(), "{review.id}")

    def test_records_the_batch_when_a_note_looks_like_a_placeholder(self):
        self.mark(1, note="{unknown.key}")
        self.main("--post")
        self.assertEqual(post.rr.read_posted(self.run_dir)[1]["note"], "{unknown.key}")


class LiveRollbackTest(LiveCase):
    def test_says_nothing_changed_when_the_first_call_fails(self):
        self.rest_rejects("POST")
        self.assertIn("nothing changed on GitHub", self.rejected())

    def test_says_nothing_is_left_after_a_full_rollback(self):
        self.graphql_rejects(lambda q, v: v.get("path") == "src/b.py")
        self.assertIn("nothing from this batch is left on GitHub", self.rejected())

    def test_deletes_the_review_it_created_when_an_answer_names_no_comment(self):
        self.graphql.side_effect = [thread_data(1), NO_COMMENT, {"data": {}}]
        self.rejected()
        self.assertEqual(self.rest.call_args.args[:2], ("DELETE", "repos/acme/widgets/pulls/7/reviews/55"))

    def test_names_the_created_review_it_could_not_delete(self):
        self.graphql_rejects(lambda q, v: v.get("path") == "src/b.py")
        self.rest_rejects("DELETE")
        self.assertIn("still on GitHub: pending review 55 (could not delete it", self.rejected())

    def test_names_a_comment_it_could_not_delete_while_its_review_stays(self):
        self.graphql_rejects(lambda q, v: v.get("path") == "src/b.py" or "deletePullRequestReviewComment" in q)
        self.rest_rejects("DELETE")
        self.assertIn("finding 1's comment https://gh/c/901 (could not delete it", self.rejected())

    def test_leaves_out_comments_the_deleted_review_took_with_it(self):
        self.graphql_rejects(lambda q, v: v.get("path") == "src/b.py" or "deletePullRequestReviewComment" in q)
        self.assertIn("nothing from this batch is left on GitHub", self.rejected())


class WhenAnAnswerNamesNoCommentOnAnExistingReviewTest(LiveCase):
    def setUp(self):
        super().setUp()
        self.pend()
        self.graphql_answers("src/b.py", NO_COMMENT)

    def test_deletes_the_comment_it_finds_on_the_pending_review(self):
        self.listed.return_value = [review_comment(3, "src/b.py")]
        self.rejected()
        self.assertIn({"id": "PRRC_3"}, self.deleted_comments())

    def test_says_nothing_is_left_once_it_deleted_it(self):
        self.listed.return_value = [review_comment(3, "src/b.py")]
        self.assertIn("rolled back; nothing from this batch is left on GitHub", self.rejected())

    def test_leaves_a_comment_that_was_on_the_review_before(self):
        self.pend(comments={903: "PRRC_3"})
        self.listed.return_value = [review_comment(3, "src/b.py")]
        self.rejected()
        self.assertNotIn({"id": "PRRC_3"}, self.deleted_comments())

    def test_says_the_comment_may_be_left_when_it_finds_none(self):
        self.assertIn("rolled back; possibly on GitHub: finding 3's comment on pending review 55; posted.tsv is unchanged", self.rejected())

    def test_never_says_nothing_changed_when_the_first_answer_names_none(self):
        self.graphql_answers("src/a.py", NO_COMMENT)
        self.assertIn("the batch stopped; possibly on GitHub: finding 1's comment on pending review 55", self.rejected())


class WhenTheBatchIsInterruptedTest(LiveCase):
    def setUp(self):
        super().setUp()
        self.graphql_answers("src/b.py", KeyboardInterrupt())

    def test_deletes_the_review_it_created(self):
        self.stopped(KeyboardInterrupt)
        self.assertEqual(self.rest.call_args.args[:2], ("DELETE", "repos/acme/widgets/pulls/7/reviews/55"))

    def test_says_what_it_rolled_back(self):
        self.assertIn("the batch stopped; rolled back; nothing from this batch is left on GitHub", self.stopped(KeyboardInterrupt))


class WhenAReplyIsMalformedTest(LiveCase):
    def test_deletes_the_review_it_created(self):
        self.graphql_answers("src/b.py", json.JSONDecodeError("Expecting value", "", 0))
        self.stopped(ValueError)
        self.assertEqual(self.rest.call_args.args[:2], ("DELETE", "repos/acme/widgets/pulls/7/reviews/55"))


class WhenInterruptedWhileCreatingTheReviewTest(LiveCase):
    def setUp(self):
        super().setUp()
        self.rest_rejects("POST", KeyboardInterrupt())

    def test_deletes_the_pending_review_it_finds(self):
        self.listed.return_value = [{"id": 56, "node_id": "PRR_56", "state": "PENDING"}]
        self.stopped(KeyboardInterrupt)
        self.assertEqual(self.rest.call_args.args[:2], ("DELETE", "repos/acme/widgets/pulls/7/reviews/56"))

    def test_says_a_review_may_be_left_when_it_finds_none(self):
        self.assertIn("possibly on GitHub: a pending review this batch began", self.stopped(KeyboardInterrupt))


class WhenPostedTsvCannotBeWrittenTest(LiveCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(post.rr, "write_posted", side_effect=OSError("disk full"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_names_what_it_posted(self):
        self.assertIn("posted.tsv was not updated; this batch is on GitHub:\n  review 55 https://gh/r/55\n"
                      "  finding 1: comment 901 https://gh/c/901\n  finding 3: comment 903 https://gh/c/903", self.stopped(OSError))


class LiveUpdateRollbackTest(LiveCase):
    def setUp(self):
        super().setUp()
        self.posted_row(1, state="edited")

    def test_deletes_the_new_comments_when_an_update_fails(self):
        self.rest_rejects("PATCH")
        self.rejected()
        self.assertEqual(self.graphql.call_args_list[-1].args[1], {"id": "PRRC_3"})

    def test_names_an_update_made_before_the_failure(self):
        self.pend(comments={901: "PRRC_901"})
        self.rest_rejects("PUT")
        self.assertIn("still on GitHub: finding 1's comment https://gh/c/901, which keeps its new text", self.rejected())


class FetchPrCase(RunCase):
    LISTS = {"repos/o/r/pulls/7/files": [{"filename": "a.py"}],
             "repos/o/r/pulls/7/reviews": [{"id": 1, "state": "COMMENTED"},
                                           {"id": 2, "node_id": "N2", "state": "PENDING", "commit_id": HEAD, "body": "Mine."}],
             "repos/o/r/pulls/7/comments": [{"id": 8}],
             "repos/o/r/pulls/7/reviews/2/comments": [{"id": 9, "node_id": "C9"}]}

    VIEW = json.dumps({"headRefOid": HEAD, "baseRefOid": "c" * 40})

    def answer(self, args, cwd):
        return self.VIEW if args[0] == "pr" else MERGE_BASE + "\n"

    def fetch(self, origin):
        with mock.patch.object(gh_api, "repo_owner_name", return_value=origin.split("/")), \
             mock.patch.object(gh_api, "pr_number", return_value=7), \
             mock.patch.object(gh_api, "gh", side_effect=self.answer) as self.gh, \
             mock.patch.object(gh_api, "rest_list", side_effect=lambda path, cwd: self.LISTS[path]):
            return post.fetch_pr("/w", self.run_dir, 7, HEAD)


class FetchPrTest(FetchPrCase):
    def setUp(self):
        super().setUp()
        self.ctx = self.fetch("o/r")

    def test_finds_the_pending_review_and_its_comment_nodes(self):
        self.assertEqual((self.ctx["pending"]["id"], self.ctx["pending"]["comments"]), (2, {9: "C9"}))

    def test_keeps_the_body_of_the_pending_review(self):
        self.assertEqual(self.ctx["pending"]["body"], "Mine.")

    def test_knows_which_reviews_are_on_github(self):
        self.assertEqual(self.ctx["review_ids"], {"1", "2"})

    def test_knows_which_comments_are_on_github_submitted_or_pending(self):
        self.assertEqual(self.ctx["comment_ids"], {"8", "9"})

    def test_finds_the_merge_base_of_the_reviewed_commit_with_the_base(self):
        self.assertEqual((self.ctx["merge_base"], self.gh.call_args_list[-1].args[0][1]),
                         (MERGE_BASE, f"repos/o/r/compare/{'c' * 40}...{HEAD}"))


class WhenTheCheckoutIsAForkTest(FetchPrCase):
    def setUp(self):
        super().setUp()
        self.write("pr/pr.txt", "7\thttps://github.com/o/r/pull/7\n")
        self.ctx = self.fetch("me/r")

    def test_posts_to_the_repository_the_pull_request_belongs_to(self):
        self.assertEqual((self.ctx["owner"], self.ctx["name"], self.ctx["pr"]), ("o", "r", 7))

    def test_reads_the_head_from_that_repository(self):
        args = next(c.args[0] for c in self.gh.call_args_list if c.args[0][0] == "pr")
        self.assertEqual(args[args.index("--repo") + 1], "o/r")


class ReviewedPrCase(RunCase):
    def setUp(self):
        super().setUp()
        self.branch_pr = self.stub("pr_number", return_value=7)
        self.origin = self.stub("repo_owner_name", return_value=["o", "r"])

    def stub(self, name, **kw):
        patcher = mock.patch.object(gh_api, name, **kw)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def reviewed(self, asked=None):
        return post.reviewed_pr("/w", self.run_dir, asked)

    def refusal(self, asked=None):
        with self.assertRaises(SystemExit) as raised:
            self.reviewed(asked)
        return str(raised.exception)


class WhenTheRunRecordedAPullRequestTest(ReviewedPrCase):
    def setUp(self):
        super().setUp()
        self.write("pr/pr.txt", "9\thttps://github.com/o/r/pull/9\n")

    def test_posts_to_it(self):
        self.assertEqual(self.reviewed(), ("o", "r", 9))

    def test_accepts_the_same_pr(self):
        self.assertEqual(self.reviewed(9), ("o", "r", 9))

    def test_refuses_another_pr(self):
        self.assertIn("--pr 8 is not the reviewed pull request #9", self.refusal(8))

    def test_posts_to_its_repository_when_origin_is_a_fork(self):
        self.origin.return_value = ["me", "r"]
        self.assertEqual(self.reviewed(), ("o", "r", 9))


class WhenTheRunReviewedAPullRequestNumberTest(ReviewedPrCase):
    def test_posts_to_that_number_on_origin(self):
        self.write_target("#9", "b" * 40, HEAD)
        self.assertEqual(self.reviewed(), ("o", "r", 9))


class WhenTheRunReviewedAPullRequestUrlTest(ReviewedPrCase):
    def test_posts_to_the_repository_of_the_url(self):
        self.origin.return_value = ["me", "r"]
        self.write_target("https://github.com/o/r/pull/9", "b" * 40, HEAD)
        self.assertEqual(self.reviewed(), ("o", "r", 9))


class WhenTheRunRecordedNoPullRequestTest(ReviewedPrCase):
    def test_posts_to_the_branch_pull_request_on_origin(self):
        self.assertEqual(self.reviewed(), ("o", "r", 7))

    def test_refuses_a_pr_other_than_the_branch_pull_request(self):
        self.assertIn("--pr 8 is not the reviewed pull request #7", self.refusal(8))

    def test_takes_the_pr_when_the_branch_has_none(self):
        self.branch_pr.side_effect = gh_api.GhError("no pull requests found")
        self.assertEqual(self.reviewed(8), ("o", "r", 8))

    def test_asks_for_a_pr_when_nothing_names_one(self):
        self.branch_pr.side_effect = gh_api.GhError("no pull requests found")
        self.assertIn("pass --pr N", self.refusal())


def reply_data(n):
    return {"data": {"addPullRequestReviewThreadReply": {"comment": {"databaseId": 950 + n, "url": f"https://gh/c/{950 + n}",
                                                                     "author": {"login": "me"}}}}}


RESOLVED = {"data": {"resolveReviewThread": {"thread": {"isResolved": True}}}}


class CloseCase(PostCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("repo"), with_origin=False)
        self.sha = self.repo.git("rev-parse", "HEAD")
        self.looks_fixed = f"Looks fixed in {self.sha[:7]}."
        self.statuses, self.threads = {}, {}
        self.closable_finding(1)
        self.viewer = self.stub("viewer_login", return_value="me")
        refresh = mock.patch.object(post, "refresh_threads")
        self.refresh = refresh.start()
        self.addCleanup(refresh.stop)

    def main(self, *args):
        return super().main(*args, "--repo", self.repo.path)

    def closable_finding(self, mid, ref=None, **thread):
        self.posted_row(mid, thread_id=f"PRRT_{mid}", comment_id=str(900 + mid), url=f"https://gh/c/{900 + mid}")
        self.set_status(mid, "fixed", ref or self.sha)
        self.thread(mid, **thread)

    def set_status(self, mid, status, ref=""):
        self.statuses[mid] = (status, ref)
        self.write_status(self.statuses)

    def thread(self, mid, **fields):
        self.threads[mid] = {"comment_id": str(900 + mid), "thread_id": f"PRRT_{mid}", "state": "open", "outdated": "0",
                             "can_resolve": "1", "line": "11", "replies": "", "date": "2026-11-06", **fields}
        post.rr.write_threads(self.run_dir, self.threads)

    def closable(self):
        return sorted(post.rr.closable(self.run_dir))

    def close_calls(self, ids="1"):
        self.main("--close", ids, "--dry-run")
        with open(os.path.join(self.run_dir, "posted", "payload.json"), encoding="utf-8") as fh:
            return json.load(fh)["calls"]

    def reply_body(self, ids="1"):
        return self.close_calls(ids)[0]["variables"]["body"]


class ClosableTest(CloseCase):
    def test_takes_a_posted_finding_marked_fixed_whose_thread_is_open(self):
        self.assertEqual(self.closable(), [1])

    def test_leaves_out_a_finding_not_marked_fixed(self):
        self.set_status(1, "open")
        self.assertEqual(self.closable(), [])

    def test_leaves_out_a_finding_posted_in_the_review_body(self):
        self.posted_row(1, kind="body", comment_id="", thread_id="")
        self.assertEqual(self.closable(), [])

    def test_leaves_out_a_credit(self):
        self.write_merged(*(finding(m, *f) for m, f in FINDINGS.items()), CREDIT)
        self.closable_finding(6)
        self.assertEqual(self.closable(), [1])

    def test_leaves_out_a_thread_kept_open(self):
        post.rr.write_kept_open(self.run_dir, {1: {"reason": "", "date": ""}})
        self.assertEqual(self.closable(), [])

    def test_leaves_out_a_resolved_thread(self):
        self.thread(1, state="resolved")
        self.assertEqual(self.closable(), [])

    def test_leaves_out_a_thread_in_the_pending_review(self):
        self.thread(1, state="pending")
        self.assertEqual(self.closable(), [])

    def test_leaves_out_a_missing_thread(self):
        self.thread(1, state="missing")
        self.assertEqual(self.closable(), [])

    def test_leaves_out_a_thread_row_of_an_earlier_comment(self):
        self.thread(1, comment_id="899")
        self.assertEqual(self.closable(), [])


class CloseListTest(CloseCase):
    def test_lists_the_closable_finding_with_its_fix_and_thread(self):
        self.assertIn(f"finding 1: Finding 1\n  fixed in: {self.sha}\n  thread: https://gh/c/901\n", self.main("--close"))

    def test_shows_the_last_reply(self):
        self.thread(1, replies="@amy: Why?; @bob: Done, see the new guard.")
        self.assertIn("  last reply: @bob: Done, see the new guard.\n", self.main("--close"))

    def test_skips_the_viewers_own_replies(self):
        self.thread(1, replies="@bob: Done, see the new guard.; @me: Looks fixed in abc1234.")
        self.assertIn("  last reply: @bob: Done, see the new guard.\n", self.main("--close"))

    def test_says_none_when_only_the_viewer_replied(self):
        self.thread(1, replies="@me: Looks fixed in abc1234.")
        self.assertIn("  last reply: none\n", self.main("--close"))

    def test_shows_the_reply_it_would_send(self):
        self.assertIn(f"  reply:\n    {self.looks_fixed}", self.main("--close"))

    def test_says_when_the_viewer_cannot_resolve(self):
        self.thread(1, can_resolve="0")
        self.assertIn("can resolve: no; the reply is sent and the thread left open", self.main("--close"))

    def test_reads_the_threads_from_the_pull_request_first(self):
        self.main("--close")
        self.assertTrue(self.refresh.called)

    def test_says_when_nothing_is_closable(self):
        self.set_status(1, "open")
        self.assertIn("nothing to close", self.main("--close"))

    def test_names_the_pending_review_that_blocks_closing(self):
        self.pend()
        self.assertIn("cannot close: you have pending review 55", self.main("--close"))

    def test_makes_no_call(self):
        writes = [self.stub("rest"), self.stub("graphql")]
        self.main("--close")
        self.assertEqual([w.call_count for w in writes], [0, 0])


class CloseDryRunTest(CloseCase):
    def test_replies_then_resolves_each_thread_in_turn(self):
        self.closable_finding(2)
        self.assertEqual([(c["graphql"], c["finding"]) for c in self.close_calls("2,1")],
                         [("addPullRequestReviewThreadReply", 1), ("resolveReviewThread", 1),
                          ("addPullRequestReviewThreadReply", 2), ("resolveReviewThread", 2)])

    def test_sends_to_the_thread_of_the_posted_comment(self):
        self.assertEqual([c["variables"].get("pullRequestReviewThreadId", c["variables"].get("threadId")) for c in self.close_calls()],
                         ["PRRT_1", "PRRT_1"])

    def test_says_looks_fixed_in_the_short_sha(self):
        self.assertEqual(self.reply_body(), self.looks_fixed)

    def test_says_looks_fixed_when_the_ref_names_no_commit(self):
        self.set_status(1, "fixed", "covered by the new tests")
        self.assertEqual(self.reply_body(), "Looks fixed.")

    def test_names_no_commit_for_a_number_that_is_not_one(self):
        self.set_status(1, "fixed", "see ticket 1234567")
        self.assertEqual(self.reply_body(), "Looks fixed.")

    def test_sends_the_default_reply_when_close_md_is_blank(self):
        self.write("posted/close-1.md", "  \n\n")
        self.assertEqual(self.reply_body(), self.looks_fixed)

    def test_sends_the_reply_text_of_close_md_unwrapped(self):
        self.write("posted/close-1.md", "Thanks, the guard\ncovers it now.\n")
        self.assertEqual(self.reply_body(), "Thanks, the guard covers it now.")

    def test_only_replies_when_the_viewer_cannot_resolve(self):
        self.thread(1, can_resolve="0")
        self.assertEqual([c["graphql"] for c in self.close_calls()], ["addPullRequestReviewThreadReply"])

    def test_makes_no_call(self):
        writes = [self.stub("rest"), self.stub("graphql")]
        self.close_calls()
        self.assertEqual([w.call_count for w in writes], [0, 0])


class WhenTheViewerAlreadyRepliedTest(CloseCase):
    def setUp(self):
        super().setUp()
        self.thread(1, replies=f"@me: {self.looks_fixed}; @bob: Thanks.")

    def test_only_resolves_the_thread(self):
        self.assertEqual([c["graphql"] for c in self.close_calls()], ["resolveReviewThread"])

    def test_says_so_in_the_listing(self):
        self.assertIn("  reply: already sent; --close only resolves the thread", self.main("--close"))


class CloseRefusalTest(CloseCase):
    def test_refuses_a_finding_that_is_not_closable(self):
        self.posted_row(2)
        self.assertIn("nothing sent; not closable (a posted thread still open, marked fixed, not kept open): finding 2",
                      self.refusal("--close", "1,2", "--dry-run"))

    def test_sends_nothing_when_one_is_not_closable(self):
        self.refusal("--close", "1,2", "--dry-run")
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "posted", "payload.json")))

    def test_refuses_while_the_viewer_has_a_pending_review(self):
        self.pend()
        self.assertIn("submit or delete your pending review first", self.refusal("--close", "1", "--dry-run"))

    def test_refuses_a_reply_naming_a_local_path(self):
        self.write("posted/close-1.md", f"Fixed, see {self.run_dir}.")
        self.assertIn("finding 1: its text names a local path of this machine", self.refusal("--close", "1", "--dry-run"))

    def test_refuses_a_dry_run_without_findings(self):
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
            self.main("--close", "--dry-run")
        self.assertEqual(raised.exception.code, 2)


class KeepOpenTest(CloseCase):
    def test_records_the_reason_in_keep_tsv(self):
        self.main("--keep-open", "1:the author wants a follow-up")
        self.assertEqual(post.rr.read_kept_open(self.run_dir)[1]["reason"], "the author wants a follow-up")

    def test_makes_the_finding_no_longer_closable(self):
        self.main("--keep-open", "1")
        self.assertEqual(self.closable(), [])

    def test_refuses_a_finding_without_a_posted_thread(self):
        self.assertIn("finding 2 has no posted thread to keep open", self.refusal("--keep-open", "2"))


class LiveCloseCase(CloseCase):
    def setUp(self):
        super().setUp()
        self.closable_finding(2, replies="@bob: Fixed it.")
        self.graphql = self.stub("graphql", side_effect=self.answer)

    def answer(self, query, variables, cwd):
        n = int(variables.get("pullRequestReviewThreadId", variables.get("threadId"))[-1])
        return reply_data(n) if "addPullRequestReviewThreadReply" in query else RESOLVED

    def thread_row(self, mid):
        return post.rr.read_threads(self.run_dir)[mid]

    def stopped(self):
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
            post.main([self.run_dir, "--close", "1,2", "--repo", self.repo.path])
        return str(raised.exception)


class LiveCloseTest(LiveCloseCase):
    def setUp(self):
        super().setUp()
        self.main("--close", "1,2")

    def test_marks_each_thread_resolved_in_threads_tsv(self):
        self.assertEqual([self.thread_row(m)["state"] for m in (1, 2)], ["resolved", "resolved"])

    def test_adds_the_reply_to_the_threads_replies(self):
        self.assertEqual(self.thread_row(2)["replies"], f"@bob: Fixed it.; @me: {self.looks_fixed}")

    def test_says_what_it_closed(self):
        self.assertIn("closed:\n  finding 1: replied and resolved\n  finding 2: replied and resolved", self.err)


class WhenTheViewerCannotResolveTest(LiveCloseCase):
    def setUp(self):
        super().setUp()
        self.thread(1, can_resolve="0")
        self.main("--close", "1")

    def test_keeps_the_thread_open_in_threads_tsv(self):
        self.assertEqual((self.thread_row(1)["state"], self.thread_row(1)["replies"]), ("open", f"@me: {self.looks_fixed}"))

    def test_reports_it_left_open(self):
        self.assertIn("finding 1: replied; left open, you cannot resolve it", self.err)


class WhenGitHubRejectsAResolveTest(LiveCloseCase):
    def setUp(self):
        super().setUp()
        self.graphql.side_effect = [reply_data(1), RESOLVED, reply_data(2), gh_api.GhError("rejected")]

    def test_names_the_threads_done_and_where_it_stopped(self):
        self.assertIn("the close stopped at finding 2: replied; not resolved; done before it: finding 1: replied and resolved",
                      self.stopped())

    def test_keeps_the_threads_done(self):
        self.stopped()
        self.assertEqual(self.thread_row(1)["state"], "resolved")

    def test_records_the_reply_it_sent_on_the_stopped_thread(self):
        self.stopped()
        self.assertEqual((self.thread_row(2)["state"], self.thread_row(2)["replies"]), ("open", f"@bob: Fixed it.; @me: {self.looks_fixed}"))


class WhenTheViewerCannotResolveAndItIsSentTest(LiveCloseCase):
    def setUp(self):
        super().setUp()
        self.thread(1, can_resolve="0")
        self.main("--close", "1")

    def test_keeps_the_thread_open(self):
        self.assertEqual(post.rr.read_kept_open(self.run_dir)[1]["reason"], post.CANNOT_RESOLVE)

    def test_no_longer_offers_it_for_closing(self):
        self.assertEqual(self.closable(), [2])


class WhenRetriedAfterAResolveFailedTest(LiveCloseCase):
    def setUp(self):
        super().setUp()
        self.graphql.side_effect = [reply_data(1), gh_api.GhError("rejected")]
        self.stopped()
        self.graphql.reset_mock(side_effect=True)
        self.graphql.side_effect = self.answer
        self.main("--close", "1")

    def test_sends_no_second_reply(self):
        self.assertEqual(["resolveReviewThread" in c.args[0] for c in self.graphql.call_args_list], [True])

    def test_marks_the_thread_resolved(self):
        self.assertEqual(self.thread_row(1)["state"], "resolved")

    def test_says_it_had_replied_already(self):
        self.assertIn("finding 1: already replied and resolved", self.err)


class WhenAThreadWasSettledSinceTheListingCase(LiveCloseCase):
    STATE = "resolved"

    def setUp(self):
        super().setUp()
        self.refresh.side_effect = lambda *a: self.thread(1, state=self.STATE)
        self.main("--close", "1,2")

    def threads_sent_to(self):
        return {c.args[1].get("pullRequestReviewThreadId", c.args[1].get("threadId")) for c in self.graphql.call_args_list}


class WhenAThreadWasResolvedSinceTheListingTest(WhenAThreadWasSettledSinceTheListingCase):
    def test_skips_it(self):
        self.assertEqual(self.threads_sent_to(), {"PRRT_2"})

    def test_says_it_skipped_it(self):
        self.assertIn("finding 1: its thread is already resolved on GitHub; skipped", self.err)

    def test_closes_the_others(self):
        self.assertIn("finding 2: replied and resolved", self.err)


class WhenAThreadWasDeletedSinceTheListingTest(WhenAThreadWasSettledSinceTheListingCase):
    STATE = "missing"

    def test_skips_it(self):
        self.assertEqual(self.threads_sent_to(), {"PRRT_2"})


class WhenTheViewersLoginIsUnavailableTest(LiveCloseCase):
    def test_sends_nothing(self):
        self.viewer.side_effect = gh_api.GhError("gh api user failed")
        self.stopped()
        self.assertEqual(self.graphql.call_count, 0)


class RefreshThreadsTest(RunCase):
    def setUp(self):
        super().setUp()
        post.rr.write_posted(self.run_dir, {1: {"state": "posted", "kind": "line", "comment_id": "901", "thread_id": "PRRT_1"}})
        live = {"reviewThreads": {"nodes": [{"id": "PRRT_1", "isResolved": True, "isOutdated": False, "viewerCanResolve": True,
                                              "path": "src/a.py", "line": 11, "originalLine": 11, "comments": {"nodes": [
                                                  {"databaseId": 901, "author": {"login": "me"}, "body": "Text.", "url": "u",
                                                   "pullRequestReview": {"state": "COMMENTED"}}]}}]}}
        fetch = mock.patch.object(post.pc, "fetch", return_value=live)
        self.fetch = fetch.start()
        self.addCleanup(fetch.stop)
        post.refresh_threads(self.run_dir, {"owner": "o", "name": "r", "pr": 7}, "/w")

    def test_reads_the_reviewed_pull_request(self):
        self.assertEqual(self.fetch.call_args.args, ("o", "r", 7, "/w"))

    def test_rewrites_threads_tsv_from_it(self):
        self.assertEqual(post.rr.read_threads(self.run_dir)[1]["state"], "resolved")


class WhenGitHubRejectsTheFirstReplyTest(LiveCloseCase):
    def test_says_nothing_was_sent(self):
        self.graphql.side_effect = gh_api.GhError("rejected")
        self.assertIn("the close stopped at finding 1: nothing sent; done before it: none", self.stopped())


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

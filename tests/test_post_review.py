import io
import json
import os
import shlex
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from helpers import SCRIPTS, GhRunCase, RunCase, TempCase, init_repo, merged_md, run_ok, write_file

sys.path.insert(0, SCRIPTS)
import gh_api
import records
import run_files

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
ANOTHER_PENDING = [{"id": 56, "node_id": "PRR_56", "state": "PENDING"}]


def thread_answer(variables):
    return thread_data(1 if variables.get("path") == "src/a.py" else 3)


def review_comment(n, path, **fields):
    return {"id": 900 + n, "node_id": f"PRRC_{n}", "html_url": f"https://gh/c/{900 + n}", "path": path, "body": f"Finding {n} text.",
            "user": {"login": "me"}, **fields}


class PostCase(GhRunCase):
    def setUp(self):
        super().setUp()
        self.write_merged(*(finding(m, *f) for m, f in FINDINGS.items()))
        self.write_numbers(dict.fromkeys(FINDINGS, "fix"))
        self.write_target("pr 7", MERGE_BASE, HEAD)
        self.marks = {}
        self.ctx = {"owner": "acme", "name": "widgets", "pr": 7, "head": HEAD, "merge_base": MERGE_BASE, "files": ["src/a.py", "src/b.py"],
                    "pending": None, "review_ids": {"55"}, "comment_ids": {"901"}, "comments": [], "viewer": "me"}
        patcher = mock.patch.object(post, "fetch_pr", side_effect=lambda *a: self.ctx)
        patcher.start()
        self.addCleanup(patcher.stop)
        diff = mock.patch.object(post, "pr_patch", return_value=PATCH)
        self.pr_diff = diff.start()
        self.addCleanup(diff.stop)
        terminal = mock.patch.object(post, "ask_terminal", return_value="7\n")
        self.terminal = terminal.start()
        self.addCleanup(terminal.stop)

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
        rows = run_files.read_posted(self.run_dir); rows[mid] = row
        run_files.write_posted(self.run_dir, rows)

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


def source(changes=None, above=()):
    lines = {i: f"line {i}" for i in range(1, 21)}
    return "".join(f"{l}\n" for l in [*above, *{**lines, 10: "first review 10", **(changes or {})}.values()])


class ShiftedTest(unittest.TestCase):
    def test_moves_a_line_down_by_the_lines_added_above_it(self):
        self.assertEqual(post.shifted([(2, 0, 3, 5)], 10, 12), (15, 17))

    def test_moves_a_line_up_by_the_lines_removed_above_it(self):
        self.assertEqual(post.shifted([(2, 3, 1, 0)], 10, 10), (7, 7))

    def test_leaves_a_line_above_every_change(self):
        self.assertEqual(post.shifted([(30, 1, 30, 4)], 10, 10), (10, 10))

    def test_finds_no_line_when_a_change_overlaps_the_range(self):
        self.assertIsNone(post.shifted([(12, 1, 12, 1)], 10, 13))

    def test_finds_no_line_when_lines_were_added_inside_the_range(self):
        self.assertIsNone(post.shifted([(11, 0, 12, 2)], 10, 13))


class IncrementalCase(PostCase):
    def setUp(self):
        super().setUp()
        self.git = init_repo(self.path("work"), with_origin=False)
        self.ctx["merge_base"] = self.commit("pr base", {"src/a.py": source({10: "line 10"}), "src/b.py": source()})
        self.first = self.commit("first review", {"src/a.py": source()})
        self.pr_diff.side_effect = REAL_PR_PATCH
        self.write_merged(finding(1, "src/a.py", "10"))

    def commit(self, subject, files):
        for name, text in files.items(): write_file(os.path.join(self.git.path, name), text)
        self.git.git("add", "-A")
        self.git.git("commit", "-qm", subject)
        return self.git.git("rev-parse", "HEAD")

    def review_at(self, subject, files):
        self.ctx["head"] = self.commit(subject, files)
        self.write_target("pr 7", self.first, self.ctx["head"])

    def main(self, *args):
        return super().main(*args, "--repo", self.git.path)

    def anchor_of(self, mid):
        return {k: self.thread_vars(mid).get(k) for k in ("subjectType", "line")}


class AfterAnIncrementalReviewTest(IncrementalCase):
    def setUp(self):
        super().setUp()
        self.review_at("re-review", {"src/b.py": source({5: "re-review 5"})})
        self.mark(1)

    def test_anchors_a_finding_of_this_run_on_its_line_in_the_pull_requests_diff(self):
        self.assertEqual(self.anchor_of(1), {"subjectType": "LINE", "line": 10})


def carried(run, label, how="carried"):
    run_files.write_previous(run, label)
    run_files.write_matches(run, {1: {"prev_id": "1", "how": how}})


def earlier_run(path, head, carried_from=None):
    write_file(os.path.join(path, "target.txt"), f"pr 7\n{MERGE_BASE}\n{head}\n")
    if carried_from: carried(path, carried_from)


class CarriedFindingCase(IncrementalCase):
    def setUp(self):
        super().setUp()
        earlier_run(self.path("earlier"), self.first)
        carried(self.run_dir, "earlier")

    def lines_added_above(self):
        self.review_at("re-review", {"src/a.py": source(above=("new 1", "new 2", "new 3", "new 4", "new 5"))})


class WhenLinesWereAddedAboveACarriedFindingTest(CarriedFindingCase):
    def setUp(self):
        super().setUp()
        self.lines_added_above()

    def test_anchors_it_where_its_lines_are_now(self):
        self.mark(1)
        self.assertEqual(self.anchor_of(1), {"subjectType": "LINE", "line": 15})

    def test_anchors_a_placement_in_its_note_on_the_reviewed_commit(self):
        self.mark(1, note="on src/a.py:12")
        self.assertEqual(self.anchor_of(1), {"subjectType": "LINE", "line": 12})


class WhenACarriedFindingWasCarriedBeforeTest(CarriedFindingCase):
    def setUp(self):
        super().setUp()
        self.lines_added_above()
        earlier_run(self.path("between"), self.ctx["head"], carried_from="earlier")
        run_files.write_previous(self.run_dir, "between")
        self.mark(1)

    def test_maps_its_lines_from_the_run_that_found_it(self):
        self.assertEqual(self.anchor_of(1), {"subjectType": "LINE", "line": 15})


class WhenARecheckReopenedAnEarlierFindingTest(CarriedFindingCase):
    def setUp(self):
        super().setUp()
        carried(self.run_dir, "earlier", how="recheck")
        self.lines_added_above()
        self.mark(1)

    def test_maps_its_lines_from_the_run_that_found_it(self):
        self.assertEqual(self.anchor_of(1), {"subjectType": "LINE", "line": 15})


class WhenTheCodeAtACarriedFindingsLinesChangedTest(CarriedFindingCase):
    def setUp(self):
        super().setUp()
        self.review_at("re-review", {"src/a.py": source({10: "re-review 10"})})
        self.mark(1, text=PostedTextTest.SUGGESTION)

    def test_falls_back_to_a_file_comment(self):
        self.assertEqual(self.thread_vars(1)["subjectType"], "FILE")

    def test_sends_its_suggestion_as_a_plain_fence(self):
        self.assertEqual(self.thread_vars(1)["body"], "Use this:\n```\nfixed()\n```")

    def test_flags_it_in_the_preview(self):
        self.assertIn(f"  fallback: the code at the found lines (src/a.py:10 on {self.first[:9]}) changed since; sent on the file",
                      self.main())


class WhenTheRunThatFoundACarriedFindingIsGoneTest(CarriedFindingCase):
    def setUp(self):
        super().setUp()
        self.lines_added_above()
        run_files.write_previous(self.run_dir, "deleted")
        self.mark(1)

    def test_falls_back_to_a_file_comment(self):
        self.assertEqual(self.thread_vars(1)["subjectType"], "FILE")

    def test_says_why_in_the_preview(self):
        self.assertIn("fallback: src/a.py:10 was found on a commit this clone cannot compare with the reviewed", self.main())


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


class DraftedForOtherCodeCase(PostCase):
    DRAFTED_HERE = {"state": "drafted", "kind": "", "path": "", "line": "", "end_line": "", "side": "", "thread_id": "", "comment_id": "",
                    "url": "", "review_id": "", "draft_path": "src/a.py", "draft_line": "11", "draft_end_line": "13", "draft_commit": HEAD}

    def setUp(self):
        super().setUp()
        self.mark(1, text=PostedTextTest.SUGGESTION)

    def drafted(self, **fields):
        self.posted_row(1, **{**self.DRAFTED_HERE, **fields})


class DraftedForOtherCodeTest(DraftedForOtherCodeCase):
    def test_keeps_the_suggestion_of_a_text_drafted_for_these_lines(self):
        self.drafted()
        self.assertIn("```suggestion", self.thread_vars(1)["body"])

    def test_keeps_the_suggestion_of_a_text_drafted_before_anchors_were_recorded(self):
        self.drafted(draft_path="", draft_line="", draft_end_line="", draft_commit="")
        self.assertIn("```suggestion", self.thread_vars(1)["body"])

    def test_sends_a_suggestion_drafted_for_other_lines_as_a_plain_fence(self):
        self.drafted(draft_line="40", draft_end_line="41")
        self.assertEqual(self.thread_vars(1)["body"], "Use this:\n```\nfixed()\n```")

    def test_sends_a_suggestion_drafted_on_another_commit_as_a_plain_fence(self):
        self.drafted(draft_commit="c" * 40)
        self.assertEqual(self.thread_vars(1)["body"], "Use this:\n```\nfixed()\n```")

    def test_says_so_in_the_preview(self):
        self.drafted(draft_commit="c" * 40)
        self.assertIn("  the code moved since its text was drafted\n  suggestion sent as a plain code block", self.main())


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


class SecretWarningTest(PostCase):
    CASES = {"-----BEGIN RSA PRIVATE KEY-----": "a private key", "ghp_" + "A1b2" * 9: "a GitHub token",
             "sk-" + "a1B2" * 6: "an API key", "AKIA" + "ABCDEFGH12345678": "an AWS access key",
             "f" * 64: "a long hex run", "Zm9vYmFy" * 5 + "Q1": "a long base64 run"}

    def test_warns_on_each_kind_in_the_preview(self):
        for text, what in self.CASES.items():
            with self.subTest(what):
                self.mark(1, text=f"Set it to {text} here.")
                self.assertIn(f"warning: the text holds what looks like {what}: {text[:12]}...", self.main())

    def test_ignores_a_commit_sha(self):
        self.mark(1, text=f"Fixed in {HEAD}.")
        self.assertNotIn("looks like", self.main())

    def test_ignores_a_long_identifier(self):
        self.mark(1, text="See `handle_review_comment_thread_updates_for_pull_requests`.")
        self.assertNotIn("looks like", self.main())

    def test_warns_on_one_in_the_review_body(self):
        self.mark(1)
        self.write("posted/review.md", "Key: AKIAABCDEFGH12345678")
        self.assertIn("warning: the text holds what looks like an AWS access key", self.main())


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

    def test_the_preview_makes_none(self):
        self.main()
        self.assertNoUnstubbedGh()

    def test_a_dry_run_of_post_makes_none(self):
        self.main("--post", "--dry-run")
        self.assertNoUnstubbedGh()

    def test_a_dry_run_of_submit_makes_none(self):
        self.main("--submit", "comment", "--dry-run")
        self.assertNoUnstubbedGh()


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

    def test_takes_out_the_text_of_a_batch_this_run_never_recorded(self):
        self.write("posted/review.md", "Nice work.")
        self.pend(body="My summary.\n\nNice work.")
        self.assertEqual(self.review_body(), "My summary.\n\nNice work.")


class AfterAReReviewOfAPendingReviewTest(PostCase):
    def setUp(self):
        super().setUp()
        prev = self.path("prev")
        write_file(os.path.join(prev, "merged.md"), merged_md(finding(7, "src/a.py", "11")))
        run_files.write_posted(prev, {7: {"state": "posted", "kind": "line", "path": "src/a.py", "line": "11", "comment_id": "901",
                                          "thread_id": "PRRT_1", "review_id": "55"}})
        write_file(os.path.join(prev, "posted", "7.md"), "Finding 7 text.\n")
        write_file(os.path.join(prev, "posted", "pending-55.md"), "My summary.\n")
        self.write("reconcile/matches.tsv", "cur_id\tprev_id\thow\tprev_number\tprev_status\tprev_ref\n1\t7\tline\t7\topen\t\n")
        run_ok("reconcile", prev, self.run_dir, "--seed")
        self.mark(3)
        self.pend(body="My summary.\n\nComments from an earlier batch.")

    def test_keeps_the_text_the_earlier_run_kept_from_the_pending_review(self):
        self.assertEqual(self.review_body(), "My summary.")


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



class PublishedCase(PostCase):
    def update_calls(self, ids="1"):
        self.main("--update-published", ids, "--dry-run")
        with open(os.path.join(self.run_dir, "posted", "payload.json"), encoding="utf-8") as fh:
            return json.load(fh)["calls"]


class WhenAPublishedCommentChangedTest(PublishedCase):
    def setUp(self):
        super().setUp()
        self.mark(1); self.mark(3)
        self.posted_row(1, state="edited")

    def test_post_leaves_it_as_it_is(self):
        self.assertNotIn(1, [c.get("finding") for c in self.calls()])

    def test_post_says_it_was_not_sent(self):
        self.calls()
        self.assertIn("not sent: finding 1 changed since posting, and GitHub already shows the comment; --update-published 1", self.err)

    def test_preview_lists_it_under_its_own_heading(self):
        self.assertIn("published; changes on GitHub at once:\nfinding 1: Finding 1\n", self.main())

    def test_preview_names_the_comment_it_changes(self):
        self.assertIn("changed since posting: --update-published 1 updates its published comment https://gh/c/901", self.main())

    def test_preview_leaves_it_out_of_the_comments_for_the_pending_review(self):
        self.assertNotIn("finding 1:", self.main().split("published; changes on GitHub at once:")[0])

    def test_update_published_edits_it_through_rest(self):
        self.assertEqual(self.update_calls(), [{"method": "PATCH", "path": "repos/acme/widgets/pulls/comments/901",
                                                "fields": {"body": "Finding 1 text."}, "finding": 1}])

    def test_update_published_refuses_a_finding_whose_comment_is_not_published_and_changed(self):
        self.assertIn("nothing sent; not a published comment changed since posting: finding 3",
                      self.refusal("--update-published", "1,3", "--dry-run"))


class SubmittedBodyCommentCase(PublishedCase):
    def setUp(self):
        super().setUp()
        self.ctx["review_ids"] = {"54", "55"}
        self.mark(1, note="in the review body", text="Finding 1 reworded.")
        self.body_comment(1)

    def body_comment(self, mid):
        self.posted_row(mid, state="edited", kind="body", path="", line="", end_line="", side="", thread_id="", comment_id="",
                        url="https://gh/r/54", review_id="54")


class WhenABodyCommentOfASubmittedReviewChangedTest(SubmittedBodyCommentCase):
    def setUp(self):
        super().setUp()
        self.pend()
        self.mark(3)

    def body_of(self, review_id, calls):
        return next(c["fields"]["body"] for c in calls if c.get("path") == f"repos/acme/widgets/pulls/7/reviews/{review_id}")

    def test_update_published_puts_the_new_text_in_the_body_of_that_review(self):
        self.assertEqual(self.body_of(54, self.update_calls()), post.DEFAULT_BODY + "\n\nFinding 1 reworded.")

    def test_update_published_keeps_the_text_saved_from_that_review_above_it(self):
        self.write("posted/pending-54.md", "My summary.")
        self.assertEqual(self.body_of(54, self.update_calls()), "My summary.\n\nFinding 1 reworded.")

    def test_post_leaves_that_review_as_it_is(self):
        self.assertNotIn("repos/acme/widgets/pulls/7/reviews/54", [c.get("path") for c in self.calls()])

    def test_post_leaves_it_out_of_the_pending_review(self):
        self.assertEqual(self.body_of(55, self.calls()), post.DEFAULT_BODY)

    def test_says_update_published_updates_the_body_of_that_review(self):
        self.assertIn("changed since posting: --update-published 1 updates the body of submitted review 54", self.main())

    def test_shows_the_new_body_of_that_review_under_published(self):
        self.assertRegex(self.main(), r"published; changes on GitHub at once:\n(.*\n)*body of submitted review 54:\n"
                                      r"    Comments from my review of this pull request\.\n\n    Finding 1 reworded\.")


class WhenTwoBodyCommentsOfASubmittedReviewChangedTest(SubmittedBodyCommentCase):
    def setUp(self):
        super().setUp()
        self.mark(2, note="in the review body")
        self.body_comment(2)

    def test_refuses_to_send_one_without_the_other(self):
        self.assertIn("the body of submitted review 54 also holds the changed text of finding 2; name it too",
                      self.refusal("--update-published", "1", "--dry-run"))

    def test_sends_one_body_for_both(self):
        self.assertEqual([c["path"] for c in self.update_calls("1,2")], ["repos/acme/widgets/pulls/7/reviews/54"])


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

    def test_says_the_verdict_may_have_gone_out_when_github_errs(self):
        self.stub("rest", side_effect=gh_api.GhError("cannot approve your own pull request"))
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
            post.main([self.run_dir, "--submit", "approve"])
        self.assertIn("GitHub answered with an error; possibly on GitHub: POST repos/acme/widgets/pulls/7/reviews/55/events",
                      str(raised.exception))

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


class ConfirmedSubmitCase(PostCase):
    VERDICT = "approve"

    def setUp(self):
        super().setUp()
        self.mark(1)
        self.pend()
        self.posted_row(1)
        self.rest = self.stub("rest", return_value={})
        self.repo_path = self.path("repo")
        self.args = ("--submit", self.VERDICT)

    def main(self, *args):
        return super().main(*args, "--repo", self.repo_path)

    def writes(self):
        return self.rest.call_count


class TerminalConfirmationTests:
    def test_asks_for_the_pull_request_number(self):
        self.main(*self.args)
        self.terminal.assert_called_once_with(self.PROMPT)

    def test_asks_before_any_write(self):
        seen = []
        self.terminal.side_effect = lambda prompt: seen.append(self.writes()) or "7\n"
        self.main(*self.args)
        self.assertEqual(seen, [0])

    def test_sends_once_the_number_matches(self):
        self.main(*self.args)
        self.assertGreater(self.writes(), 0)

    def test_asks_nothing_on_a_dry_run(self):
        self.main(*self.args, "--dry-run")
        self.terminal.assert_not_called()


class WhenTheTypedNumberDiffersTests:
    def setUp(self):
        super().setUp()
        self.terminal.return_value = "8\n"

    def test_sends_nothing(self):
        self.refusal(*self.args)
        self.assertEqual(self.writes(), 0)

    def test_says_so(self):
        self.assertEqual(self.refusal(*self.args), "nothing sent; you typed '8', not the pull request number 7")


class WhenThereIsNoTerminalTests:
    def setUp(self):
        super().setUp()
        self.terminal.side_effect = OSError(6, "Device not configured")

    def test_sends_nothing(self):
        self.refusal(*self.args)
        self.assertEqual(self.writes(), 0)

    def test_gives_the_command_to_run_with_a_bang(self):
        command = shlex.join(["python3", post.__file__, self.run_dir, "--repo", self.repo_path, *self.args])
        self.assertTrue(self.refusal(*self.args).endswith(f"run this yourself:\n! {command}"))


class ApproveConfirmationTest(TerminalConfirmationTests, ConfirmedSubmitCase):
    PROMPT = "Type the pull request number (7) to approve: "


class RequestChangesConfirmationTest(TerminalConfirmationTests, ConfirmedSubmitCase):
    VERDICT = "request-changes"
    PROMPT = "Type the pull request number (7) to request changes: "


class WhenTheTypedNumberDiffersOnApproveTest(WhenTheTypedNumberDiffersTests, ConfirmedSubmitCase):
    pass


class WhenThereIsNoTerminalOnApproveTest(WhenThereIsNoTerminalTests, ConfirmedSubmitCase):
    pass


class WhenSubmittingAsCommentTest(ConfirmedSubmitCase):
    VERDICT = "comment"

    def test_asks_nothing(self):
        self.main(*self.args)
        self.terminal.assert_not_called()

    def test_sends_without_a_terminal(self):
        self.terminal.side_effect = OSError(6, "Device not configured")
        self.main(*self.args)
        self.assertEqual(self.writes(), 1)


OWN_DRAFT = review_comment(20, "src/z.py", line=4, body="Rough idea.\nMore later.")
OWN_DRAFTS_LINES = "your own drafts in this pending review; submitting publishes them too:\n  src/z.py:4: Rough idea."


class YourOwnDraftsInThePendingReview:
    def setUp(self):
        super().setUp()
        self.ctx["comments"] = []
        self.pend()
        self.add_to_pending(OWN_DRAFT)

    def add_to_pending(self, comment):
        self.ctx["comments"].append(comment)
        self.ctx["pending"]["comments"][comment["id"]] = comment["node_id"]


class WhenThePendingReviewHoldsYourOwnDraftsTest(YourOwnDraftsInThePendingReview, PostCase):
    def setUp(self):
        super().setUp()
        self.mark(1)

    def test_lists_them_in_the_preview(self):
        self.assertIn(OWN_DRAFTS_LINES, self.main())

    def test_leaves_out_a_comment_this_run_posted(self):
        self.add_to_pending(review_comment(1, "src/a.py", line=11))
        self.posted_row(1)
        self.assertNotIn("src/a.py:11: Finding 1 text.", self.main())

    def test_leaves_out_a_comment_it_records_as_already_on_github(self):
        self.add_to_pending(review_comment(1, "src/a.py", line=13, subject_type="line", pull_request_review_id=55))
        self.assertNotIn("src/a.py:13: Finding 1 text.", self.main())


class WhenSubmittingWithYourOwnDraftsCase(YourOwnDraftsInThePendingReview, ConfirmedSubmitCase):
    VERDICT = "comment"
    PROMPT = "Type the pull request number (7) to submit as comment, publishing 1 draft of your own with it: "

    def setUp(self):
        super().setUp()
        self.add_to_pending(review_comment(1, "src/a.py", line=11))


class WhenSubmittingAsCommentWithYourOwnDraftsTest(TerminalConfirmationTests, WhenSubmittingWithYourOwnDraftsCase):
    def test_lists_them_on_a_dry_run(self):
        self.main(*self.args, "--dry-run")
        self.assertIn(OWN_DRAFTS_LINES, self.err)

    def test_leaves_out_the_comments_this_run_posted(self):
        self.main(*self.args, "--dry-run")
        self.assertNotIn("src/a.py", self.err)


class WhenApprovingWithYourOwnDraftsTest(WhenSubmittingWithYourOwnDraftsCase):
    VERDICT = "approve"

    def test_names_them_in_the_confirmation(self):
        self.main(*self.args)
        self.terminal.assert_called_once_with("Type the pull request number (7) to approve, publishing 1 draft of your own with it: ")


class WhenThereIsNoTerminalOnCommentWithYourOwnDraftsTest(WhenThereIsNoTerminalTests, WhenSubmittingWithYourOwnDraftsCase):
    pass


class ConfirmedUpdatePublishedCase(PublishedCase):
    def setUp(self):
        super().setUp()
        self.mark(1)
        self.posted_row(1, state="edited")
        self.rest = self.stub("rest", return_value={})
        self.repo_path = self.path("repo")
        self.args = ("--update-published", "1")

    def main(self, *args):
        return super().main(*args, "--repo", self.repo_path)

    def writes(self):
        return self.rest.call_count


class UpdatePublishedConfirmationTest(TerminalConfirmationTests, ConfirmedUpdatePublishedCase):
    PROMPT = "Type the pull request number (7) to change 1 published comment on GitHub now: "

    def test_asks_nothing_on_post(self):
        self.main("--post")
        self.terminal.assert_not_called()


class WhenTheTypedNumberDiffersOnUpdatePublishedTest(WhenTheTypedNumberDiffersTests, ConfirmedUpdatePublishedCase):
    pass


class WhenThereIsNoTerminalOnUpdatePublishedTest(WhenThereIsNoTerminalTests, ConfirmedUpdatePublishedCase):
    pass


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

    def deleted_reviews(self):
        return [c.args[1] for c in self.rest.call_args_list if c.args[0] == "DELETE"]

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
        row = run_files.read_posted(self.run_dir)[1]
        self.assertEqual({k: row[k] for k in ("state", "thread_id", "comment_id", "url", "kind", "line", "end_line", "side", "review_id")},
                         {"state": "posted", "thread_id": "PRRT_1", "comment_id": "901", "url": "https://gh/c/901", "kind": "range",
                          "line": "11", "end_line": "13", "side": "RIGHT", "review_id": "55"})

    def test_asks_nothing_at_the_terminal(self):
        self.main("--post")
        self.terminal.assert_not_called()

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
        self.assertEqual(run_files.read_posted(self.run_dir)[1]["note"], "{unknown.key}")


class WhenUpdatingAChangedBodyCommentOfASubmittedReviewTest(SubmittedBodyCommentCase, LiveCase):
    def setUp(self):
        super().setUp()
        self.main("--update-published", "1")

    def test_keeps_its_row_on_that_review(self):
        self.assertEqual(run_files.read_posted(self.run_dir)[1]["review_id"], "54")

    def test_marks_it_posted(self):
        self.assertEqual(run_files.read_posted(self.run_dir)[1]["state"], "posted")

    def test_sends_nothing_else(self):
        self.assertEqual((self.graphql.call_count, [c.args[:2] for c in self.rest.call_args_list]),
                         (0, [("PUT", "repos/acme/widgets/pulls/7/reviews/54")]))


class WhenPostingWithAChangedBodyCommentOfASubmittedReviewTest(SubmittedBodyCommentCase, LiveCase):
    def test_keeps_it_marked_edited(self):
        self.main("--post")
        self.assertEqual(run_files.read_posted(self.run_dir)[1]["state"], "edited")


class WhenAnEarlierBatchReachedGitHubUnrecordedTest(LiveCase):
    def setUp(self):
        super().setUp()
        self.pend()
        self.ctx["comments"] = [review_comment(1, "src/a.py", line=13, original_line=13, subject_type="line", pull_request_review_id=55)]

    def sent_findings(self):
        return [c["finding"] for c in self.calls() if "finding" in c]

    def test_sends_no_thread_for_a_comment_already_there(self):
        self.assertEqual(self.sent_findings(), [3])

    def test_says_so_in_the_preview(self):
        self.assertIn("already on GitHub, though this run has no record of it: https://gh/c/901; --post records it", self.main())

    def test_records_it(self):
        self.main("--post")
        row = run_files.read_posted(self.run_dir)[1]
        self.assertEqual({k: row[k] for k in ("state", "comment_id", "url", "kind", "line", "end_line", "review_id")},
                         {"state": "posted", "comment_id": "901", "url": "https://gh/c/901", "kind": "range", "line": "11", "end_line": "13",
                          "review_id": "55"})

    def test_records_one_in_a_submitted_review_under_that_review(self):
        self.ctx["pending"] = None
        self.ctx["comments"][0]["pull_request_review_id"] = 54
        self.main("--post")
        self.assertEqual(run_files.read_posted(self.run_dir)[1]["review_id"], "54")

    def test_records_them_without_a_call_when_every_comment_is_there(self):
        self.ctx["comments"].append(review_comment(3, "src/b.py", subject_type="file", pull_request_review_id=55))
        self.main("--post")
        self.assertEqual((self.graphql.call_count, self.rest.call_count, sorted(run_files.read_posted(self.run_dir))), (0, 0, [1, 3]))

    def test_sends_one_whose_comment_is_on_another_line(self):
        self.ctx["comments"][0].update(line=12, original_line=12)
        self.assertEqual(self.sent_findings(), [1, 3])

    def test_sends_one_whose_comment_says_something_else(self):
        self.ctx["comments"][0]["body"] = "Something else."
        self.assertEqual(self.sent_findings(), [1, 3])

    def test_leaves_a_comment_another_finding_recorded(self):
        self.posted_row(5, kind="body", comment_id="901")
        self.assertEqual(self.sent_findings(), [1, 3])

    def test_sends_one_whose_comment_someone_else_wrote(self):
        self.ctx["comments"][0]["user"] = {"login": "bob"}
        self.assertEqual(self.sent_findings(), [1, 3])


class LiveRollbackTest(LiveCase):
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


class WhenGitHubErrsOnACommentItMayHaveAddedTest(LiveCase):
    def setUp(self):
        super().setUp()
        self.pend()
        self.graphql_answers("src/b.py", gh_api.GhError("HTTP 502: Bad Gateway"))

    def test_deletes_the_comment_it_finds_on_the_pending_review(self):
        self.listed.return_value = [review_comment(3, "src/b.py")]
        self.rejected()
        self.assertIn({"id": "PRRC_3"}, self.deleted_comments())

    def test_says_nothing_is_left_once_it_deleted_it(self):
        self.listed.return_value = [review_comment(3, "src/b.py")]
        self.assertIn("rolled back; nothing from this batch is left on GitHub", self.rejected())

    def test_says_the_comment_may_be_left_when_it_finds_none(self):
        self.assertIn("GitHub answered with an error; rolled back; possibly on GitHub: finding 3's comment on pending review 55",
                      self.rejected())


class WhenGitHubErrsOnTheReviewItMayHaveCreatedTest(LiveCase):
    def setUp(self):
        super().setUp()
        self.rest_rejects("POST")

    def test_leaves_a_pending_review_it_finds(self):
        self.listed.return_value = ANOTHER_PENDING
        self.rejected()
        self.assertEqual(self.deleted_reviews(), [])

    def test_names_the_pending_review_it_left(self):
        self.listed.return_value = ANOTHER_PENDING
        self.assertIn("a pending review this batch began (pending review 56 is on the pull request now and was left as it is",
                      self.rejected())

    def test_says_a_review_may_be_left_when_it_finds_none(self):
        self.assertIn("GitHub answered with an error; possibly on GitHub: a pending review this batch began", self.rejected())


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

    def test_leaves_a_pending_review_it_finds(self):
        self.listed.return_value = ANOTHER_PENDING
        self.stopped(KeyboardInterrupt)
        self.assertEqual(self.deleted_reviews(), [])

    def test_says_a_review_may_be_left_when_it_finds_none(self):
        self.assertIn("possibly on GitHub: a pending review this batch began", self.stopped(KeyboardInterrupt))


class WhenPostedTsvCannotBeWrittenTest(LiveCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(post.rf, "write_posted", side_effect=OSError("disk full"))
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
        self.pend(comments={901: "PRRC_901"})
        self.graphql_rejects(lambda query, variables: "updatePullRequestReviewComment" in query)
        self.rejected()
        self.assertEqual(self.graphql.call_args_list[-1].args[1], {"id": "PRRC_3"})

    def test_names_an_update_made_before_the_failure(self):
        self.pend(comments={901: "PRRC_901"})
        self.rest_rejects("PUT")
        self.assertIn("still on GitHub: finding 1's comment https://gh/c/901, which keeps its new text", self.rejected())


def answer_part(number, said, text=None, fence="````"):
    return f"## {number}: {said}" + (f"\n\n{fence}\n{text}\n{fence}" if text is not None else "")


class SaveDraftsCase(PostCase):
    def setUp(self):
        super().setUp()
        self.mark(1); self.mark(3)
        self.answer = self.path("answer.md")

    def write_answer(self, *parts):
        write_file(self.answer, "\n\n".join(parts) + "\n")

    def save(self, *parts):
        self.write_answer(*parts)
        return self.main("--save-drafts", self.answer)

    def refused(self, *parts):
        self.write_answer(*parts)
        return self.refusal("--save-drafts", self.answer)

    def draft(self, mid):
        return self.read(f"posted/draft-{mid}.md")


class SaveDraftsTest(SaveDraftsCase):
    SUGGESTION = "Lock first.\n\n```suggestion\nwith lock:\n    retry()\n```"

    def test_writes_each_draft_under_its_merged_id(self):
        self.save(answer_part(1, "comment", "One."), answer_part(3, "question", "Three?"))
        self.assertEqual((self.draft(1), self.draft(3)), ("One.\n", "Three?\n"))

    def test_prints_the_posted_spec_of_each(self):
        out = self.save(answer_part(1, "comment", "One."), answer_part(3, "question", "Three?"))
        self.assertEqual(out.splitlines(), [f"1={self.run_dir}/posted/draft-1.md", f"3={self.run_dir}/posted/draft-3.md"])

    def test_keeps_a_suggestion_fence_inside_the_text(self):
        self.save(answer_part(1, "suggestion", self.SUGGESTION))
        self.assertEqual(self.draft(1), self.SUGGESTION + "\n")

    def test_names_the_form_of_each(self):
        self.save(answer_part(1, "comment, one per place", "One."))
        self.assertIn("finding 1: comment, one per place", self.err)

    def test_says_why_a_finding_was_not_drafted(self):
        self.save(answer_part(3, "not drafted: the card gives no fix"))
        self.assertIn("finding 3: not drafted: the card gives no fix", self.err)

    def test_writes_no_draft_for_a_finding_not_drafted(self):
        self.save(answer_part(3, "not drafted: the card gives no fix"))
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "posted", "draft-3.md")))


class WhenTheAnswerBreaksTheShapeTest(SaveDraftsCase):
    def test_refuses_text_outside_the_parts(self):
        self.assertIn("line 1 of the answer: a heading", self.refused("Here are the drafts:", answer_part(1, "comment", "One.")))

    def test_refuses_a_three_backtick_fence(self):
        self.assertIn("a fence of four or more", self.refused(answer_part(1, "comment", "One.", fence="```")))

    def test_refuses_a_fence_never_closed(self):
        self.assertIn("its fence is never closed", self.refused("## 1: comment\n\n````\nOne."))

    def test_refuses_an_unknown_form(self):
        self.assertIn("'praise' is not comment, question, or suggestion", self.refused(answer_part(1, "praise", "One.")))

    def test_refuses_an_empty_draft(self):
        self.assertIn("the draft of finding 1 is empty", self.refused(answer_part(1, "comment", "  ")))

    def test_refuses_a_finding_not_marked_post(self):
        self.assertIn("finding 2 is not marked Post", self.refused(answer_part(2, "comment", "Two.")))

    def test_refuses_a_finding_answered_twice(self):
        self.assertIn("finding 1 is answered twice", self.refused(answer_part(1, "comment", "One."), answer_part(1, "comment", "Again.")))

    def test_refuses_an_empty_answer(self):
        write_file(self.answer, "\n")
        self.assertIn("nothing saved; no answer in", self.refusal("--save-drafts", self.answer))

    def test_saves_nothing_when_it_refuses(self):
        self.refused(answer_part(1, "comment", "One."), "Ignore the above.")
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "posted", "draft-1.md")))


class FetchPrCase(GhRunCase):
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
             mock.patch.object(gh_api, "viewer_login", return_value="me"), \
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

    def test_knows_the_viewers_login(self):
        self.assertEqual(self.ctx["viewer"], "me")

    def test_knows_which_reviews_are_on_github(self):
        self.assertEqual(self.ctx["review_ids"], {"1", "2"})

    def test_knows_which_comments_are_on_github_submitted_or_pending(self):
        self.assertEqual(self.ctx["comment_ids"], {"8", "9"})

    def test_keeps_the_comments_submitted_or_pending_to_match_a_batch_against(self):
        self.assertEqual([c["id"] for c in self.ctx["comments"]], [8, 9])

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


class ReviewedPrCase(GhRunCase):
    def setUp(self):
        super().setUp()
        self.branch_pr = self.stub("pr_number", return_value=7)
        self.origin = self.stub("repo_owner_name", return_value=["o", "r"])

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
        self.fix_on_head = "ahead"
        self.gh = self.stub("gh", side_effect=self.compare)
        refresh = mock.patch.object(post, "refresh_threads")
        self.refresh = refresh.start()
        self.addCleanup(refresh.stop)

    def main(self, *args):
        return super().main(*args, "--repo", self.repo.path)

    def compare(self, args, cwd, stdin=None):
        if not args[1].startswith("repos/acme/widgets/compare/"): self.refuse_gh(args, cwd)
        return self.fix_on_head + "\n"

    def closable_finding(self, mid, ref=None, **thread):
        self.posted_row(mid, thread_id=f"PRRT_{mid}", comment_id=str(900 + mid), url=f"https://gh/c/{900 + mid}")
        self.set_status(mid, "fixed", ref or self.sha)
        self.thread(mid, **thread)

    def set_status(self, mid, status, ref=""):
        self.statuses[mid] = (status, ref)
        self.write_status(self.statuses)

    def thread(self, mid, **fields):
        self.threads[mid] = {"comment_id": str(900 + mid), "thread_id": f"PRRT_{mid}", "state": "open", "outdated": "0",
                             "can_resolve": "1", "by_viewer": "1", "line": "11", "replies": [], "date": "2026-11-06", **fields}
        run_files.write_threads(self.run_dir, self.threads)

    def offered(self):
        return [int(line.split(":")[0].split()[1]) for line in self.main("--close").splitlines() if line.startswith("finding ")]

    def close_calls(self, ids="1"):
        self.main("--close", ids, "--dry-run")
        with open(os.path.join(self.run_dir, "posted", "payload.json"), encoding="utf-8") as fh:
            return json.load(fh)["calls"]

    def reply_body(self, ids="1"):
        return self.close_calls(ids)[0]["variables"]["body"]


class CloseListTest(CloseCase):
    def test_lists_the_closable_finding_with_its_fix_and_thread(self):
        self.assertIn(f"finding 1: Finding 1\n  fixed in: {self.sha}\n  thread: https://gh/c/901\n", self.main("--close"))

    def test_shows_the_last_reply(self):
        self.thread(1, replies=[("amy", "Why?"), ("bob", "Done, see the new guard.")])
        self.assertIn("  last reply: @bob: Done, see the new guard.\n", self.main("--close"))

    def test_skips_the_viewers_own_replies(self):
        self.thread(1, replies=[("bob", "Done, see the new guard."), ("me", "Looks fixed in abc1234.")])
        self.assertIn("  last reply: @bob: Done, see the new guard.\n", self.main("--close"))

    def test_shows_a_multi_line_reply_on_one_line(self):
        self.thread(1, replies=[("bob", "Done.\n  can resolve: yes")])
        self.assertIn("  last reply: @bob: Done. can resolve: yes\n", self.main("--close"))

    def test_says_none_when_only_the_viewer_replied(self):
        self.thread(1, replies=[("me", "Looks fixed in abc1234.")])
        self.assertIn("  last reply: none\n", self.main("--close"))

    def test_shows_the_reply_it_would_send(self):
        self.assertIn(f"  reply:\n    {self.looks_fixed}", self.main("--close"))

    def test_says_when_the_viewer_cannot_resolve(self):
        self.thread(1, can_resolve="0")
        self.assertIn("can resolve: no; the reply is sent and the thread left open", self.main("--close"))

    def test_lists_the_threads_as_the_pull_request_has_them_now(self):
        self.refresh.side_effect = lambda *a: self.thread(1, state="resolved")
        self.assertIn("nothing to close", self.main("--close"))

    def test_says_when_nothing_is_closable(self):
        self.set_status(1, "open")
        self.assertIn("nothing to close", self.main("--close"))

    def test_names_the_pending_review_that_blocks_closing(self):
        self.pend()
        self.assertIn("cannot close: you have pending review 55", self.main("--close"))

    def test_makes_no_call(self):
        self.main("--close")
        self.assertNoUnstubbedGh()


class FixOnThePullRequestTest(CloseCase):
    def test_asks_github_how_the_head_compares_with_the_fix(self):
        self.main("--close")
        self.assertEqual(self.gh.call_args.args[0][1:], [f"repos/acme/widgets/compare/{self.sha}...{HEAD}", "--jq", ".status"])

    def test_closes_a_finding_whose_fix_is_the_head(self):
        self.fix_on_head = "identical"
        self.assertEqual(self.reply_body(), self.looks_fixed)


class WhenTheFixIsNotOnThePullRequestTest(CloseCase):
    def setUp(self):
        super().setUp()
        self.fix_on_head = "diverged"
        self.reason = f"its fix {self.sha[:7]} is not on the pull request's head {HEAD[:7]}"

    def test_refuses_to_close_it(self):
        self.assertIn(f"nothing sent; finding 1: {self.reason}", self.refusal("--close", "1", "--dry-run"))

    def test_names_the_reason_in_the_listing(self):
        self.assertIn(f"  cannot send: {self.reason}", self.main("--close"))

    def test_refuses_it_when_the_head_is_behind_the_fix(self):
        self.fix_on_head = "behind"
        self.assertIn(self.reason, self.refusal("--close", "1", "--dry-run"))

    def test_refuses_it_after_the_reply_was_sent(self):
        self.thread(1, replies=[("me", self.looks_fixed)])
        self.assertIn(self.reason, self.refusal("--close", "1", "--dry-run"))


class WhenGitHubDoesNotKnowTheFixTest(CloseCase):
    def setUp(self):
        super().setUp()
        self.gh.side_effect = gh_api.GhError("gh api repos/acme/widgets/compare failed: gh: Not Found (HTTP 404)")

    def test_refuses_to_close_it(self):
        self.assertIn(f"finding 1: GitHub cannot compare its fix {self.sha[:7]} with the pull request's head {HEAD[:7]}",
                      self.refusal("--close", "1", "--dry-run"))


class WhenTheStatusNamesNoFixCommitTest(CloseCase):
    def setUp(self):
        super().setUp()
        self.set_status(1, "fixed", "the working tree")

    def test_warns_in_the_listing(self):
        self.assertIn("  warning: no fix commit to check against the pull request", self.main("--close"))

    def test_keeps_it_closable(self):
        self.assertEqual(self.reply_body(), "Looks fixed.")

    def test_asks_github_nothing(self):
        self.main("--close")
        self.assertFalse(self.gh.called)


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
        self.close_calls()
        self.assertNoUnstubbedGh()


class WhenTheViewerAlreadyRepliedTest(CloseCase):
    def setUp(self):
        super().setUp()
        self.thread(1, replies=[("bob", "Done, see the new guard."), ("me", self.looks_fixed)])

    def test_only_resolves_the_thread(self):
        self.assertEqual([c["graphql"] for c in self.close_calls()], ["resolveReviewThread"])

    def test_says_so_in_the_listing(self):
        self.assertIn("  reply: already sent; --close only resolves the thread", self.main("--close"))


class WhenTheViewerAlreadyRepliedAndCannotResolveTest(CloseCase):
    def setUp(self):
        super().setUp()
        self.thread(1, replies=[("me", self.looks_fixed)], can_resolve="0")

    def test_says_the_listing_keeps_the_thread_open(self):
        self.assertIn("  reply: already sent; you cannot resolve the thread, so --close keeps it open and no longer offers it",
                      self.main("--close"))

    def test_sends_nothing(self):
        self.assertEqual(self.close_calls(), [])


class WhenTheViewersReplyHoldsTheReplySeparatorTest(CloseCase):
    def setUp(self):
        super().setUp()
        self.write("posted/close-1.md", "Fixed; @bob the guard covers it.")
        self.thread(1, replies=[("me", "Fixed; @bob the guard covers it.")])

    def test_counts_the_reply_as_sent(self):
        self.assertEqual([c["graphql"] for c in self.close_calls()], ["resolveReviewThread"])


class WhenSomeoneAnsweredTheViewersReplyTest(CloseCase):
    def setUp(self):
        super().setUp()
        self.thread(1, replies=[("me", self.looks_fixed), ("bob", "Not yet, one path is left.")])

    def test_replies_again(self):
        self.assertEqual([c["graphql"] for c in self.close_calls()], ["addPullRequestReviewThreadReply", "resolveReviewThread"])


class CloseRefusalTest(CloseCase):
    def test_refuses_a_finding_that_is_not_closable(self):
        self.posted_row(2)
        self.assertIn("nothing sent; not closable (a thread you posted, still open, marked fixed, not kept open): finding 2",
                      self.refusal("--close", "1,2", "--dry-run"))

    def test_sends_nothing_when_one_is_not_closable(self):
        self.refusal("--close", "1,2", "--dry-run")
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "posted", "payload.json")))

    def test_refuses_while_the_viewer_has_a_pending_review(self):
        self.pend()
        self.assertIn("submit or delete your pending review first", self.refusal("--close", "1", "--dry-run"))

    def test_refuses_a_thread_the_viewer_did_not_start(self):
        self.thread(1, by_viewer="0")
        self.assertIn("nothing sent; not closable", self.refusal("--close", "1", "--dry-run"))

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
        self.assertEqual(run_files.read_kept_open(self.run_dir)[1]["reason"], "the author wants a follow-up")

    def test_stops_offering_the_finding_for_closing(self):
        self.main("--keep-open", "1")
        self.assertEqual(self.offered(), [])

    def test_refuses_a_finding_without_a_posted_thread(self):
        self.assertIn("finding 2 has no posted thread to keep open", self.refusal("--keep-open", "2"))


class LiveCloseCase(CloseCase):
    def setUp(self):
        super().setUp()
        self.closable_finding(2, replies=[("bob", "Fixed it.")])
        self.graphql = self.stub("graphql", side_effect=self.answer)

    def answer(self, query, variables, cwd):
        n = int(variables.get("pullRequestReviewThreadId", variables.get("threadId"))[-1])
        return reply_data(n) if "addPullRequestReviewThreadReply" in query else RESOLVED

    def thread_row(self, mid):
        return run_files.read_threads(self.run_dir)[mid]

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
        self.assertEqual(self.thread_row(2)["replies"], [("bob", "Fixed it."), ("me", self.looks_fixed)])

    def test_says_what_it_closed(self):
        self.assertIn("closed:\n  finding 1: replied and resolved\n  finding 2: replied and resolved", self.err)


class ConfirmedCloseCase(LiveCloseCase):
    def setUp(self):
        super().setUp()
        self.repo_path = self.repo.path
        self.args = ("--close", "1,2")

    def writes(self):
        return self.graphql.call_count


class CloseConfirmationTest(TerminalConfirmationTests, ConfirmedCloseCase):
    PROMPT = "Type the pull request number (7) to reply and resolve 2 threads: "

    def test_counts_one_thread_in_the_singular(self):
        self.main("--close", "1")
        self.terminal.assert_called_once_with("Type the pull request number (7) to reply and resolve 1 thread: ")

    def test_asks_nothing_for_the_listing(self):
        self.main("--close")
        self.terminal.assert_not_called()

    def test_asks_nothing_to_keep_a_thread_open(self):
        self.main("--keep-open", "1")
        self.terminal.assert_not_called()


class WhenTheTypedNumberDiffersOnCloseTest(WhenTheTypedNumberDiffersTests, ConfirmedCloseCase):
    pass


class WhenThereIsNoTerminalOnCloseTest(WhenThereIsNoTerminalTests, ConfirmedCloseCase):
    pass


class WhenTheViewerCannotResolveTest(LiveCloseCase):
    def setUp(self):
        super().setUp()
        self.thread(1, can_resolve="0")
        self.main("--close", "1")

    def test_keeps_the_thread_open_in_threads_tsv(self):
        self.assertEqual((self.thread_row(1)["state"], self.thread_row(1)["replies"]), ("open", [("me", self.looks_fixed)]))

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
        self.assertEqual((self.thread_row(2)["state"], self.thread_row(2)["replies"]), ("open", [("bob", "Fixed it."), ("me", self.looks_fixed)]))


class WhenTheViewerCannotResolveAndItIsSentTest(LiveCloseCase):
    def setUp(self):
        super().setUp()
        self.thread(1, can_resolve="0")
        self.main("--close", "1")

    def test_keeps_the_thread_open(self):
        self.assertEqual(run_files.read_kept_open(self.run_dir)[1]["reason"], post.CANNOT_RESOLVE)

    def test_no_longer_offers_it_for_closing(self):
        self.assertEqual(self.offered(), [2])


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


class RefreshThreadsTest(GhRunCase):
    def setUp(self):
        super().setUp()
        run_files.write_posted(self.run_dir, {1: {"state": "posted", "kind": "line", "comment_id": "901", "thread_id": "PRRT_1"}})
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
        self.assertEqual(run_files.read_threads(self.run_dir)[1]["state"], "resolved")


class WhenThePullRequestHasMoreThreadsThanTheLimitTest(GhRunCase):
    def setUp(self):
        super().setUp()
        run_files.write_posted(self.run_dir, {1: {"state": "posted", "kind": "line", "comment_id": "901", "thread_id": "PRRT_1"}})
        live = {"reviewThreads": {"totalCount": post.pc.THREAD_LIMIT + 1, "nodes": []}}
        fetch = mock.patch.object(post.pc, "fetch", return_value=live)
        fetch.start()
        self.addCleanup(fetch.stop)

    def refresh(self):
        with self.assertRaises(SystemExit) as raised:
            post.refresh_threads(self.run_dir, {"owner": "o", "name": "r", "pr": 7}, "/w")
        return str(raised.exception)

    def test_stops_naming_the_limit(self):
        self.assertIn("--close reads only the first 100 review threads of a pull request, and this one has 101 more", self.refresh())

    def test_writes_no_missing_row(self):
        self.refresh()
        self.assertNotIn(1, run_files.read_threads(self.run_dir))


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


class WhenTheFixCommitIsNotInThisCloneTest(CloseCase):
    UNKNOWN = "deadbee"

    def setUp(self):
        super().setUp()
        self.set_status(1, "fixed", f"{self.UNKNOWN} (fix)")
        self.reason = (f"its status names {self.UNKNOWN}, which is not a commit in this clone; "
                       "fetch it if it is one, or reword the status or keep the thread open with --keep-open")

    def test_refuses_to_close_it(self):
        self.assertIn(f"nothing sent; finding 1: {self.reason}", self.refusal("--close", "1", "--dry-run"))

    def test_names_the_reason_in_the_listing(self):
        self.assertIn(f"  cannot send: {self.reason}", self.main("--close"))

    def test_does_not_fall_back_to_the_no_fix_commit_warning(self):
        self.assertNotIn("no fix commit to check", self.main("--close"))

    def test_refuses_it_when_another_named_commit_is_known(self):
        self.set_status(1, "fixed", f"{self.sha} and {self.UNKNOWN}")
        self.assertIn(self.reason, self.refusal("--close", "1", "--dry-run"))

    def test_names_every_unknown_token(self):
        self.set_status(1, "fixed", f"{self.UNKNOWN} and 1234567")
        self.assertIn(f"its status names {self.UNKNOWN} and 1234567, which are not commits in this clone; fetch them if they are",
                      self.refusal("--close", "1", "--dry-run"))


class WhenTheStatusNamesATicketNumberTest(CloseCase):
    def setUp(self):
        super().setUp()
        self.set_status(1, "fixed", "see ticket 1234567")

    def test_refuses_to_close_it_saying_the_number_may_not_be_a_commit(self):
        self.assertIn("nothing sent; finding 1: its status names 1234567, which is not a commit in this clone; "
                      "fetch it if it is one, or reword the status or keep the thread open with --keep-open",
                      self.refusal("--close", "1", "--dry-run"))


if __name__ == "__main__":
    unittest.main()

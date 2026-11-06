import json
import subprocess
import sys
import unittest
from unittest import mock

from helpers import SCRIPTS

sys.path.insert(0, SCRIPTS)
import gh_api


def completed(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class GhApiTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(gh_api.subprocess, "run")
        self.run = patcher.start()
        self.addCleanup(patcher.stop)
        which = mock.patch.object(gh_api.shutil, "which", return_value="/usr/bin/gh")
        self.which = which.start()
        self.addCleanup(which.stop)

    def test_gh_returns_stdout(self):
        self.run.return_value = completed("out")
        self.assertEqual(gh_api.gh(["pr", "view"], "/w"), "out")
        self.assertEqual(self.run.call_args.args[0], ["gh", "pr", "view"])
        self.assertEqual(self.run.call_args.kwargs["cwd"], "/w")

    def test_gh_exits_with_stderr_on_failure(self):
        self.run.return_value = completed(returncode=1, stderr="boom")
        with self.assertRaises(SystemExit) as raised:
            gh_api.gh(["pr", "view"], "/w")
        self.assertIn("boom", str(raised.exception))

    def test_gh_failure_carries_what_github_answered(self):
        self.run.return_value = completed('{"message":"Unprocessable Entity","errors":["commit_id is not part of the pull request"]}',
                                          returncode=1, stderr="gh: Unprocessable Entity (HTTP 422)")
        with self.assertRaises(gh_api.GhError) as raised:
            gh_api.gh(["api", "x"], "/w")
        self.assertIn("commit_id is not part of the pull request", str(raised.exception))

    def test_gh_says_when_gh_is_not_installed(self):
        self.which.return_value = None
        with self.assertRaises(gh_api.GhError) as raised:
            gh_api.gh(["pr", "view"], "/w")
        self.assertIn("gh is not installed", str(raised.exception))

    def test_graphql_sends_query_and_variables_as_json_on_stdin(self):
        self.run.return_value = completed(json.dumps({"data": 1}))
        self.assertEqual(gh_api.graphql("query{x}", {"o": "a", "n": 3}, "/w"), {"data": 1})
        self.assertEqual(
            (self.run.call_args.args[0], json.loads(self.run.call_args.kwargs["input"])),
            (["gh", "api", "graphql", "--input", "-"], {"query": "query{x}", "variables": {"o": "a", "n": 3}}),
        )

    def test_graphql_sends_a_value_starting_with_at_as_text(self):
        self.run.return_value = completed("{}")
        gh_api.graphql("q", {"body": "@etc/passwd"}, "/w")
        self.assertEqual(json.loads(self.run.call_args.kwargs["input"])["variables"]["body"], "@etc/passwd")

    def test_rest_sends_fields_as_json_on_stdin(self):
        self.run.return_value = completed(json.dumps({"id": 5}))
        self.assertEqual(gh_api.rest("POST", "repos/o/r/pulls/1/reviews", {"body": "b"}, "/w"), {"id": 5})
        self.assertEqual(
            (self.run.call_args.args[0], json.loads(self.run.call_args.kwargs["input"])),
            (["gh", "api", "-X", "POST", "repos/o/r/pulls/1/reviews", "--input", "-"], {"body": "b"}),
        )

    def test_rest_without_fields_sends_no_body(self):
        self.run.return_value = completed("")
        self.assertIsNone(gh_api.rest("DELETE", "repos/o/r/pulls/1/reviews/2", {}, "/w"))
        self.assertEqual(self.run.call_args.args[0], ["gh", "api", "-X", "DELETE", "repos/o/r/pulls/1/reviews/2"])

    def test_rest_list_reads_one_item_per_line(self):
        self.run.return_value = completed('{"id": 1}\n{"id": 2}\n')
        self.assertEqual(gh_api.rest_list("repos/o/r/pulls/1/files", "/w"), [{"id": 1}, {"id": 2}])

    def test_gh_failure_is_a_catchable_gh_error(self):
        self.run.return_value = completed(returncode=1, stderr="boom")
        with self.assertRaises(gh_api.GhError):
            gh_api.gh(["api", "x"], "/w")

    def test_repo_owner_name_splits_name_with_owner(self):
        self.run.return_value = completed(json.dumps({"nameWithOwner": "acme/widgets"}))
        self.assertEqual(gh_api.repo_owner_name("/w"), ["acme", "widgets"])

    def test_pr_number_reads_number(self):
        self.run.return_value = completed(json.dumps({"number": 42}))
        self.assertEqual(gh_api.pr_number("/w"), 42)

    def test_viewer_login_reads_the_signed_in_user(self):
        self.run.return_value = completed(json.dumps({"login": "me"}))
        self.assertEqual(gh_api.viewer_login("/w"), "me")


if __name__ == "__main__":
    unittest.main()

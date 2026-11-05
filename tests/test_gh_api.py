import json
import subprocess
import sys
import unittest
from unittest import mock

from helpers import SCRIPTS

sys.path.insert(0, SCRIPTS)
import gh_api
import records

pr_comments = records.load_script("pr-comments.py")


def completed(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class GhApiTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(gh_api.subprocess, "run")
        self.run = patcher.start()
        self.addCleanup(patcher.stop)

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

    def test_graphql_passes_query_and_variables(self):
        self.run.return_value = completed(json.dumps({"data": 1}))
        self.assertEqual(gh_api.graphql("query{x}", {"o": "a", "n": 3}, "/w"), {"data": 1})
        self.assertEqual(
            self.run.call_args.args[0],
            ["gh", "api", "graphql", "-f", "query=query{x}", "-F", "o=a", "-F", "n=3"],
        )

    def test_repo_owner_name_splits_name_with_owner(self):
        self.run.return_value = completed(json.dumps({"nameWithOwner": "acme/widgets"}))
        self.assertEqual(gh_api.repo_owner_name("/w"), ["acme", "widgets"])

    def test_pr_number_reads_number(self):
        self.run.return_value = completed(json.dumps({"number": 42}))
        self.assertEqual(gh_api.pr_number("/w"), 42)

    def test_pr_comments_imports_them(self):
        self.assertIs(pr_comments.graphql, gh_api.graphql)


if __name__ == "__main__":
    unittest.main()

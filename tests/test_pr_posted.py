import os
import unittest

from helpers import TempCase, run_ok
import paths
import records

pr_posted = records.load_script("pr-posted.py")

URL = "https://github.com/clerk/api/pull/42"


class PrPostedCase(TempCase):
    def setUp(self):
        super().setUp()
        self.wt = self.path("wt")
        os.makedirs(self.wt)


class PrPostedTest(PrPostedCase):
    def test_nothing_is_read_before_a_pull_request_is_recorded(self):
        self.assertIsNone(pr_posted.read(self.wt))

    def test_reads_back_the_number_and_link_recorded(self):
        pr_posted.record(self.wt, 42, URL)
        self.assertEqual(pr_posted.read(self.wt), (42, URL))

    def test_a_later_record_replaces_the_earlier(self):
        pr_posted.record(self.wt, 41, "https://github.com/clerk/api/pull/41")
        pr_posted.record(self.wt, 42, URL)
        self.assertEqual(pr_posted.read(self.wt), (42, URL))

    def test_a_file_that_is_not_a_number_and_link_reads_as_nothing(self):
        os.makedirs(paths.ledger(self.wt))
        with open(paths.pr_posted(self.wt), "w") as f:
            f.write("garbage\n")
        self.assertIsNone(pr_posted.read(self.wt))


class PrPostedCommandTest(PrPostedCase):
    def test_record_then_show_prints_the_number_and_link(self):
        run_ok("pr-posted", "record", self.wt, "--number", 42, "--url", URL)
        self.assertEqual(run_ok("pr-posted", "show", self.wt), f"42\t{URL}")

    def test_show_prints_nothing_when_none_was_posted(self):
        self.assertEqual(run_ok("pr-posted", "show", self.wt), "")


if __name__ == "__main__":
    unittest.main()

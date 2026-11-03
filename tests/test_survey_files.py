import os
import unittest

from helpers import TempCase, init_repo, run_script, write_file


class SurveyFilesCase(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("work"), with_origin=False)
        for rel in ("src/b/c.py", "src/a.py", "src/yarn.lock", "src/dist/bundle.js", "tests/test_a.py"):
            self.write(rel, "x = 1\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-qm", "files")
        self.out = self.path("checks/SURVEY-1/files.txt")

    def write(self, rel, text):
        write_file(os.path.join(self.repo.path, rel), text)

    def at(self, rel):
        return os.path.join(self.repo.path, rel)

    def resolve(self, *args):
        return run_script("survey-files", self.repo.path, *args, "--out", self.out)

    def listed(self, *args):
        code, out = self.resolve(*args)
        self.assertEqual(code, 0, out)
        with open(self.out) as f:
            return f.read().splitlines()


class SurveyFilesTests(SurveyFilesCase):
    def test_writes_the_tracked_files_as_absolute_sorted_paths(self):
        self.assertEqual(self.listed("src"), [self.at("src/a.py"), self.at("src/b/c.py")])

    def test_drops_a_lockfile_and_build_output(self):
        listed = self.listed("src")
        self.assertNotIn(self.at("src/yarn.lock"), listed)
        self.assertNotIn(self.at("src/dist/bundle.js"), listed)

    def test_drops_a_data_file_over_the_size_limit(self):
        self.write("src/data.json", "[\n" + "1,\n" * 600 + "]\n")
        self.repo.git("add", "-A")
        self.assertNotIn(self.at("src/data.json"), self.listed("src"))

    def test_leaves_out_untracked_files_of_a_directory(self):
        self.write("src/scratch.py", "y = 2\n")
        self.assertNotIn(self.at("src/scratch.py"), self.listed("src"))

    def test_drops_files_an_exclude_glob_matches_in_a_directory(self):
        self.assertNotIn(self.at("tests/test_a.py"), self.listed(".", "--exclude", "tests/**"))

    def test_keeps_a_file_named_directly_that_an_exclude_glob_matches(self):
        self.assertEqual(self.listed("tests/test_a.py", "--exclude", "tests/**"), [self.at("tests/test_a.py")])

    def test_refuses_a_path_outside_the_repository(self):
        code, out = self.resolve("..")
        self.assertNotEqual(code, 0, out)
        self.assertIn("is not under", out)


class OverTheCapTests(SurveyFilesCase):
    def setUp(self):
        super().setUp()
        self.code, self.printed = self.resolve("src", "--cap", "1")

    def test_exits_non_zero(self):
        self.assertNotEqual(self.code, 0, self.printed)

    def test_prints_each_directory_with_its_file_count(self):
        self.assertIn("2 files, over the cap of 1", self.printed)
        self.assertIn("  src/: 1", self.printed)
        self.assertIn("  src/b/: 1", self.printed)

    def test_writes_no_file_list(self):
        self.assertFalse(os.path.exists(self.out))


class StaleFileListTests(SurveyFilesCase):
    def setUp(self):
        super().setUp()
        write_file(self.out, "stale\n")

    def test_an_over_cap_run_removes_the_earlier_list(self):
        self.resolve("src", "--cap", "1")
        self.assertFalse(os.path.exists(self.out))

    def test_a_failed_run_removes_the_earlier_list(self):
        self.resolve("missing")
        self.assertFalse(os.path.exists(self.out))


class CapBelowOneTests(SurveyFilesCase):
    def setUp(self):
        super().setUp()
        write_file(self.out, "stale\n")

    def test_a_zero_cap_is_a_usage_error(self):
        code, out = self.resolve("src", "--cap", "0")
        self.assertNotEqual(code, 0, out)
        self.assertIn("--cap must be at least 1", out)

    def test_a_cap_below_one_removes_the_earlier_list(self):
        self.resolve("src", "--cap", "0")
        self.assertFalse(os.path.exists(self.out))

    def test_a_cap_that_is_not_a_number_removes_the_earlier_list(self):
        code, out = self.resolve("src", "--cap", "abc")
        self.assertNotEqual(code, 0, out)
        self.assertIn("--cap must be at least 1", out)
        self.assertFalse(os.path.exists(self.out))


class MissingPathTests(SurveyFilesCase):
    def test_a_path_that_does_not_exist_is_refused(self):
        code, out = self.resolve("nowhere")
        self.assertNotEqual(code, 0, out)
        self.assertIn("nowhere does not exist under", out)

    def test_an_absolute_path_outside_the_repository_is_refused(self):
        code, out = self.resolve(self.path("checks"))
        self.assertNotEqual(code, 0, out)
        self.assertIn("is not under", out)


class EveryFileExcludedTests(SurveyFilesCase):
    def test_a_directory_of_only_build_output_leaves_nothing(self):
        code, out = self.resolve("src/dist")
        self.assertNotEqual(code, 0, out)
        self.assertIn("no files to survey after exclusions", out)
        self.assertFalse(os.path.exists(self.out))

    def test_an_exclude_glob_that_matches_every_file_leaves_nothing(self):
        code, out = self.resolve("tests", "--exclude", "tests/**")
        self.assertNotEqual(code, 0, out)
        self.assertIn("no files to survey after exclusions", out)


class ExcludeGlobWithDirectoryAndFileTests(SurveyFilesCase):
    def test_drops_the_file_the_directory_expanded_to_but_keeps_it_named_directly(self):
        self.assertEqual(
            self.listed("src", "src/b/c.py", "--exclude", "src/b/**"),
            [self.at("src/a.py"), self.at("src/b/c.py")],
        )

    def test_drops_the_file_when_only_the_directory_names_it(self):
        self.assertEqual(self.listed("src", "--exclude", "src/b/**"), [self.at("src/a.py")])


class PrintedTotalsTests(SurveyFilesCase):
    def setUp(self):
        super().setUp()
        self.write("src/a.py", "x = 1\n" * 100)
        self.write("src/b/c.py", "y = 2\n" * 2)
        self.repo.git("add", "-A")
        self.repo.git("commit", "-qm", "sizes")

    def test_the_success_line_gives_files_lines_and_estimated_tokens(self):
        code, out = self.resolve("src")
        self.assertEqual(code, 0, out)
        self.assertIn("2 files, 102 lines, ~153 tokens in", out)


if __name__ == "__main__":
    unittest.main()

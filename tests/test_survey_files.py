import os
import unittest

from helpers import TempCase, init_repo, run_script


class CapBelowOneKeepsNoEarlierListTests(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("work"), with_origin=False)
        os.makedirs(self.path("work/src"))
        with open(self.path("work/src/a.py"), "w") as f:
            f.write("x = 1\n")
        self.repo.git("add", "-A")
        self.repo.commit("add src")
        self.out = self.path("checks/files.txt")
        os.makedirs(os.path.dirname(self.out))
        with open(self.out, "w") as f:
            f.write("stale\n")

    def test_a_cap_below_one_removes_the_earlier_list(self):
        code, out = run_script("survey-files", self.path("work"), "src", "--cap", "0", "--out", self.out)
        self.assertNotEqual(code, 0, out)
        self.assertFalse(os.path.exists(self.out))

    def test_a_cap_that_is_not_a_number_removes_the_earlier_list(self):
        code, out = run_script("survey-files", self.path("work"), "src", "--cap", "abc", "--out", self.out)
        self.assertNotEqual(code, 0, out)
        self.assertFalse(os.path.exists(self.out))


if __name__ == "__main__":
    unittest.main()

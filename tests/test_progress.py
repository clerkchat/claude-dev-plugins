import os
import sys
import unittest

from helpers import SCRIPTS, TempCase, write_file

sys.path.insert(0, SCRIPTS)
import records

progress = records.load_script("progress.py")

PLAN = """# Plan

## Instances
| # | lens | scope | patch | model | raw file |
| --- | --- | --- | --- | --- | --- |
| 1 | security | entities | patch/entities.patch | opus | raw/security-entities.md |
| 2 | rollout | all | patch/whole.patch | opus | raw/rollout.md |
"""


class StateTest(TempCase):
    def setUp(self):
        super().setUp()
        self.run_dir = self.path("run")
        write_file(os.path.join(self.run_dir, "plan.md"), PLAN)

    def test_state_counts_the_raw_files_written(self):
        write_file(os.path.join(self.run_dir, "raw", "rollout.md"), "done\n")
        self.assertEqual(progress.state(self.run_dir)[:2], ("reviewing", "1/2"))


if __name__ == "__main__":
    unittest.main()

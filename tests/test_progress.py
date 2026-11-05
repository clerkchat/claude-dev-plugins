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


class InstancesTest(TempCase):
    def setUp(self):
        super().setUp()
        self.run_dir = self.path("run")
        write_file(os.path.join(self.run_dir, "plan.md"), PLAN)

    def test_returns_each_instance_as_lens_and_raw_file_in_table_order(self):
        self.assertEqual(progress.instances(self.run_dir), [("security", "raw/security-entities.md"), ("rollout", "raw/rollout.md")])

    def test_returns_none_without_a_plan(self):
        self.assertIsNone(progress.instances(self.path("empty")))

    def test_state_counts_the_raw_files_written(self):
        write_file(os.path.join(self.run_dir, "raw", "rollout.md"), "done\n")
        self.assertEqual(progress.state(self.run_dir)[:2], ("reviewing", "1/2"))


if __name__ == "__main__":
    unittest.main()

import sys
import unittest

from helpers import SCRIPTS, RunCase

sys.path.insert(0, SCRIPTS)
import records

progress = records.load_script("progress.py")

class StateTest(RunCase):
    def setUp(self):
        super().setUp()
        self.write_plan()

    def test_state_counts_the_raw_files_written(self):
        self.write("raw/rollout.md", "done\n")
        self.assertEqual(progress.state(self.run_dir)[:2], ("reviewing", "1/2"))


if __name__ == "__main__":
    unittest.main()

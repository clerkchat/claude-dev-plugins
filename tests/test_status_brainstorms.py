import unittest

from helpers import TempCase, init_repo, write_feature_md, write_record

LEANING = "## Leaning\n\nTyped fragments beside the builder.\n"


class BrainstormStatusTests(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("work"))
        self.repo.git("checkout", "-q", "-b", "feat")
        write_feature_md(self.repo.path)
        write_record(self.repo.path, "IDEAS-1", "brainstorm", "Typed fragments", status="", body=LEANING)

    def status(self):
        code, out = self.repo.status()
        self.assertEqual(code, 0, out)
        return out

    def test_an_open_brainstorm_is_shown_with_its_leaning_and_picking_it_up_comes_first(self):
        out = self.status()
        self.assertIn("1 open brainstorm", out)
        self.assertIn("brainstorm STORM-1 Typed fragments, nothing settled from it yet: Typed fragments beside the builder.", out)
        self.assertIn("1. Pick up the brainstorm STORM-1 Typed fragments", out)

    def test_a_brainstorm_a_record_settles_from_is_not_open(self):
        write_record(self.repo.path, "R2", "decision", "Fragments", extra="from: IDEAS-1\n")
        out = self.status()
        self.assertNotIn("open brainstorm", out)
        self.assertNotIn("Pick up the brainstorm", out)


if __name__ == "__main__":
    unittest.main()

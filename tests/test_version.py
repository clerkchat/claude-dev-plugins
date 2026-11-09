import json
import os
import subprocess
import unittest
from unittest import mock

from helpers import GIT_ENV, ROOT, TempCase, git, init_repo
import records

BUMP = os.path.join(ROOT, "scripts", "bump-version.py")
HOOKS = os.path.join(ROOT, ".githooks")
PLUGIN_JSON = os.path.join("plugins", "clerk-dev", ".claude-plugin", "plugin.json")


def read(path):
    with open(path) as f:
        return f.read()


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


def bump(*args, cwd=None, script=BUMP):
    done = subprocess.run(["python3", script, *args], capture_output=True, text=True, cwd=cwd)
    return done.returncode, (done.stdout + done.stderr).strip()


class BumpScriptTest(TempCase):
    def setUp(self):
        super().setUp()
        self.root = self.path("checkout")
        self.manifest = os.path.join(self.root, PLUGIN_JSON)
        self.script = os.path.join(self.root, "scripts", "bump-version.py")
        for src, dst in ((os.path.join(ROOT, PLUGIN_JSON), self.manifest), (BUMP, self.script)):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            write(dst, read(src))
        self.original = read(self.manifest)
        self.current = records.plugin_version()

    def bump(self, *args):
        return bump(*args, script=self.script)

    def set_version(self, version):
        write(self.manifest, self.original.replace(f'"version": "{self.current}"', f'"version": "{version}"'))

    def test_bumps_the_patch_part(self):
        self.set_version("1.2.3")
        self.assertEqual(self.bump("patch"), (0, "1.2.3 -> 1.2.4"))

    def test_bumps_the_minor_part_and_resets_patch(self):
        self.set_version("1.2.3")
        self.assertEqual(self.bump("minor"), (0, "1.2.3 -> 1.3.0"))

    def test_bumps_the_major_part_and_resets_the_rest(self):
        self.set_version("1.2.3")
        self.assertEqual(self.bump("major"), (0, "1.2.3 -> 2.0.0"))

    def test_leaves_every_other_byte_alone(self):
        self.set_version("1.2.3")
        before = read(self.manifest)
        self.bump("patch")
        self.assertEqual(read(self.manifest), before.replace("1.2.3", "1.2.4"))

    def test_stops_on_a_version_that_is_not_x_y_z(self):
        self.set_version("1.2")
        code, out = self.bump("patch")
        self.assertEqual(code, 1)
        self.assertIn("is not X.Y.Z", out)

    def test_stops_on_an_unknown_part(self):
        self.assertEqual(self.bump("huge")[0], 1)


class PreMergeCommitHookTest(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = init_repo(self.path("repo"), with_origin=False)
        git(self.repo.path, "config", "core.hooksPath", HOOKS)
        self.write_version("1.0.0")
        self.commit_all("add manifest")
        git(self.repo.path, "checkout", "-q", "-b", "feat")
        self.repo.commit("feature work", "feature.txt")

    def write_version(self, version):
        path = os.path.join(self.repo.path, PLUGIN_JSON)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"version": version}, f)

    def commit_all(self, subject):
        git(self.repo.path, "add", "-A")
        git(self.repo.path, "commit", "-qm", subject)

    def move_main_to(self, version):
        git(self.repo.path, "checkout", "-q", "main")
        self.write_version(version)
        self.commit_all("main bumps")

    def merge(self, onto):
        git(self.repo.path, "checkout", "-q", onto)
        return subprocess.run(["git", "-C", self.repo.path, "merge", "--no-ff", "-m", "merge", "feat"],
                              capture_output=True, text=True, env=GIT_ENV)

    def test_refuses_an_unbumped_merge_on_main(self):
        done = self.merge("main")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("1.0.0", done.stdout + done.stderr)
        self.assertIn("bump-version.py", done.stdout + done.stderr)

    def test_passes_a_bumped_merge_on_main(self):
        self.write_version("1.0.1")
        self.commit_all("bump")
        self.assertEqual(self.merge("main").returncode, 0)

    def test_refuses_a_merge_whose_result_keeps_the_higher_version_main_moved_to(self):
        self.move_main_to("1.1.0")
        done = self.merge("main")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("1.1.0", done.stdout + done.stderr)

    def test_passes_off_main(self):
        git(self.repo.path, "checkout", "-q", "-b", "other", "main")
        self.assertEqual(self.merge("other").returncode, 0)


class PluginVersionTest(unittest.TestCase):
    def test_reads_the_manifest_version(self):
        with open(os.path.join(ROOT, PLUGIN_JSON)) as f:
            self.assertEqual(records.plugin_version(), json.load(f)["version"])

    def test_is_none_when_the_manifest_is_unreadable(self):
        with mock.patch.object(records, "PLUGIN_ROOT", "/nonexistent"):
            self.assertIsNone(records.plugin_version())


class PluginVersionIsBumpedTest(unittest.TestCase):
    def test_is_at_least_the_version_this_branch_bumped_to(self):
        self.assertGreaterEqual(tuple(map(int, records.plugin_version().split("."))), (1, 2, 0))


class PluginStampTest(TempCase):
    def test_names_the_version_when_the_plugin_is_not_in_a_git_checkout(self):
        plugin = self.path("plugin")
        os.makedirs(os.path.join(plugin, ".claude-plugin"))
        write(os.path.join(plugin, ".claude-plugin", "plugin.json"), '{"version": "4.5.6"}')
        passes = records.load_script("passes.py")
        with mock.patch.object(records, "PLUGIN_ROOT", plugin), mock.patch.object(passes, "PLUGIN_ROOT", plugin):
            self.assertEqual(passes.plugin_stamp(), "v4.5.6")

"""Tests for what the repo commits (#106): no macOS Finder files.

Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args):
    return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True)


@unittest.skipIf(shutil.which("git") is None, "git isn't installed")
class RepoFilesTest(unittest.TestCase):

    def test_no_ds_store_is_committed(self):
        tracked = git("ls-files", "--full-name", ":/").stdout.splitlines()   # ":/" = the whole repo
        self.assertEqual([p for p in tracked if os.path.basename(p) == ".DS_Store"], [])

    def test_a_new_ds_store_anywhere_is_ignored(self):
        # check-ignore works on a path that doesn't exist yet. Exit 0 = ignored.
        for path in [".DS_Store", "docs/.DS_Store", "../.DS_Store"]:
            with self.subTest(path):
                self.assertEqual(git("check-ignore", "-q", path).returncode, 0, f"{path} isn't ignored")


if __name__ == "__main__":
    unittest.main()

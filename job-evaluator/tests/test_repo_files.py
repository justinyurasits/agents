"""Tests for what the repo commits: no macOS Finder files (#106), and a root
README whose links work and that holds no key or contact details (#102).

Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import os
import re
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(HERE)
# The only outside addresses the root README may link to: the repo itself and
# the published page.
ALLOWED_URLS = ("https://github.com/justinyurasits/agents", "https://justinyurasits.github.io/agents/")
ANTHROPIC_KEY = re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}")


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



class RootReadmeTest(unittest.TestCase):
    """The repo's front page (#102)."""

    def setUp(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            self.readme = f.read()

    def test_every_link_points_at_something_real(self):
        links = re.findall(r"\]\(([^)]+)\)", self.readme)
        self.assertGreaterEqual(len(links), 6)
        for link in links:
            with self.subTest(link):
                if link.startswith("http"):
                    self.assertTrue(link.startswith(ALLOWED_URLS), f"{link} isn't the repo or the page")
                else:
                    self.assertTrue(os.path.exists(os.path.join(ROOT, link)), f"{link} doesn't exist")

    def test_it_links_the_live_page_and_the_four_build_docs(self):
        for target in ["https://justinyurasits.github.io/agents/job-evaluator/site/", "CLAUDE.md",
                       "job-evaluator/docs/DECISIONS.md", "LEARNINGS.md", "job-evaluator/docs/BUILD_LOG.md"]:
            with self.subTest(target):
                self.assertIn(f"]({target})", self.readme)

    def test_no_key_or_email(self):
        self.assertIsNone(ANTHROPIC_KEY.search(self.readme))
        self.assertIsNone(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", self.readme), "an email address")


@unittest.skipIf(shutil.which("git") is None, "git isn't installed")
class NoKeyInTheRepoTest(unittest.TestCase):

    # Two test files hold made-up key-shaped strings on purpose: the fake key
    # the tests run with, and the input of a test proving the trace writer
    # refuses anything key-shaped. Any other match fails.
    FAKE_KEYS_ON_PURPOSE = {"job-evaluator/tests/fakes.py", "job-evaluator/tests/test_tracing.py"}

    def test_no_tracked_file_holds_an_anthropic_key(self):
        # git grep -l lists the files that match (never the text); paths from the repo root.
        found = git("grep", "-l", "--full-name", "-E", r"sk-ant-[A-Za-z0-9_-]{10,}", "--", ":/")
        self.assertEqual(set(found.stdout.split()) - self.FAKE_KEYS_ON_PURPOSE, set(), "possible key in these files")


if __name__ == "__main__":
    unittest.main()

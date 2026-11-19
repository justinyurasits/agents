"""Tests for what the repo commits: no macOS Finder files (#106), a root
README whose links work and that holds no key or contact details (#102), and
no reference to the design docs that moved to the design repo (#125).

Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import os
import re
import shutil
import subprocess
import unittest

from design_repo import design_path

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(HERE)
# The only outside addresses the READMEs may link to: the repo itself, the
# published page, and the design repo, where the design docs live (#125).
DESIGN_URL = "https://github.com/justinyurasits/design"
ALLOWED_URLS = ("https://github.com/justinyurasits/agents", "https://justinyurasits.github.io/agents/", DESIGN_URL)
# The docs that moved to the design repo (#125). Only CHANGELOG history may name them.
MOVED_DOCS = r"(BRIEF|SPEC|DECISIONS|BUILD_LOG|LEARNINGS)\.md"   # POSIX ERE: git grep on macOS has no \b
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



def check_links(test, readme, folder):
    """Every markdown link in a README points at something real: a file in this
    repo (relative to the README's folder), a file in the design repo, or the
    repo or the page."""
    links = re.findall(r"\]\(([^)]+)\)", readme)
    for link in links:
        with test.subTest(link):
            if link.startswith(DESIGN_URL):
                # .../design, .../design/tree/main/<path> or .../design/blob/main/<path>[#anchor]
                path = re.sub(r"^/(tree|blob)/main/?", "", link[len(DESIGN_URL):].split("#")[0])
                test.assertTrue(os.path.exists(design_path(path)), f"{path} isn't in the design repo")
            elif link.startswith("http"):
                test.assertTrue(link.startswith(ALLOWED_URLS), f"{link} isn't the repo, the page or design")
            else:
                test.assertTrue(os.path.exists(os.path.join(folder, link.split("#")[0])), f"{link} doesn't exist")
    return links


class RootReadmeTest(unittest.TestCase):
    """The repo's front page (#102)."""

    def setUp(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            self.readme = f.read()

    def test_every_link_points_at_something_real(self):
        self.assertGreaterEqual(len(check_links(self, self.readme, ROOT)), 6)

    def test_it_links_the_live_page_claude_md_and_the_design_docs(self):
        # The decision log, principles and build log are in the design repo now,
        # with the design index that lists them (#124, #125).
        for target in ["https://justinyurasits.github.io/agents/job-evaluator/site/", "CLAUDE.md",
                       DESIGN_URL + "/tree/main/agents",
                       DESIGN_URL + "/blob/main/agents/job-evaluator/design.md#decision-log",
                       DESIGN_URL + "/blob/main/agents/principles.md",
                       DESIGN_URL + "/blob/main/agents/job-evaluator/build-log.md"]:
            with self.subTest(target):
                self.assertIn(f"]({target})", self.readme)

    def test_no_key_or_email(self):
        self.assertIsNone(ANTHROPIC_KEY.search(self.readme))
        self.assertIsNone(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", self.readme), "an email address")


class AgentReadmeTest(unittest.TestCase):
    """job-evaluator/README.md: its doc links resolve too (#125)."""

    def test_every_link_points_at_something_real(self):
        with open(os.path.join(HERE, "README.md"), encoding="utf-8") as f:
            self.assertGreaterEqual(len(check_links(self, f.read(), HERE)), 4)


@unittest.skipIf(shutil.which("git") is None, "git isn't installed")
class MovedDocsTest(unittest.TestCase):
    """BRIEF, SPEC, DECISIONS, BUILD_LOG and LEARNINGS moved to the design repo
    (#125). Nothing here may read or link them, so nothing points at a file
    that's gone; the design repo's copies are the only ones."""

    def test_the_moved_files_are_gone(self):
        tracked = git("ls-files", "--full-name", ":/").stdout.splitlines()
        self.assertEqual([p for p in tracked if re.fullmatch(MOVED_DOCS, os.path.basename(p))], [])

    def test_no_tracked_file_names_a_moved_doc(self):
        # Changelogs keep their history; this file names them to check for them.
        found = git("grep", "-l", "--full-name", "-E", MOVED_DOCS, "--", ":/",
                    ":(exclude,glob)**/CHANGELOG.md", ":/job-evaluator/tests/test_repo_files.py")
        self.assertEqual(found.stdout.split(), [])


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

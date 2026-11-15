"""Tests for how build_numbers.py counts merged pull requests (#108, D41).

The count is the "Merge pull request #" commits before this PR. On main just
after a merge, HEAD is that PR's own merge commit and isn't counted. On a new
branch with no commits yet, HEAD is the previous PR's merge commit, and it
must be counted, or the branch commits a number that's one short.

Each test builds a throwaway git repo with real merge commits. No API calls.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import os
import shutil
import subprocess
import tempfile
import unittest

import build_numbers

NAME = ["-c", "user.name=test", "-c", "user.email=test@example.invalid"]


@unittest.skipIf(shutil.which("git") is None, "git isn't installed")
class MergedPrCountTest(unittest.TestCase):

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.repo)
        self.git("init", "-q", "-b", "main")
        self.commit("start")

    def git(self, *args):
        subprocess.run(["git", *NAME, *args], cwd=self.repo, check=True, capture_output=True, text=True)

    def commit(self, message):
        with open(os.path.join(self.repo, "log.txt"), "a", encoding="utf-8") as f:
            f.write(message + "\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def merge_pr(self, number, branch):
        """A GitHub-style merge of branch into main, as PR #number."""
        self.git("checkout", "-q", "-b", branch)
        self.commit(f"work for #{number}")
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--no-ff", branch, "-m", f"Merge pull request #{number} from someone/{branch}")

    def count(self):
        return build_numbers.count_merged_prs(cwd=self.repo)

    def test_on_main_just_after_a_merge_the_merge_itself_isnt_counted(self):
        # D41: the number PR #2 committed (1) still matches once it's merged.
        self.merge_pr(1, "one")
        self.merge_pr(2, "two")
        self.assertEqual(self.count(), 1)

    def test_a_new_branch_with_no_commits_counts_the_merge_it_started_from(self):
        # #108: this was 0, one short.
        self.merge_pr(1, "one")
        self.git("checkout", "-q", "-b", "issue-2")
        self.assertEqual(self.count(), 1)

    def test_the_count_is_the_same_before_and_after_a_branchs_first_commit(self):
        self.merge_pr(1, "one")
        self.git("checkout", "-q", "-b", "issue-2")
        before = self.count()
        self.commit("first commit on the branch")
        self.assertEqual((before, self.count()), (1, 1))

    def test_what_a_branch_commits_matches_main_after_its_merge(self):
        # The whole point: the branch's count, and main's count once the branch
        # is merged, are the same number.
        self.merge_pr(1, "one")
        self.git("checkout", "-q", "-b", "two")
        on_branch = self.count()
        self.commit("work for #2")
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--no-ff", "two", "-m", "Merge pull request #2 from someone/two")
        self.assertEqual((on_branch, self.count()), (1, 1))

    def test_a_detached_checkout_of_main_counts_like_main(self):
        self.merge_pr(1, "one")
        self.merge_pr(2, "two")
        self.git("checkout", "-q", "--detach", "main")
        self.assertEqual(self.count(), 1)

    def test_on_main_after_a_plain_commit_every_merge_counts(self):
        self.merge_pr(1, "one")
        self.commit("a commit straight on main")
        self.assertEqual(self.count(), 1)


if __name__ == "__main__":
    unittest.main()

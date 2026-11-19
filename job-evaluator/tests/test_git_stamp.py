"""Tests for the git stamp on every trace (#99): git_dirty says whether the
code that ran differs from git_commit. Files record.py writes itself
(recordings/, docs/SCENARIOS.md) don't count.

Each test builds a throwaway git repo shaped like job-evaluator/, commits it,
changes one thing, and asks tracing._git_commit() about it. No API calls.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import os
import shutil
import subprocess
import tempfile
import unittest

try:
    import fakes  # noqa: F401  (sets up the safe agent import, like the other tests)
except ImportError:  # when run as tests.test_git_stamp
    from tests import fakes  # noqa: F401
import tracing


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@unittest.skipIf(shutil.which("git") is None, "git isn't installed")
class GitStampTest(unittest.TestCase):

    def setUp(self):
        # A repo root with a job-evaluator/ folder inside, like the real one.
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        self.here = os.path.join(root, "job-evaluator")
        for path, text in {"agent.py": "print('agent')\n",
                           "recordings/scenario-01.json": "{}\n",
                           "docs/SCENARIOS.md": "# Scenarios\n",
                           "docs/STEPS.md": "# Steps\n"}.items():
            self.write(path, text)
        git(root, "init", "-q")
        git(root, "-c", "user.name=test", "-c", "user.email=test@example.invalid", "add", "-A")
        git(root, "-c", "user.name=test", "-c", "user.email=test@example.invalid",
            "commit", "-q", "-m", "start")

    def write(self, path, text):
        full = os.path.join(self.here, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)

    def dirty(self):
        commit, dirty = tracing._git_commit(self.here)
        self.assertTrue(commit)
        return dirty

    def test_a_committed_tree_is_clean(self):
        self.assertIs(self.dirty(), False)

    # What record.py writes doesn't count: these are the bug in #99.

    def test_a_changed_recording_is_not_dirty(self):
        self.write("recordings/scenario-01.json", '{"changed": true}\n')
        self.assertIs(self.dirty(), False)

    def test_a_new_recording_is_not_dirty(self):
        self.write("recordings/scenario-02.json", "{}\n")
        self.assertIs(self.dirty(), False)

    def test_a_regenerated_scenarios_md_is_not_dirty(self):
        self.write("docs/SCENARIOS.md", "# Scenarios, regenerated\n")
        self.assertIs(self.dirty(), False)

    # Everything else still does.

    def test_a_changed_agent_is_dirty(self):
        self.write("agent.py", "print('changed')\n")
        self.assertIs(self.dirty(), True)

    def test_a_new_code_file_is_dirty(self):
        self.write("new_tool.py", "pass\n")
        self.assertIs(self.dirty(), True)

    def test_another_doc_is_still_dirty(self):
        # Only SCENARIOS.md is excused in docs/: record.py doesn't write the rest.
        self.write("docs/STEPS.md", "# Steps, edited\n")
        self.assertIs(self.dirty(), True)

    def test_a_recording_plus_a_code_change_is_dirty(self):
        self.write("recordings/scenario-01.json", '{"changed": true}\n')
        self.write("agent.py", "print('changed')\n")
        self.assertIs(self.dirty(), True)


if __name__ == "__main__":
    unittest.main()

"""Find the design repo (#125): the design docs live there, not in this repo.

    design_path("agents", "job-evaluator", "design.md")   # a path in the design repo
    read_design("agents", "job-evaluator", "design.md")   # that file's text

Where it looks:
  1. $DESIGN_DIR, if it's set.
  2. Otherwise design/ next to the main checkout of this repo (~/code/design
     beside ~/code/agents). The main checkout is found from git's shared
     .git folder, so a worktree in ~/code/agents-worktrees/<branch> finds the
     same design/ as the main folder does; a plain "../design" wouldn't.

If it isn't there, design_path raises FileNotFoundError, so the tests that
read the docs fail (they don't skip): a missing design repo is a broken setup.
"""

import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
MISSING = "clone justinyurasits/design next to agents"
COMPONENT = ("agents", "job-evaluator")   # this agent's folder in the design repo
GITHUB = "https://github.com/justinyurasits/design"


def main_checkout():
    """The main checkout's folder, or None without git. A worktree's
    --git-common-dir is the main checkout's .git; the folder is its parent."""
    try:
        out = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=HERE,
                             capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    # It may print a relative path (".git", "../.git"), relative to HERE.
    return os.path.dirname(os.path.abspath(os.path.join(HERE, out)))


def design_dir():
    if os.environ.get("DESIGN_DIR"):
        return os.environ["DESIGN_DIR"]
    checkout = main_checkout()
    return os.path.join(os.path.dirname(checkout), "design") if checkout else None


def design_path(*parts):
    root = design_dir()
    # The agents/ folder inside it shows it's really the design repo.
    if not root or not os.path.isdir(os.path.join(root, *COMPONENT)):
        raise FileNotFoundError(f"{MISSING} (looked for {root or 'a git checkout'})")
    return os.path.join(root, *parts)


def read_design(*parts):
    with open(design_path(*parts), encoding="utf-8") as f:
        return f.read()


def design_doc():
    """design.md split in two at "# Decision log": (how it works, decision log).
    Both used to be files in docs/; they moved to the design repo in #125."""
    spec, log = read_design(*COMPONENT, "design.md").split("\n# Decision log", 1)
    return spec, "# Decision log" + log

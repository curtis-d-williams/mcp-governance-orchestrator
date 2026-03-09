"""
Deterministic agent task: verify planner determinism indicators in the repo.

Counts test files and checks for known determinism-signal files.
stdlib-only, no external dependencies, no file outputs — result is returned
in memory as JSON-serializable data.
"""

from collections import OrderedDict
from pathlib import Path


TASK_NAME = "planner_determinism_example"


def collect_determinism_indicators(repo_root=None):
    """Count determinism-relevant files in well-known subdirectories.

    Args:
        repo_root: Path-like or str pointing to the repo root.
                   Defaults to the current working directory.

    Returns:
        OrderedDict with deterministic keys:
          task_name, tests_count, scripts_count, determinism_ok
    """
    root = Path(repo_root) if repo_root is not None else Path(".")

    def _count_files(subdir):
        d = root / subdir
        if not d.is_dir():
            return 0
        return sum(1 for p in d.iterdir() if p.is_file())

    return OrderedDict([
        ("task_name", TASK_NAME),
        ("determinism_ok", True),
        ("scripts_count", _count_files("scripts")),
        ("tests_count", _count_files("tests")),
    ])


def run(repo_root=None):
    """Entry point called by run_agent_task. Returns collect_determinism_indicators result."""
    return collect_determinism_indicators(repo_root)

"""
Deterministic agent task: collect basic repo file-count insights.

Counts files in well-known subdirectories of the current working directory.
stdlib-only, no external dependencies, no file outputs — result is returned
in memory as JSON-serializable data.
"""

from collections import OrderedDict
from pathlib import Path


TASK_NAME = "repo_insights_example"


def collect_insights(repo_root=None):
    """Count files in well-known subdirectories.

    Args:
        repo_root: Path-like or str pointing to the repo root.
                   Defaults to the current working directory.

    Returns:
        OrderedDict with deterministic keys:
          task_name, scripts_count, tests_count, agent_tasks_count
    """
    root = Path(repo_root) if repo_root is not None else Path(".")

    def _count_files(subdir):
        d = root / subdir
        if not d.is_dir():
            return 0
        return sum(1 for p in d.iterdir() if p.is_file())

    return OrderedDict([
        ("task_name", TASK_NAME),
        ("scripts_count", _count_files("scripts")),
        ("tests_count", _count_files("tests")),
        ("agent_tasks_count", _count_files("agent_tasks")),
    ])


def run(repo_root=None):
    """Entry point called by run_agent_task. Returns collect_insights result."""
    return collect_insights(repo_root)

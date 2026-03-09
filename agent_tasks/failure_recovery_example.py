"""
Deterministic agent task: collect failure recovery indicators from the repo.

Counts scripts, experiments, and agent_tasks files as a proxy for repo
recovery surface. stdlib-only, no external dependencies, no file outputs —
result is returned in memory as JSON-serializable data.
"""

from collections import OrderedDict
from pathlib import Path


TASK_NAME = "failure_recovery_example"


def collect_recovery_indicators(repo_root=None):
    """Count failure-recovery relevant files in well-known subdirectories.

    Args:
        repo_root: Path-like or str pointing to the repo root.
                   Defaults to the current working directory.

    Returns:
        OrderedDict with deterministic keys:
          task_name, agent_tasks_count, experiments_count, scripts_count,
          recovery_eligible
    """
    root = Path(repo_root) if repo_root is not None else Path(".")

    def _count_files(subdir):
        d = root / subdir
        if not d.is_dir():
            return 0
        return sum(1 for p in d.iterdir() if p.is_file())

    return OrderedDict([
        ("task_name", TASK_NAME),
        ("agent_tasks_count", _count_files("agent_tasks")),
        ("experiments_count", _count_files("experiments")),
        ("recovery_eligible", True),
        ("scripts_count", _count_files("scripts")),
    ])


def run(repo_root=None):
    """Entry point called by run_agent_task. Returns collect_recovery_indicators result."""
    return collect_recovery_indicators(repo_root)

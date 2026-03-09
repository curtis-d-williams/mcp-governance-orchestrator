"""
Deterministic agent task: audit artifact presence in the repo.

Counts artifact files in well-known output locations.
stdlib-only, no external dependencies, no file outputs — result is returned
in memory as JSON-serializable data.
"""

from collections import OrderedDict
from pathlib import Path


TASK_NAME = "artifact_audit_example"


def collect_artifact_audit(repo_root=None):
    """Count artifact files in well-known output locations.

    Args:
        repo_root: Path-like or str pointing to the repo root.
                   Defaults to the current working directory.

    Returns:
        OrderedDict with deterministic keys:
          task_name, experiments_count, json_artifacts_count, audit_ok
    """
    root = Path(repo_root) if repo_root is not None else Path(".")

    def _count_files(subdir):
        d = root / subdir
        if not d.is_dir():
            return 0
        return sum(1 for p in d.iterdir() if p.is_file())

    def _count_glob(pattern):
        return sum(1 for _ in root.glob(pattern))

    return OrderedDict([
        ("task_name", TASK_NAME),
        ("audit_ok", True),
        ("experiments_count", _count_files("experiments")),
        ("json_artifacts_count", _count_glob("*.json")),
    ])


def run(repo_root=None):
    """Entry point called by run_agent_task. Returns collect_artifact_audit result."""
    return collect_artifact_audit(repo_root)

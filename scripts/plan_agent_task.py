#!/usr/bin/env python3
"""
Plan an approved deterministic agent task without executing it.
"""

import json
import sys

from agent_tasks.registry import TASK_REGISTRY


def _execution_strategy_for_scope(scope):
    if scope == "local_repo":
        return "single_repo_runner"
    if scope == "portfolio":
        return "portfolio_runner"
    return "unknown"


def plan_agent_task(task_name):
    if task_name not in TASK_REGISTRY:
        print(json.dumps({
            "task": task_name,
            "valid": False,
            "error": "task_not_registered",
        }, indent=2))
        return

    spec = TASK_REGISTRY[task_name]

    print(json.dumps({
        "task": task_name,
        "valid": True,
        "scope": spec["scope"],
        "deterministic": spec["deterministic"],
        "portfolio_safe": spec["portfolio_safe"],
        "execution_strategy": _execution_strategy_for_scope(spec["scope"]),
        "inputs": spec["inputs"],
        "outputs": spec["outputs"],
    }, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 -m scripts.plan_agent_task <task_name>")
    plan_agent_task(sys.argv[1])

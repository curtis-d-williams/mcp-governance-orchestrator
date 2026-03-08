#!/usr/bin/env python3
"""
List available agent tasks with metadata.
"""

import json
from agent_tasks.registry import TASK_REGISTRY


def list_tasks():
    tasks = []

    for name, spec in sorted(TASK_REGISTRY.items()):
        tasks.append({
            "task": name,
            "description": spec["description"],
            "scope": spec["scope"],
            "outputs": spec["outputs"],
            "deterministic": spec["deterministic"],
            "portfolio_safe": spec["portfolio_safe"],
        })

    print(json.dumps(tasks, indent=2))


if __name__ == "__main__":
    list_tasks()

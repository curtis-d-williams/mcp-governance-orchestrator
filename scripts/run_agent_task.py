#!/usr/bin/env python3
"""
Run an approved deterministic agent task by name.
"""

import io
import json
import sys
from contextlib import redirect_stdout
from importlib import import_module


ALLOWED_TASKS = {
    "build_portfolio_dashboard": "agent_tasks.build_portfolio_dashboard",
}


def run_agent_task(task_name):
    if task_name not in ALLOWED_TASKS:
        raise SystemExit(f"Unknown agent task: {task_name}")

    module = import_module(ALLOWED_TASKS[task_name])

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        result = module.run()

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 -m scripts.run_agent_task <task_name>")
    run_agent_task(sys.argv[1])

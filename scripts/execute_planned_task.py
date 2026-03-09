#!/usr/bin/env python3
"""
Execute an approved agent task only after deterministic planning validation.
"""

import io
import json
import sys
from contextlib import redirect_stdout

from scripts.plan_agent_task import plan_agent_task
from scripts.run_agent_task import run_agent_task


def execute_planned_task(task_name):
    plan_buffer = io.StringIO()
    with redirect_stdout(plan_buffer):
        plan_agent_task(task_name)

    plan = json.loads(plan_buffer.getvalue())

    if not plan.get("valid", False):
        print(json.dumps({
            "task": task_name,
            "planned": False,
            "executed": False,
            "error": plan["error"],
        }, indent=2))
        return

    if not plan.get("deterministic", False):
        print(json.dumps({
            "task": task_name,
            "planned": True,
            "executed": False,
            "error": "task_not_deterministic",
        }, indent=2))
        return

    result_buffer = io.StringIO()
    with redirect_stdout(result_buffer):
        run_agent_task(task_name)

    result = json.loads(result_buffer.getvalue())

    print(json.dumps({
        "task": task_name,
        "planned": True,
        "executed": True,
        "execution_strategy": plan["execution_strategy"],
        "result": result,
    }, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python3 -m scripts.execute_planned_task <task_name>"
        )
    execute_planned_task(sys.argv[1])

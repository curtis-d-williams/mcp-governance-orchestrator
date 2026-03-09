#!/usr/bin/env python3
"""
Lifecycle orchestrator: plan, execute, and review a deterministic agent task.
"""

import json
import sys
from pathlib import Path
from scripts.plan_agent_task import plan_agent_task
from scripts.execute_planned_task import execute_planned_task
from scripts.review_task_execution import review_build_portfolio_dashboard

def run_lifecycle(task_name):
    lifecycle = {
        "task": task_name,
        "plan": {},
        "execute": {},
        "review": {},
        "lifecycle_ok": False
    }

    # --- Plan ---
    import io
    from contextlib import redirect_stdout
    plan_buf = io.StringIO()
    with redirect_stdout(plan_buf):
        plan_agent_task(task_name)
    plan_result = json.loads(plan_buf.getvalue())
    lifecycle["plan"] = plan_result

    if not plan_result.get("valid", False):
        print(json.dumps(lifecycle, indent=2))
        return

    # --- Execute ---
    exec_buf = io.StringIO()
    with redirect_stdout(exec_buf):
        execute_planned_task(task_name)
    exec_result = json.loads(exec_buf.getvalue())
    lifecycle["execute"] = exec_result

    if not exec_result.get("executed", False):
        print(json.dumps(lifecycle, indent=2))
        return

    # --- Review ---
    review_buf = io.StringIO()
    with redirect_stdout(review_buf):
        if task_name == "build_portfolio_dashboard":
            review_build_portfolio_dashboard()
        else:
            # Future: other tasks
            review_buf.write(json.dumps({"ok": False, "error": "no_reviewer"}))
    review_result = json.loads(review_buf.getvalue())
    lifecycle["review"] = review_result

    lifecycle["lifecycle_ok"] = plan_result.get("valid", False) \
                                 and exec_result.get("executed", False) \
                                 and review_result.get("ok", False)

    print(json.dumps(lifecycle, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python3 -m scripts.run_agent_lifecycle <task_name>"
        )
    run_lifecycle(sys.argv[1])

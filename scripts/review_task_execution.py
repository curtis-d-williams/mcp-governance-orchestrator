#!/usr/bin/env python3
"""
Reviewer for deterministic agent task execution.
Validates execution envelope and expected outputs.
"""

import json
import sys
from pathlib import Path

from scripts.execute_planned_task import execute_planned_task


def review_build_portfolio_dashboard():
    repo_root = Path(__file__).resolve().parent.parent
    # Execute the planned task
    result_buffer = execute_task_capture("build_portfolio_dashboard")
    payload = json.loads(result_buffer)
    task_result = payload.get("result", {})

    review = {
        "task": "build_portfolio_dashboard",
        "reviewed": True,
        "ok": True,
        "checks": {},
        "artifacts": [],
    }

    # Check envelope fields inside result
    required_fields = ["task_name", "csv_path", "html_path", "suggestion_ids"]
    for field in required_fields:
        if field not in task_result:
            review["ok"] = False
            review["checks"][field] = False
        else:
            review["checks"][field] = True

    # Check artifact existence
    csv_file = repo_root / task_result.get("csv_path", "")
    html_file = repo_root / task_result.get("html_path", "")
    artifacts_missing = []
    for f in [csv_file, html_file]:
        if f.exists():
            review["artifacts"].append(str(f))
        else:
            review["ok"] = False
            artifacts_missing.append(str(f))
    if artifacts_missing:
        review["error"] = "missing_expected_output"
        review["missing"] = artifacts_missing

    print(json.dumps(review, indent=2))


def execute_task_capture(task_name):
    import io
    from contextlib import redirect_stdout
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        execute_planned_task(task_name)
    return buffer.getvalue()


if __name__ == "__main__":
    review_build_portfolio_dashboard()

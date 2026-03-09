import json
import subprocess
import sys


def run_planner(task):
    result = subprocess.run(
        [sys.executable, "-m", "scripts.plan_agent_task", task],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_plan_valid_task():
    data = run_planner("build_portfolio_dashboard")

    assert data["task"] == "build_portfolio_dashboard"
    assert data["valid"] is True
    assert data["scope"] == "local_repo"
    assert data["deterministic"] is True
    assert data["portfolio_safe"] is True
    assert data["execution_strategy"] == "single_repo_runner"
    assert "tier3_portfolio_report.csv" in data["outputs"]


def test_plan_unknown_task():
    data = run_planner("unknown_task")

    assert data["task"] == "unknown_task"
    assert data["valid"] is False
    assert data["error"] == "task_not_registered"

import json
import subprocess
import sys


def run_execute(task):
    result = subprocess.run(
        [sys.executable, "-m", "scripts.execute_planned_task", task],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_execute_valid_planned_task():
    data = run_execute("build_portfolio_dashboard")

    assert data["task"] == "build_portfolio_dashboard"
    assert data["planned"] is True
    assert data["executed"] is True
    assert data["execution_strategy"] == "single_repo_runner"
    assert data["result"]["task_name"] == "build_portfolio_dashboard"
    assert data["result"]["csv_path"] == "tier3_portfolio_report.csv"
    assert data["result"]["html_path"] == "tier3_portfolio_dashboard_styled.html"


def test_execute_unknown_task_fails_closed():
    data = run_execute("unknown_task")

    assert data["task"] == "unknown_task"
    assert data["planned"] is False
    assert data["executed"] is False
    assert data["error"] == "task_not_registered"

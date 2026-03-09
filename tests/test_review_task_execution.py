import json
import subprocess
import sys
from pathlib import Path


def run_reviewer(task):
    result = subprocess.run(
        [sys.executable, "-m", "scripts.review_task_execution"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_review_build_portfolio_dashboard_passes():
    repo_root = Path(__file__).resolve().parent.parent
    # Ensure artifacts exist before review
    csv_file = repo_root / "tier3_portfolio_report.csv"
    html_file = repo_root / "tier3_portfolio_dashboard_styled.html"

    # Run planner + executor to produce artifacts
    subprocess.run(
        [sys.executable, "-m", "scripts.execute_planned_task", "build_portfolio_dashboard"],
        check=True,
        cwd=repo_root
    )

    review = run_reviewer("build_portfolio_dashboard")

    assert review["task"] == "build_portfolio_dashboard"
    assert review["reviewed"] is True
    assert review["ok"] is True
    assert all(review["checks"].values())
    assert csv_file.exists()
    assert html_file.exists()
    assert set(review["artifacts"]) == {str(csv_file), str(html_file)}

import json
import subprocess
import sys
from pathlib import Path


def run_lifecycle(task):
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "scripts.run_agent_lifecycle", task],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo_root
    )
    return json.loads(result.stdout)


def test_lifecycle_build_portfolio_dashboard():
    repo_root = Path(__file__).resolve().parent.parent

    # Ensure artifacts exist
    csv_file = repo_root / "tier3_portfolio_report.csv"
    html_file = repo_root / "tier3_portfolio_dashboard_styled.html"

    lifecycle = run_lifecycle("build_portfolio_dashboard")

    assert lifecycle["task"] == "build_portfolio_dashboard"
    assert lifecycle["plan"]["valid"] is True
    assert lifecycle["execute"]["executed"] is True
    assert lifecycle["review"]["ok"] is True
    assert lifecycle["lifecycle_ok"] is True

    # Validate artifact paths
    assert csv_file.exists()
    assert html_file.exists()
    assert set(lifecycle["review"]["artifacts"]) == {str(csv_file), str(html_file)}

import json
import subprocess
from pathlib import Path


def test_run_agent_task_build_portfolio_dashboard(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    csv_file = repo_root / "tier3_portfolio_report.csv"
    html_file = repo_root / "tier3_portfolio_dashboard_styled.html"

    if csv_file.exists():
        csv_file.unlink()
    if html_file.exists():
        html_file.unlink()

    result = subprocess.run(
        ["python3", "-m", "scripts.run_agent_task", "build_portfolio_dashboard"],
        check=True,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    payload = json.loads(result.stdout)

    assert payload["task_name"] == "build_portfolio_dashboard"
    assert payload["csv_path"] == "tier3_portfolio_report.csv"
    assert payload["html_path"] == "tier3_portfolio_dashboard_styled.html"
    assert payload["suggestion_ids"] == [
        "sample_template_example",
        "repo_insights_example",
        "intelligence_layer_example",
    ]

    assert csv_file.exists()
    assert html_file.exists()

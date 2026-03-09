import csv
import subprocess
from pathlib import Path


def test_tier3_workflow_outputs_contract(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    csv_file = repo_root / "tier3_portfolio_report.csv"
    html_file = repo_root / "tier3_portfolio_dashboard_styled.html"

    if csv_file.exists():
        csv_file.unlink()
    if html_file.exists():
        html_file.unlink()

    subprocess.run(
        ["python3", "-m", "scripts.tier3_agent_dashboard_workflow"],
        check=True,
        cwd=repo_root,
    )

    assert csv_file.exists()
    assert html_file.exists()

    with open(csv_file) as f:
        rows = list(csv.reader(f))

    assert rows[0] == [
        "Suggestion ID",
        "Description",
        "Example Metric",
        "Notes",
    ]

    suggestion_ids = [r[0] for r in rows[1:]]

    assert suggestion_ids == [
        "sample_template_example",
        "repo_insights_example",
        "intelligence_layer_example",
    ]

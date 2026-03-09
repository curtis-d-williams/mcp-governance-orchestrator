from pathlib import Path
import subprocess
import pandas as pd

PORTFOLIO_CSV = Path("tier3_portfolio_report.csv")
AGGREGATE_JSON = Path("tier3_multi_run_aggregate.json")
DASHBOARD_PNG = Path("tier3_portfolio_dashboard_summary.png")

EXPECTED_TASKS = [
    "build_portfolio_dashboard",
    "repo_insights_example",
    "intelligence_layer_example",
]

def test_visualize_portfolio_dashboard_generation():
    # Seed the expected portfolio-task CSV shape so this test is isolated
    subprocess.run(
        [
            "python3",
            "scripts/run_portfolio_task.py",
            "build_portfolio_dashboard",
            "repo_insights_example",
            "intelligence_layer_example",
            "portfolio_repos_example.json",
        ],
        check=True,
    )

    # Run the visualization script
    subprocess.run(
        ["python3", "scripts/visualize_portfolio_dashboard.py"],
        check=True,
    )

    # Validate dashboard PNG was created
    assert DASHBOARD_PNG.exists(), "Dashboard PNG was not generated"

    # Validate CSV and JSON exist
    assert PORTFOLIO_CSV.exists(), "Portfolio CSV missing"
    assert AGGREGATE_JSON.exists(), "Aggregate JSON missing"

    # Validate that all expected tasks appear in the CSV
    df = pd.read_csv(PORTFOLIO_CSV)
    for task in EXPECTED_TASKS:
        assert task in df["task"].values, f"Task {task} missing from portfolio CSV"

import json
import subprocess
from pathlib import Path


def test_list_agent_tasks_output():
    repo_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        ["python3", "-m", "scripts.list_agent_tasks"],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo_root,
    )

    payload = json.loads(result.stdout)

    assert payload == [
        {
            "task": "build_portfolio_dashboard",
            "description": "Generate Tier-3 portfolio dashboard artifacts",
            "scope": "local_repo",
            "outputs": [
                "tier3_portfolio_report.csv",
                "tier3_portfolio_dashboard_styled.html",
            ],
            "deterministic": True,
            "portfolio_safe": True,
        }
    ]

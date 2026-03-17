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
            "task": "artifact_audit_example",
            "description": "Audit artifact presence in the repo",
            "scope": "local_repo",
            "outputs": [],
            "deterministic": True,
            "portfolio_safe": True,
        },
        {
            "task": "build_mcp_server_example",
            "description": "Generate an MCP server via the canonical governed build path",
            "scope": "local_repo",
            "outputs": [],
            "deterministic": True,
            "portfolio_safe": True,
        },
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
        },
        {
            "task": "failure_recovery_example",
            "description": "Collect failure recovery indicators from the repo",
            "scope": "local_repo",
            "outputs": [],
            "deterministic": True,
            "portfolio_safe": True,
        },
        {
            "task": "health_probe_example",
            "description": "Emit known degraded health signals for example pipeline validation",
            "scope": "local_repo",
            "outputs": [],
            "deterministic": True,
            "portfolio_safe": True,
        },
        {
            "task": "planner_determinism_example",
            "description": "Verify planner determinism indicators in the repo",
            "scope": "local_repo",
            "outputs": [],
            "deterministic": True,
            "portfolio_safe": True,
        },
        {
            "task": "repo_insights_example",
            "description": "Collect basic repo file-count insights",
            "scope": "local_repo",
            "outputs": [],
            "deterministic": True,
            "portfolio_safe": True,
        },
    ]

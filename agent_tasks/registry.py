"""
Deterministic registry of approved agent task specifications.
"""

TASK_REGISTRY = {
    "build_portfolio_dashboard": {
        "module": "agent_tasks.build_portfolio_dashboard",
        "description": "Generate Tier-3 portfolio dashboard artifacts",
        "scope": "local_repo",
        "inputs": [],
        "outputs": [
            "tier3_portfolio_report.csv",
            "tier3_portfolio_dashboard_styled.html",
        ],
        "deterministic": True,
        "portfolio_safe": True,
    }
}

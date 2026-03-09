"""
Deterministic registry of approved agent task specifications.
"""

TASK_REGISTRY = {
    "artifact_audit_example": {
        "module": "agent_tasks.artifact_audit_example",
        "description": "Audit artifact presence in the repo",
        "scope": "local_repo",
        "inputs": [],
        "outputs": [],
        "deterministic": True,
        "portfolio_safe": True,
    },
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
    },
    "repo_insights_example": {
        "module": "agent_tasks.repo_insights_example",
        "description": "Collect basic repo file-count insights",
        "scope": "local_repo",
        "inputs": [],
        "outputs": [],
        "deterministic": True,
        "portfolio_safe": True,
    },
    "failure_recovery_example": {
        "module": "agent_tasks.failure_recovery_example",
        "description": "Collect failure recovery indicators from the repo",
        "scope": "local_repo",
        "inputs": [],
        "outputs": [],
        "deterministic": True,
        "portfolio_safe": True,
    },
    "planner_determinism_example": {
        "module": "agent_tasks.planner_determinism_example",
        "description": "Verify planner determinism indicators in the repo",
        "scope": "local_repo",
        "inputs": [],
        "outputs": [],
        "deterministic": True,
        "portfolio_safe": True,
    },
}

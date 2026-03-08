from agent_tasks.registry import TASK_REGISTRY


def test_task_registry_contains_build_portfolio_dashboard():
    assert TASK_REGISTRY == {
        "build_portfolio_dashboard": "agent_tasks.build_portfolio_dashboard",
    }

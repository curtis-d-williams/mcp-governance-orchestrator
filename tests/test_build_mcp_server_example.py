# SPDX-License-Identifier: MIT
"""Targeted regression tests for the build_mcp_server_example task seam."""

from collections import OrderedDict
from unittest.mock import patch

from agent_tasks.build_mcp_server_example import run, TASK_NAME, DEFAULT_CAPABILITY, DEFAULT_NAME
from agent_tasks.registry import TASK_REGISTRY
from scripts.claude_dynamic_planner_loop import ACTION_TO_TASK


_MOCK_BUILDER_RESULT = {
    "status": "ok",
    "generated_repo": "generated_mcp_server_github",
}


def test_run_calls_canonical_builder_with_expected_args():
    with patch("agent_tasks.build_mcp_server_example.build_mcp_server") as mock_builder:
        mock_builder.return_value = _MOCK_BUILDER_RESULT
        run()
    mock_builder.assert_called_once_with(
        name=DEFAULT_NAME,
        capability=DEFAULT_CAPABILITY,
    )


def test_run_returns_expected_shape():
    with patch("agent_tasks.build_mcp_server_example.build_mcp_server") as mock_builder:
        mock_builder.return_value = _MOCK_BUILDER_RESULT
        result = run()
    assert isinstance(result, OrderedDict)
    assert result["task_name"] == TASK_NAME
    assert result["capability"] == DEFAULT_CAPABILITY
    assert result["status"] == "ok"
    assert result["generated_repo"] == "generated_mcp_server_github"


def test_task_registry_entry_present():
    assert "build_mcp_server_example" in TASK_REGISTRY
    assert TASK_REGISTRY["build_mcp_server_example"]["module"] == "agent_tasks.build_mcp_server_example"
    assert TASK_REGISTRY["build_mcp_server_example"]["deterministic"] is True
    assert TASK_REGISTRY["build_mcp_server_example"]["portfolio_safe"] is True


def test_action_to_task_routes_build_mcp_server():
    assert ACTION_TO_TASK["build_mcp_server"] == "build_mcp_server_example"
